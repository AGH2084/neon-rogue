# Neon Rogue

A small, dependency-free roguelike that runs in your terminal. Descend procedurally generated floors, fight neon creatures, grab loot, and see how deep you can go before you flatline.

Built with Python's standard `curses` library — no third-party packages, no assets, no build step.

## Features

- Procedurally generated 80x24 dungeon floors with non-overlapping rooms and L-shaped corridors
- Line-of-sight fog of war via recursive symmetric shadowcasting
- Turn-based combat with three enemy types and distinct AI
- XP, leveling, medkits, and permanent attack upgrades
- Escalating difficulty: enemies grow stronger on every floor, and a Warden guards the stairs

## Requirements

- Python 3.9+
- A curses-capable terminal, at least **80x30** (80 map columns x 24 map rows, plus a 2-line HUD and 4-line log); color is recommended but optional
- Linux, macOS, or WSL

> **Windows note:** the standard Windows Python does not ship a working `curses` module (`_curses` is missing). Run the game inside WSL, or use a Python distribution that provides curses.

## Running

From the repository root:

```sh
python main.py
```

There is nothing to install and no configuration file to create.

## Controls

| Key | Action |
| --- | --- |
| `W` `A` `S` `D` / arrow keys | Move one tile (walk into an enemy to attack) |
| `.` or `Space` | Wait one turn |
| `Q` | Quit |
| `R` | Restart after game over |

There is no separate "use stairs" key: stepping onto `>` immediately descends.

## How to play

You are `@`, starting on floor 1 with 30 HP, 6 ATK, and 2 DEF. Find the stairs (`>`) in the farthest room and descend. Each new floor is fully regenerated and heals you for up to 25% of your max HP.

### Combat

Attacks resolve as:

```
damage = max(1, attacker_ATK - defender_DEF + random(-1..2))
```

Enemies act after every turn you take. Walking into a wall or pressing an unbound key costs no turn.

### Enemies

| Symbol | Enemy | Behavior |
| --- | --- | --- |
| `g` | Goblin | Wanders randomly until it has line of sight, then chases greedily |
| `s` | Stalker | Pathfinds with A*; within 10 tiles it closes two tiles every other turn |
| `W` | Warden | Floor mini-boss posted beside the stairs; chases within ~6.5 tiles with line of sight, then returns to its post |

Enemy HP, attack, defense, and XP rewards scale with the current floor.

### Loot

Items are picked up automatically by walking onto them.

| Symbol | Item | Effect |
| --- | --- | --- |
| `+` | Medkit | Restores up to `10 + 2 x floor` HP |
| `/` | Overclock Blade | Permanent `+2 ATK` |

### Leveling

Killing enemies grants XP; the next level costs `20 + 15 x (level - 1)` XP. Each level grants:

- `+6` max HP and heals `6` HP
- `+1` ATK
- `+1` DEF on even-numbered levels

## Configuration

All gameplay and layout tuning lives in `config.py`, including map size, FOV radius, room counts and sizes, player base stats, tile/symbol characters, and terminal minimums. If you change `MAP_WIDTH` or `MAP_HEIGHT`, the UI layout follows automatically, but keep the terminal large enough for the derived `MIN_TERM_WIDTH` and `MIN_TERM_HEIGHT`.

## Project layout

| File | Purpose |
| --- | --- |
| `main.py` | Curses setup, `Game` state, turn loop, combat, progression, rendering, input |
| `dungeon.py` | Room/corridor generation, tile queries, shadowcasting FOV, Bresenham line of sight |
| `entities.py` | Player, items, enemy classes and AI, A* pathfinding, floor spawning |
| `config.py` | Constants for map, colors, stats, symbols, and UI dimensions |
| `AGENTS.md` | Notes for AI coding agents working in this repo |

## Notes

- Game state is in memory only; quitting or dying ends the run (press `R` to start over).
- Rendering draws directly to the terminal with absolute coordinates, so the game expects a terminal of at least 80x30 and will show a resize prompt below that.
