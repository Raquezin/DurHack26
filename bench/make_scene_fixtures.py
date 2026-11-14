import json
import math
from pathlib import Path

import numpy as np
from PIL import Image

OUT = Path(__file__).resolve().parents[1] / "fixtures" / "scenes"
WIDTH, HEIGHT, ROWS, COLS = 512, 384, 3, 5
FOV_DEG, EYE_M, MAX_M, PERCENTILE, MIN_HIT_FRACTION = 70.0, 1.4, 10.0, 10, 0.05
WALL, FAR_WALL, BOX, DOOR, LINTEL = (190, 185, 170), (150, 160, 175), (200, 90, 40), (110, 70, 35), (175, 170, 155)
FLOOR, TILE, SKY = (120, 115, 105), (95, 90, 82), (60, 64, 72)


def corridor(half_width, length):
    return [
        (-half_width - 0.1, -half_width, 0, 2.5, 0, length, WALL),
        (half_width, half_width + 0.1, 0, 2.5, 0, length, WALL),
    ]


SCENES = {
    "clear_corridor": dict(
        expected="PATH_CLEAR",
        boxes=corridor(1.0, 40) + [(-1.0, 1.0, 0, 2.5, 40, 40.1, FAR_WALL)],
    ),
    "wall_ahead_1m": dict(
        expected="TURN_RIGHT",
        boxes=[
            (-1.1, -1.0, 0, 2.5, 0, 1.1, WALL),
            (-1.1, 0.35, 0, 2.5, 1.0, 1.1, WALL),
            (0.35, 12, 0, 2.5, 6.0, 6.1, FAR_WALL),
        ],
    ),
    "obstacle_left": dict(
        expected="VEER_RIGHT",
        boxes=corridor(1.5, 40) + [
            (-1.5, 1.5, 0, 2.5, 40, 40.1, FAR_WALL),
            (-1.1, -0.25, 0, 1.1, 2.5, 3.2, BOX),
        ],
        invalid=[(0, 4)],
    ),
    "doorway": dict(
        expected="DOOR_AHEAD",
        boxes=corridor(1.5, 4.0) + [
            (-1.5, -0.6, 0, 2.5, 4.0, 4.1, WALL),
            (0.6, 1.5, 0, 2.5, 4.0, 4.1, WALL),
            (-0.6, 0.6, 2.0, 2.5, 4.0, 4.1, LINTEL),
            (-0.7, -0.6, 0, 2.05, 3.95, 4.1, DOOR),
            (0.6, 0.7, 0, 2.05, 3.95, 4.1, DOOR),
            (-0.7, 0.7, 2.0, 2.05, 3.95, 4.1, DOOR),
            (-3, 3, 0, 2.5, 8.0, 8.1, FAR_WALL),
        ],
    ),
}


def rays():
    focal = (WIDTH / 2) / math.tan(math.radians(FOV_DEG / 2))
    u, v = np.meshgrid(np.arange(WIDTH) + 0.5 - WIDTH / 2, HEIGHT / 2 - (np.arange(HEIGHT) + 0.5))
    directions = np.stack([u, v, np.full_like(u, focal)], axis=-1)
    return directions / np.linalg.norm(directions, axis=-1, keepdims=True)


def hit_box(origin, directions, box):
    low, high = np.array(box[0:6:2], float), np.array(box[1:6:2], float)
    with np.errstate(divide="ignore", invalid="ignore"):
        t1, t2 = (low - origin) / directions, (high - origin) / directions
    near, far = np.fmin(t1, t2), np.fmax(t1, t2)
    t_enter, t_exit = np.nanmax(near, axis=-1), np.nanmin(far, axis=-1)
    hit = (t_exit >= t_enter) & (t_enter > 0)
    return np.where(hit, t_enter, np.inf), np.nanargmax(near, axis=-1)


def render(boxes):
    origin = np.array([0.0, EYE_M, 0.0])
    directions = rays()
    depth = np.full((HEIGHT, WIDTH), np.inf)
    image = np.empty((HEIGHT, WIDTH, 3))
    image[:] = SKY
    with np.errstate(divide="ignore"):
        floor_t = np.where(directions[..., 1] < 0, -EYE_M / directions[..., 1], np.inf)
    floor = np.isfinite(floor_t)
    point = origin + directions * np.where(floor, floor_t, 0)[..., None]
    tiles = (np.floor(point[..., 0]).astype(int) + np.floor(point[..., 2]).astype(int)) % 2 == 0
    image[floor] = np.where(tiles[floor][:, None], FLOOR, TILE)
    nearest = np.where(floor, floor_t, np.inf)
    for box in boxes:
        t, axis = hit_box(origin, directions, box)
        closer = t < nearest
        nearest = np.where(closer, t, nearest)
        depth = np.where(closer, t, depth)
        floor &= ~closer
        light = np.choose(axis, [0.8, 1.1, 1.0])[closer][:, None]
        image[closer] = np.array(box[6]) * light
    fade = 1 / (1 + 0.06 * np.minimum(nearest, 30))
    image = image * (0.55 + 0.45 * fade[..., None])
    return Image.fromarray(np.clip(image, 0, 255).astype(np.uint8)), depth


def zone_distances(depth):
    distances = []
    for row in np.array_split(np.arange(HEIGHT), ROWS):
        for col in np.array_split(np.arange(WIDTH), COLS):
            zone = depth[np.ix_(row, col)]
            hits = zone[zone <= MAX_M]
            near = hits.size >= MIN_HIT_FRACTION * zone.size
            distances.append(round(float(np.percentile(hits, PERCENTILE)), 2) if near else None)
    return distances


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for frame_id, (name, scene) in enumerate(SCENES.items(), start=1):
        image, depth = render(scene["boxes"])
        distances = zone_distances(depth)
        valid = [True] * (ROWS * COLS)
        for row, col in scene.get("invalid", []):
            valid[row * COLS + col] = False
            distances[row * COLS + col] = None
        geometry = dict(
            frame_id=frame_id,
            t_capture_ns=frame_id * 1_000_000_000,
            rows=ROWS,
            cols=COLS,
            distances_m=distances,
            valid=valid,
            horizontal_fov_deg=FOV_DEG,
            expected=scene["expected"],
        )
        (OUT / f"{name}.json").write_text(json.dumps(geometry, indent=2) + "\n")
        image.save(OUT / f"{name}.jpg", quality=90)
        grid = [distances[r * COLS:(r + 1) * COLS] for r in range(ROWS)]
        print(name, scene["expected"], *("  ".join(f"{d if d is not None else 'inf':>5}" for d in g) for g in grid), sep="\n  ")


if __name__ == "__main__":
    main()
