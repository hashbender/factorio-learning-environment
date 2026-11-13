"""Chemical plant fluid connection points are the tiles a pipe must occupy (the
target_position of the game's pipe connections), like the assembler's and the
refinery's points; they were the midpoint between the port tile and that tile,
which lies on the plant's edge (y = -45.0 for a plant at y = -43.5).
Server-free: recipe_fluid_connection_mappings.lua runs in lupa against a fake
LuaFluidBox shaped like a Factorio 2.0 chemical plant's."""

from pathlib import Path

import pytest

lupa = pytest.importorskip("lupa")

MAPPINGS_LUA = (
    Path(__file__).resolve().parents[2]
    / "fle/env/mods/recipe_fluid_connection_mappings.lua"
)

# A north-facing chemical plant at (0.5, -43.5) running heavy-oil-cracking:
# inputs (water, heavy oil) on the north side, outputs on the south side.
FAKE = """
local cx, cy = 0.5, -43.5
local boxes = {
  {kind = "input", dx = -1, side = -1, filter = "water"},
  {kind = "input", dx = 1, side = -1, filter = "heavy-oil"},
  {kind = "output", dx = -1, side = 1, filter = "light-oil"},
  {kind = "output", dx = 1, side = 1, filter = nil},
}
fluidbox = setmetatable({}, {__len = function() return #boxes end})
function fluidbox.get_prototype(i) return {production_type = boxes[i].kind} end
function fluidbox.get_filter(i) return boxes[i].filter and {name = boxes[i].filter} or nil end
function fluidbox.get_pipe_connections(i)
  local b = boxes[i]
  return {{flow_direction = b.kind,
           position = {x = cx + b.dx, y = cy + b.side},
           target_position = {x = cx + b.dx, y = cy + 2 * b.side}}}
end
"""


def _lua():
    lua = lupa.LuaRuntime()
    lua.execute(
        "defines = {direction = {north = 0, east = 4, south = 8, west = 12}}\n"
        "storage = {utils = {}}"
    )
    lua.execute(MAPPINGS_LUA.read_text())
    lua.execute(FAKE)
    return lua


def _points(result, side):
    t = result[side]
    return {(t[i].type.strip('"'), t[i].x, t[i].y) for i in range(1, len(t) + 1)}


RECIPE = (
    "{name = 'heavy-oil-cracking', "
    "ingredients = {{name = 'water', type = 'fluid'}, {name = 'heavy-oil', type = 'fluid'}}, "
    "products = {{name = 'light-oil', type = 'fluid'}}}"
)


def test_points_are_the_pipe_tiles_read_from_the_game():
    lua = _lua()
    r = lua.eval(
        "storage.utils.get_chemical_plant_fluid_mappings("
        "{valid = true, position = {x = 0.5, y = -43.5}, direction = 0, fluidbox = fluidbox}, "
        + RECIPE
        + ")"
    )
    assert _points(r, "inputs") == {("water", -0.5, -45.5), ("heavy-oil", 1.5, -45.5)}
    # (the second output box has no filter and the recipe one fluid product: not listed)
    assert _points(r, "outputs") == {("light-oil", -0.5, -41.5)}
    # every point is a tile centre outside the 3x3 plant, never on its edge
    for side in ("inputs", "outputs"):
        for _, x, y in _points(r, side):
            assert x % 1 == 0.5 and y % 1 == 0.5
            assert abs(y - -43.5) == 2


@pytest.mark.parametrize(
    "direction,expected_in,expected_out",
    [
        (0, {(-0.5, -45.5), (1.5, -45.5)}, {(-0.5, -41.5)}),
        (8, {(1.5, -41.5), (-0.5, -41.5)}, {(1.5, -45.5)}),
    ],
)
def test_fallback_offsets_are_pipe_tiles(direction, expected_in, expected_out):
    # the fluid boxes can't be read (entity not valid): the static offsets are used
    lua = _lua()
    r = lua.eval(
        "storage.utils.get_chemical_plant_fluid_mappings("
        f"{{valid = false, position = {{x = 0.5, y = -43.5}}, direction = {direction}}}, "
        + RECIPE
        + ")"
    )
    assert {(x, y) for _, x, y in _points(r, "inputs")} == expected_in
    assert {(x, y) for _, x, y in _points(r, "outputs")} == expected_out
