"""Elevation data source using Terrarium's NASADEM tiles."""

import math
import numpy as np

from earth2mt.config import TILE_SIZE
from earth2mt.data.tile_source import TileSource
from earth2mt.data.raster_reader import read_raster
from earth2mt.terrain.coords import (
    CoordinateTransform,
    best_zoom_for_scale,
    global_pixel_to_tile_pixel,
    meters_per_pixel,
)


ELEVATION_ENDPOINT = "elevation2"
ELEVATION_MAX_ZOOM = 6

NEAREST = "nearest"
LINEAR = "linear"
COSINE = "cosine"
CUBIC = "cubic"


def _select_interpolation_mode(relative_scale: float) -> str:
    """Mirror Terrarium's interpolation choice for raster resampling."""
    if relative_scale <= 1.0:
        return NEAREST
    if relative_scale <= 2.0:
        return LINEAR
    if relative_scale <= 3.0:
        return COSINE
    return CUBIC


def _interpolate_1d(mode: str, values: list[float], x: float) -> float:
    if mode == NEAREST:
        return values[0]
    if mode == LINEAR:
        return values[0] + (values[1] - values[0]) * x
    if mode == COSINE:
        cosine_x = (1.0 - math.cos(x * math.pi)) / 2.0
        return values[0] + (values[1] - values[0]) * cosine_x
    return values[1] + 0.5 * x * (
        values[2] - values[0] + x * (
            2.0 * values[0] - 5.0 * values[1] + 4.0 * values[2] - values[3] + x * (
                3.0 * (values[1] - values[2]) + values[3] - values[0]
            )
        )
    )


class ElevationSource:
    def __init__(self, cache_dir: str, scale: float):
        self.tile_source = TileSource(cache_dir)
        self.zoom = best_zoom_for_scale(scale, ELEVATION_MAX_ZOOM)
        self.interpolation = _select_interpolation_mode(meters_per_pixel(self.zoom) / scale)
        self._tile_cache: dict[tuple[int, int], np.ndarray] = {}

    def get_tile(self, tile_x: int, tile_y: int) -> np.ndarray:
        """Get a parsed elevation tile (1000x1000 int16 array, values in meters)."""
        key = (tile_x, tile_y)
        if key not in self._tile_cache:
            try:
                raw = self.tile_source.fetch_tile(
                    ELEVATION_ENDPOINT, self.zoom, tile_x, tile_y
                )
                self._tile_cache[key] = read_raster(raw)
            except Exception:
                # Return zeros (sea level) for missing tiles
                self._tile_cache[key] = np.zeros((TILE_SIZE, TILE_SIZE), dtype=np.int16)
        return self._tile_cache[key]

    def sample(self, coords: CoordinateTransform, bx: int, bz: int) -> float:
        """Get elevation in meters for a block coordinate."""
        lat, lon = coords.block_to_geo(bx, bz)
        global_px, global_py = coords.geo_to_global_pixel(lat, lon, self.zoom)
        return self._sample_global_pixel(global_px, global_py)

    def sample_region(self, coords: CoordinateTransform,
                      bx_start: int, bz_start: int,
                      width: int, height: int) -> np.ndarray:
        """Get elevation for a rectangular region of blocks. Returns (height, width) array."""
        result = np.zeros((height, width), dtype=np.float32)
        for dz in range(height):
            for dx in range(width):
                result[dz, dx] = self.sample(coords, bx_start + dx, bz_start + dz)
        return result

    def clear_cache(self):
        self._tile_cache.clear()

    def _get_global_value(self, global_px: int, global_py: int) -> float:
        tile_x, tile_y, px, py = global_pixel_to_tile_pixel(global_px, global_py, self.zoom)
        tile = self.get_tile(tile_x, tile_y)
        return float(tile[py, px])

    def _sample_global_pixel(self, global_px: float, global_py: float) -> float:
        sample_x = global_px - 0.5
        sample_y = global_py - 0.5

        if self.interpolation == NEAREST:
            src_x = math.floor(sample_x)
            src_y = math.floor(sample_y)
            return self._get_global_value(src_x, src_y)

        origin_x = math.floor(sample_x)
        origin_y = math.floor(sample_y)
        frac_x = sample_x - origin_x
        frac_y = sample_y - origin_y

        if self.interpolation in (LINEAR, COSINE):
            kernel_width = 2
            kernel_offset = 0
        else:
            kernel_width = 4
            kernel_offset = -1

        columns = []
        for kernel_x in range(kernel_width):
            source_x = origin_x + kernel_x + kernel_offset
            column = []
            for kernel_y in range(kernel_width):
                source_y = origin_y + kernel_y + kernel_offset
                column.append(self._get_global_value(source_x, source_y))
            columns.append(_interpolate_1d(self.interpolation, column, frac_y))

        return _interpolate_1d(self.interpolation, columns, frac_x)
