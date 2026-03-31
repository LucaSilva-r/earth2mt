"""Nominatim geocoder for place name -> lat/lon lookup."""

import json
import urllib.request
import urllib.parse


def geocode(place: str) -> tuple[float, float] | None:
    """Look up a place name and return (lat, lon) or None."""
    encoded = urllib.parse.quote(place)
    url = f"https://nominatim.openstreetmap.org/search/{encoded}?format=jsonv2&limit=1"

    req = urllib.request.Request(url, headers={"User-Agent": "earth2mt"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read())

    if not data:
        return None

    return float(data[0]["lat"]), float(data[0]["lon"])
