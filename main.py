import tcod
import tcod.event
from typing import Optional
from typing import Tuple, TypeVar
from typing import Set, Iterable, Any
from typing import List, Reversible, Union
from typing import Callable, Dict, Iterator
from tcod.context import Context
from tcod.console import Console
import numpy as np
import random
from tcod.map import compute_fov
import copy
from enum import auto, Enum
import textwrap
import traceback
import math
import lzma
import pickle
import os


def main():
    screen_width = 80
    screen_height = 50
    #tileset = tcod.tileset.load_tilesheet("./dejavu10x10_gs_tc.png", 32, 8, tcod.tileset.CHARMAP_TCOD)  tileset=tileset,
    player = copy.deepcopy(player_gen)

    handler = MainMenu()

    with tcod.context.new_terminal(screen_width, screen_height, title="Compiler Game", vsync=True,) as context:
        root_console = tcod.Console(screen_width, screen_height, order="F")
        try:
            while True:
                root_console.clear()
                handler.on_render(console=root_console)
                context.present(root_console)
                try:
                    for event in tcod.event.wait():
                        context.convert_event(event)
                        handler = handler.handle_events(event)
                except Exception:
                    traceback.print_exc()
                    if isinstance(handler, EventHandler):
                        handler.engine.message_log.add_message(traceback.format_exc(), error)
        except QuitWithoutSaving:
            raise
        except SystemExit:
            save_game(handler, "savegame.sav")
            raise
        except BaseException:
            save_game(handler, "savegame.sav")
            raise

def save_game(handler, filename):
    if isinstance(handler, EventHandler):
        handler.engine.save_as(filename)
        print("Game saved.")

def new_game():
    map_width = 80
    map_height = 43

    room_max_size = 10
    room_min_size = 6
    max_rooms = 30

    player = copy.deepcopy(player_gen)

    engine = Engine(player=player)
    engine.game_world = GameWorld(
        engine=engine,
        max_rooms=max_rooms,
        room_min_size=room_min_size,
        room_max_size=room_max_size,
        map_width=map_width,
        map_height=map_height,
    )
    engine.game_world.generate_floor()
    engine.update_fov()
    engine.message_log.add_message("Welcome to yet another dungeon.", welcome_text)
    dag = copy.deepcopy(dagger)
    l_armor = copy.deepcopy(leather_armor)

    dag.parent = player.inventory
    l_armor.parent = player.inventory

    player.inventory.items.append(dag)
    player.equipment.toggle_equip(dag, add_message=False)

    player.inventory.items.append(l_armor)
    player.equipment.toggle_equip(l_armor, add_message=False)
    return engine

def load_game(filename):
    with open(filename, "rb") as f:
        engine = pickle.loads(lzma.decompress(f.read()))
    assert isinstance(engine, Engine)
    return engine

class RenderOrder(Enum):
    CORPSE = auto()
    ITEM = auto()
    ACTOR = auto()

class Action:
    def __init__(self, entity):
        super().__init__()
        self.entity = entity

    @property
    def engine(self):
        return self.entity.gamemap.engine

    def perform(self):
        raise NotImplementedError()

class ItemAction(Action):
    def __init__(self, entity, item, target_xy=None):
        super().__init__(entity)
        self.item = item
        if not target_xy:
            target_xy = entity.x, entity.y
        self.target_xy = target_xy

    @property
    def target_actor(self):
        return self.engine.game_map.get_actor_at_location(*self.target_xy)
    
    def perform(self):
        if self.item.consumable:
            self.item.consumable.activate(self)
    
class DropItem(ItemAction):
    def perform(self):
        if self.entity.equipment.item_is_equipped(self.item):
            self.entity.equipment.toggle_equip(self.item)
        self.entity.inventory.drop(self.item)

class EquipAction(Action):
    def __init__(self, entity, item):
        super().__init__(entity)
        self.item = item
    
    def perform(self):
        self.entity.equipment.toggle_equip(self.item)
    
class ActionWithDirection(Action):
    def __init__(self, entity, dx: int, dy: int):
        super().__init__(entity)

        self.dx = dx
        self.dy = dy

    @property
    def dest_xy(self):
        return self.entity.x + self.dx, self.entity.y + self.dy

    @property
    def blocking_entity(self):
        return self.engine.game_map.get_blocking_entity_at_location(*self.dest_xy)

    @property
    def target_actor(self):
        return self.engine.game_map.get_actor_at_location(*self.dest_xy)
    
    def perform(self) -> None:
        raise NotImplementedError()
    
class MeleeAction(ActionWithDirection):
    def perform(self):
        target = self.target_actor
        if not target:
            raise Impossible("Nothing to attack.")
        damage = self.entity.fighter.power - target.fighter.defense
        attack_desc = f"{self.entity.name.capitalize()} attacks {target.name}"
        if self.entity is self.engine.player:
            attack_color = player_atk
        else:
            attack_color = enemy_atk
        if damage > 0:
            self.engine.message_log.add_message(f"{attack_desc} for {damage} hit points.", attack_color)
            target.fighter.hp -= damage
        else:
            self.engine.message_log.add_message(f"{attack_desc} but does no damage.", attack_color)

class BumpAction(ActionWithDirection):
    def perform(self):
        if self.target_actor:
            return MeleeAction(self.entity, self.dx, self.dy).perform()
        else:
            return MovementAction(self.entity, self.dx, self.dy).perform()

class MovementAction(ActionWithDirection):
    def perform(self):
        dest_x, dest_y = self.dest_xy
        if not self.engine.game_map.in_bounds(dest_x, dest_y):
            raise Impossible("That way is blocked.")
        if not self.engine.game_map.tiles["walkable"][dest_x, dest_y]:
            raise Impossible("That way is blocked.")
        if self.engine.game_map.get_blocking_entity_at_location(dest_x, dest_y):
            raise Impossible("That way is blocked.")
        self.entity.move(self.dx, self.dy)

class WaitAction(Action):
    def perform(self):
        pass

class PickupAction(Action):

    def __init__(self, entity):
        super().__init__(entity)

    def perform(self) -> None:
        actor_location_x = self.entity.x
        actor_location_y = self.entity.y
        inventory = self.entity.inventory

        for item in self.engine.game_map.items:
            if actor_location_x == item.x and actor_location_y == item.y:
                if len(inventory.items) >= inventory.capacity:
                    raise Impossible("Your inventory is full.")

                self.engine.game_map.entities.remove(item)
                item.parent = self.entity.inventory
                inventory.items.append(item)

                self.engine.message_log.add_message(f"You picked up the {item.name}!")
                return

        raise Impossible("There is nothing here to pick up.")
    
class TakeStairsAction(Action):
    def perform(self):
        if (self.entity.x, self.entity.y) == self.engine.game_map.downstairs_location:
            self.engine.game_world.generate_floor()
            self.engine.message_log.add_message("You descend the staircase.", descend)
        else:
            raise Impossible("There are no stairs here.")

MOVE_KEYS = {
    # Arrow keys.
    tcod.event.K_UP: (0, -1),
    tcod.event.K_DOWN: (0, 1),
    tcod.event.K_LEFT: (-1, 0),
    tcod.event.K_RIGHT: (1, 0),
    tcod.event.K_HOME: (-1, -1),
    tcod.event.K_END: (-1, 1),
    tcod.event.K_PAGEUP: (1, -1),
    tcod.event.K_PAGEDOWN: (1, 1),
    # Numpad keys.
    tcod.event.K_KP_1: (-1, 1),
    tcod.event.K_KP_2: (0, 1),
    tcod.event.K_KP_3: (1, 1),
    tcod.event.K_KP_4: (-1, 0),
    tcod.event.K_KP_6: (1, 0),
    tcod.event.K_KP_7: (-1, -1),
    tcod.event.K_KP_8: (0, -1),
    tcod.event.K_KP_9: (1, -1),
    # Vi keys.
    tcod.event.K_h: (-1, 0),
    tcod.event.K_j: (0, 1),
    tcod.event.K_k: (0, -1),
    tcod.event.K_l: (1, 0),
    tcod.event.K_y: (-1, -1),
    tcod.event.K_u: (1, -1),
    tcod.event.K_b: (-1, 1),
    tcod.event.K_n: (1, 1),
}

WAIT_KEYS = {
    tcod.event.K_PERIOD,
    tcod.event.K_KP_5,
    tcod.event.K_CLEAR,
}

CONFIRM_KEYS = {
    tcod.event.K_RETURN,
    tcod.event.K_KP_ENTER,
}

CURSOR_Y_KEYS = {
    tcod.event.K_UP: -1,
    tcod.event.K_DOWN: 1,
    tcod.event.K_PAGEUP: -10,
    tcod.event.K_PAGEDOWN: 10,
}

ActionOrHandler = Union[Action, "BaseEventHandler"]

class BaseEventHandler(tcod.event.EventDispatch[ActionOrHandler]):
    def handle_events(self, event):
        state = self.dispatch(event)
        if isinstance(state, BaseEventHandler):
            return state
        assert not isinstance(state, Action), f"{self!r} cannot handle actions."
        return self
    def on_render(self, console):
        raise NotImplementedError()
    def ev_quit(self, event):
        raise SystemExit()

class MainMenu(BaseEventHandler):
    def on_render(self, console):
        console.print(console.width // 2, console.height // 2 - 4, "DARK CRYPT", fg=menu_title, alignment=tcod.CENTER)
        console.print(console.width // 2, console.height // 2 - 2, "By Raymond Wu", fg=menu_title, alignment=tcod.CENTER)
        menu_width = 24
        for i, txt in enumerate(["[N] Start new game", "[C] Continue last game", "[Q] Quit"]):
            console.print(console.width // 2, console.height // 2 - 2 + i, txt.ljust(menu_width), fg=menu_text, bg=black, alignment=tcod.CENTER, bg_blend=tcod.BKGND_ALPHA(64))
    def ev_keydown(self, event):
        if event.sym in (tcod.event.K_q, tcod.event.K_ESCAPE):
            raise SystemExit()
        elif event.sym == tcod.event.K_c:
            try:
                return MainGameEventHandler(load_game("savegame.sav"))
            except FileNotFoundError:
                return PopupMessage(self, "No saved game to load.")
            except Exception as exc:
                traceback.print_exc()
                return PopupMessage(self, f"Failed to load save:\n{exc}")
        elif event.sym == tcod.event.K_n:
            return MainGameEventHandler(new_game())
        return None
    
class PopupMessage(BaseEventHandler):
    def __init__(self, parent_handler, text):
        self.parent = parent_handler
        self.text = text
    def on_render(self, console):
        self.parent.on_render(console)
        console.tiles_rgb["fg"] //= 8
        console.tiles_rgb["bg"] //= 8
        console.print(console.width // 2, console.height // 2, self.text, fg=white, bg=black, alignment=tcod.CENTER)
    def ev_keydown(self, event):
        return self.parent

class EventHandler(BaseEventHandler):
    def __init__(self, engine):
        self.engine = engine

    def handle_events(self, event):
        action_or_state = self.dispatch(event)
        if isinstance(action_or_state, BaseEventHandler):
            return action_or_state
        if self.handle_action(action_or_state):
            if not self.engine.player.isAlive:
                return GameOverEventHandler(self.engine)
            elif self.engine.player.level.requires_level_up:
                return LevelUpEventHandler(self.engine)
            return MainGameEventHandler(self.engine)
        return self

    def handle_action(self, action):
        if action is None:
            return False
        try:
            action.perform()
        except Impossible as exc:
            self.engine.message_log.add_message(exc.args[0], impossible)
            return False
        self.engine.handle_enemy_turns()
        self.engine.update_fov()
        return True

    def ev_mousemotion(self, event):
        if self.engine.game_map.in_bounds(event.tile.x, event.tile.y):
            self.engine.mouse_location = event.tile.x, event.tile.y
    
    def on_render(self, console):
        self.engine.render(console)

class AskUserEventHandler(EventHandler):

    def ev_keydown(self, event):
        if event.sym in { 
            tcod.event.K_LSHIFT,
            tcod.event.K_RSHIFT,
            tcod.event.K_LCTRL,
            tcod.event.K_RCTRL,
            tcod.event.K_LALT,
            tcod.event.K_RALT,
        }:
            return None
        return self.on_exit()

    def ev_mousebuttondown(self, event):
        return self.on_exit()

    def on_exit(self):
        return MainGameEventHandler(self.engine)
    
class CharacterScreenEventHandler(AskUserEventHandler):
    TITLE = "Character Information"
    def on_render(self, console):
        super().on_render(console)
        if self.engine.player.x <= 30:
            x = 40
        else:
            x = 0
        y = 0
        width = len(self.TITLE) + 4
        console.draw_frame(x=x, y=y, width=width, height=7, title=self.TITLE, clear=True, fg=(255, 255, 255), bg=(0, 0, 0))
        console.print(
            x=x + 1, y=y + 1, string=f"Level: {self.engine.player.level.current_level}"
        )
        console.print(
            x=x + 1, y=y + 2, string=f"XP: {self.engine.player.level.current_xp}"
        )
        console.print(
            x=x + 1,
            y=y + 3,
            string=f"XP for next Level: {self.engine.player.level.experience_to_next_level}",
        )

        console.print(
            x=x + 1, y=y + 4, string=f"Attack: {self.engine.player.fighter.power}"
        )
        console.print(
            x=x + 1, y=y + 5, string=f"Defense: {self.engine.player.fighter.defense}"
        )

class HistoryViewer(EventHandler):
    def __init__(self, engine):
        super().__init__(engine)
        self.log_length = len(engine.message_log.messages)
        self.cursor = self.log_length - 1

    def on_render(self, console):
        super().on_render(console)
        log_console = tcod.Console(console.width - 6, console.height - 6)
        log_console.draw_frame(0, 0, log_console.width, log_console.height)
        log_console.print_box(0, 0, log_console.width, 1, "┤Message history├", alignment=tcod.CENTER)

        self.engine.message_log.render_messages(log_console, 1, 1, log_console.width - 2, log_console.height - 2, self.engine.message_log.messages[:self.cursor + 1])
        log_console.blit(console, 3, 3)

    def ev_keydown(self, event):
        if event.sym in CURSOR_Y_KEYS:
            adjust = CURSOR_Y_KEYS[event.sym]
            if adjust < 0 and self.cursor == 0:
                self.cursor = self.log_length - 1
            elif adjust > 0 and self.cursor == self.log_length - 1:
                self.cursor = 0
            else:
                self.cursor = max(0, min(self.cursor + adjust, self.log_length - 1))
        else:
            return MainGameEventHandler(self.engine)
        return None

class MainGameEventHandler(EventHandler):

    def ev_keydown(self, event):
        action: Optional[Action] = None

        key = event.sym
        modifier = event.mod
        player = self.engine.player

        if key == tcod.event.K_PERIOD and modifier & (tcod.event.KMOD_LSHIFT | tcod.event.KMOD_RSHIFT):
            return TakeStairsAction(player)

        if key in MOVE_KEYS:
            dx, dy = MOVE_KEYS[key]
            action = BumpAction(player, dx, dy)
        elif key in WAIT_KEYS:
            action = WaitAction(player)
        elif key == tcod.event.K_ESCAPE:
            raise SystemExit()
        elif key == tcod.event.K_v:
            return HistoryViewer(self.engine)
        elif key == tcod.event.K_g:
            action = PickupAction(player)
        elif key == tcod.event.K_i:
            return InventoryActivateHandler(self.engine)
        elif key == tcod.event.K_d:
            return InventoryDropHandler(self.engine)
        elif key == tcod.event.K_SLASH:
            return LookHandler(self.engine)
        elif key == tcod.event.K_c:
            return CharacterScreenEventHandler(self.engine)
        return action

class GameOverEventHandler(EventHandler):
    def on_quit(self):
        if os.path.exists("savegame.sav"):
            os.remove("savegame.sav")
        raise QuitWithoutSaving()
    
    def ev_quit(self, event):
        self.on_quit()

    def ev_keydown(self, event):
        if event.sym == tcod.event.K_ESCAPE:
            self.on_quit()
        
class InventoryEventHandler(AskUserEventHandler):
    TITLE = "<missing title>"
    def on_render(self, console: tcod.Console) -> None:
        super().on_render(console)
        number_of_items_in_inventory = len(self.engine.player.inventory.items)
        height = number_of_items_in_inventory + 2
        if height <= 3:
            height = 3
        if self.engine.player.x <= 30:
            x = 40
        else:
            x = 0
        y = 0
        width = len(self.TITLE) + 4
        console.draw_frame(
            x=x,
            y=y,
            width=width,
            height=height,
            title=self.TITLE,
            clear=True,
            fg=(255, 255, 255),
            bg=(0, 0, 0),
        )
        if number_of_items_in_inventory > 0:
            for i, item in enumerate(self.engine.player.inventory.items):
                item_key = chr(ord("a") + i)
                is_equipped = self.engine.player.equipment.item_is_equipped(item)
                item_string = f"({item_key}) {item.name}"
                if is_equipped:
                    item_string = f"{item_string} (E)"
                console.print(x + 1, y + i + 1, item_string)
        else:
            console.print(x + 1, y + 1, "(Empty)")

    def ev_keydown(self, event):
        player = self.engine.player
        key = event.sym
        index = key - tcod.event.K_a
        if 0 <= index <= 26:
            try:
                selected_item = player.inventory.items[index]
            except IndexError:
                self.engine.message_log.add_message("Invalid entry.", invalid)
                return None
            return self.on_item_selected(selected_item)
        return super().ev_keydown(event)

    def on_item_selected(self, item) -> Optional[Action]:
        raise NotImplementedError()
    
class InventoryActivateHandler(InventoryEventHandler):
    TITLE = "Select an item to use"
    def on_item_selected(self, item):
        if item.consumable:
            return item.consumable.get_action(self.engine.player)
        elif item.equippable:
            return EquipAction(self.engine.player, item)
        else:
            return None


class InventoryDropHandler(InventoryEventHandler):
    TITLE = "Select an item to drop"
    def on_item_selected(self, item):
        return DropItem(self.engine.player, item)

class SelectIndexHandler(AskUserEventHandler):
    def __init__(self, engine):
        super().__init__(engine)
        player = self.engine.player
        engine.mouse_location = player.x, player.y

    def on_render(self, console):
        super().on_render(console)
        x, y = self.engine.mouse_location
        console.tiles_rgb["bg"][x, y] = white
        console.tiles_rgb["fg"][x, y] = black

    def ev_keydown(self, event):
        key = event.sym
        if key in MOVE_KEYS:
            modifier = 1
            if event.mod & (tcod.event.KMOD_LSHIFT | tcod.event.KMOD_RSHIFT):
                modifier *= 5
            if event.mod & (tcod.event.KMOD_LCTRL | tcod.event.KMOD_RCTRL):
                modifier *= 10
            if event.mod & (tcod.event.KMOD_LALT | tcod.event.KMOD_RALT):
                modifier *= 20
            
            x, y = self.engine.mouse_location
            dx, dy = MOVE_KEYS[key]
            x += dx * modifier
            y += dy * modifier
            x = max(0, min(x, self.engine.game_map.width - 1))
            y = max(0, min(y, self.engine.game_map.height - 1))
            self.engine.mouse_location = x, y
            return None
        elif key in CONFIRM_KEYS:
            return self.on_index_selected(*self.engine.mouse_location)
        return super().ev_keydown(event)
    
    def ev_mousebuttondown(self, event):
        if self.engine.game_map.in_bounds(*event.tile):
            if event.button == 1:
                return self.on_index_selected(*event.tile)
        return super().ev_mousebuttondown(event)
    
    def on_index_selected(self, x, y):
        raise NotImplementedError()
    
class LookHandler(SelectIndexHandler):
    def on_index_selected(self, x, y):
        return MainGameEventHandler(self.engine)

class SingleRangedAttackHandler(SelectIndexHandler):
    def __init__(self, engine, callback):
        super().__init__(engine)
        self.callback = callback

    def on_index_selected(self, x, y):
        return self.callback((x, y))
    
class AreaRangedAttackHandler(SelectIndexHandler):
    def __init__(self, engine, radius, callback):
        super().__init__(engine)
        self.radius = radius
        self.callback = callback

    def on_render(self, console):
        super().on_render(console)
        x, y = self.engine.mouse_location
        console.draw_frame(
            x=x - self.radius - 1,
            y=y - self.radius - 1,
            width=self.radius**2,
            height=self.radius**2,
            fg=red, clear=False
        )
    
    def on_index_selected(self, x, y):
        return self.callback((x, y))

class LevelUpEventHandler(AskUserEventHandler):
    TITLE = "Level Up"
    def on_render(self, console):
        super().on_render(console)
        if self.engine.player.x <= 30:
            x = 40
        else:
            x = 0
        console.draw_frame(x=x, y=0, width=35, height=8, title=self.TITLE, clear=True, fg=(255, 255, 255), bg=(0, 0, 0))
        console.print(x=x + 1, y=1, string="Congratulations! You leveled up!")
        console.print(x=x + 1, y=2, string="Select an attribute to increase.")
        console.print(
            x=x + 1,
            y=4,
            string=f"a) Constitution (+20 HP, from {self.engine.player.fighter.max_hp})",
        )
        console.print(
            x=x + 1,
            y=5,
            string=f"b) Strength (+1 attack, from {self.engine.player.fighter.power})",
        )
        console.print(
            x=x + 1,
            y=6,
            string=f"c) Defense (+1 defense, from {self.engine.player.fighter.defense})",
        )

    def ev_keydown(self, event):
        player = self.engine.player
        key = event.sym
        index = key - tcod.event.K_a
        if 0 <= index <= 2:
            if index == 0:
                player.level.increase_max_hp()
            elif index == 1:
                player.level.increase_power()
            else:
                player.level.increase_defense()
        else:
            self.engine.message_log.add_message("Invalid entry", invalid)
            return None
        return super().ev_keydown(event)
    def ev_mousebuttondown(self, event):
        return None

T = TypeVar("T", bound="Entity")

class Entity:
    def __init__(self, parent = None, x = 0, y = 0, char = "?", color = (255, 255, 255), name = "<Unnamed>", blocks_movement = False, render_order = RenderOrder.CORPSE):
        self.x = x
        self.y = y
        self.char = char
        self.color = color
        self.name = name
        self.blocks_movement = blocks_movement
        self.render_order = render_order
        if parent:
            self.parent = parent
            parent.entities.add(self)

    @property
    def gamemap(self):
        return self.parent.gamemap

    def spawn(self, gamemap, x, y):
        clone = copy.deepcopy(self)
        clone.x, clone.y = x, y
        clone.parent = gamemap
        gamemap.entities.add(clone)
        return clone

    def move(self, dx, dy):
        self.x += dx
        self.y += dy

    def place(self, x, y, gamemap):
        self.x = x
        self.y = y
        if gamemap:
            if hasattr(self, "parent"):
                if self.parent is self.gamemap:
                    self.gamemap.entities.remove(self)
            self.parent = gamemap
            gamemap.entities.add(self)
    
    def distance(self, x, y):
        return math.sqrt((x - self.x) ** 2 + (y - self.y) ** 2)

class Actor(Entity):
    def __init__(self, *, x=0, y=0, char="?", color=(255, 255, 255), name="<Unnamed>", ai_cls, equipment, fighter, inventory, level):
        super().__init__(x=x, y=y, char=char, color=color, name=name, blocks_movement=True, render_order=RenderOrder.ACTOR)
        self.ai = ai_cls(self)
        self.equipment = equipment
        self.equipment.parent = self
        self.fighter = fighter
        self.fighter.parent = self
        self.inventory = inventory
        self.inventory.parent = self
        self.level = level
        self.level.parent = self

    @property
    def isAlive(self):
        return bool(self.ai)

class Item(Entity):
    def __init__(self, *, x=0, y=0, char="?", color=(255, 255, 255), name="<Unnamed>", consumable=None, equippable=None):
        super().__init__(x=x, y=y, char=char, color=color, name=name, blocks_movement=False, render_order=RenderOrder.ITEM)
        self.consumable = consumable
        if self.consumable:
            self.consumable.parent = self
        self.equippable = equippable
        if self.equippable:
            self.equippable.parent = self

class Engine:
    def __init__(self, player):
        self.message_log = MessageLog()
        self.mouse_loc = (0, 0)
        self.player = player

    def handle_enemy_turns(self):
        for entity in set(self.game_map.actors) - {self.player}:
            if entity.ai:
                try:
                    entity.ai.perform()
                except Impossible:
                    pass
    
    def update_fov(self):
        self.game_map.visible[:] = compute_fov(self.game_map.tiles["transparent"], (self.player.x, self.player.y), radius=8)
        self.game_map.explored |= self.game_map.visible
    
    def render(self, console):
        self.game_map.render(console)
        self.message_log.render(console=console, x=21, y=45, width=40, height=5)
        render_bar(console=console, curr_value=self.player.fighter.hp, max_value=self.player.fighter.max_hp, total_width=20)
        render_dungeon_level(console=console, dungeon_level=self.game_world.current_floor, location=(0, 47))
        render_names_at_mouse_loc(console=console, x=21, y=44, engine=self)

    def save_as(self, filename):
        save_data = lzma.compress(pickle.dumps(self))
        with open(filename, "wb") as f:
            f.write(save_data)
    
graphic_dt = np.dtype([("ch", np.int32), ("fg", "3B"), ("bg", "3B")])
tile_dt = np.dtype([("walkable", bool), ("transparent", bool), ("dark", graphic_dt), ("light", graphic_dt)])
def new_tile(*, walkable, transparent, dark, light):
    return np.array((walkable, transparent, dark, light), dtype=tile_dt)
SHROUD = np.array((ord(" "), (255, 255, 255), (0, 0, 0)), dtype=graphic_dt)
floor = new_tile(walkable=True, transparent=True, dark=(ord("."), (100, 100, 100), (0, 0, 0)), light=(ord("."), (200, 200, 200), (0, 0, 0)))
wall = new_tile(walkable=False, transparent=False, dark=(ord("#"), (100, 100, 100), (0, 0, 0)), light=(ord("#"), (200, 200, 200), (0, 0, 0)))
down_stairs = new_tile(walkable=True, transparent=True, dark=(ord(">"), (100, 100, 100), (0, 0, 0)), light=(ord(">"), (200, 200, 200), (0, 0, 0)))

class GameMap:
    def __init__(self, engine, width, height, entities):
        self.width = width
        self.height = height
        self.engine = engine
        self.entities = set(entities)
        self.tiles = np.full((width, height), fill_value=wall, order="F")
        self.visible = np.full((width, height), fill_value=False, order="F")
        self.explored = np.full((width, height), fill_value=False, order="F")
        self.downstairs_location = (0, 0)

    def in_bounds(self, x, y):
        return 0 <= x < self.width and 0 <= y < self.height
    
    def render(self, console):
        console.tiles_rgb[0:self.width, 0:self.height] = np.select(
            condlist=[self.visible, self.explored], 
            choicelist=[self.tiles["light"], self.tiles["dark"]], 
            default=SHROUD
        )
        entites_sorted_for_rendering = sorted(self.entities, key=lambda x: x.render_order.value)
        for entity in entites_sorted_for_rendering:
            if self.visible[entity.x, entity.y]:
                console.print(x=entity.x, y=entity.y, string=entity.char, fg=entity.color)

    def get_blocking_entity_at_location(self, loc_x, loc_y):
        for entity in self.entities:
            if entity.blocks_movement and entity.x == loc_x and entity.y == loc_y:
                return entity
        return None
    
    @property
    def gamemap(self):
        return self

    @property
    def actors(self):
        yield from (entity for entity in self.entities if isinstance(entity, Actor) and entity.isAlive)

    @property
    def items(self):
        yield from (entity for entity in self.entities if isinstance(entity, Item))

    def get_actor_at_location(self, x, y):
        for actor in self.actors:
            if actor.x == x and actor.y == y:
                return actor
        return None
    
class GameWorld:
    def __init__(self, *, engine, map_width, map_height, max_rooms, room_min_size, room_max_size, current_floor=0):
        self.engine = engine
        self.map_width = map_width
        self.map_height = map_height
        self.max_rooms = max_rooms
        self.room_min_size = room_min_size
        self.room_max_size = room_max_size
        self.current_floor = current_floor

    def generate_floor(self):
        self.current_floor += 1
        self.engine.game_map = generate_dungeon(
            max_rooms=self.max_rooms,
            room_min_size=self.room_min_size,
            room_max_size=self.room_max_size,
            map_width=self.map_width,
            map_height=self.map_height,
            engine=self.engine,
            )

class RectangularRoom:
    def __init__(self, x, y, width, height):
        self.x1 = x
        self.y1 = y
        self.x2 = x + width
        self.y2 = y + height
    @property
    def center(self):
        center_x = int((self.x1 + self.x2) / 2)
        center_y = int((self.y1 + self.y2) / 2)
        return center_x, center_y
    @property
    def inner(self):
        return slice(self.x1 + 1, self.x2), slice(self.y1 + 1, self.y2)
    
    def intersects(self, other):
        return (self.x1 <= other.x2 and self.x2 >= other.x1 and self.y1 <= other.y2 and self.y2 >= other.y1)
    
max_items_by_floor = [
    (1, 1),
    (4, 2),
]

max_monsters_by_floor = [
    (1, 2),
    (4, 3),
    (6, 5),
]

def get_max_value_for_floor(max_value_by_floor, floor):
    current_value = 0
    for floor_minimum, value in max_value_by_floor:
        if floor_minimum > floor:
            break
        else:
            current_value = value
    return current_value

def get_entities_at_random(weighted_chances_by_floor, number_of_entities, floor):
    entity_weighted_chances = {}
    for key, values in weighted_chances_by_floor.items():
        if key > floor:
            break
        else:
            for value in values:
                entity = value[0]
                weighted_chance = value[1]
                entity_weighted_chances[entity] = weighted_chance
    entities = list(entity_weighted_chances.keys())
    entity_weighted_chance_values = list(entity_weighted_chances.values())
    chosen_entities = random.choices(entities, weights=entity_weighted_chance_values, k=number_of_entities)
    return chosen_entities

def tunnel_between(start, end):
    x1, y1 = start
    x2, y2 = end
    if random.random() < 0.5:
        corner_x, corner_y = x2, y1
    else:
        corner_x, corner_y = x1, y2
    for x, y in tcod.los.bresenham((x1, y1), (corner_x, corner_y)).tolist():
        yield x, y
    for x, y in tcod.los.bresenham((corner_x, corner_y), (x2, y2)).tolist():
        yield x, y

def place_entities(room, dungeon, floor_number):
    num_monsters = random.randint(0, get_max_value_for_floor(max_monsters_by_floor, floor_number))
    num_items = random.randint(0, get_max_value_for_floor(max_items_by_floor, floor_number))
    monsters = get_entities_at_random(enemy_chances, num_monsters, floor_number)
    items = get_entities_at_random(item_chances, num_items, floor_number)

    for entity in monsters + items:
        x = random.randint(room.x1 + 1, room.x2 - 1)
        y = random.randint(room.y1 + 1, room.y2 - 1)

        if not any(entity.x == x and entity.y == y for entity in dungeon.entities):
            entity.spawn(dungeon, x, y)

def generate_dungeon(max_rooms, room_min_size, room_max_size, map_width, map_height, engine):
    player = engine.player
    dungeon = GameMap(engine, map_width, map_height, entities=[player])
    rooms = []
    center_of_last_room = (0, 0)
    for r in range(max_rooms):
        room_width = random.randint(room_min_size, room_max_size)
        room_height = random.randint(room_min_size, room_max_size)
        x = random.randint(0, dungeon.width - room_width - 1)
        y = random.randint(0, dungeon.height - room_height - 1)
        new_room = RectangularRoom(x, y, room_width, room_height)
        if any(new_room.intersects(other_room) for other_room in rooms):
            continue
        dungeon.tiles[new_room.inner] = floor
        if not rooms:
            player.place(*new_room.center, dungeon)
        else:
            for x, y in tunnel_between(rooms[-1].center, new_room.center):
                dungeon.tiles[x, y] = floor
            center_of_last_room = new_room.center
        place_entities(new_room, dungeon, engine.game_world.current_floor)
        dungeon.tiles[center_of_last_room] = down_stairs
        dungeon.downstairs_location = center_of_last_room
        rooms.append(new_room)
    return dungeon

class BaseComponent:
    @property
    def gamemap(self):
        return self.parent.gamemap

    @property
    def engine(self):
        return self.gamemap.engine

class Fighter(BaseComponent):
    def __init__(self, hp, base_defense, base_power):
        self.max_hp = hp
        self._hp = hp
        self.base_defense = base_defense
        self.base_power = base_power
    
    @property
    def hp(self):
        return self._hp
    
    @hp.setter
    def hp(self, val):
        self._hp = max(0, min(val, self.max_hp))
        if self._hp == 0 and self.parent.ai:
            self.die()

    @property
    def defense(self):
        return self.base_defense + self.defense_bonus
    
    @property
    def power(self):
        return self.base_power + self.power_bonus

    @property
    def defense_bonus(self):
        if self.parent.equipment:
            return self.parent.equipment.defense_bonus
        else:
            return 0

    @property
    def power_bonus(self):
        if self.parent.equipment:
            return self.parent.equipment.power_bonus
        else:
            return 0

    def die(self):
        if self.engine.player is self.parent:
            death_message = "You died!"
            death_message_color = player_die
        else:
            death_message = f"{self.parent.name} is dead!"
            death_message_color = enemy_die
        
        self.parent.char = "%"
        self.parent.color = (190, 0, 0)
        self.parent.blocks_movement = False
        self.parent.ai = None
        self.parent.name = f"remains of {self.parent.name}"
        self.parent.render_order = RenderOrder.CORPSE

        self.engine.message_log.add_message(death_message, death_message_color)

        self.engine.player.level.add_xp(self.parent.level.xp_given)

    def heal(self, amount):
        if self.hp == self.max_hp:
            return 0
        new_hp_value = self.hp + amount
        if new_hp_value > self.max_hp:
            new_hp_value = self.max_hp
        amount_recovered = new_hp_value - self.hp
        self.hp = new_hp_value
        return amount_recovered
    
    def take_damage(self, amount):
        self.hp -= amount

class Inventory(BaseComponent):
    def __init__(self, capacity):
        self.capacity = capacity
        self.items = []
    
    def drop(self, item):
        self.items.remove(item)
        item.place(self.parent.x, self.parent.y, self.gamemap)
        self.engine.message_log.add_message(f"You dropped [{item.name}]")

class Consumable(BaseComponent):
    def get_action(self, consumer):
        return ItemAction(consumer, self.parent)
    def activate(self, action):
        raise NotImplementedError()
    def consume(self) -> None:
        entity = self.parent
        inventory = entity.parent
        if isinstance(inventory, Inventory):
            inventory.items.remove(entity)

    
class HealingConsumable(Consumable):
    def __init__(self, amount):
        self.amount = amount
    def activate(self, action):
        consumer = action.entity
        amount_recovered = consumer.fighter.heal(self.amount)
        if amount_recovered > 0:
            self.engine.message_log.add_message(f"You consume the {self.parent.name}, and recover {amount_recovered} HP.", health_recovered)
            self.consume()
        else:
            raise Impossible(f"Your health is already full.")

class ArcaneDamageConsumable(Consumable):
    def __init__(self, damage, maximum_range):
        self.damage = damage
        self.maximum_range = maximum_range

    def activate(self, action):
        consumer = action.entity
        target = None
        closest_distance = self.maximum_range + 1.0
        for actor in self.engine.game_map.actors:
            if actor is not consumer and self.parent.gamemap.visible[actor.x, actor.y]:
                distance = consumer.distance(actor.x, actor.y)
                if distance < closest_distance:
                    target, closest_distance = actor, distance
        if target:
            self.engine.message_log.add_message(f"A blast of concentrated energy strikes [{target.name}], dealing {self.damage} damage!")
            target.fighter.take_damage(self.damage)
            self.consume()
        else:
            raise Impossible("No enemy is close enough to strike.")
        
class ConfusionConsumable(Consumable):
    def __init__(self, number_of_turns):
        self.number_of_turns = number_of_turns

    def get_action(self, consumer):
        self.engine.message_log.add_message(f"Select a target location.", needs_target)
        return SingleRangedAttackHandler(self.engine, callback=lambda xy: ItemAction(consumer, self.parent, xy))
    
    def activate(self, action):
        consumer = action.entity
        target = action.target_actor
        if not self.engine.game_map.visible[action.target_xy]:
            raise Impossible("You cannot target an area you cannot see.")
        if not target:
            raise Impossible("You must select an enemy to target.")
        if target is consumer:
            raise Impossible("You cannot confuse yourself.")
        self.engine.message_log.add_message(f"The eyes of [{target.name}] grow vacant, and it starts to stumble around.", status_effect_applied)
        target.ai = ConfusedEnemy(entity=target, previous_ai=target.ai, turns_remaining=self.number_of_turns)
        self.consume()
        
class FireballConsumable(Consumable):
    def __init__(self, damage, radius):
        self.damage = damage
        self.radius = radius

    def get_action(self, consumer):
        self.engine.message_log.add_message(f"Select a target location.", needs_target)
        return AreaRangedAttackHandler(self.engine, radius=self.radius, callback=lambda xy: ItemAction(consumer, self.parent, xy))
    
    def activate(self, action):
        target_xy = action.target_xy
        if not self.engine.game_map.visible[target_xy]:
            raise Impossible("You cannot target an area you cannot see.")
        targets_hit = False
        for actor in self.engine.game_map.actors:
            if actor.distance(*target_xy) <= self.radius:
                self.engine.message_log.add_message(f"[{actor.name}] is enveloped in a fiery blaze, taking {self.damage} damage.")
                actor.fighter.take_damage(self.damage)
                targets_hit = True
        if not targets_hit:
            raise Impossible("There are no targets in the radius.")
        self.consume()

class Level(BaseComponent):
    def __init__(self, current_level=1, current_xp=0, level_up_base=0, level_up_factor=150, xp_given=0):
        self.current_level = current_level
        self.current_xp = current_xp
        self.level_up_base = level_up_base
        self.level_up_factor = level_up_factor
        self.xp_given = xp_given

    @property
    def experience_to_next_level(self):
        return self.level_up_base + self.current_level * self.level_up_factor
    
    @property
    def requires_level_up(self):
        return self.current_xp > self.experience_to_next_level
    
    def add_xp(self, xp):
        if xp == 0 or self.level_up_base == 0:
            return
        self.current_xp += xp
        self.engine.message_log.add_message(f"You gained {xp} experience points.")
        if self.requires_level_up:
            self.engine.message_log.add_message(f"You are now level {self.current_level + 1}!")

    def increase_level(self):
        self.current_xp -= self.experience_to_next_level
        self.current_level += 1

    def increase_max_hp(self, amount=20):
        self.parent.fighter.max_hp += amount
        self.parent.fighter.hp += amount
        self.engine.message_log.add_message("Your health improves.")
        self.increase_level()

    def increase_power(self, amount=1):
        self.parent.fighter.base_power += amount
        self.engine.message_log.add_message("Your body feels stronger.")
        self.increase_level()
    
    def increase_defense(self, amount=1):
        self.parent.fighter.base_defense += amount
        self.engine.message_log.add_message("You feel less vulnerable.")
        self.increase_level()

class EquipmentType(Enum):
    WEAPON = auto()
    ARMOR = auto()

class Equippable(BaseComponent):
    def __init__(self, equipment_type, power_bonus=0, defense_bonus=0):
        self.equipment_type = equipment_type
        self.power_bonus = power_bonus
        self.defense_bonus = defense_bonus

class Dagger(Equippable):
    def __init__(self):
        super().__init__(equipment_type=EquipmentType.WEAPON, power_bonus=2)

class Sword(Equippable):
    def __init__(self):
        super().__init__(equipment_type=EquipmentType.WEAPON, power_bonus=4)

class LeatherArmor(Equippable):
    def __init__(self):
        super().__init__(equipment_type=EquipmentType.ARMOR, defense_bonus=0)

class Chainmail(Equippable):
    def __init__(self):
        super().__init__(equipment_type=EquipmentType.ARMOR, defense_bonus=2)

class Equipment(BaseComponent):
    def __init__(self, weapon=None, armor=None):
        self.weapon = weapon
        self.armor = armor

    @property
    def defense_bonus(self):
        bonus = 0
        if self.weapon is not None and self.weapon.equippable is not None:
            bonus += self.weapon.equippable.defense_bonus
        if self.armor is not None and self.armor.equippable is not None:
            bonus += self.armor.equippable.defense_bonus
        return bonus
    
    @property
    def power_bonus(self):
        bonus = 0
        if self.weapon is not None and self.weapon.equippable is not None:
            bonus += self.weapon.equippable.power_bonus
        if self.armor is not None and self.armor.equippable is not None:
            bonus += self.armor.equippable.power_bonus
        return bonus
    
    def item_is_equipped(self, item):
        return self.weapon == item or self.armor == item
    
    def unequip_message(self, item_name):
        self.parent.gamemap.engine.message_log.add_message(f"You remove the {item_name}.")

    def equip_message(self, item_name):
        self.parent.gamemap.engine.message_log.add_message(f"You equip the {item_name}.")

    def equip_to_slot(self, slot, item, add_message):
        current_item = getattr(self, slot)
        if current_item is not None:
            self.unequip_from_slot(slot, add_message)
        setattr(self, slot, item)
        if add_message:
            self.equip_message(item.name)
    
    def unequip_from_slot(self, slot, add_message):
        current_item = getattr(self, slot)
        if add_message:
            self.unequip_message(current_item.name)
        setattr(self, slot, None)

    def toggle_equip(self, equippable_item, add_message=True):
        if (equippable_item.equippable and equippable_item.equippable.equipment_type == EquipmentType.WEAPON):
            slot = "weapon"
        else:
            slot = "armor"
        if getattr(self, slot) == equippable_item:
            self.unequip_from_slot(slot, add_message)
        else:
            self.equip_to_slot(slot, equippable_item, add_message)

class BaseAI(Action):
    def perform(self):
        raise NotImplementedError()
    def get_path_to(self, dest_x, dest_y):
        cost = np.array(self.entity.gamemap.tiles["walkable"], dtype = np.int8)
        for entity in self.entity.gamemap.entities:
            if entity.blocks_movement and cost[entity.x, entity.y]:
                cost[entity.x, entity.y] += 10
        graph = tcod.path.SimpleGraph(cost=cost, cardinal=2, diagonal=3)
        pathfinder = tcod.path.Pathfinder(graph)
        pathfinder.add_root((self.entity.x, self.entity.y))
        path = pathfinder.path_to((dest_x, dest_y))[1:].tolist()

        return [(i[0], i[1]) for i in path]

class HostileEnemy(BaseAI):
    def __init__(self, entity):
        super().__init__(entity)
        self.path = []
    
    def perform(self):
        target = self.engine.player
        dx = target.x - self.entity.x
        dy = target.y - self.entity.y
        dist = max(abs(dx), abs(dy))
        if self.engine.game_map.visible[self.entity.x, self.entity.y]:
            if dist <= 1:
                return MeleeAction(self.entity, dx, dy).perform()
            self.path = self.get_path_to(target.x, target.y)
        if self.path:
            dest_x, dest_y = self.path.pop(0)
            return MovementAction(self.entity, dest_x - self.entity.x, dest_y - self.entity.y).perform()
        return WaitAction(self.entity).perform()
    
class ConfusedEnemy(BaseAI):
    def __init__(self, entity, previous_ai, turns_remaining):
        super().__init__(entity)
        self.previous_ai = previous_ai
        self.turns_remaining = turns_remaining

    def perform(self):
        if self.turns_remaining <= 0:
            self.engine.message_log.add_message(f"[{self.entity.name}] is no longer confused.")
            self.entity.ai = self.previous_ai
        else:
            direction_x, direction_y = random.choice([
                (-1, -1), (0, -1), (1, -1), (-1, 0), (1, 0), (-1, 1), (0, 1), (1, 1)
            ])
            self.turns_remaining -= 1
            return BumpAction(self.entity, direction_x, direction_y).perform()
    
white = (0xFF, 0xFF, 0xFF)
black = (0x0, 0x0, 0x0)
red = (0xFF, 0x0, 0x0)

player_atk = (0xE0, 0xE0, 0xE0)
enemy_atk = (0xFF, 0xC0, 0xC0)
needs_target = (0x3F, 0xFF, 0xFF)
status_effect_applied = (0x3F, 0xFF, 0x3F)
descend = (0x9F, 0x3F, 0xFF)

player_die = (0xFF, 0x30, 0x30)
enemy_die = (0xFF, 0xA0, 0x30)

invalid = (0xFF, 0xFF, 0x00)
impossible = (0x80, 0x80, 0x80)
error = (0xFF, 0x40, 0x40)

welcome_text = (0x20, 0xA0, 0xFF)
health_recovered = (0x0, 0xFF, 0x0)

bar_text = white
bar_filled = (0x0, 0x60, 0x0)
bar_empty = (0x40, 0x10, 0x10)

menu_title = (255, 255, 63)
menu_text = white

def get_names_at_location(x, y, game_map):
    if not game_map.in_bounds(x, y) or not game_map.visible[x, y]:
        return ""
    names = ", ".join(entity.name for entity in game_map.entities if entity.x == x and entity.y == y)
    return names.capitalize()

def render_bar(console, curr_value, max_value, total_width):
    bar_width = int(float(curr_value) / max_value * total_width)
    console.draw_rect(x=0, y=45, width=total_width, height=1, ch=1, bg=bar_empty)
    if bar_width > 0:
        console.draw_rect(x=0, y=45, width=bar_width, height=1, ch=1, bg=bar_filled)
    console.print(x=1, y=45, string=f"HP: {curr_value}/{max_value}", fg=bar_text)

def render_names_at_mouse_loc(console, x, y, engine):
    mouse_x, mouse_y = engine.mouse_loc
    names_at_mouse_location = get_names_at_location(x=mouse_x, y=mouse_y, game_map=engine.game_map)
    console.print(x=x, y=y, string=names_at_mouse_location)

def render_dungeon_level(console, dungeon_level, location):
    x, y = location
    console.print(x=x, y=y, string=f"Dungeon level: {dungeon_level}")

class Message:
    def __init__(self, text, fg):
        self.plain_text = text
        self.fg = fg
        self.count = 1
    @property
    def full_text(self):
        if self.count > 1:
            return f"{self.plain_text} (x{self.count}"
        return self.plain_text
    
class MessageLog:
    def __init__(self):
        self.messages = []

    def add_message(self, text, fg=white, *, canStack=True):
        if canStack and self.messages and text == self.messages[-1].plain_text:
            self.messages[-1].count += 1
        else:
            self.messages.append(Message(text, fg))

    def render(self, console, x, y, width, height):
        self.render_messages(console, x, y, width, height, self.messages)

    @staticmethod
    def wrap(string, width):
        for line in string.splitlines():
            yield from textwrap.wrap(line, width, expand_tabs=True)
    
    @classmethod
    def render_messages(cls, console, x, y, width, height, messages):
        y_offset = height - 1
        for message in reversed(messages):
            for line in reversed(list(cls.wrap(message.full_text, width))):
                console.print(x=x, y=y + y_offset, string=line, fg=message.fg)
                y_offset -= 1
                if y_offset < 0:
                    return
                
class Impossible(Exception):
    '''catches exceptions, makes code more readable'''
class QuitWithoutSaving(SystemExit):
    '''Raised to exit game without auto saving'''
                
#add more items and monsters
player_gen = Actor(char="@", color=(255, 255, 255), name="Player", ai_cls=HostileEnemy, equipment=Equipment(), fighter=Fighter(hp=30, base_defense=2, base_power=2), inventory=Inventory(capacity=26), level=Level(level_up_base=200))
vampire = Actor(char="v", color=(50, 50, 50), name="Vampire", ai_cls=HostileEnemy, equipment=Equipment(), fighter=Fighter(hp=10, base_defense=0, base_power=3), inventory=Inventory(capacity=0), level=Level(xp_given=35))
shadow_knight = Actor(char="K", color=(255, 100, 100), name="Shadow Knight", ai_cls=HostileEnemy, equipment=Equipment(), fighter=Fighter(hp=16, base_defense=1, base_power=4), inventory=Inventory(capacity=0), level=Level(xp_given=100))
health_potion = Item(char="!", color=(127, 0, 255), name="Health Potion", consumable=HealingConsumable(amount=4))
arcane_blast = Item(char="#", color=(255, 255, 0), name="Arcane Blast", consumable=ArcaneDamageConsumable(damage=20, maximum_range=5))
zoink = Item(char="~", color=(207, 63, 255), name="Confusion Scroll", consumable=ConfusionConsumable(number_of_turns=10))
fireball = Item(char="&", color=(255, 0, 0), name="Fireball", consumable=FireballConsumable(damage=12, radius=3))
dagger = Item(char="^", color=(0, 190, 255), name="Dagger", equippable=Dagger())
sword = Item(char="/", color=(0, 190, 255), name="Sword", equippable=Sword())
leather_armor = Item(char="[", color=(139, 69, 19), name="Leather Armor", equippable=LeatherArmor())
chainmail = Item(char="]", color=(139, 69, 19), name="Chainmail Armor", equippable=Chainmail())

item_chances = {
    0: [(health_potion, 35)],
    2: [(zoink, 10)],
    4: [(arcane_blast, 25), (sword, 5)],
    6: [(fireball, 25), (chainmail, 3)],
}

enemy_chances = {
    0: [(vampire, 80)],
    3: [(shadow_knight, 15)],
    5: [(shadow_knight, 30)],
    7: [(shadow_knight, 60)],
}

if __name__ == "__main__":
    main()
