"""Coordinate transforms between geographic (lat/lon), block, and tile coordinates."""

import math

from earth2mt.config import EQUATOR_CIRCUMFERENCE, TILE_SIZE, ZOOM_BASE

try:
    from pyproj import CRS, Transformer
except ImportError:
    CRS = None
    Transformer = None


AUTO_PROJECTION = "auto"
LEGACY_PROJECTION = "legacy"
EUROPE_LCC_PROJECTION = "europe-lcc"

EUROPE_LCC_BOUNDS = {
    "min_lat": 24.0,
    "max_lat": 72.0,
    "min_lon": -35.0,
    "max_lon": 45.0,
}
EUROPE_LCC_EPSG = 3034


def _projection_requires_pyproj(projection: str) -> bool:
    return projection == EUROPE_LCC_PROJECTION


def _is_europe_lcc_candidate(center_lat: float, center_lon: float) -> bool:
    return (
        EUROPE_LCC_BOUNDS["min_lat"] <= center_lat <= EUROPE_LCC_BOUNDS["max_lat"]
        and EUROPE_LCC_BOUNDS["min_lon"] <= center_lon <= EUROPE_LCC_BOUNDS["max_lon"]
    )


def _resolve_projection(center_lat: float, center_lon: float, projection: str) -> str:
    if projection == AUTO_PROJECTION:
        if _is_europe_lcc_candidate(center_lat, center_lon):
            return EUROPE_LCC_PROJECTION
        return LEGACY_PROJECTION
    if projection in {LEGACY_PROJECTION, EUROPE_LCC_PROJECTION}:
        return projection
    raise ValueError(f"Unknown projection mode: {projection}")


def _require_pyproj(projection: str):
    if Transformer is None and _projection_requires_pyproj(projection):
        raise RuntimeError(
            "Projection "
            f"{projection!r} requires pyproj. Install earth2mt requirements to enable it."
        )


def tile_count_x(zoom: int) -> float:
    return tile_count_y(zoom) * 2.0


def tile_count_y(zoom: int) -> float:
    return ZOOM_BASE ** zoom


def global_width(zoom: int) -> float:
    return tile_count_x(zoom) * TILE_SIZE


def global_height(zoom: int) -> float:
    return tile_count_y(zoom) * TILE_SIZE


def global_pixel_to_tile_pixel(global_px: float, global_py: float, zoom: int) -> tuple[int, int, int, int]:
    """Convert global pixel coordinates to (tile_x, tile_y, pixel_x, pixel_y)."""
    max_px = global_width(zoom) - 1.0
    max_py = global_height(zoom) - 1.0

    global_px = max(0.0, min(global_px, max_px))
    global_py = max(0.0, min(global_py, max_py))

    tile_x = int(global_px // TILE_SIZE)
    tile_y = int(global_py // TILE_SIZE)
    pixel_x = int(global_px % TILE_SIZE)
    pixel_y = int(global_py % TILE_SIZE)

    return tile_x, tile_y, pixel_x, pixel_y


def meters_per_pixel(zoom: int) -> float:
    return EQUATOR_CIRCUMFERENCE / global_width(zoom)


def best_zoom_for_scale(scale: float, max_zoom: int) -> int:
    """Pick the Terrarium zoom level that best matches the world scale."""
    zoom = math.log(EQUATOR_CIRCUMFERENCE / (2.0 * TILE_SIZE * scale), ZOOM_BASE)
    return max(0, min(max_zoom, int(round(zoom))))


class CoordinateTransform:
    """Converts between geographic coordinates, block coordinates, and tile pixel coordinates.

    Block coordinate (0, 0) corresponds to (center_lat, center_lon).
    In Luanti: +X = east, +Z = south (matching Terrarium's convention).
    """

    def __init__(
        self,
        center_lat: float,
        center_lon: float,
        scale: float,
        height_multiplier: float = 1.0,
        projection: str = AUTO_PROJECTION,
    ):
        self.center_lat = center_lat
        self.center_lon = center_lon
        self.scale = scale  # meters per block
        self.height_multiplier = height_multiplier
        self.requested_projection = projection
        self.projection = _resolve_projection(center_lat, center_lon, projection)

        self._geo_to_projected = None
        self._projected_to_geo = None
        self.center_projected_x = None
        self.center_projected_y = None

        if self.projection == LEGACY_PROJECTION:
            center_lat_radians = math.radians(center_lat)
            # Longitude degrees shrink toward the poles; use the local scale at the
            # world center so east/west distances stay consistent for small regions.
            self.meters_per_deg_lon = (EQUATOR_CIRCUMFERENCE * math.cos(center_lat_radians)) / 360.0
            self.meters_per_deg_lat = EQUATOR_CIRCUMFERENCE / 360.0  # local approximation
        elif self.projection == EUROPE_LCC_PROJECTION:
            _require_pyproj(self.projection)

            wgs84 = CRS.from_epsg(4326)
            europe_lcc = CRS.from_epsg(EUROPE_LCC_EPSG)
            self._geo_to_projected = Transformer.from_crs(
                wgs84,
                europe_lcc,
                always_xy=True,
            )
            self._projected_to_geo = Transformer.from_crs(
                europe_lcc,
                wgs84,
                always_xy=True,
            )
            self.center_projected_x, self.center_projected_y = self._geo_to_projected.transform(
                center_lon,
                center_lat,
            )
        else:
            raise AssertionError(f"Unhandled projection mode: {self.projection}")

    def block_to_geo(self, bx: int, bz: int) -> tuple[float, float]:
        """Convert block coordinates to (lat, lon)."""
        # +X = east, +Z = south
        east_meters = bx * self.scale
        south_meters = bz * self.scale

        if self.projection == LEGACY_PROJECTION:
            lon = self.center_lon + east_meters / self.meters_per_deg_lon
            lat = self.center_lat - south_meters / self.meters_per_deg_lat
            return lat, lon

        projected_x = self.center_projected_x + east_meters
        projected_y = self.center_projected_y - south_meters
        lon, lat = self._projected_to_geo.transform(projected_x, projected_y)
        return lat, lon

    def geo_to_block(self, lat: float, lon: float) -> tuple[int, int]:
        """Convert (lat, lon) to block coordinates."""
        if self.projection == LEGACY_PROJECTION:
            east_meters = (lon - self.center_lon) * self.meters_per_deg_lon
            south_meters = (self.center_lat - lat) * self.meters_per_deg_lat
        else:
            projected_x, projected_y = self._geo_to_projected.transform(lon, lat)
            east_meters = projected_x - self.center_projected_x
            south_meters = self.center_projected_y - projected_y

        bx = int(round(east_meters / self.scale))
        bz = int(round(south_meters / self.scale))
        return bx, bz

    def elevation_to_world_y(self, elevation_meters: float, sea_level: int = 0) -> int:
        """Convert a real-world elevation in meters to a Luanti Y coordinate.

        `self.scale` sets the baseline meters-per-block conversion while
        `self.height_multiplier` exaggerates or compresses the vertical axis
        without changing horizontal distances. Sea level remains at the
        requested Y offset.
        """
        return int(round((elevation_meters / self.scale) * self.height_multiplier)) + sea_level

    def geo_to_global_pixel(self, lat: float, lon: float, zoom: int) -> tuple[float, float]:
        """Convert (lat, lon) to floating-point global pixel coordinates."""
        tc_x = tile_count_x(zoom)
        tc_y = tile_count_y(zoom)

        norm_lon = (lon + 180.0) / 360.0
        norm_lat = (90.0 - lat) / 180.0

        global_px = norm_lon * tc_x * TILE_SIZE
        global_py = norm_lat * tc_y * TILE_SIZE

        max_px = global_width(zoom) - 1.0
        max_py = global_height(zoom) - 1.0
        global_px = max(0.0, min(global_px, max_px))
        global_py = max(0.0, min(global_py, max_py))

        return global_px, global_py

    def geo_to_tile_pixel(self, lat: float, lon: float, zoom: int) -> tuple[int, int, int, int]:
        """Convert (lat, lon) to (tile_x, tile_y, pixel_x, pixel_y) in the tile grid.

        The tile grid covers the whole globe:
        - tile_x: 0..tile_count_x-1, left (lon=-180) to right (lon=+180)
        - tile_y: 0..tile_count_y-1, top (lat=+90) to bottom (lat=-90)
        """
        global_px, global_py = self.geo_to_global_pixel(lat, lon, zoom)
        return global_pixel_to_tile_pixel(global_px, global_py, zoom)

    def block_to_tile_pixel(self, bx: int, bz: int, zoom: int) -> tuple[int, int, int, int]:
        """Convert block coordinates to tile + pixel coordinates."""
        lat, lon = self.block_to_geo(bx, bz)
        return self.geo_to_tile_pixel(lat, lon, zoom)
