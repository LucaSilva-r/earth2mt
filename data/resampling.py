"""Helpers for Terrarium-style raster resampling."""

import hashlib
import math
from typing import Callable, TypeVar


T = TypeVar("T")

VORONOI_SEED = 2016969737595986194
VORONOI_FUZZ_RADIUS = 0.45


def _hash_unit_interval(payload: bytes) -> float:
    digest = hashlib.blake2b(payload, digest_size=8).digest()
    return int.from_bytes(digest, "big") / float(1 << 64)


def _voronoi_fuzz(cell_x: int, cell_y: int) -> tuple[float, float]:
    key = f"{VORONOI_SEED}:{cell_x}:{cell_y}".encode("ascii")
    fuzz_x = _hash_unit_interval(key + b":x")
    fuzz_y = _hash_unit_interval(key + b":y")
    return (
        0.5 + (fuzz_x * 2.0 - 1.0) * VORONOI_FUZZ_RADIUS,
        0.5 + (fuzz_y * 2.0 - 1.0) * VORONOI_FUZZ_RADIUS,
    )


def sample_voronoi_cell(global_px: float, global_py: float, value_at: Callable[[int, int], T]) -> T:
    """Sample a categorical raster with soft Voronoi-style cell boundaries."""
    sample_x = global_px - 0.5
    sample_y = global_py - 0.5

    origin_x = math.floor(sample_x)
    origin_y = math.floor(sample_y)

    best_cell = (origin_x, origin_y)
    best_distance = float("inf")

    for cell_y in range(origin_y - 1, origin_y + 2):
        for cell_x in range(origin_x - 1, origin_x + 2):
            fuzz_x, fuzz_y = _voronoi_fuzz(cell_x, cell_y)
            delta_x = sample_x - (cell_x + fuzz_x)
            delta_y = sample_y - (cell_y + fuzz_y)
            distance = delta_x * delta_x + delta_y * delta_y

            if distance < best_distance:
                best_distance = distance
                best_cell = (cell_x, cell_y)

    return value_at(*best_cell)
