"""Main entry point, combat loop, progression, and curses UI for Neon Rogue."""

import curses
import random
from collections import deque
from typing import Optional

from config import (
    COLOR_BLADE,
    COLOR_FLOOR_LIT,
    COLOR_FOG,
    COLOR_GOBLIN,
    COLOR_HP_HIGH,
    COLOR_HP_LOW,
    COLOR_HUD,
    COLOR_LOG,
    COLOR_MEDKIT,
    COLOR_PLAYER,
    COLOR_STAIRS,
    COLOR_STALKER,
    COLOR_WALL_LIT,
    COLOR_WARDEN,
    FOV_RADIUS,
    LOG_LINES,
    MAP_HEIGHT,
    MAP_WIDTH,
    MIN_TERM_HEIGHT,
    MIN_TERM_WIDTH,
    TILE_STAIRS,
    TILE_WALL,
    TOP_BAR_HEIGHT,
    VIS_EXPLORED,
    VIS_VISIBLE,
)
from dungeon import Dungeon
from entities import Enemy, Entity, Item, Player, spawn_floor_entities


def safe_addstr(
    stdscr: "curses.window", y: int, x: int, text: str, attr: int = 0
) -> None:
    """Write text to curses window, guarding against out-of-bounds curses.error."""
    max_y, max_x = stdscr.getmaxyx()
    if y < 0 or y >= max_y or x >= max_x:
        return
    if x < 0:
        text = text[-x:]
        x = 0
    if not text:
        return
    available = max_x - x
    if available <= 0:
        return
    clipped = text[:available]
    try:
        stdscr.addstr(y, x, clipped, attr)
    except curses.error:
        pass


def init_colors() -> None:
    """Initialize ANSI color pairs with default terminal background."""
    if not curses.has_colors():
        return
    curses.start_color()
    try:
        curses.use_default_colors()
        bg = -1
    except curses.error:
        bg = curses.COLOR_BLACK

    curses.init_pair(COLOR_PLAYER, curses.COLOR_CYAN, bg)
    curses.init_pair(COLOR_GOBLIN, curses.COLOR_GREEN, bg)
    curses.init_pair(COLOR_STALKER, curses.COLOR_YELLOW, bg)
    curses.init_pair(COLOR_WARDEN, curses.COLOR_RED, bg)
    curses.init_pair(COLOR_MEDKIT, curses.COLOR_CYAN, bg)
    curses.init_pair(COLOR_BLADE, curses.COLOR_MAGENTA, bg)
    curses.init_pair(COLOR_WALL_LIT, curses.COLOR_WHITE, bg)
    curses.init_pair(COLOR_FLOOR_LIT, curses.COLOR_WHITE, bg)
    curses.init_pair(COLOR_FOG, curses.COLOR_WHITE, bg)
    curses.init_pair(COLOR_STAIRS, curses.COLOR_YELLOW, bg)
    curses.init_pair(COLOR_HUD, curses.COLOR_CYAN, bg)
    curses.init_pair(COLOR_HP_HIGH, curses.COLOR_GREEN, bg)
    curses.init_pair(COLOR_HP_LOW, curses.COLOR_RED, bg)
    curses.init_pair(COLOR_LOG, curses.COLOR_WHITE, bg)


def calc_damage(atk: int, def_: int) -> int:
    """Compute melee combat damage with variance."""
    return max(1, atk - def_ + random.randint(-1, 2))


def render_hp_bar(hp: int, max_hp: int, width: int = 12) -> str:
    """Build an ASCII HP bar."""
    ratio = max(0.0, min(1.0, hp / max(1, max_hp)))
    filled = round(ratio * width)
    return "[" + "#" * filled + "-" * (width - filled) + "]"


class Game:
    """Encapsulates game state, turn resolution, and rendering."""

    def __init__(self) -> None:
        self.dungeon = Dungeon(MAP_WIDTH, MAP_HEIGHT)
        px, py = self.dungeon.player_start
        self.player = Player(px, py)
        self.enemies: list[Enemy] = []
        self.items: list[Item] = []
        self.log: deque[str] = deque(maxlen=LOG_LINES)
        self.turn_count = 0
        self.game_over = False

        self.enemies, self.items = spawn_floor_entities(self.dungeon, self.player.floor)
        self.dungeon.compute_fov(self.player.x, self.player.y, FOV_RADIUS)
        self.add_log("Entered Neon Rogue. Find the '>' stairs to descend deeper.")

    def add_log(self, message: str) -> None:
        self.log.append(message)

    def _enemy_at(self, x: int, y: int) -> Optional[Enemy]:
        for enemy in self.enemies:
            if enemy.is_alive and enemy.x == x and enemy.y == y:
                return enemy
        return None

    def _descend_stairs(self) -> None:
        self.player.floor += 1
        heal_amt = max(1, int(self.player.max_hp * 0.25))
        restored = self.player.heal(heal_amt)

        self.dungeon = Dungeon(MAP_WIDTH, MAP_HEIGHT)
        self.player.x, self.player.y = self.dungeon.player_start
        self.enemies, self.items = spawn_floor_entities(self.dungeon, self.player.floor)
        self.dungeon.compute_fov(self.player.x, self.player.y, FOV_RADIUS)

        self.add_log(
            f"Descended to Floor {self.player.floor}! Restored {restored} HP."
        )

    def _resolve_attack(self, attacker: Entity, defender: Entity) -> None:
        dmg = calc_damage(attacker.atk, defender.def_)
        defender.hp = max(0, defender.hp - dmg)

        if attacker is self.player:
            self.add_log(f"You hit {defender.name} for {dmg} DMG.")
            if not defender.is_alive and isinstance(defender, Enemy):
                self.player.kills += 1
                self.add_log(
                    f"{defender.name} destroyed! (+{defender.xp_value} XP)"
                )
                for lvl_msg in self.player.gain_xp(defender.xp_value):
                    self.add_log(lvl_msg)
        else:
            self.add_log(f"{attacker.name} hits you for {dmg} DMG!")
            if not self.player.is_alive:
                self.game_over = True
                self.add_log("You flatlined! Press R to restart or Q to quit.")

    def _pickup_items_at_player(self) -> None:
        remaining: list[Item] = []
        for item in self.items:
            if item.x == self.player.x and item.y == self.player.y:
                if item.kind == "medkit":
                    restored = self.player.heal(item.value)
                    self.add_log(f"Used {item.name}: +{restored} HP.")
                elif item.kind == "blade":
                    self.player.atk += item.value
                    self.add_log(
                        f"Equipped {item.name}: +{item.value} ATK (now {self.player.atk})."
                    )
            else:
                remaining.append(item)
        self.items = remaining

    def handle_player_action(self, dx: int, dy: int, wait: bool = False) -> bool:
        """Process a player move/attack/wait. Returns True if a turn elapsed."""
        if self.game_over:
            return False

        if wait:
            self.add_log("You wait a turn, scanning the shadows.")
            self._end_player_turn()
            return True

        nx = self.player.x + dx
        ny = self.player.y + dy

        target_enemy = self._enemy_at(nx, ny)
        if target_enemy is not None:
            self._resolve_attack(self.player, target_enemy)
            self.enemies = [e for e in self.enemies if e.is_alive]
            self._end_player_turn()
            return True

        if self.dungeon.is_walkable(nx, ny):
            self.player.x = nx
            self.player.y = ny
            self._pickup_items_at_player()

            if (nx, ny) == self.dungeon.stairs_pos:
                self._descend_stairs()
                return True

            self._end_player_turn()
            return True

        return False

    def _end_player_turn(self) -> None:
        self.turn_count += 1
        self.dungeon.compute_fov(self.player.x, self.player.y, FOV_RADIUS)

        occupied: set[tuple[int, int]] = {(self.player.x, self.player.y)}
        for enemy in self.enemies:
            if enemy.is_alive:
                occupied.add((enemy.x, enemy.y))

        for enemy in self.enemies:
            if not enemy.is_alive or self.game_over:
                continue
            action = enemy.take_turn(
                self.player, self.dungeon, occupied, self.turn_count
            )
            if action == "attack":
                self._resolve_attack(enemy, self.player)

    def render(self, stdscr: "curses.window") -> None:
        """Render top HUD, dungeon viewport, and bottom 4-line combat log."""
        stdscr.erase()
        max_y, max_x = stdscr.getmaxyx()

        if max_y < MIN_TERM_HEIGHT or max_x < MIN_TERM_WIDTH:
            msg1 = "Terminal too small for Neon Rogue!"
            msg2 = f"Required: {MIN_TERM_WIDTH}x{MIN_TERM_HEIGHT} | Current: {max_x}x{max_y}"
            msg3 = "Please resize your terminal window (or press Q to quit)."
            safe_addstr(stdscr, max(0, max_y // 2 - 1), max(0, (max_x - len(msg1)) // 2), msg1, curses.A_BOLD)
            safe_addstr(stdscr, max(0, max_y // 2), max(0, (max_x - len(msg2)) // 2), msg2)
            safe_addstr(stdscr, max(0, max_y // 2 + 1), max(0, (max_x - len(msg3)) // 2), msg3)
            stdscr.refresh()
            return

        # --- Top Bar (2 lines) ---
        hp_bar = render_hp_bar(self.player.hp, self.player.max_hp)
        hp_ratio = self.player.hp / max(1, self.player.max_hp)
        hp_attr = curses.color_pair(COLOR_HP_HIGH if hp_ratio > 0.35 else COLOR_HP_LOW) | curses.A_BOLD

        hud_left = f"FL:{self.player.floor}  HP {hp_bar} {self.player.hp}/{self.player.max_hp}"
        hud_right = (
            f"  ATK:{self.player.atk}  DEF:{self.player.def_}"
            f"  LV:{self.player.level} ({self.player.xp}/{self.player.xp_to_next} XP)"
        )
        safe_addstr(stdscr, 0, 0, hud_left, hp_attr)
        safe_addstr(stdscr, 0, len(hud_left), hud_right, curses.color_pair(COLOR_HUD) | curses.A_BOLD)

        controls = "WASD/Arrows: Move | .: Wait | Q: Quit"
        if self.game_over:
            controls = "GAME OVER - Press R to Restart | Q to Quit"
        safe_addstr(stdscr, 1, 0, controls.ljust(MAP_WIDTH), curses.A_DIM)

        # --- Center Viewport (80x24) ---
        map_y_offset = TOP_BAR_HEIGHT
        for y in range(self.dungeon.height):
            for x in range(self.dungeon.width):
                vis = self.dungeon.visibility[y][x]
                if vis == 0:  # VIS_UNEXPLORED
                    continue

                tile = self.dungeon.tiles[y][x]
                if vis == VIS_VISIBLE:
                    if tile == TILE_WALL:
                        attr = curses.color_pair(COLOR_WALL_LIT) | curses.A_BOLD
                    elif tile == TILE_STAIRS:
                        attr = curses.color_pair(COLOR_STAIRS) | curses.A_BOLD
                    else:
                        attr = curses.color_pair(COLOR_FLOOR_LIT)
                else:  # VIS_EXPLORED (fogged / dim)
                    attr = curses.color_pair(COLOR_FOG) | curses.A_DIM

                safe_addstr(stdscr, map_y_offset + y, x, tile, attr)

        # Draw items on explored/visible tiles (visible items lit, explored items dim)
        for item in self.items:
            vis = self.dungeon.visibility[item.y][item.x]
            if vis == VIS_VISIBLE:
                safe_addstr(
                    stdscr,
                    map_y_offset + item.y,
                    item.x,
                    item.symbol,
                    curses.color_pair(item.color_pair) | curses.A_BOLD,
                )
            elif vis == VIS_EXPLORED:
                safe_addstr(
                    stdscr,
                    map_y_offset + item.y,
                    item.x,
                    item.symbol,
                    curses.color_pair(COLOR_FOG) | curses.A_DIM,
                )

        # Draw visible enemies
        for enemy in self.enemies:
            if enemy.is_alive and self.dungeon.is_visible(enemy.x, enemy.y):
                attr = curses.color_pair(enemy.color_pair)
                if enemy.bold:
                    attr |= curses.A_BOLD
                safe_addstr(
                    stdscr,
                    map_y_offset + enemy.y,
                    enemy.x,
                    enemy.symbol,
                    attr,
                )

        # Draw player
        safe_addstr(
            stdscr,
            map_y_offset + self.player.y,
            self.player.x,
            self.player.symbol,
            curses.color_pair(self.player.color_pair) | curses.A_BOLD,
        )

        # --- Bottom 4-line Combat/Event Log ---
        log_y_offset = TOP_BAR_HEIGHT + MAP_HEIGHT
        log_list = list(self.log)
        for idx in range(LOG_LINES):
            line_text = log_list[idx] if idx < len(log_list) else ""
            attr = curses.color_pair(COLOR_LOG)
            if idx == len(log_list) - 1:
                attr |= curses.A_BOLD
            safe_addstr(stdscr, log_y_offset + idx, 0, line_text, attr)

        stdscr.refresh()


def run_game(stdscr: "curses.window") -> None:
    """Curses main loop."""
    try:
        curses.curs_set(0)
    except curses.error:
        pass
    stdscr.keypad(True)
    init_colors()

    game = Game()

    move_keys: dict[int, tuple[int, int]] = {
        curses.KEY_UP: (0, -1),
        curses.KEY_DOWN: (0, 1),
        curses.KEY_LEFT: (-1, 0),
        curses.KEY_RIGHT: (1, 0),
        ord("w"): (0, -1),
        ord("W"): (0, -1),
        ord("s"): (0, 1),
        ord("S"): (0, 1),
        ord("a"): (-1, 0),
        ord("A"): (-1, 0),
        ord("d"): (1, 0),
        ord("D"): (1, 0),
    }

    while True:
        game.render(stdscr)
        key = stdscr.getch()

        if key in (ord("q"), ord("Q")):
            break

        if key == curses.KEY_RESIZE:
            continue

        if game.game_over:
            if key in (ord("r"), ord("R")):
                game = Game()
            continue

        if key in move_keys:
            dx, dy = move_keys[key]
            game.handle_player_action(dx, dy)
        elif key in (ord("."), ord(" ")):
            game.handle_player_action(0, 0, wait=True)
        elif key == ord(">") and (game.player.x, game.player.y) == game.dungeon.stairs_pos:
            game._descend_stairs()


def main() -> None:
    curses.wrapper(run_game)


if __name__ == "__main__":
    main()
