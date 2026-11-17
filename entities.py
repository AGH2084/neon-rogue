"""Entities, AI behaviors, A* pathfinding, and loot items."""

import heapq
import math
import random
from typing import Optional

from config import (
    COLOR_BLADE,
    COLOR_GOBLIN,
    COLOR_MEDKIT,
    COLOR_PLAYER,
    COLOR_STALKER,
    COLOR_WARDEN,
    PLAYER_BASE_ATK,
    PLAYER_BASE_DEF,
    PLAYER_BASE_HP,
    SYMBOL_BLADE,
    SYMBOL_GOBLIN,
    SYMBOL_MEDKIT,
    SYMBOL_PLAYER,
    SYMBOL_STALKER,
    SYMBOL_WARDEN,
)
from dungeon import Dungeon

_CARDINAL_DIRS = ((0, -1), (0, 1), (-1, 0), (1, 0))


class Entity:
    """Base class for actors on the dungeon grid."""

    def __init__(
        self,
        x: int,
        y: int,
        symbol: str,
        name: str,
        color_pair: int,
        hp: int,
        atk: int,
        def_: int,
        bold: bool = False,
    ) -> None:
        self.x = x
        self.y = y
        self.symbol = symbol
        self.name = name
        self.color_pair = color_pair
        self.hp = hp
        self.max_hp = hp
        self.atk = atk
        self.def_ = def_
        self.bold = bold

    @property
    def is_alive(self) -> bool:
        return self.hp > 0

    def distance_to(self, x: int, y: int) -> float:
        return math.hypot(self.x - x, self.y - y)


class Player(Entity):
    """Player character tracking progression stats."""

    def __init__(self, x: int, y: int) -> None:
        super().__init__(
            x=x,
            y=y,
            symbol=SYMBOL_PLAYER,
            name="Runner",
            color_pair=COLOR_PLAYER,
            hp=PLAYER_BASE_HP,
            atk=PLAYER_BASE_ATK,
            def_=PLAYER_BASE_DEF,
            bold=True,
        )
        self.xp = 0
        self.level = 1
        self.floor = 1
        self.kills = 0

    @property
    def xp_to_next(self) -> int:
        return 20 + (self.level - 1) * 15

    def gain_xp(self, amount: int) -> list[str]:
        """Add XP and process any level-ups, returning log messages."""
        messages: list[str] = []
        self.xp += amount
        while self.xp >= self.xp_to_next:
            self.xp -= self.xp_to_next
            self.level += 1
            self.max_hp += 6
            heal = 6
            self.hp = min(self.max_hp, self.hp + heal)
            self.atk += 1
            if self.level % 2 == 0:
                self.def_ += 1
            messages.append(
                f"LEVEL UP! Lv.{self.level} (+6 Max HP, +1 ATK"
                + (", +1 DEF" if self.level % 2 == 0 else "")
                + ")."
            )
        return messages

    def heal(self, amount: int) -> int:
        """Restore up to `amount` HP and return actual HP restored."""
        before = self.hp
        self.hp = min(self.max_hp, self.hp + amount)
        return self.hp - before


class Item:
    """Pickable loot item on the dungeon floor."""

    def __init__(
        self,
        x: int,
        y: int,
        symbol: str,
        name: str,
        color_pair: int,
        kind: str,
        value: int,
    ) -> None:
        self.x = x
        self.y = y
        self.symbol = symbol
        self.name = name
        self.color_pair = color_pair
        self.kind = kind  # "medkit" or "blade"
        self.value = value


def astar_next_step(
    start: tuple[int, int],
    goal: tuple[int, int],
    dungeon: Dungeon,
    blocked: set[tuple[int, int]],
    max_nodes: int = 300,
) -> Optional[tuple[int, int]]:
    """Compute the next step from `start` toward `goal` using A* (`heapq`)."""
    if start == goal:
        return None

    open_heap: list[tuple[int, int, tuple[int, int]]] = []
    heapq.heappush(open_heap, (0, 0, start))
    came_from: dict[tuple[int, int], Optional[tuple[int, int]]] = {start: None}
    g_score: dict[tuple[int, int], int] = {start: 0}
    counter = 0
    expanded = 0

    while open_heap and expanded < max_nodes:
        _, _, current = heapq.heappop(open_heap)
        expanded += 1

        if current == goal:
            # Reconstruct first step after start
            step = current
            while came_from[step] is not None and came_from[step] != start:
                step = came_from[step]  # type: ignore[assignment]
            return step if came_from[step] == start else None

        cx, cy = current
        for dx, dy in _CARDINAL_DIRS:
            nx, ny = cx + dx, cy + dy
            nxt = (nx, ny)
            if not dungeon.is_walkable(nx, ny):
                continue
            if nxt != goal and nxt in blocked:
                continue

            tentative_g = g_score[current] + 1
            if tentative_g < g_score.get(nxt, 10**9):
                came_from[nxt] = current
                g_score[nxt] = tentative_g
                h = abs(goal[0] - nx) + abs(goal[1] - ny)
                counter += 1
                heapq.heappush(open_heap, (tentative_g + h, counter, nxt))

    return None


class Enemy(Entity):
    """Base enemy with turn-based AI."""

    def __init__(
        self,
        x: int,
        y: int,
        symbol: str,
        name: str,
        color_pair: int,
        hp: int,
        atk: int,
        def_: int,
        xp_value: int,
        bold: bool = False,
    ) -> None:
        super().__init__(x, y, symbol, name, color_pair, hp, atk, def_, bold=bold)
        self.xp_value = xp_value

    def take_turn(
        self,
        player: Player,
        dungeon: Dungeon,
        occupied: set[tuple[int, int]],
        turn_count: int,
    ) -> Optional[str]:
        """Execute one turn of AI. Returns 'attack' if adjacent & attacking player."""
        raise NotImplementedError

    def _try_greedy_step(
        self,
        target_x: int,
        target_y: int,
        dungeon: Dungeon,
        occupied: set[tuple[int, int]],
    ) -> bool:
        """Move 1 tile closer to target if a walkable, unoccupied step improves distance."""
        best_dist = math.hypot(self.x - target_x, self.y - target_y)
        best_pos: Optional[tuple[int, int]] = None

        dirs = list(_CARDINAL_DIRS)
        random.shuffle(dirs)
        for dx, dy in dirs:
            nx, ny = self.x + dx, self.y + dy
            if not dungeon.is_walkable(nx, ny):
                continue
            if (nx, ny) in occupied:
                continue
            dist = math.hypot(nx - target_x, ny - target_y)
            if dist < best_dist:
                best_dist = dist
                best_pos = (nx, ny)

        if best_pos is not None:
            occupied.discard((self.x, self.y))
            self.x, self.y = best_pos
            occupied.add(best_pos)
            return True
        return False

    def _wander(self, dungeon: Dungeon, occupied: set[tuple[int, int]]) -> None:
        dirs = list(_CARDINAL_DIRS)
        random.shuffle(dirs)
        for dx, dy in dirs:
            nx, ny = self.x + dx, self.y + dy
            if dungeon.is_walkable(nx, ny) and (nx, ny) not in occupied:
                occupied.discard((self.x, self.y))
                self.x, self.y = nx, ny
                occupied.add((nx, ny))
                return


class Goblin(Enemy):
    """Wanders randomly until player enters LOS, then chases greedily."""

    def __init__(self, x: int, y: int, floor: int) -> None:
        hp = 10 + (floor - 1) * 3
        atk = 4 + (floor - 1)
        def_ = 1 + (floor - 1) // 2
        xp = 10 + (floor - 1) * 3
        super().__init__(
            x, y, SYMBOL_GOBLIN, "Goblin", COLOR_GOBLIN, hp, atk, def_, xp
        )

    def take_turn(
        self,
        player: Player,
        dungeon: Dungeon,
        occupied: set[tuple[int, int]],
        turn_count: int,
    ) -> Optional[str]:
        if abs(self.x - player.x) + abs(self.y - player.y) == 1:
            return "attack"

        if dungeon.has_line_of_sight(self.x, self.y, player.x, player.y):
            self._try_greedy_step(player.x, player.y, dungeon, occupied)
        else:
            self._wander(dungeon, occupied)
        return None


class Stalker(Enemy):
    """Fast ambusher using A* pathfinding when within 10 tiles."""

    def __init__(self, x: int, y: int, floor: int) -> None:
        hp = 12 + (floor - 1) * 3
        atk = 6 + (floor - 1)
        def_ = 1 + (floor - 1) // 2
        xp = 18 + (floor - 1) * 4
        super().__init__(
            x, y, SYMBOL_STALKER, "Stalker", COLOR_STALKER, hp, atk, def_, xp
        )

    def take_turn(
        self,
        player: Player,
        dungeon: Dungeon,
        occupied: set[tuple[int, int]],
        turn_count: int,
    ) -> Optional[str]:
        if abs(self.x - player.x) + abs(self.y - player.y) == 1:
            return "attack"

        if self.distance_to(player.x, player.y) <= 10.0:
            steps = 2 if turn_count % 2 == 0 else 1
            for _ in range(steps):
                if abs(self.x - player.x) + abs(self.y - player.y) == 1:
                    break
                nxt = astar_next_step(
                    (self.x, self.y),
                    (player.x, player.y),
                    dungeon,
                    occupied,
                )
                if nxt is None or nxt == (player.x, player.y) or nxt in occupied:
                    break
                occupied.discard((self.x, self.y))
                self.x, self.y = nxt
                occupied.add(nxt)
        return None


class Warden(Enemy):
    """Floor mini-boss guarding the '>' stairs with high HP/ATK."""

    def __init__(self, x: int, y: int, floor: int, anchor: tuple[int, int]) -> None:
        hp = 28 + (floor - 1) * 7
        atk = 8 + (floor - 1) * 2
        def_ = 3 + (floor - 1) // 2
        xp = 40 + (floor - 1) * 10
        super().__init__(
            x, y, SYMBOL_WARDEN, "Warden", COLOR_WARDEN, hp, atk, def_, xp, bold=True
        )
        self.anchor = anchor

    def take_turn(
        self,
        player: Player,
        dungeon: Dungeon,
        occupied: set[tuple[int, int]],
        turn_count: int,
    ) -> Optional[str]:
        if abs(self.x - player.x) + abs(self.y - player.y) == 1:
            return "attack"

        if self.distance_to(player.x, player.y) <= 6.5 and dungeon.has_line_of_sight(
            self.x, self.y, player.x, player.y
        ):
            nxt = astar_next_step(
                (self.x, self.y),
                (player.x, player.y),
                dungeon,
                occupied,
            )
            if nxt is not None and nxt != (player.x, player.y) and nxt not in occupied:
                occupied.discard((self.x, self.y))
                self.x, self.y = nxt
                occupied.add(nxt)
            else:
                self._try_greedy_step(player.x, player.y, dungeon, occupied)
        elif self.distance_to(self.anchor[0], self.anchor[1]) > 2.5:
            self._try_greedy_step(self.anchor[0], self.anchor[1], dungeon, occupied)
        return None


def spawn_floor_entities(
    dungeon: Dungeon, floor: int
) -> tuple[list[Enemy], list[Item]]:
    """Populate a newly generated dungeon floor with enemies and loot."""
    enemies: list[Enemy] = []
    items: list[Item] = []

    used_positions: set[tuple[int, int]] = {dungeon.player_start, dungeon.stairs_pos}

    # Spawn Warden guarding the '>' stairs
    sx, sy = dungeon.stairs_pos
    warden_pos: Optional[tuple[int, int]] = None
    candidates = [(sx + dx, sy + dy) for dx, dy in _CARDINAL_DIRS]
    random.shuffle(candidates)
    for cx, cy in candidates:
        if dungeon.is_walkable(cx, cy) and (cx, cy) not in used_positions:
            warden_pos = (cx, cy)
            break
    if warden_pos is None:
        warden_pos = dungeon.stairs_pos

    used_positions.add(warden_pos)
    enemies.append(Warden(warden_pos[0], warden_pos[1], floor, dungeon.stairs_pos))

    # Gather candidate floor tiles from non-starting rooms
    candidate_tiles: list[tuple[int, int]] = []
    for room in dungeon.rooms[1:]:
        for tx, ty in room.inner_tiles():
            if (tx, ty) not in used_positions:
                candidate_tiles.append((tx, ty))

    random.shuffle(candidate_tiles)

    num_goblins = min(len(candidate_tiles), 4 + floor)
    num_stalkers = min(max(0, len(candidate_tiles) - num_goblins), 2 + floor // 2)

    for _ in range(num_goblins):
        pos = candidate_tiles.pop()
        used_positions.add(pos)
        enemies.append(Goblin(pos[0], pos[1], floor))

    for _ in range(num_stalkers):
        pos = candidate_tiles.pop()
        used_positions.add(pos)
        enemies.append(Stalker(pos[0], pos[1], floor))

    # Spawn loot: Medkits and Overclock Blades
    num_medkits = min(len(candidate_tiles), 2 + floor // 3)
    num_blades = min(max(0, len(candidate_tiles) - num_medkits), 1 + (1 if floor % 2 == 0 else 0))

    for _ in range(num_medkits):
        pos = candidate_tiles.pop()
        used_positions.add(pos)
        heal_amt = 10 + floor * 2
        items.append(
            Item(pos[0], pos[1], SYMBOL_MEDKIT, "Medkit", COLOR_MEDKIT, "medkit", heal_amt)
        )

    for _ in range(num_blades):
        pos = candidate_tiles.pop()
        used_positions.add(pos)
        items.append(
            Item(pos[0], pos[1], SYMBOL_BLADE, "Overclock Blade", COLOR_BLADE, "blade", 2)
        )

    return enemies, items
