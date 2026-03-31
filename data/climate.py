"""WorldClim climate raster: mean temperature, min temperature, annual rainfall.

The data is a single XZ-compressed file (4320x2160 global grid) from the Terrarium server.
Format: XZ-compressed stream of 3 layers, each 4320*2160 bytes (uint8 packed):
  1. Mean temperature (packed)
  2. Min temperature (packed)
  3. Annual rainfall (packed)

Unpacking:
  Temperature: TEMP_MIN + TEMP_RANGE * (packed / 255) ^ TEMP_CURVE
  Rainfall: RAIN_MIN + RAIN_RANGE * (packed / 255) ^ RAIN_CURVE
"""

import lzma
import math
import os
import time
import urllib.request
from pathlib import Path

import numpy as np

CLIMATE_URL = "https://terrarium.gegy.dev/geo3/climatic_variables.xz"
CLIMATE_WIDTH = 4320
CLIMATE_HEIGHT = 2160
CLIMATE_PIXELS = CLIMATE_WIDTH * CLIMATE_HEIGHT

# Unpacking constants
TEMP_MIN = -40.0
TEMP_MAX = 45.0
TEMP_RANGE = TEMP_MAX - TEMP_MIN
TEMP_CURVE = 1.0

RAIN_MIN = 0.0
RAIN_RANGE = 7200.0
RAIN_CURVE = 2.3

# Defaults for out-of-bounds
STANDARD_TEMPERATURE = 14.0
STANDARD_RAINFALL = 600


def _unpack_temperature(packed: np.ndarray) -> np.ndarray:
    shifted = packed.astype(np.float32)
    return TEMP_MIN + TEMP_RANGE * np.power(shifted / 255.0, TEMP_CURVE)


def _unpack_rainfall(packed: np.ndarray) -> np.ndarray:
    shifted = packed.astype(np.float32)
    return RAIN_MIN + RAIN_RANGE * np.power(shifted / 255.0, RAIN_CURVE)


def _sample_linear(field: np.ndarray, px: float, py: float) -> float:
    sample_x = px - 0.5
    sample_y = py - 0.5

    origin_x = math.floor(sample_x)
    origin_y = math.floor(sample_y)
    frac_x = sample_x - origin_x
    frac_y = sample_y - origin_y

    x0 = max(0, min(origin_x, CLIMATE_WIDTH - 1))
    x1 = max(0, min(origin_x + 1, CLIMATE_WIDTH - 1))
    y0 = max(0, min(origin_y, CLIMATE_HEIGHT - 1))
    y1 = max(0, min(origin_y + 1, CLIMATE_HEIGHT - 1))

    v00 = float(field[y0, x0])
    v10 = float(field[y0, x1])
    v01 = float(field[y1, x0])
    v11 = float(field[y1, x1])

    vx0 = v00 + frac_x * (v10 - v00)
    vx1 = v01 + frac_x * (v11 - v01)
    return vx0 + frac_y * (vx1 - vx0)


class ClimateSource:
    def __init__(self, cache_dir: str):
        self.cache_path = Path(cache_dir) / "climatic_variables.xz"
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)

        self.mean_temperature: np.ndarray | None = None
        self.min_temperature: np.ndarray | None = None
        self.annual_rainfall: np.ndarray | None = None

    def _ensure_loaded(self):
        if self.mean_temperature is not None:
            return

        raw = self._get_raw_data()
        decompressed = lzma.decompress(raw, format=lzma.FORMAT_XZ)

        expected = CLIMATE_PIXELS * 3
        if len(decompressed) < expected:
            raise ValueError(f"Climate data too short: {len(decompressed)} < {expected}")

        mean_packed = np.frombuffer(decompressed[0:CLIMATE_PIXELS], dtype=np.uint8)
        min_packed = np.frombuffer(decompressed[CLIMATE_PIXELS:CLIMATE_PIXELS * 2], dtype=np.uint8)
        rain_packed = np.frombuffer(decompressed[CLIMATE_PIXELS * 2:CLIMATE_PIXELS * 3], dtype=np.uint8)

        self.mean_temperature = _unpack_temperature(mean_packed).reshape((CLIMATE_HEIGHT, CLIMATE_WIDTH))
        self.min_temperature = _unpack_temperature(min_packed).reshape((CLIMATE_HEIGHT, CLIMATE_WIDTH))
        self.annual_rainfall = _unpack_rainfall(rain_packed).reshape((CLIMATE_HEIGHT, CLIMATE_WIDTH))

    def _get_raw_data(self) -> bytes:
        if self.cache_path.exists():
            return self.cache_path.read_bytes()

        print("Downloading climate data...")
        req = urllib.request.Request(CLIMATE_URL, headers={"User-Agent": "earth2mt"})
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = resp.read()
        self.cache_path.write_bytes(data)
        print(f"  Climate data cached ({len(data)} bytes)")
        return data

    def sample(self, lat: float, lon: float) -> tuple[float, float, float]:
        """Get (mean_temp, min_temp, annual_rainfall) for a geographic coordinate.

        Climate raster: x=0 is lon=-180, x=4319 is lon=+180
                        y=0 is lat=+90, y=2159 is lat=-90
        """
        self._ensure_loaded()

        # Convert lat/lon to pixel coordinates
        px = ((lon + 180.0) / 360.0) * CLIMATE_WIDTH
        py = ((90.0 - lat) / 180.0) * CLIMATE_HEIGHT

        if px < 0 or px >= CLIMATE_WIDTH or py < 0 or py >= CLIMATE_HEIGHT:
            return STANDARD_TEMPERATURE, STANDARD_TEMPERATURE, STANDARD_RAINFALL

        return (
            _sample_linear(self.mean_temperature, px, py),
            _sample_linear(self.min_temperature, px, py),
            _sample_linear(self.annual_rainfall, px, py),
        )
