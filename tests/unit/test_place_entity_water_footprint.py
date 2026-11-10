"""place_entity's water check covers only the tiles under the entity. Server-free (lupa).

The footprint block of place_entity/server.lua runs against a fake surface where the given
tiles are water. Collision boxes are Factorio 2.0.73's: pipe +-0.29, steam engine
(-1.35, -2.35)-(1.35, 2.35) facing north.
"""

from pathlib import Path

import pytest

lupa = pytest.importorskip("lupa")

SERVER_LUA = (
    Path(__file__).resolve().parents[2] / "fle/env/tools/agent/place_entity/server.lua"
).read_text()

START = "            -- Get entity prototype's collision box"
END = "        storage.utils.avoid_entity(player_index, entity, position, direction)"


def _check(box, x, y, water, direction=0):
    lua = lupa.LuaRuntime(unpack_returned_tuples=True)
    block = SERVER_LUA[SERVER_LUA.index(START) : SERVER_LUA.index(END)]
    # the block closes the `if exact then` it sits in
    block = block[: block.rindex("end")]
    fn = lua.execute(
        "local water = ... "
        "defines = {direction = {north = 0, east = 4, south = 8, west = 12}} "
        "rendering = {draw_circle = function() end} "
        "local function is_water_tile(name) return name == 'water' end "
        "return function(entity_prototype, entity_direction, position) "
        "  local entity = 'thing' "
        "  local player = {surface = {get_tile = function(tx, ty) "
        "    return {name = water[tx .. ',' .. ty] and 'water' or 'grass-1'} end}} "
        + block
        + " return 'ok' end",
        lua.table_from({f"{a},{b}": True for a, b in water}),
    )
    proto = lua.eval(
        f"{{collision_box = {{left_top = {{x = {box[0]}, y = {box[1]}}}, right_bottom = {{x = {box[2]}, y = {box[3]}}}}}}}"
    )
    ok, result = lua.eval("function(f, p, d, pos) return pcall(f, p, d, pos) end")(
        fn, proto, direction, lua.eval(f"{{x = {x}, y = {y}}}")
    )
    return ok


PIPE = (-0.29, -0.29, 0.29, 0.29)
ENGINE = (-1.35, -2.35, 1.35, 2.35)


def test_pipe_next_to_water_is_allowed():
    # pipe on tile (-15, 34); water all around it
    water = [(-14, 34), (-16, 34), (-15, 33), (-15, 35), (-14, 35)]
    assert _check(PIPE, -14.5, 34.5, water)


def test_pipe_on_water_is_refused():
    assert not _check(PIPE, -14.5, 34.5, [(-15, 34)])


def test_steam_engine_footprint_turns_with_direction():
    # facing north it covers x -1..1, y -2..2 around (0.5, 0.5); facing east x -2..2, y -1..1
    assert not _check(ENGINE, 0.5, 0.5, [(0, 2)], direction=0)
    assert _check(ENGINE, 0.5, 0.5, [(0, 2)], direction=4)
    assert not _check(ENGINE, 0.5, 0.5, [(2, 0)], direction=4)
    assert _check(ENGINE, 0.5, 0.5, [(2, 0)], direction=0)
