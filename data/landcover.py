"""Land cover data source using Terrarium's ESA CCI tiles."""

import numpy as np

from earth2mt.config import TILE_SIZE, Cover, cover_by_id
from earth2mt.data.tile_source import TileSource
from earth2mt.data.raster_reader import read_raster
from earth2mt.terrain.coords import CoordinateTransform, best_zoom_for_scale


LANDCOVER_ENDPOINT = "landcover"
LANDCOVER_MAX_ZOOM = 4


class LandcoverSource:
    def __init__(self, cache_dir: str, scale: float):
        self.tile_source = TileSource(cache_dir)
        self.zoom = best_zoom_for_scale(scale, LANDCOVER_MAX_ZOOM)
        self._tile_cache: dict[tuple[int, int], np.ndarray] = {}

    def get_tile(self, tile_x: int, tile_y: int) -> np.ndarray:
        """Get a parsed landcover tile (1000x1000 uint8 array, values are Cover IDs)."""
        key = (tile_x, tile_y)
        if key not in self._tile_cache:
            try:
                raw = self.tile_source.fetch_tile(
                    LANDCOVER_ENDPOINT, self.zoom, tile_x, tile_y
                )
                self._tile_cache[key] = read_raster(raw)
            except Exception:
                self._tile_cache[key] = np.zeros((TILE_SIZE, TILE_SIZE), dtype=np.uint8)
        return self._tile_cache[key]

    def sample(self, coords: CoordinateTransform, bx: int, bz: int) -> Cover:
        """Get land cover type for a block coordinate."""
        lat, lon = coords.block_to_geo(bx, bz)
        tile_x, tile_y, px, py = coords.geo_to_tile_pixel(lat, lon, self.zoom)
        tile = self.get_tile(tile_x, tile_y)
        return cover_by_id(int(tile[py, px]))

    def clear_cache(self):
        self._tile_cache.clear()
