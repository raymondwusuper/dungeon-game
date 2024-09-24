# 2d game
If you want to slack off, this is the perfect game for you. </br>
The textures and styles (minus some items and enemies) all look like bash, so you can pretend you are in terminal when you are working. </br>
## Prerequisites
This game only requires 2 libraries, both of which can be installed using requirements.txt.
In python3, run the following: 
```bash
pip3 install -r requirements.txt
```
Alternatively, you can just install the libraries independently.
```bash
pip3 install numpy tcod
```
This may encounter issues with version numbers, so be warned.
## About
This game has infinite floors, and you can obtain more overpowered items and gear as you go on. This comes at a cost, because the monsters that spawn also get stronger. </br>
You can add your own custom monsters and items and equipment. Just copy-paste existing equipment (code located near the end of the file), tweak some parameters, and add spawn rates in the map right under. </br>
Upon level up, you can select the stat which you want to increase. </br>
Modifications to the code can be done by changing the code in your IDE of choice.
## Controls
- **Up Arrow:** Moves you one tile upward.
- **Right Arrow:** Moves you one tile rightward.
- **Left Arrow:** Moves you one tile leftward.
- **Down Arrow:** Moves you one tile downward.
- **Escape:** Quits the game.
- **V:** Views action history.
- **G:** Picks up an item (if you are standing on it).
- **I:** Opens your inventory (preparing to use item).
  - **A-Z:** Uses the selected item in the inventory.
- **D:** Opens your inventory (preparing to drop item).
  - **A-Z:** Drops the selected item in the inventory
- **SLASH:** Looks around and can identify your surroundings.
  - **ARROWS:** Moves the looking tile by 1 increment
  - **LSHIFT/RSHIFT:** Holding increases the speed at which you look around by a factor of 5 tiles (only works when you are looking).
  - **LCTRL/RCTRL:** Holding increases the speed at which you look around by a factor of 10 tiles (only works when you are looking).
  - **LALT/RALT:** Holding increases the speed at which you look around by a factor of 20 tiles (only works when you are looking).
- **C:** Views your stats.
- **>:** Goes down the stairs to the next floor (if you are on a staircase).
I think that's it but let me know if there are more. These are the main controls.
## How to play
You can open the code in an IDE and run it, but you can alternatively navigate to the directory that the main script is located in, using:
```bash
cd /your/path/name
```
Then after doing that, run:
```bash
python3 main.py
```
This is if you are using Python 3.
