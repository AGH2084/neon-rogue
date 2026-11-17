"""Procedural dungeon generation and symmetric shadowcasting FOV."""

import random
from config import (
    FOV_RADIUS,
    MAP_HEIGHT,
    MAP_WIDTH,
    MAX_ROOMS,
    ROOM_MAX_SIZE,
    ROOM_MIN_SIZE,
    TILE_FLOOR,
    TILE_STAIRS,
    TILE_WALL,
    VIS_EXPLORED,
    VIS_UNEXPLORED,
    VIS_VISIBLE,
)

# Multipliers for the 8 octants of recursive shadowcasting
_OCTANT_TRANSFORMS = (
    (1, 0, 0, 1),
    (0, 1, 1, 0),
    (0, -1, 1, 0),
    (-1, 0, 0, 1),
    (-1, 0, 0, -1),
    (0, -1, -1, 0),
    (0, 1, -1, 0),
    (1, 0, 0, -1),
)


class Room:
    """A rectangular room on the dungeon grid."""

    def __init__(self, x: int, y: int, width: int, height: int) -> None:
        self.x1 = x
        self.y1 = y
        self.x2 = x + width
        self.y2 = y + height

    def center(self) -> tuple[int, int]:
        cx = (self.x1 + self.x2) // 2
        cy = (self.y1 + self.y2) // 2
        return cx, cy

    def intersects(self, other: "Room") -> bool:
        # Leave at least 1 wall tile between rooms
        return (
            self.x1 <= other.x2 + 1
            and self.x2 + 1 >= other.x1
            and self.y1 <= other.y2 + 1
            and self.y2 + 1 >= other.y1
        )

    def inner_tiles(self) -> list[tuple[int, int]]:
        return [
            (x, y)
            for y in range(self.y1 + 1, self.y2)
            for x in range(self.x1 + 1, self.x2)
        ]


class Dungeon:
    """80x24 tile grid with procedural rooms, L-corridors, and FOV state."""

    def __init__(self, width: int = MAP_WIDTH, height: int = MAP_HEIGHT) -> None:
        self.width = width
        self.height = height
        self.tiles: list[list[str]] = []
        self.visibility: list[list[int]] = []
        self.rooms: list[Room] = []
        self.player_start: tuple[int, int] = (1, 1)
        self.stairs_pos: tuple[int, int] = (1, 1)
        self.generate()

    def generate(self) -> None:
        """Generate non-overlapping rooms connected by L-shaped corridors."""
        self.tiles = [
            [TILE_WALL for _ in range(self.width)] for _ in range(self.height)
        ]
        self.visibility = [
            [VIS_UNEXPLORED for _ in range(self.width)] for _ in range(self.height)
        ]
        self.rooms = []

        for _ in range(MAX_ROOMS * 3):
            if len(self.rooms) >= MAX_ROOMS:
                break

            w = random.randint(ROOM_MIN_SIZE, ROOM_MAX_SIZE)
            h = random.randint(ROOM_MIN_SIZE, min(ROOM_MAX_SIZE, self.height - 2))
            x = random.randint(1, self.width - w - 2)
            y = random.randint(1, self.height - h - 2)

            new_room = Room(x, y, w, h)
            if any(new_room.intersects(other) for other in self.rooms):
                continue

            self._carve_room(new_room)
            new_cx, new_cy = new_room.center()

            if self.rooms:
                prev_cx, prev_cy = self.rooms[-1].center()
                if random.random() < 0.5:
                    self._carve_h_tunnel(prev_cx, new_cx, prev_cy)
                    self._carve_v_tunnel(prev_cy, new_cy, new_cx)
                else:
                    self._carve_v_tunnel(prev_cy, new_cy, prev_cx)
                    self._carve_h_tunnel(prev_cx, new_cx, new_cy)

            self.rooms.append(new_room)

        # Fallback if somehow fewer than 2 rooms were placed
        if not self.rooms:
            fallback = Room(2, 2, 10, 6)
            self._carve_room(fallback)
            self.rooms.append(fallback)

        self.player_start = self.rooms[0].center()

        # Place stairs in the room farthest from player_start
        px, py = self.player_start
        farthest_room = max(
            self.rooms,
            key=lambda r: (r.center()[0] - px) ** 2 + (r.center()[1] - py) ** 2,
        )
        self.stairs_pos = farthest_room.center()
        sx, sy = self.stairs_pos
        self.tiles[sy][sx] = TILE_STAIRS

    def _carve_room(self, room: Room) -> None:
        for y in range(room.y1 + 1, room.y2):
            for x in range(room.x1 + 1, room.x2):
                if self.in_bounds(x, y):
                    self.tiles[y][x] = TILE_FLOOR

    def _carve_h_tunnel(self, x1: int, x2: int, y: int) -> None:
        for x in range(min(x1, x2), max(x1, x2) + 1):
            if self.in_bounds(x, y):
                self.tiles[y][x] = TILE_FLOOR

    def _carve_v_tunnel(self, y1: int, y2: int, x: int) -> None:
        for y in range(min(y1, y2), max(y1, y2) + 1):
            if self.in_bounds(x, y):
                self.tiles[y][x] = TILE_FLOOR

    def in_bounds(self, x: int, y: int) -> bool:
        return 0 <= x < self.width and 0 <= y < self.height

    def is_walkable(self, x: int, y: int) -> bool:
        return self.in_bounds(x, y) and self.tiles[y][x] != TILE_WALL

    def is_opaque(self, x: int, y: int) -> bool:
        return not self.in_bounds(x, y) or self.tiles[y][x] == TILE_WALL

    def is_visible(self, x: int, y: int) -> bool:
        return self.in_bounds(x, y) and self.visibility[y][x] == VIS_VISIBLE

    def is_explored(self, x: int, y: int) -> bool:
        return self.in_bounds(x, y) and self.visibility[y][x] != VIS_UNEXPLORED

    def compute_fov(self, origin_x: int, origin_y: int, radius: int = FOV_RADIUS) -> None:
        """Update tile visibility states using recursive symmetric shadowcasting."""
        for y in range(self.height):
            for x in range(self.width):
                if self.visibility[y][x] == VIS_VISIBLE:
                    self.visibility[y][x] = VIS_EXPLORED

        if self.in_bounds(origin_x, origin_y):
            self.visibility[origin_y][origin_x] = VIS_VISIBLE

        for xx, xy, yx, yy in _OCTANT_TRANSFORMS:
            self._cast_light(origin_x, origin_y, 1, 1.0, 0.0, radius, xx, xy, yx, yy)

    def _cast_light(
        self,
        cx: int,
        cy: int,
        row: int,
        start_slope: float,
        end_slope: float,
        radius: int,
        xx: int,
        xy: int,
        yx: int,
        yy: int,
    ) -> None:
        if start_slope < end_slope:
            return

        next_start_slope = start_slope
        radius_sq = radius * radius

        for i in range(row, radius + 1):
            blocked = False
            dy = -i
            for dx in range(-i, 1):
                l_slope = (dx - 0.5) / (dy + 0.5)
                r_slope = (dx + 0.5) / (dy - 0.5)

                if start_slope < r_slope:
                    continue
                if end_slope > l_slope:
                    break

                ax = cx + dx * xx + dy * xy
                ay = cy + dx * yx + dy * yy

                if self.in_bounds(ax, ay) and (dx * dx + dy * dy) <= radius_sq:
                    self.visibility[ay][ax] = VIS_VISIBLE

                if blocked:
                    if self.is_opaque(ax, ay):
                        next_start_slope = r_slope
                    else:
                        blocked = False
                        start_slope = next_start_slope
                elif self.is_opaque(ax, ay) and i < radius:
                    blocked = True
                    self._cast_light(
                        cx, cy, i + 1, start_slope, l_slope, radius, xx, xy, yx, yy
                    )
                    next_start_slope = r_slope

            if blocked:
                break

    def has_line_of_sight(self, x1: int, y1: int, x2: int, y2: int) -> bool:
        """Return True if an unobstructed Bresenham line exists between two tiles."""
        dx = abs(x2 - x1)
        dy = abs(y2 - y1)
        sx = 1 if x1 < x2 else -1
        sy = 1 if y1 < y2 else -1
        err = dx - dy

        cx, cy = x1, y1
        while (cx, cy) != (x2, y2):
            if (cx, cy) != (x1, y1) and self.is_opaque(cx, cy):
                return False
            e2 = 2 * err
            if e2 > -dy:
                err -= dy
                cx += sx
            if e2 < dx:
                err += dx
                cy += sy
        return True
