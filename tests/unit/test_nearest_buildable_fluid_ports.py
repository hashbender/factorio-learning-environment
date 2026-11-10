"""nearest_buildable keeps an entity's fluid ports off water. Server-free (lupa).

The fake oil refinery has the Factorio 2.0.73 pipe connections of its crude-oil input box
(per-direction port tiles, opening south when the refinery faces north). The fake surface
is all land except the water tiles given; the box itself is never on water.
"""

from pathlib import Path

import pytest

lupa = pytest.importorskip("lupa")

SERVER_LUA = (
    Path(__file__).resolve().parents[2]
    / "fle/env/tools/agent/nearest_buildable/server.lua"
).read_text()

FAKE = """
local water = ...
local function key(x, y) return math.floor(x) .. "," .. math.floor(y) end
local surface = {}
function surface.count_tiles_filtered(_) return 0 end
function surface.count_entities_filtered(_) return 0 end
function surface.find_entities_filtered(_) return {} end
function surface.get_tile(x, y)
    return {valid = true, name = water[key(x, y)] and "water" or "grass-1"}
end
rendering = {draw_rectangle = function() end}
local crude = {production_type = "input", pipe_connections = {
    {direction = 8, connection_type = "normal", flow_direction = "input",
     positions = {{x = -1, y = 2}, {x = -2, y = -1}, {x = 1, y = -2}, {x = 2, y = 1}}}}}
prototypes = {entity = {
    ["oil-refinery"] = {type = "assembling-machine", crafting_categories = {["oil-processing"] = true},
                        fluidbox_prototypes = {crude}},
    ["assembling-machine-2"] = {type = "assembling-machine", crafting_categories = {crafting = true},
                        fluidbox_prototypes = {crude}},
    ["offshore-pump"] = {type = "offshore-pump", fluidbox_prototypes = {crude}},
    ["wooden-chest"] = {type = "container"},
}}
storage = {actions = {}, agent_characters = {[1] = {surface = surface, position = {x = 0, y = 0}}}}
"""


def _find(entity, water_tiles):
    lua = lupa.LuaRuntime(unpack_returned_tuples=True)
    water = lua.table_from({f"{x},{y}": True for x, y in water_tiles})
    lua.execute(FAKE, water)
    lua.execute(SERVER_LUA)
    box = lua.eval("{left_top = {x = 0, y = 0}, right_bottom = {x = 5, y = 5}}")
    result = lua.eval(
        "function(name, box) return storage.actions.nearest_buildable(1, name, box, {x = 0, y = 0}) end"
    )(entity, box)
    return result.position.x, result.position.y


# A refinery at the first candidate (box (0,0)-(5,5), centre (2.5, 2.5)) facing north has
# its crude input port tile at (1.5, 4.5) and opens onto (1.5, 5.5): make that tile water.
WATER_AT_FIRST_PORT = [(1, 5)]


def test_spot_with_a_port_onto_water_is_skipped():
    assert _find("oil-refinery", []) == (0, 0)
    x, y = _find("oil-refinery", WATER_AT_FIRST_PORT)
    assert (x, y) != (0, 0)


def test_every_direction_is_checked():
    # facing west the same port opens onto (2.5 + 2 + 1, 2.5 + 1) = (5.5, 3.5)
    assert _find("oil-refinery", [(5, 3)]) != (0, 0)


def test_offshore_pump_and_general_assembler_are_not_checked():
    assert _find("offshore-pump", WATER_AT_FIRST_PORT) == (0, 0)
    assert _find("assembling-machine-2", WATER_AT_FIRST_PORT) == (0, 0)


def test_entity_without_fluid_boxes():
    assert _find("wooden-chest", WATER_AT_FIRST_PORT) == (0, 0)
