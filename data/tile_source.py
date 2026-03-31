"""HTTP tile fetcher with disk caching for Terrarium tile server."""

import os
import time
import urllib.request
from pathlib import Path

from earth2mt.config import TILE_BASE_URL


class TileSource:
    def __init__(self, cache_dir: str):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def fetch_tile(self, endpoint: str, zoom: int, tile_x: int, tile_y: int) -> bytes:
        """Fetch a tile, using disk cache if available."""
        cache_path = self.cache_dir / endpoint / str(zoom) / str(tile_x) / str(tile_y)

        if cache_path.exists():
            return cache_path.read_bytes()

        url = f"{TILE_BASE_URL}/{endpoint}/{zoom}/{tile_x}/{tile_y}"
        data = self._http_get(url)

        cache_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = cache_path.with_name(
            f".{cache_path.name}.{os.getpid()}.{time.time_ns()}.tmp"
        )
        try:
            tmp_path.write_bytes(data)
            os.replace(tmp_path, cache_path)
        finally:
            if tmp_path.exists():
                tmp_path.unlink()

        return data

    def _http_get(self, url: str, retries: int = 3) -> bytes:
        """HTTP GET with retries."""
        req = urllib.request.Request(url, headers={"User-Agent": "earth2mt"})
        for attempt in range(retries):
            try:
                with urllib.request.urlopen(req, timeout=30) as resp:
                    return resp.read()
            except Exception as e:
                if attempt == retries - 1:
                    raise RuntimeError(f"Failed to fetch {url}: {e}") from e
                time.sleep(1 * (attempt + 1))
