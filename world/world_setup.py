"""Create the Luanti world directory structure for Mineclonia."""

import os

from earth2mt.terrain.mineclonia_biome import DEFAULT_MINECLONIA_BIOME, MINECLONIA_BIOME_IDS


def _write_map_meta(path: str, seed: int):
    """Write the minimum map metadata needed to force singlenode worlds."""
    with open(os.path.join(path, "map_meta.txt"), "w") as f:
        f.write(f"seed = {seed}\n")
        f.write("mg_name = singlenode\n")
        f.write("water_level = 1\n")
        f.write("mcl_singlenode_mapgen = false\n")
        f.write("[end_of_params]\n")


def _biome_assignments_lua() -> str:
    lines = ["local earth2mt_biome_assignments = {\n"]
    for biome_name, biome_id in MINECLONIA_BIOME_IDS.items():
        lines.append(f'\t["{biome_name}"] = {biome_id},\n')
    lines.append("}\n")
    return "".join(lines)


def _spawn_overrides_lua(spawn_pos: tuple[int, int, int] | None) -> str:
    if spawn_pos is None:
        return ""

    x, y, z = spawn_pos
    spawn_y = y - 0.5
    return "\n".join((
        f"local earth2mt_spawn = vector.new({x}, {spawn_y}, {z})",
        "",
        "local function earth2mt_spawn_pos()",
        "\treturn vector.new(earth2mt_spawn.x, earth2mt_spawn.y, earth2mt_spawn.z)",
        "end",
        "",
        "local function earth2mt_place_player(player)",
        "\tif not player or not player:is_player() then",
        "\t\treturn",
        "\tend",
        "\tlocal pos = earth2mt_spawn_pos()",
        "\tminetest.load_area(vector.offset(pos, -1, -1, -1), vector.offset(pos, 1, 2, 1))",
        "\tplayer:set_pos(pos)",
        "end",
        "",
        "if mcl_biome_dispatch then",
        "\tmcl_biome_dispatch.get_spawn_point_2d = earth2mt_spawn_pos",
        "\tmcl_biome_dispatch.next_respawn_position = function(_)",
        "\t\treturn earth2mt_spawn_pos()",
        "\tend",
        "end",
        "",
        "if mcl_spawn then",
        "\tlocal original_spawn = mcl_spawn.spawn",
        "\tmcl_spawn.get_world_spawn_pos = function(_)",
        "\t\treturn earth2mt_spawn_pos(), false",
        "\tend",
        "\tmcl_spawn.spawn = function(player)",
        "\t\tif player:get_meta():get_string(\"mcl_beds:spawn\") ~= \"\" then",
        "\t\t\treturn original_spawn(player)",
        "\t\tend",
        "\t\tearth2mt_place_player(player)",
        "\t\treturn true",
        "\tend",
        "else",
        "\tminetest.register_on_newplayer(earth2mt_place_player)",
        "\tminetest.register_on_respawnplayer(function(player)",
        "\t\tearth2mt_place_player(player)",
        "\t\treturn true",
        "\tend)",
        "end",
        "",
    ))


def _worldmod_init_lua(spawn_pos: tuple[int, int, int] | None) -> str:
    lines = [
        "-- earth2mt world overrides: keep Mineclonia from regenerating terrain and",
        "-- read stored biome metadata from generated mapblocks.",
        'local earth2mt_disabled_generators = {',
        '\t"world_structure",',
        '\t"end_fixes",',
        '\t"set_param2_nodes",',
        '\t"structures",',
        '\t"villages",',
        '\t"end_island",',
        '\t"railcorridors",',
        '\t"dungeons",',
        '\t"chorus_grow",',
        "}",
        "",
        _biome_assignments_lua().rstrip("\n"),
        'local earth2mt_biome_meta_key = "mcl_levelgen:biome_index"',
        f'local earth2mt_default_biome = "{DEFAULT_MINECLONIA_BIOME}"',
        "local earth2mt_floor = math.floor",
        "local earth2mt_pairs = pairs",
        "local earth2mt_string_byte = string.byte",
        "local earth2mt_tostring = tostring",
        "local earth2mt_vector_new = vector.new",
        "",
        "local earth2mt_marshaled_id_to_name_map",
        "local earth2mt_marshaled_biomes",
        "",
        "local function earth2mt_noop(...)",
        "\treturn nil",
        "end",
        "",
        "local function earth2mt_biome_type(biome_name, def)",
        "\tif not def then",
        '\t\treturn "normal"',
        "\tend",
        "\tlocal temperature = def.temperature or 1.0",
        '\tif biome_name == "FrozenOcean"',
        '\t\tor biome_name == "DeepFrozenOcean"',
        '\t\tor biome_name == "FrozenRiver"',
        '\t\tor biome_name == "SnowyBeach"',
        '\t\tor biome_name == "SnowyPlains"',
        '\t\tor biome_name == "SnowyTaiga"',
        "\t\tor temperature <= 0.15 then",
        '\t\treturn "snowy"',
        "\tend",
        "\tif def.has_precipitation == false and temperature >= 1.5 then",
        '\t\treturn "hot"',
        "\tend",
        "\tif temperature < 0.8 then",
        '\t\treturn "cold"',
        "\tend",
        '\treturn "normal"',
        "end",
        "",
        "local function earth2mt_get_biome_def(biome_name)",
        "\treturn mcl_levelgen",
        "\t\tand mcl_levelgen.registered_biomes",
        "\t\tand mcl_levelgen.registered_biomes[biome_name]",
        "\t\tor nil",
        "end",
        "",
        "local function earth2mt_get_biome_meta_string(bx, by, bz)",
        "\tlocal origin = earth2mt_vector_new(bx * 16, by * 16, bz * 16)",
        '\tlocal meta = minetest.get_meta(origin):get_string(earth2mt_biome_meta_key)',
        '\tif meta == "" then',
        "\t\treturn nil",
        "\tend",
        "\treturn meta",
        "end",
        "",
        "local function earth2mt_get_block_coords(pos)",
        "\tlocal x = earth2mt_floor((pos.x or 0) + 0.5)",
        "\tlocal y = earth2mt_floor((pos.y or 0) + 0.5)",
        "\tlocal z = earth2mt_floor((pos.z or 0) + 0.5)",
        "\tlocal bx = earth2mt_floor(x / 16)",
        "\tlocal by = earth2mt_floor(y / 16)",
        "\tlocal bz = earth2mt_floor(z / 16)",
        "\treturn bx, by, bz, x - bx * 16, y - by * 16, z - bz * 16",
        "end",
        "",
        "local function earth2mt_decode_biome_name(meta, qx, qy, qz)",
        "\tif mcl_levelgen and mcl_levelgen.index_biome_list then",
        "\t\treturn mcl_levelgen.index_biome_list(meta, qx, qy, qz)",
        "\tend",
        "\tlocal idx = qx * 16 + qy * 4 + qz + 1",
        "\tlocal i = 1",
        "\twhile i <= #meta do",
        "\t\tidx = idx - earth2mt_string_byte(meta, i)",
        "\t\tif idx <= 0 then",
        "\t\t\tlocal biome_id = earth2mt_string_byte(meta, i + 1)",
        "\t\t\tif mcl_levelgen and mcl_levelgen.biome_id_to_name_map then",
        "\t\t\t\treturn mcl_levelgen.biome_id_to_name_map[biome_id] or earth2mt_default_biome",
        "\t\t\tend",
        "\t\t\treturn earth2mt_default_biome",
        "\t\tend",
        "\t\ti = i + 2",
        "\tend",
        "\treturn earth2mt_default_biome",
        "end",
        "",
        "local function earth2mt_biome_name_from_pos(pos, allow_default)",
        "\tlocal bx, by, bz, lx, ly, lz = earth2mt_get_block_coords(pos)",
        "\tlocal meta = earth2mt_get_biome_meta_string(bx, by, bz)",
        "\tif not meta then",
        "\t\treturn allow_default and earth2mt_default_biome or nil",
        "\tend",
        "\treturn earth2mt_decode_biome_name(",
        "\t\tmeta,",
        "\t\tearth2mt_floor(lx / 4),",
        "\t\tearth2mt_floor(ly / 4),",
        "\t\tearth2mt_floor(lz / 4)",
        "\t)",
        "end",
        "",
        "local function earth2mt_biome_def_from_pos(pos, allow_default)",
        "\tlocal biome_name = earth2mt_biome_name_from_pos(pos, allow_default)",
        "\tif not biome_name then",
        "\t\treturn nil, nil",
        "\tend",
        "\treturn earth2mt_get_biome_def(biome_name), biome_name",
        "end",
        "",
        "minetest.register_on_mods_loaded(function()",
        '\tminetest.log("action", "[__earth2mt] Locking world to pre-generated terrain")',
        "\tif mcl_mapgen_core and mcl_mapgen_core.unregister_generator then",
        "\t\tfor _, id in ipairs(earth2mt_disabled_generators) do",
        "\t\t\tmcl_mapgen_core.unregister_generator(id)",
        "\t\tend",
        "\tend",
        "\tif minetest.clear_registered_decorations then",
        "\t\tminetest.clear_registered_decorations()",
        "\tend",
        "\tif minetest.clear_registered_schematics then",
        "\t\tminetest.clear_registered_schematics()",
        "\tend",
        "\tif minetest.clear_registered_ores then",
        "\t\tminetest.clear_registered_ores()",
        "\tend",
        "\tif minetest.generate_decorations then",
        "\t\tminetest.generate_decorations = earth2mt_noop",
        "\tend",
        "\tif minetest.generate_ores then",
        "\t\tminetest.generate_ores = earth2mt_noop",
        "\tend",
        "",
        "\tif mcl_levelgen and mcl_levelgen.assign_biome_ids then",
        "\t\tmcl_levelgen.assign_biome_ids(earth2mt_biome_assignments)",
        "\tend",
        "",
        "\tif mcl_biome_dispatch then",
        "\t\tmcl_biome_dispatch.get_biome_name = function(pos)",
        "\t\t\treturn earth2mt_biome_name_from_pos(pos, true)",
        "\t\tend",
        "\t\tmcl_biome_dispatch.get_biome_name_nosample = function(pos)",
        "\t\t\treturn earth2mt_biome_name_from_pos(pos, false)",
        "\t\tend",
        "\t\tmcl_biome_dispatch.is_position_cold = function(biome_name, pos)",
        "\t\t\tlocal def = biome_name and earth2mt_get_biome_def(biome_name) or nil",
        "\t\t\tif not def and pos then",
        "\t\t\t\tdef, biome_name = earth2mt_biome_def_from_pos(pos, false)",
        "\t\t\tend",
        '\t\t\treturn earth2mt_biome_type(biome_name, def) == "snowy"',
        "\t\tend",
        "\t\tmcl_biome_dispatch.is_position_arid = function(biome_name)",
        "\t\t\tlocal def = biome_name and earth2mt_get_biome_def(biome_name) or nil",
        "\t\t\treturn def and def.has_precipitation == false or false",
        "\t\tend",
        "\t\tmcl_biome_dispatch.get_sky_color = function(pos)",
        "\t\t\tlocal def = select(1, earth2mt_biome_def_from_pos(pos, false))",
        "\t\t\treturn def and def.sky_color or false",
        "\t\tend",
        "\t\tmcl_biome_dispatch.get_fog_color = function(pos)",
        "\t\t\tlocal def = select(1, earth2mt_biome_def_from_pos(pos, false))",
        "\t\t\treturn def and def.fog_color or false",
        "\t\tend",
        "\t\tmcl_biome_dispatch.get_sky_and_fog_colors = function(pos)",
        "\t\t\tlocal def = select(1, earth2mt_biome_def_from_pos(pos, false))",
        "\t\t\tif def then",
        "\t\t\t\treturn def.sky_color, def.fog_color",
        "\t\t\tend",
        "\t\t\treturn false",
        "\t\tend",
        "\t\tmcl_biome_dispatch.get_temperature_in_biome = function(biome_name, pos)",
        "\t\t\tif biome_name then",
        "\t\t\t\tlocal def = earth2mt_get_biome_def(biome_name)",
        "\t\t\t\treturn def and def.temperature or 1.0",
        "\t\t\tend",
        "\t\t\tlocal def = select(1, earth2mt_biome_def_from_pos(pos, false))",
        "\t\t\treturn def and def.temperature or 1.0",
        "\t\tend",
        "\tend",
        "",
        "\tif mcl_core then",
        "\t\tmcl_core.get_grass_palette_index = function(pos)",
        "\t\t\tlocal def = select(1, earth2mt_biome_def_from_pos(pos, true))",
        "\t\t\treturn def and def.grass_palette_index or 0",
        "\t\tend",
        "\tend",
        "",
        "\tif mcl_util then",
        "\t\tmcl_util.get_pos_p2 = function(pos, for_trees)",
        "\t\t\tlocal def = select(1, earth2mt_biome_def_from_pos(pos, true))",
        "\t\t\tif not def then",
        "\t\t\t\treturn 0",
        "\t\t\tend",
        "\t\t\tif for_trees then",
        "\t\t\t\treturn def.leaves_palette_index or def.grass_palette_index or 0",
        "\t\t\tend",
        "\t\t\treturn def.grass_palette_index or 0",
        "\t\tend",
        "\tend",
        "",
        "\tif mcl_serverplayer then",
        "\t\tmcl_serverplayer.get_engine_biome_meta = function(bx, by, bz)",
        "\t\t\treturn earth2mt_get_biome_meta_string(bx, by, bz)",
        "\t\tend",
        "\t\tmcl_serverplayer.marshal_engine_biomes = function()",
        "\t\t\tif earth2mt_marshaled_id_to_name_map and earth2mt_marshaled_biomes then",
        "\t\t\t\treturn earth2mt_marshaled_id_to_name_map, earth2mt_marshaled_biomes",
        "\t\t\tend",
        "\t\t\tearth2mt_marshaled_id_to_name_map = {}",
        "\t\t\tearth2mt_marshaled_biomes = {}",
        "\t\t\tif mcl_levelgen and mcl_levelgen.biome_id_to_name_map then",
        "\t\t\t\tfor id, biome_name in earth2mt_pairs(mcl_levelgen.biome_id_to_name_map) do",
        "\t\t\t\t\tlocal def = earth2mt_get_biome_def(biome_name)",
        "\t\t\t\t\tif def and id > 0 then",
        "\t\t\t\t\t\tearth2mt_marshaled_id_to_name_map[earth2mt_tostring(id)] = biome_name",
        "\t\t\t\t\t\tearth2mt_marshaled_biomes[biome_name] = {",
        "\t\t\t\t\t\t\ttemperature = def.temperature,",
        "\t\t\t\t\t\t\ttemperature_modifier = def.temperature_modifier,",
        "\t\t\t\t\t\t\thas_precipitation = def.has_precipitation,",
        '\t\t\t\t\t\t\t_mcl_biome_type = earth2mt_biome_type(biome_name, def),',
        "\t\t\t\t\t\t}",
        "\t\t\t\t\tend",
        "\t\t\t\tend",
        "\t\t\tend",
        "\t\t\treturn earth2mt_marshaled_id_to_name_map, earth2mt_marshaled_biomes",
        "\t\tend",
        "\tend",
        "end)",
        "",
        _spawn_overrides_lua(spawn_pos).rstrip("\n"),
    ]
    return "\n".join(line for line in lines if line != "") + "\n"


def create_world(
    path: str,
    spawn_pos: tuple[int, int, int] | None = None,
    seed: int | None = None,
    world_name: str | None = None,
):
    """Create the world directory with earth2mt-specific Mineclonia overrides."""
    os.makedirs(path, exist_ok=True)

    with open(os.path.join(path, "world.mt"), "w") as f:
        f.write("backend = sqlite3\n")
        f.write("player_backend = sqlite3\n")
        f.write("auth_backend = sqlite3\n")
        f.write("mod_storage_backend = sqlite3\n")
        f.write("gameid = mineclonia\n")
        if world_name:
            f.write(f"world_name = {world_name}\n")
        if spawn_pos is not None:
            x, y, z = spawn_pos
            f.write(f"static_spawnpoint = ({x},{y},{z})\n")
            f.write("mcl_spawn_radius = 0\n")

    _write_map_meta(path, 1 if seed is None else seed)

    mod_dir = os.path.join(path, "worldmods", "__earth2mt")
    os.makedirs(mod_dir, exist_ok=True)

    with open(os.path.join(mod_dir, "mod.conf"), "w") as f:
        f.write("name = __earth2mt\n")
        f.write("description = earth2mt world overrides for Mineclonia\n")
        f.write(
            "optional_depends = mcl_spawn, mcl_biome_dispatch, mcl_mapgen_core, "
            "mcl_levelgen, mcl_serverplayer, mcl_core, mcl_util, mcl_biomes\n"
        )

    with open(os.path.join(mod_dir, "mcl_levelgen.conf"), "w") as f:
        f.write("disable_mcl_levelgen = true\n")

    with open(os.path.join(mod_dir, "init.lua"), "w") as f:
        f.write(_worldmod_init_lua(spawn_pos))
