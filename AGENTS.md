# AGENTS.md

Four-file stdlib-only Python terminal roguelike. No package, manifests, tests, linter, or CI.

## Run and verify

- Play from the repo root: `python main.py`. Needs a curses-capable terminal (Linux/macOS/WSL).
- `import curses` fails with the local Windows Python 3.15 (`_curses` is missing), so the game cannot start as-is on this host. Do not waste turns debugging `main.py` imports locally.
- Syntax check: `python -m py_compile config.py dungeon.py entities.py main.py`.
- Headless checks: `dungeon.py` and `entities.py` do not import curses. Import them directly (e.g. `Dungeon()` + `spawn_floor_entities(d, 1)`) to smoke-test generation, spawning, and AI without a terminal.
- No test suite or type/lint config exists; don't invent commands for them.

## Module roles

- `config.py` — all tuning constants, tiles, symbols, and curses color-pair IDs.
- `dungeon.py` — room/corridor generation, recursive symmetric shadowcasting FOV, Bresenham LOS.
- `entities.py` — `Entity`/`Player`/`Item`, enemy subclasses with their AI, A* step search, floor spawning.
- `main.py` — curses setup, `Game` turn loop/combat/leveling, rendering, key handling.

## Gotchas

- All rendering writes directly to `stdscr` in absolute screen coordinates (`map_y_offset = TOP_BAR_HEIGHT`). Always draw through `safe_addstr`; a raw `stdscr.addstr` at the terminal edge raises `curses.error`.
- `MAP_WIDTH`x`MAP_HEIGHT` is 80x24, plus a 2-line HUD and 4-line log. The terminal must be at least `MIN_TERM_WIDTH`x`MIN_TERM_HEIGHT` (80x30); smaller terminals only show a resize prompt.
- `MAP_WIDTH`/`MAP_HEIGHT` drive both generation and screen layout, so resizing the map also shifts the log offset. Leave `MIN_TERM_HEIGHT` derived as `TOP_BAR_HEIGHT + MAP_HEIGHT + LOG_LINES`.
- Adding a color requires three edits: a new `COLOR_*` ID starting at 1 in `config.py`, `curses.init_pair(...)` in `init_colors()`, and the explicit import list at the top of `main.py`.
- Enemies act only inside `Game._end_player_turn`, invoked when `handle_player_action` returns True. Stepping onto `>` descends immediately inside `handle_player_action`, so the `>` key branch in `run_game` is redundant and normally unreachable.
- Imports are absolute top-level (`from config import ...`), not package-relative. Keep running from the repo root; a package layout would require rewriting every import.
