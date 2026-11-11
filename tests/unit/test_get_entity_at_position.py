"""get_entity returns only the entity that occupies the position (no server).

The Lua action runs in lupa (Lua 5.2, as Factorio) against a stub surface whose
area search matches collision boxes, like LuaSurface.find_entities_filtered; the
client runs with execute stubbed.

Regression: two adjacent entities of the same prototype (e.g. 3x3 assemblers)
both "covered" a position on their shared border, and the one picked depended on
search order. A position that no entity covered returned None silently.
"""

from pathlib import Path

import pytest

from fle.env.entities import Position
from fle.env.game_types import Prototype
from fle.env.tools import Tool
from fle.env.tools.agent.get_entity.client import GetEntity

SERVER_LUA = (
    Path(__file__).resolve().parents[2] / "fle/env/tools/agent/get_entity/server.lua"
)

STUB_LUA = """
prototypes = {entity = {["assembling-machine-1"] = {tile = 3}, ["wooden-chest"] = {tile = 1},
                        ["stone-furnace"] = {tile = 2}}}
world = {}
function add(name, x, y)
    local half = prototypes.entity[name].tile / 2 - 0.3   -- collision box inset, as in the game
    local e = {valid = true, name = name, position = {x = x, y = y},
               bounding_box = {left_top = {x = x - half, y = y - half},
                               right_bottom = {x = x + half, y = y + half}}}
    table.insert(world, e)
    return e
end
function clear() world = {} end
local surface = {
    find_entities_filtered = function(f)
        local out = {}
        for _, e in ipairs(world) do
            local b = e.bounding_box
            if (f.name == nil or f.name == e.name)
                and b.left_top.x < f.area[2][1] and b.right_bottom.x > f.area[1][1]
                and b.left_top.y < f.area[2][2] and b.right_bottom.y > f.area[1][2] then
                table.insert(out, e)
            end
        end
        return out
    end,
}
player = {valid = true, surface = surface}
storage = {actions = {}, utils = {
    ensure_valid_character = function() return player end,
    serialize_entity = function(e) return {name = e.name, x = e.position.x, y = e.position.y} end,
}}
function call(name, x, y)
    local ok, res = pcall(storage.actions.get_entity, 1, name, x, y)
    if ok then return "ok", res.x, res.y end
    return "error", res
end
"""


@pytest.fixture()
def lua():
    lupa = pytest.importorskip("lupa.lua52")
    rt = lupa.LuaRuntime(unpack_returned_tuples=True)
    rt.execute(STUB_LUA)
    rt.execute(SERVER_LUA.read_text())
    return rt


def _add(lua, name, x, y):
    lua.globals().add(name, x, y)


def _get(lua, name, x, y):
    """(x, y) of the entity returned, or raises with the message a caller would see."""
    out = lua.globals().call(name, x, y)
    if out[0] == "ok":
        return (out[1], out[2])
    tool = object.__new__(GetEntity)
    raise LookupError(Tool.get_error_message(tool, out[1]))


@pytest.fixture()
def two_assemblers(lua):
    # Tiles x 0..2 and 3..5, y 0..2: they share the border x = 3.
    _add(lua, "assembling-machine-1", 1.5, 1.5)
    _add(lua, "assembling-machine-1", 4.5, 1.5)
    return lua


def test_centre_returns_that_entity(two_assemblers):
    assert _get(two_assemblers, "assembling-machine-1", 1.5, 1.5) == (1.5, 1.5)
    assert _get(two_assemblers, "assembling-machine-1", 4.5, 1.5) == (4.5, 1.5)


@pytest.mark.parametrize(
    "x, y, expected",
    [
        (2.9, 1.5, (1.5, 1.5)),  # last column of the left machine
        (2.5, 0.0, (1.5, 1.5)),  # its top-right tile
        (3.1, 1.5, (4.5, 1.5)),  # first column of the right machine
        (3.0, 1.5, (4.5, 1.5)),  # the shared border: tile 3 belongs to the right machine
        (3.0, 2.9, (4.5, 1.5)),
        (0.0, 0.0, (1.5, 1.5)),  # outer corner of the left machine
        (6.0, 1.5, (4.5, 1.5)),  # outer border of the right machine, nothing beyond it
    ],
)
def test_adjacent_assemblers_never_swap(two_assemblers, x, y, expected):
    assert _get(two_assemblers, "assembling-machine-1", x, y) == expected


def test_order_of_search_results_does_not_matter(lua):
    # Same layout, entities created in the other order.
    _add(lua, "assembling-machine-1", 4.5, 1.5)
    _add(lua, "assembling-machine-1", 1.5, 1.5)
    assert _get(lua, "assembling-machine-1", 3.0, 1.5) == (4.5, 1.5)
    assert _get(lua, "assembling-machine-1", 2.99, 1.5) == (1.5, 1.5)


def test_adjacent_chests(lua):
    _add(lua, "wooden-chest", 0.5, 0.5)
    _add(lua, "wooden-chest", 1.5, 0.5)
    assert _get(lua, "wooden-chest", 0, 0) == (0.5, 0.5)
    assert _get(lua, "wooden-chest", 1, 0) == (1.5, 0.5)
    assert _get(lua, "wooden-chest", 1.5, 0.5) == (1.5, 0.5)


def test_empty_neighbouring_tile_raises_with_nearest(two_assemblers):
    with pytest.raises(LookupError) as e:
        _get(two_assemblers, "assembling-machine-1", 7.5, 1.5)
    assert str(e.value) == (
        "Could not get assembling-machine-1 at position (7.5, 1.5): no "
        "assembling-machine-1 covers that position. Nearest: assembling-machine-1 at "
        "(4.5, 1.5) 3.0 tiles away; assembling-machine-1 at (1.5, 1.5) 6.0 tiles away."
    )


def test_error_lists_at_most_three_nearest(lua):
    for x in (2.5, 4.5, 6.5, 8.5, 10.5):
        _add(lua, "wooden-chest", x, 0.5)
    _add(lua, "stone-furnace", 0, 0)  # another prototype is never listed
    with pytest.raises(LookupError) as e:
        _get(lua, "wooden-chest", 0.5, 0.5)
    msg = str(e.value)
    assert "(2.5, 0.5) 2.0 tiles away; " in msg
    assert "(4.5, 0.5) 4.0 tiles away; " in msg
    assert "(6.5, 0.5) 6.0 tiles away." in msg
    assert "8.5" not in msg and "stone-furnace" not in msg


def test_error_when_none_nearby(lua):
    _add(lua, "wooden-chest", 100.5, 0.5)
    with pytest.raises(LookupError) as e:
        _get(lua, "wooden-chest", 0.5, 0.5)
    assert str(e.value) == (
        "Could not get wooden-chest at position (0.5, 0.5): no wooden-chest covers "
        "that position. There is no wooden-chest within 30 tiles."
    )


def test_other_prototype_on_the_tile_is_not_returned(lua):
    _add(lua, "stone-furnace", 1, 1)
    with pytest.raises(LookupError):
        _get(lua, "wooden-chest", 0.5, 0.5)


# --- client ------------------------------------------------------------------------


def _tool(response):
    tool = object.__new__(GetEntity)
    tool.player_index = 1
    tool.execute = lambda *args: (response, 0)
    return tool


def _chest_response(x, y):
    return {
        "name": "wooden-chest",
        "position": {"x": x, "y": y},
        "direction": 0,
        "health": 100,
        "status": "normal",
        "energy": 0,
        "dimensions": {"width": 1, "height": 1},
        "tile_dimensions": {"tile_width": 1, "tile_height": 1},
    }


def test_client_returns_entity():
    chest = _tool(_chest_response(0.5, 0.5))(Prototype.WoodenChest, Position(x=0, y=0))
    assert chest.position == Position(x=0.5, y=0.5)


def test_client_raises_server_message_instead_of_none():
    msg = (
        '[string "storage.actions.get_entity = ..."]:88: "Could not get wooden-chest '
        "at position (7.5, 1.5): no wooden-chest covers that position. Nearest: "
        'wooden-chest at (4.5, 1.5) 3.0 tiles away."'
    )
    with pytest.raises(Exception) as e:
        _tool(msg)(Prototype.WoodenChest, Position(x=7.5, y=1.5))
    assert str(e.value) == (
        "Could not get wooden-chest at position (7.5, 1.5): no wooden-chest covers "
        "that position. Nearest: wooden-chest at (4.5, 1.5) 3.0 tiles away."
    )


def test_client_raises_without_a_response():
    with pytest.raises(Exception) as e:
        _tool({})(Prototype.WoodenChest, Position(x=7.5, y=1.5))
    assert "Could not get wooden-chest at position (7.5, 1.5)" in str(e.value)


@pytest.mark.parametrize(
    "group", [Prototype.BeltGroup, Prototype.PipeGroup, Prototype.ElectricityGroup]
)
def test_groups_still_come_from_get_entities(group):
    tool = _tool("unused")
    calls = []

    def get_entities(entities, position=None):
        calls.append((entities, position))
        return ["group"]

    tool.get_entities = get_entities
    assert tool(group, Position(x=1, y=2)) == "group"
    assert calls[0][1] == Position(x=1, y=2)
    tool.get_entities = lambda entities, position=None: []
    assert tool(group, Position(x=1, y=2)) is None
