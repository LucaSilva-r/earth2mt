#!/usr/bin/env python3
"""CLI entry point for earth2mt - Earth terrain to Luanti world generator."""

import argparse
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait
import hashlib
import multiprocessing
import os
import shutil
import sys
import time


_WORKER_COORDS = None
_WORKER_ELEVATION_SRC = None
_WORKER_LANDCOVER_SRC = None
_WORKER_CLIMATE_SRC = None
_WORKER_ORGANIC_CARBON_SRC = None
_WORKER_SOIL_CLASS_SRC = None
_WORKER_WORLD_SEED = None


def _positive_int(raw_value: str) -> int:
    """argparse type that only accepts positive integers."""
    value = int(raw_value)
    if value < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return value


def _non_negative_float(raw_value: str) -> float:
    """argparse type that only accepts floats >= 0."""
    value = float(raw_value)
    if value < 0.0:
        raise argparse.ArgumentTypeError("must be at least 0")
    return value


def resolve_jobs(requested_jobs: int | None, total_columns: int) -> int:
    """Choose a sane worker count for the current world size."""
    if total_columns <= 1:
        return 1

    available = os.cpu_count() or 1
    jobs = available if requested_jobs is None else requested_jobs
    return max(1, min(jobs, total_columns))


def block_bounds_for_radius(radius_blocks: int) -> tuple[int, int, int, int]:
    """Return inclusive world block bounds for a centered square radius."""
    return -radius_blocks, radius_blocks, -radius_blocks, radius_blocks


def _mapblock_columns(
    mb_min_x: int,
    mb_max_x: int,
    mb_min_z: int,
    mb_max_z: int,
):
    """Yield all mapblock column coordinates in generation order."""
    for mb_x in range(mb_min_x, mb_max_x + 1):
        for mb_z in range(mb_min_z, mb_max_z + 1):
            yield mb_x, mb_z


def _set_generation_worker_state(
    coords,
    elevation_src,
    landcover_src,
    climate_src,
    organic_carbon_src,
    soil_class_src,
    world_seed: int,
):
    """Populate process-local generation state used by workers."""
    global _WORKER_COORDS
    global _WORKER_ELEVATION_SRC
    global _WORKER_LANDCOVER_SRC
    global _WORKER_CLIMATE_SRC
    global _WORKER_ORGANIC_CARBON_SRC
    global _WORKER_SOIL_CLASS_SRC
    global _WORKER_WORLD_SEED

    _WORKER_COORDS = coords
    _WORKER_ELEVATION_SRC = elevation_src
    _WORKER_LANDCOVER_SRC = landcover_src
    _WORKER_CLIMATE_SRC = climate_src
    _WORKER_ORGANIC_CARBON_SRC = organic_carbon_src
    _WORKER_SOIL_CLASS_SRC = soil_class_src
    _WORKER_WORLD_SEED = world_seed


def _clear_generation_worker_state():
    """Release process-local generation state."""
    global _WORKER_COORDS
    global _WORKER_ELEVATION_SRC
    global _WORKER_LANDCOVER_SRC
    global _WORKER_CLIMATE_SRC
    global _WORKER_ORGANIC_CARBON_SRC
    global _WORKER_SOIL_CLASS_SRC
    global _WORKER_WORLD_SEED

    _WORKER_COORDS = None
    _WORKER_ELEVATION_SRC = None
    _WORKER_LANDCOVER_SRC = None
    _WORKER_CLIMATE_SRC = None
    _WORKER_ORGANIC_CARBON_SRC = None
    _WORKER_SOIL_CLASS_SRC = None
    _WORKER_WORLD_SEED = None


def _init_generation_worker(
    cache_dir: str,
    center_lat: float,
    center_lon: float,
    scale: float,
    world_seed: int,
):
    """Initialize per-process generation state when spawning workers."""
    if _WORKER_COORDS is not None:
        return

    from earth2mt.data.climate import ClimateSource
    from earth2mt.data.elevation import ElevationSource
    from earth2mt.data.landcover import LandcoverSource
    from earth2mt.data.soil import OrganicCarbonSource, SoilClassSource
    from earth2mt.terrain.coords import CoordinateTransform

    _set_generation_worker_state(
        CoordinateTransform(center_lat, center_lon, scale),
        ElevationSource(cache_dir, scale),
        LandcoverSource(cache_dir, scale),
        ClimateSource(cache_dir),
        OrganicCarbonSource(cache_dir, scale),
        SoilClassSource(cache_dir, scale),
        world_seed,
    )


def _generate_serialized_column(
    column: tuple[int, int],
) -> tuple[int, int, list[tuple[int, bytes]]]:
    """Generate and serialize all non-empty mapblocks for one X/Z column."""
    if _WORKER_COORDS is None:
        raise RuntimeError("Generation worker state was not initialized")

    from earth2mt.terrain.surface import generate_mapblock_column
    from earth2mt.world.mapblock import serialize_mapblock_column

    mb_x, mb_z = column
    mapblocks = generate_mapblock_column(
        mb_x,
        mb_z,
        _WORKER_COORDS,
        _WORKER_ELEVATION_SRC,
        _WORKER_LANDCOVER_SRC,
        _WORKER_CLIMATE_SRC,
        _WORKER_ORGANIC_CARBON_SRC,
        _WORKER_SOIL_CLASS_SRC,
        _WORKER_WORLD_SEED,
    )
    serialized = serialize_mapblock_column(mapblocks, mb_x, mb_z)
    return mb_x, mb_z, serialized


def _preferred_mp_context():
    """Prefer fork so workers can share the large read-only climate raster."""
    if "fork" in multiprocessing.get_all_start_methods():
        return multiprocessing.get_context("fork")
    return multiprocessing.get_context()


def _iter_parallel_generated_columns(executor, columns, jobs: int):
    """Yield serialized columns from a live process pool."""
    column_iter = iter(columns)
    max_pending = max(jobs * 2, 1)
    pending = set()

    while len(pending) < max_pending:
        try:
            column = next(column_iter)
        except StopIteration:
            break
        pending.add(executor.submit(_generate_serialized_column, column))

    while pending:
        done, pending = wait(pending, return_when=FIRST_COMPLETED)
        for future in done:
            yield future.result()

            try:
                column = next(column_iter)
            except StopIteration:
                continue
            pending.add(executor.submit(_generate_serialized_column, column))


def _print_progress(done: int, total_columns: int, start_time: float, now: float | None = None):
    """Render an in-place generation progress line."""
    if now is None:
        now = time.monotonic()

    elapsed = now - start_time
    rate = done / elapsed if elapsed > 0 else 0.0
    remaining = (total_columns - done) / rate if rate > 0 else 0.0
    print(
        f"\r  [{done}/{total_columns}] "
        f"{done * 100 / total_columns:.1f}% "
        f"({rate:.1f} col/s, ~{remaining:.0f}s remaining)   ",
        end="",
        flush=True,
    )


def _should_print_progress(
    done: int,
    total_columns: int,
    last_update_time: float,
    now: float,
    progress_interval: float,
) -> bool:
    """Decide whether enough time has passed to print another progress update."""
    if done >= total_columns:
        return True
    if progress_interval == 0.0:
        return True
    return (now - last_update_time) >= progress_interval


def _spiral_offsets(max_radius: int):
    """Yield (x, z) offsets from the center in expanding square rings."""
    yield 0, 0
    for radius in range(1, max_radius + 1):
        for x in range(-radius, radius + 1):
            yield x, -radius
        for z in range(-radius + 1, radius + 1):
            yield radius, z
        for x in range(radius - 1, -radius - 1, -1):
            yield x, radius
        for z in range(radius - 1, -radius, -1):
            yield -radius, z


def find_spawn_position(
    radius_blocks: int,
    coords,
    elevation_src,
    landcover_src,
    climate_src,
) -> tuple[int, int, int]:
    """Pick a grounded spawn near the world center.

    We prefer the center if it is above sea level and not classified as water.
    If not, search outward in a spiral until we find the nearest solid surface.
    """
    from earth2mt.config import SEA_LEVEL, Biome
    from earth2mt.terrain.biome import classify_biome

    water_biomes = {
        Biome.VOID,
        Biome.DEEP_OCEAN,
        Biome.OCEAN,
        Biome.RIVER,
        Biome.FROZEN_RIVER,
    }

    search_radius = min(radius_blocks, 256)
    fallback = None

    for bx, bz in _spiral_offsets(search_radius):
        lat, lon = coords.block_to_geo(bx, bz)
        elevation = elevation_src.sample(coords, bx, bz)
        cover = landcover_src.sample(coords, bx, bz)
        mean_temp, min_temp, rainfall = climate_src.sample(lat, lon)
        biome = classify_biome(elevation, cover, mean_temp, min_temp, rainfall)
        terrain_y = coords.elevation_to_world_y(elevation, SEA_LEVEL)

        spawn_y = terrain_y + 1
        if fallback is None or spawn_y > fallback[1]:
            fallback = (bx, spawn_y, bz)

        if terrain_y >= SEA_LEVEL and biome not in water_biomes:
            return bx, spawn_y, bz

    if fallback is not None:
        return fallback

    return 0, SEA_LEVEL + 1, 0


def compute_world_seed(lat: float, lon: float, radius_blocks: int, scale: float) -> int:
    """Build a stable positive 63-bit seed from the generation parameters."""
    seed_input = f"{lat:.12f}:{lon:.12f}:{radius_blocks:d}:{scale:.6f}"
    digest = hashlib.blake2b(seed_input.encode("ascii"), digest_size=8).digest()
    seed = int.from_bytes(digest, "big") & ((1 << 63) - 1)
    return seed or 1


def _luanti_world_dirs() -> list[str]:
    """Return known Luanti world directories for common desktop installs."""
    return [
        os.path.expanduser("~/.var/app/org.luanti.luanti/.minetest/worlds"),
        os.path.expanduser("~/.minetest/worlds"),
        os.path.expanduser("~/.luanti/worlds"),
    ]


def _sanitize_world_basename(path: str) -> str:
    """Build a filesystem-safe label from an output path."""
    base = os.path.basename(os.path.normpath(path)) or "world"
    safe = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in base)
    return safe.strip("._") or "world"


def find_luanti_launch_world(output_path: str) -> str | None:
    """Return a Luanti-managed launch path when the output is elsewhere.

    Flatpak Luanti only respected the singlenode world metadata when the world
    lived under its managed `worlds/` directory, so we mirror generated worlds
    there for launching when needed.
    """
    output_abs = os.path.abspath(output_path)
    output_real = os.path.realpath(output_abs)

    for worlds_dir in _luanti_world_dirs():
        if not os.path.isdir(worlds_dir):
            continue

        worlds_abs = os.path.abspath(worlds_dir)
        worlds_real = os.path.realpath(worlds_abs)
        try:
            if os.path.commonpath([output_real, worlds_real]) == worlds_real:
                return None
        except ValueError:
            pass

        label = _sanitize_world_basename(output_abs)
        suffix = hashlib.blake2b(output_abs.encode("utf-8"), digest_size=3).hexdigest()
        return os.path.join(worlds_abs, f"earth2mt_{label}_{suffix}")

    return None


def sync_luanti_launch_world(source_path: str, launch_path: str):
    """Copy the generated world into Luanti's managed worlds directory."""
    if os.path.isdir(launch_path):
        shutil.rmtree(launch_path)

    os.makedirs(launch_path, exist_ok=True)

    for filename in ("world.mt", "map_meta.txt", "map.sqlite"):
        src = os.path.join(source_path, filename)
        if os.path.exists(src):
            shutil.copy2(src, os.path.join(launch_path, filename))

    worldmods_src = os.path.join(source_path, "worldmods")
    if os.path.isdir(worldmods_src):
        shutil.copytree(worldmods_src, os.path.join(launch_path, "worldmods"), dirs_exist_ok=True)


def parse_args():
    parser = argparse.ArgumentParser(
        prog="earth2mt",
        description="Generate Luanti (Mineclonia) worlds from real-world terrain data.",
    )

    location = parser.add_mutually_exclusive_group(required=True)
    location.add_argument(
        "--coords",
        nargs=2,
        type=float,
        metavar=("LAT", "LON"),
        help="Center coordinates (latitude, longitude)",
    )
    location.add_argument(
        "--place",
        type=str,
        help="Place name to geocode (e.g. 'Rome, Italy')",
    )

    parser.add_argument(
        "--radius",
        type=_positive_int,
        default=5000,
        help="Generation radius in Luanti blocks from the center (default: 5000)",
    )
    parser.add_argument(
        "--scale",
        type=float,
        default=1.0,
        help="Meters per block (default: 1.0)",
    )
    parser.add_argument(
        "--output", "-o",
        type=str,
        required=True,
        help="Output world directory path",
    )
    parser.add_argument(
        "--cache-dir",
        type=str,
        default=os.path.expanduser("~/.cache/earth2mt"),
        help="Tile cache directory (default: ~/.cache/earth2mt/)",
    )
    parser.add_argument(
        "--jobs",
        type=_positive_int,
        default=None,
        help="Worker processes for column generation (default: CPU count)",
    )
    parser.add_argument(
        "--progress-interval",
        type=_non_negative_float,
        default=1.0,
        help="Seconds between progress updates (default: 1.0, use 0 for every column)",
    )

    return parser.parse_args()


def reset_output_world(path: str):
    """Remove generated world state that would interfere with regeneration."""
    files_to_remove = (
        "map.sqlite",
        "map.sqlite-shm",
        "map.sqlite-wal",
        "players.sqlite",
        "players.sqlite-journal",
        "auth.sqlite",
        "auth.sqlite-journal",
        "mod_storage.sqlite",
        "mod_storage.sqlite-journal",
        "env_meta.txt",
        "map_meta.txt",
        "force_loaded.txt",
        "ipban.txt",
    )

    for relpath in files_to_remove:
        target = os.path.join(path, relpath)
        if os.path.exists(target):
            os.remove(target)

    earth2mt_mod = os.path.join(path, "worldmods", "__earth2mt")
    if os.path.isdir(earth2mt_mod):
        shutil.rmtree(earth2mt_mod)


def main():
    args = parse_args()

    # Resolve center coordinates
    if args.place:
        from earth2mt.data.geocoder import geocode
        print(f"Geocoding '{args.place}'...")
        result = geocode(args.place)
        if result is None:
            print(f"Error: Could not geocode '{args.place}'", file=sys.stderr)
            sys.exit(1)
        lat, lon = result
        print(f"  -> {lat:.4f}, {lon:.4f}")
    else:
        lat, lon = args.coords

    print(f"Center: {lat:.4f}, {lon:.4f}")
    print(f"Radius: {args.radius} blocks")
    print(f"Scale: {args.scale} m/block")
    print(f"Approximate geographic radius: {(args.radius * args.scale) / 1000.0:.3f} km")
    print(f"Progress interval: {args.progress_interval:.1f}s")
    print(f"Output: {args.output}")

    # Check output path
    if os.path.exists(os.path.join(args.output, "map.sqlite")):
        resp = input("Warning: generated world data already exists at output path. Overwrite? [y/N] ")
        if resp.lower() != "y":
            print("Aborted.")
            sys.exit(0)
        reset_output_world(args.output)

    from earth2mt.terrain.coords import CoordinateTransform
    from earth2mt.data.elevation import ElevationSource
    from earth2mt.data.landcover import LandcoverSource
    from earth2mt.data.climate import ClimateSource
    from earth2mt.data.soil import OrganicCarbonSource, SoilClassSource
    from earth2mt.world.world_setup import create_world
    from earth2mt.world.world_db import WorldDB
    from earth2mt.config import MAP_BLOCK_SIZE

    # Set up coordinate transform
    coords = CoordinateTransform(lat, lon, args.scale)

    # Calculate block bounds
    radius_blocks = args.radius
    min_bx, max_bx, min_bz, max_bz = block_bounds_for_radius(radius_blocks)

    # MapBlock range
    mb_min_x = min_bx // MAP_BLOCK_SIZE
    mb_max_x = max_bx // MAP_BLOCK_SIZE
    mb_min_z = min_bz // MAP_BLOCK_SIZE
    mb_max_z = max_bz // MAP_BLOCK_SIZE

    total_columns = (mb_max_x - mb_min_x + 1) * (mb_max_z - mb_min_z + 1)
    generated_width_blocks = (mb_max_x - mb_min_x + 1) * MAP_BLOCK_SIZE
    generated_depth_blocks = (mb_max_z - mb_min_z + 1) * MAP_BLOCK_SIZE
    jobs = resolve_jobs(args.jobs, total_columns)
    print(f"Generating {total_columns} MapBlock columns "
          f"({mb_max_x - mb_min_x + 1} x {mb_max_z - mb_min_z + 1}) "
          f"covering about {generated_width_blocks} x {generated_depth_blocks} blocks "
          f"using {jobs} worker{'s' if jobs != 1 else ''}...")

    # Initialize data sources
    elevation_src = ElevationSource(args.cache_dir, args.scale)
    landcover_src = LandcoverSource(args.cache_dir, args.scale)
    climate_src = ClimateSource(args.cache_dir)
    organic_carbon_src = OrganicCarbonSource(args.cache_dir, args.scale)
    soil_class_src = SoilClassSource(args.cache_dir, args.scale)

    spawn_x, spawn_y, spawn_z = find_spawn_position(
        radius_blocks,
        coords,
        elevation_src,
        landcover_src,
        climate_src,
    )
    world_seed = compute_world_seed(lat, lon, args.radius, args.scale)
    world_name = _sanitize_world_basename(args.output)
    launch_world = find_luanti_launch_world(args.output)
    print(f"Spawn: ({spawn_x}, {spawn_y}, {spawn_z})")
    print(f"Seed: {world_seed}")
    if launch_world is not None:
        print(f"Luanti launch world: {launch_world}")

    _set_generation_worker_state(
        coords,
        elevation_src,
        landcover_src,
        climate_src,
        organic_carbon_src,
        soil_class_src,
        world_seed,
    )

    # Create world
    create_world(args.output, (spawn_x, spawn_y, spawn_z), world_seed, world_name)

    start_time = time.monotonic()
    last_progress_update = start_time
    done = 0
    columns = _mapblock_columns(mb_min_x, mb_max_x, mb_min_z, mb_max_z)

    def write_generated_columns(generated_columns):
        nonlocal done
        nonlocal last_progress_update
        db = WorldDB(args.output)
        try:
            db.begin()
            batch_count = 0

            for mb_x, mb_z, mapblocks in generated_columns:
                for mb_y, data in mapblocks:
                    db.save_block(mb_x, mb_y, mb_z, data)
                    batch_count += 1

                    if batch_count >= 1000:
                        db.end()
                        db.begin()
                        batch_count = 0

                done += 1
                now = time.monotonic()
                if _should_print_progress(
                    done,
                    total_columns,
                    last_progress_update,
                    now,
                    args.progress_interval,
                ):
                    _print_progress(done, total_columns, start_time, now=now)
                    last_progress_update = now

            db.end()
        finally:
            db.close()

    try:
        if jobs == 1:
            write_generated_columns(_generate_serialized_column(column) for column in columns)
        else:
            with ProcessPoolExecutor(
                max_workers=jobs,
                mp_context=_preferred_mp_context(),
                initializer=_init_generation_worker,
                initargs=(args.cache_dir, lat, lon, args.scale, world_seed),
            ) as executor:
                write_generated_columns(
                    _iter_parallel_generated_columns(executor, columns, jobs)
                )
    finally:
        _clear_generation_worker_state()

    if launch_world is not None:
        sync_luanti_launch_world(args.output, launch_world)

    elapsed = time.monotonic() - start_time
    print(f"\nDone in {elapsed:.1f}s. World saved to: {args.output}")
    if launch_world is not None:
        print(f"Open this world in Luanti: {launch_world}")


if __name__ == "__main__":
    main()
