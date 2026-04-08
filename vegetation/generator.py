"""Deterministic biome-matched vegetation and small-tree placement."""

from __future__ import annotations

from hashlib import blake2b

from earth2mt.config import (
    COARSE_DIRT,
    DIRT,
    GRASS_BLOCK,
    GRASS_BLOCK_SNOW,
    MAP_BLOCK_SIZE,
    PODZOL,
    PODZOL_SNOW,
    RED_SAND,
    SAND,
)

TREE_GROUND_NODES = frozenset({
    DIRT,
    COARSE_DIRT,
    GRASS_BLOCK,
    GRASS_BLOCK_SNOW,
    PODZOL,
    PODZOL_SNOW,
})

REEDS_GROUND_NODES = frozenset({
    DIRT,
    COARSE_DIRT,
    GRASS_BLOCK,
    PODZOL,
    SAND,
    RED_SAND,
})

SANDY_GROUND_NODES = frozenset({
    SAND,
    RED_SAND,
})

TREE_SPECIES = {
    "oak": ("mcl_trees:tree_oak", "mcl_trees:leaves_oak"),
    "birch": ("mcl_trees:tree_birch", "mcl_trees:leaves_birch"),
    "spruce": ("mcl_trees:tree_spruce", "mcl_trees:leaves_spruce"),
    "jungle": ("mcl_trees:tree_jungle", "mcl_trees:leaves_jungle"),
    "acacia": ("mcl_trees:tree_acacia", "mcl_trees:leaves_acacia"),
    "dark_oak": ("mcl_trees:tree_dark_oak", "mcl_trees:leaves_dark_oak"),
    "mangrove": ("mcl_trees:tree_mangrove", "mcl_trees:leaves_mangrove"),
}

TREE_PROFILES = {
    "Plains": {"chance": 0.006, "species": "oak", "style": "round", "margin": 3},
    "Forest": {"chance": 0.035, "species": "oak", "style": "round", "margin": 3},
    "BirchForest": {"chance": 0.04, "species": "birch", "style": "round", "margin": 3},
    "DarkForest": {"chance": 0.05, "species": "dark_oak", "style": "wide", "margin": 4},
    "Taiga": {"chance": 0.04, "species": "spruce", "style": "spruce", "margin": 3},
    "SnowyTaiga": {"chance": 0.03, "species": "spruce", "style": "spruce", "margin": 3},
    "Jungle": {"chance": 0.045, "species": "jungle", "style": "jungle", "margin": 3},
    "SparseJungle": {"chance": 0.02, "species": "jungle", "style": "jungle", "margin": 3},
    "Savannah": {"chance": 0.018, "species": "acacia", "style": "acacia", "margin": 4},
    "Swamp": {"chance": 0.018, "species": "oak", "style": "swamp", "margin": 3},
    "MangroveSwamp": {"chance": 0.02, "species": "mangrove", "style": "mangrove", "margin": 4},
    "WoodedMesa": {"chance": 0.01, "species": "oak", "style": "round", "margin": 3},
}

LIGHT_TRANSPARENT_VEGETATION_NODES = frozenset({
    "mcl_core:cactus",
    "mcl_core:deadbush",
    "mcl_core:reeds",
    "mcl_core:vine",
    "mcl_trees:leaves_acacia",
    "mcl_trees:leaves_birch",
    "mcl_trees:leaves_dark_oak",
    "mcl_trees:leaves_jungle",
    "mcl_trees:leaves_mangrove",
    "mcl_trees:leaves_oak",
    "mcl_trees:leaves_spruce",
})

LIGHT_TRANSPARENT_VEGETATION_PREFIXES = ("mcl_flowers:",)

_ORTHOGONAL_NEIGHBORS = ((1, 0), (-1, 0), (0, 1), (0, -1))
_COMMON_FLOWERS = (
    "mcl_flowers:dandelion",
    "mcl_flowers:poppy",
    "mcl_flowers:azure_bluet",
    "mcl_flowers:oxeye_daisy",
    "mcl_flowers:cornflower",
)


class _PlacementBuffer:
    __slots__ = ("nodes", "max_y")

    def __init__(self):
        self.nodes: dict[tuple[int, int, int], tuple[str, int]] = {}
        self.max_y = -1_000_000

    def occupied(self, x: int, y: int, z: int) -> bool:
        return (x, y, z) in self.nodes

    def set(self, x: int, y: int, z: int, node_name: str, param2: int = 0) -> bool:
        if not (0 <= x < MAP_BLOCK_SIZE and 0 <= z < MAP_BLOCK_SIZE):
            return False
        self.nodes[(x, y, z)] = (node_name, param2)
        if y > self.max_y:
            self.max_y = y
        return True

    def set_if_empty(self, x: int, y: int, z: int, node_name: str, param2: int = 0) -> bool:
        if self.occupied(x, y, z):
            return False
        return self.set(x, y, z, node_name, param2)


def generate_vegetation_column(
    base_bx: int,
    base_bz: int,
    heights,
    snow_cover,
    soil_profiles,
    biome_names: list[list[str]],
    grass_palette_indices,
    leaves_palette_indices,
    water_level: int,
    world_seed: int,
) -> tuple[dict[tuple[int, int, int], tuple[str, int]], int]:
    """Place deterministic biome vegetation inside one 16x16 mapblock column."""
    placement = _PlacementBuffer()

    for dz in range(MAP_BLOCK_SIZE):
        for dx in range(MAP_BLOCK_SIZE):
            _place_tree(
                placement,
                base_bx,
                base_bz,
                dx,
                dz,
                heights,
                soil_profiles,
                biome_names,
                leaves_palette_indices,
                water_level,
                world_seed,
            )

    for dz in range(MAP_BLOCK_SIZE):
        for dx in range(MAP_BLOCK_SIZE):
            _place_ground_cover(
                placement,
                base_bx,
                base_bz,
                dx,
                dz,
                heights,
                snow_cover,
                soil_profiles,
                biome_names,
                grass_palette_indices,
                water_level,
                world_seed,
            )

    return placement.nodes, placement.max_y


def is_light_transparent_vegetation(node_name: str) -> bool:
    return (
        node_name in LIGHT_TRANSPARENT_VEGETATION_NODES
        or node_name.startswith(LIGHT_TRANSPARENT_VEGETATION_PREFIXES)
    )


def _place_tree(
    placement: _PlacementBuffer,
    base_bx: int,
    base_bz: int,
    dx: int,
    dz: int,
    heights,
    soil_profiles,
    biome_names: list[list[str]],
    leaves_palette_indices,
    water_level: int,
    world_seed: int,
):
    biome_name = biome_names[dz][dx]
    profile = TREE_PROFILES.get(biome_name)
    if profile is None:
        return

    margin = int(profile["margin"])
    if dx < margin or dz < margin or dx >= MAP_BLOCK_SIZE - margin or dz >= MAP_BLOCK_SIZE - margin:
        return

    soil_profile = soil_profiles[dz][dx]
    if not soil_profile:
        return

    surface_block = soil_profile[0]
    if surface_block not in TREE_GROUND_NODES:
        return

    terrain_h = int(heights[dz, dx])
    if terrain_h < water_level and biome_name != "MangroveSwamp":
        return

    surface_y = terrain_h + 1
    world_x = base_bx + dx
    world_z = base_bz + dz
    if _rand_float(world_seed, world_x, world_z, f"{biome_name}:tree") >= float(profile["chance"]):
        return

    trunk_name, leaves_name = TREE_SPECIES[str(profile["species"])]
    leaves_param2 = 32 + int(leaves_palette_indices[dz, dx])
    style = str(profile["style"])

    if style == "round":
        _grow_round_tree(
            placement,
            dx,
            surface_y,
            dz,
            trunk_name,
            leaves_name,
            leaves_param2,
            _rand_int(world_seed, world_x, world_z, "round:height", 4, 5),
        )
    elif style == "wide":
        _grow_wide_tree(
            placement,
            dx,
            surface_y,
            dz,
            trunk_name,
            leaves_name,
            leaves_param2,
            _rand_int(world_seed, world_x, world_z, "wide:height", 5, 6),
        )
    elif style == "spruce":
        _grow_spruce_tree(
            placement,
            dx,
            surface_y,
            dz,
            trunk_name,
            leaves_name,
            leaves_param2,
            _rand_int(world_seed, world_x, world_z, "spruce:height", 6, 7),
        )
    elif style == "jungle":
        _grow_jungle_tree(
            placement,
            dx,
            surface_y,
            dz,
            trunk_name,
            leaves_name,
            leaves_param2,
            _rand_int(world_seed, world_x, world_z, "jungle:height", 6, 8),
            world_seed,
            world_x,
            world_z,
        )
    elif style == "acacia":
        _grow_acacia_tree(
            placement,
            dx,
            surface_y,
            dz,
            trunk_name,
            leaves_name,
            leaves_param2,
            _rand_int(world_seed, world_x, world_z, "acacia:height", 4, 5),
            _choice(world_seed, world_x, world_z, "acacia:dir", _ORTHOGONAL_NEIGHBORS),
        )
    elif style == "swamp":
        _grow_swamp_tree(
            placement,
            dx,
            surface_y,
            dz,
            trunk_name,
            leaves_name,
            leaves_param2,
            _rand_int(world_seed, world_x, world_z, "swamp:height", 4, 5),
        )
    elif style == "mangrove":
        _grow_mangrove_tree(
            placement,
            dx,
            surface_y,
            dz,
            trunk_name,
            leaves_name,
            leaves_param2,
            _rand_int(world_seed, world_x, world_z, "mangrove:height", 5, 6),
        )


def _place_ground_cover(
    placement: _PlacementBuffer,
    base_bx: int,
    base_bz: int,
    dx: int,
    dz: int,
    heights,
    snow_cover,
    soil_profiles,
    biome_names: list[list[str]],
    grass_palette_indices,
    water_level: int,
    world_seed: int,
):
    soil_profile = soil_profiles[dz][dx]
    if not soil_profile:
        return

    biome_name = biome_names[dz][dx]
    terrain_h = int(heights[dz, dx])
    surface_y = terrain_h + 1
    surface_block = soil_profile[0]
    world_x = base_bx + dx
    world_z = base_bz + dz
    grass_param2 = int(grass_palette_indices[dz, dx])

    if terrain_h < water_level:
        if biome_name in {"River", "Swamp", "MangroveSwamp"}:
            if _rand_float(world_seed, world_x, world_z, "waterlily") < 0.12:
                placement.set_if_empty(
                    dx,
                    water_level + 1,
                    dz,
                    "mcl_flowers:waterlily",
                    _rand_int(world_seed, world_x, world_z, "waterlily:rot", 0, 3),
                )
        return

    if placement.occupied(dx, surface_y, dz):
        return

    adjacent_water = _has_adjacent_water(dx, dz, heights, water_level, surface_y)

    if surface_block in REEDS_GROUND_NODES and adjacent_water and not snow_cover[dz, dx]:
        reeds_chance = 0.0
        if biome_name in {"Swamp", "MangroveSwamp", "River"}:
            reeds_chance = 0.16
        elif biome_name in {"Beach", "Desert", "Mesa", "WoodedMesa"}:
            reeds_chance = 0.08
        if reeds_chance and _rand_float(world_seed, world_x, world_z, "reeds") < reeds_chance:
            _place_column(
                placement,
                dx,
                surface_y,
                dz,
                "mcl_core:reeds",
                _rand_int(world_seed, world_x, world_z, "reeds:height", 2, 4),
                grass_param2,
            )
            return

    if biome_name in {"Desert", "Mesa", "WoodedMesa"} and surface_block in SANDY_GROUND_NODES:
        dry_roll = _rand_float(world_seed, world_x, world_z, "dry")
        if dry_roll < 0.08:
            _place_column(
                placement,
                dx,
                surface_y,
                dz,
                "mcl_core:cactus",
                _rand_int(world_seed, world_x, world_z, "cactus:height", 2, 3),
            )
            return
        if dry_roll < 0.18:
            placement.set_if_empty(dx, surface_y, dz, "mcl_core:deadbush")
            return

    if snow_cover[dz, dx]:
        return

    flora_roll = _rand_float(world_seed, world_x, world_z, f"{biome_name}:flora")

    if biome_name == "Plains":
        if flora_roll < 0.22:
            _place_grass_flora(placement, dx, surface_y, dz, grass_param2, flora_roll, "plains")
        elif flora_roll < 0.26:
            placement.set_if_empty(dx, surface_y, dz, _choice(world_seed, world_x, world_z, "plains:flower", _COMMON_FLOWERS))
    elif biome_name in {"Forest", "BirchForest"}:
        if flora_roll < 0.18:
            _place_grass_flora(placement, dx, surface_y, dz, grass_param2, flora_roll, biome_name)
        elif flora_roll < 0.22:
            placement.set_if_empty(dx, surface_y, dz, _choice(world_seed, world_x, world_z, "forest:flower", _COMMON_FLOWERS))
    elif biome_name == "DarkForest":
        if flora_roll < 0.16:
            _place_fern_flora(placement, dx, surface_y, dz, grass_param2, flora_roll)
    elif biome_name in {"Taiga", "SnowyTaiga"}:
        if flora_roll < 0.18:
            _place_fern_flora(placement, dx, surface_y, dz, grass_param2, flora_roll)
    elif biome_name in {"Jungle", "SparseJungle"}:
        if flora_roll < 0.26:
            if flora_roll < 0.16:
                _place_fern_flora(placement, dx, surface_y, dz, grass_param2, flora_roll)
            else:
                _place_grass_flora(placement, dx, surface_y, dz, grass_param2, flora_roll, biome_name)
    elif biome_name == "Savannah":
        if flora_roll < 0.18:
            _place_grass_flora(placement, dx, surface_y, dz, grass_param2, flora_roll, biome_name)
        elif flora_roll < 0.26:
            placement.set_if_empty(dx, surface_y, dz, "mcl_core:deadbush")
    elif biome_name == "Swamp":
        if flora_roll < 0.12:
            placement.set_if_empty(dx, surface_y, dz, "mcl_flowers:blue_orchid")
        elif flora_roll < 0.22:
            _place_grass_flora(placement, dx, surface_y, dz, grass_param2, flora_roll, biome_name)
    elif biome_name == "MangroveSwamp":
        if flora_roll < 0.12:
            _place_fern_flora(placement, dx, surface_y, dz, grass_param2, flora_roll)
        elif flora_roll < 0.2:
            _place_grass_flora(placement, dx, surface_y, dz, grass_param2, flora_roll, biome_name)


def _place_grass_flora(
    placement: _PlacementBuffer,
    x: int,
    y: int,
    z: int,
    grass_param2: int,
    flora_roll: float,
    salt: str,
):
    if flora_roll < 0.06:
        _place_double_plant(
            placement,
            x,
            y,
            z,
            "mcl_flowers:double_grass",
            "mcl_flowers:double_grass_top",
            grass_param2,
        )
        return
    placement.set_if_empty(x, y, z, "mcl_flowers:tallgrass", grass_param2)


def _place_fern_flora(
    placement: _PlacementBuffer,
    x: int,
    y: int,
    z: int,
    grass_param2: int,
    flora_roll: float,
):
    if flora_roll < 0.06:
        _place_double_plant(
            placement,
            x,
            y,
            z,
            "mcl_flowers:double_fern",
            "mcl_flowers:double_fern_top",
            grass_param2,
        )
        return
    placement.set_if_empty(x, y, z, "mcl_flowers:fern", grass_param2)


def _place_double_plant(
    placement: _PlacementBuffer,
    x: int,
    y: int,
    z: int,
    bottom_name: str,
    top_name: str,
    param2: int,
):
    if placement.occupied(x, y, z) or placement.occupied(x, y + 1, z):
        return
    if placement.set_if_empty(x, y, z, bottom_name, param2):
        placement.set_if_empty(x, y + 1, z, top_name, param2)


def _place_column(
    placement: _PlacementBuffer,
    x: int,
    y: int,
    z: int,
    node_name: str,
    height: int,
    param2: int = 0,
):
    for dy in range(height):
        placement.set_if_empty(x, y + dy, z, node_name, param2)


def _grow_round_tree(
    placement: _PlacementBuffer,
    x: int,
    y: int,
    z: int,
    trunk_name: str,
    leaves_name: str,
    leaves_param2: int,
    height: int,
):
    for dy in range(height):
        placement.set(x, y + dy, z, trunk_name)

    top_y = y + height - 1
    _place_leaf_disc(placement, x, top_y - 1, z, 2, leaves_name, leaves_param2)
    _place_leaf_disc(placement, x, top_y, z, 2, leaves_name, leaves_param2)
    _place_leaf_disc(placement, x, top_y + 1, z, 1, leaves_name, leaves_param2)
    placement.set_if_empty(x, top_y + 2, z, leaves_name, leaves_param2)


def _grow_wide_tree(
    placement: _PlacementBuffer,
    x: int,
    y: int,
    z: int,
    trunk_name: str,
    leaves_name: str,
    leaves_param2: int,
    height: int,
):
    for dy in range(height):
        placement.set(x, y + dy, z, trunk_name)

    top_y = y + height - 1
    _place_leaf_disc(placement, x, top_y - 1, z, 2, leaves_name, leaves_param2)
    _place_leaf_disc(placement, x, top_y, z, 3, leaves_name, leaves_param2)
    _place_leaf_disc(placement, x, top_y + 1, z, 2, leaves_name, leaves_param2)
    placement.set_if_empty(x, top_y + 2, z, leaves_name, leaves_param2)


def _grow_spruce_tree(
    placement: _PlacementBuffer,
    x: int,
    y: int,
    z: int,
    trunk_name: str,
    leaves_name: str,
    leaves_param2: int,
    height: int,
):
    for dy in range(height):
        placement.set(x, y + dy, z, trunk_name)

    canopy_base = y + height - 4
    _place_leaf_disc(placement, x, canopy_base, z, 2, leaves_name, leaves_param2)
    _place_leaf_disc(placement, x, canopy_base + 1, z, 1, leaves_name, leaves_param2)
    _place_leaf_disc(placement, x, canopy_base + 2, z, 2, leaves_name, leaves_param2)
    _place_leaf_disc(placement, x, canopy_base + 3, z, 1, leaves_name, leaves_param2)
    placement.set_if_empty(x, canopy_base + 4, z, leaves_name, leaves_param2)


def _grow_jungle_tree(
    placement: _PlacementBuffer,
    x: int,
    y: int,
    z: int,
    trunk_name: str,
    leaves_name: str,
    leaves_param2: int,
    height: int,
    world_seed: int,
    world_x: int,
    world_z: int,
):
    for dy in range(height):
        placement.set(x, y + dy, z, trunk_name)

    top_y = y + height - 1
    _place_leaf_disc(placement, x, top_y, z, 2, leaves_name, leaves_param2)
    _place_leaf_disc(placement, x, top_y + 1, z, 2, leaves_name, leaves_param2)
    placement.set_if_empty(x, top_y + 2, z, leaves_name, leaves_param2)

    for branch_index, (off_x, off_z) in enumerate(_ORTHOGONAL_NEIGHBORS[:2]):
        branch_y = top_y - branch_index - 1
        if _rand_float(world_seed, world_x, world_z, f"jungle:branch:{branch_index}") < 0.5:
            _place_leaf_disc(
                placement,
                x + off_x * 2,
                branch_y,
                z + off_z * 2,
                1,
                leaves_name,
                leaves_param2,
            )


def _grow_acacia_tree(
    placement: _PlacementBuffer,
    x: int,
    y: int,
    z: int,
    trunk_name: str,
    leaves_name: str,
    leaves_param2: int,
    height: int,
    direction: tuple[int, int],
):
    dir_x, dir_z = direction
    for dy in range(height):
        placement.set(x, y + dy, z, trunk_name)

    branch_y = y + height - 1
    branch_x = x + dir_x
    branch_z = z + dir_z
    crown_x = x + dir_x * 2
    crown_z = z + dir_z * 2

    placement.set(branch_x, branch_y, branch_z, trunk_name)
    placement.set(crown_x, branch_y + 1, crown_z, trunk_name)

    _place_leaf_disc(placement, crown_x, branch_y + 1, crown_z, 2, leaves_name, leaves_param2)
    _place_leaf_disc(placement, crown_x, branch_y + 2, crown_z, 1, leaves_name, leaves_param2)
    _place_leaf_disc(placement, x, branch_y, z, 1, leaves_name, leaves_param2)


def _grow_swamp_tree(
    placement: _PlacementBuffer,
    x: int,
    y: int,
    z: int,
    trunk_name: str,
    leaves_name: str,
    leaves_param2: int,
    height: int,
):
    for dy in range(height):
        placement.set(x, y + dy, z, trunk_name)

    top_y = y + height - 1
    _place_leaf_disc(placement, x, top_y - 1, z, 2, leaves_name, leaves_param2)
    _place_leaf_disc(placement, x, top_y, z, 2, leaves_name, leaves_param2)
    _place_leaf_disc(placement, x, top_y + 1, z, 1, leaves_name, leaves_param2)


def _grow_mangrove_tree(
    placement: _PlacementBuffer,
    x: int,
    y: int,
    z: int,
    trunk_name: str,
    leaves_name: str,
    leaves_param2: int,
    height: int,
):
    for off_x, off_z in _ORTHOGONAL_NEIGHBORS:
        placement.set_if_empty(x + off_x, y, z + off_z, "mcl_mangrove:mangrove_roots")

    for dy in range(height):
        placement.set(x, y + dy, z, trunk_name)

    top_y = y + height - 1
    _place_leaf_disc(placement, x, top_y - 1, z, 2, leaves_name, leaves_param2)
    _place_leaf_disc(placement, x, top_y, z, 2, leaves_name, leaves_param2)
    _place_leaf_disc(placement, x, top_y + 1, z, 1, leaves_name, leaves_param2)
    placement.set_if_empty(x, top_y + 2, z, leaves_name, leaves_param2)


def _place_leaf_disc(
    placement: _PlacementBuffer,
    center_x: int,
    y: int,
    center_z: int,
    radius: int,
    leaves_name: str,
    leaves_param2: int,
):
    for off_z in range(-radius, radius + 1):
        for off_x in range(-radius, radius + 1):
            if max(abs(off_x), abs(off_z)) > radius:
                continue
            if radius > 1 and abs(off_x) == radius and abs(off_z) == radius:
                continue
            placement.set_if_empty(center_x + off_x, y, center_z + off_z, leaves_name, leaves_param2)


def _has_adjacent_water(dx: int, dz: int, heights, water_level: int, surface_y: int) -> bool:
    for off_x, off_z in _ORTHOGONAL_NEIGHBORS:
        test_x = dx + off_x
        test_z = dz + off_z
        if not (0 <= test_x < MAP_BLOCK_SIZE and 0 <= test_z < MAP_BLOCK_SIZE):
            continue
        if int(heights[test_z, test_x]) < surface_y <= water_level:
            return True
    return False


def _choice(world_seed: int, world_x: int, world_z: int, salt: str, values):
    return values[_hash_value(world_seed, world_x, world_z, salt) % len(values)]


def _rand_int(world_seed: int, world_x: int, world_z: int, salt: str, low: int, high: int) -> int:
    return low + (_hash_value(world_seed, world_x, world_z, salt) % (high - low + 1))


def _rand_float(world_seed: int, world_x: int, world_z: int, salt: str) -> float:
    return _hash_value(world_seed, world_x, world_z, salt) / float(2**64)


def _hash_value(world_seed: int, world_x: int, world_z: int, salt: str) -> int:
    digest = blake2b(
        f"{world_seed}|{world_x}|{world_z}|{salt}".encode("ascii"),
        digest_size=8,
    ).digest()
    return int.from_bytes(digest, "big")
