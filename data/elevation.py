"""Elevation data source using Terrarium's NASADEM tiles."""

import numpy as np

from earth2mt.config import TILE_SIZE
from earth2mt.data.tile_source import TileSource
from earth2mt.data.raster_reader import read_raster
from earth2mt.terrain.coords import CoordinateTransform, best_zoom_for_scale


ELEVATION_ENDPOINT = "elevation2"
ELEVATION_MAX_ZOOM = 6


class ElevationSource:
    def __init__(self, cache_dir: str, scale: float):
        self.tile_source = TileSource(cache_dir)
        self.zoom = best_zoom_for_scale(scale, ELEVATION_MAX_ZOOM)
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
        tile_x, tile_y, px, py = coords.geo_to_tile_pixel(lat, lon, self.zoom)
        tile = self.get_tile(tile_x, tile_y)
        return float(tile[py, px])

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
