"""extract_item takes items only from the entity at the given position (no server).

The Lua action runs in lupa (Lua 5.2, as Factorio) against a stub surface whose
area search matches collision boxes, like LuaSurface.find_entities_filtered.

Regression: extract_item(item, Position) took from the nearest entity within 10
tiles that held the item, so with an empty furnace at the position it drained a
chest a few tiles away. An Entity source whose entity was gone did the same.
"""

from pathlib import Path

import pytest

from fle.env.tools import Tool
from fle.env.tools.agent.extract_item.client import ExtractItem

SERVER_LUA = (
    Path(__file__).resolve().parents[2] / "fle/env/tools/agent/extract_item/server.lua"
)

STUB_LUA = """
TILE = {["wooden-chest"] = 1, ["stone-furnace"] = 2, ["assembling-machine-1"] = 3, ["character"] = 1}
world = {}
local player_force = {name = "player"}
function add(name, x, y, items)
    local half = TILE[name] / 2 - 0.15   -- collision box inset, as in the game
    local slots = {}
    for item, n in pairs(items or {}) do
        table.insert(slots, {item = item, n = n})
    end
    local e = {valid = true, name = name, type = (name == "character") and "character" or "container",
               force = player_force, position = {x = x, y = y},
               bounding_box = {left_top = {x = x - half, y = y - half},
                               right_bottom = {x = x + half, y = y + half}}}
    function e.get_item_count(item)
        local n = 0
        for _, s in ipairs(slots) do if s.item == item then n = n + s.n end end
        return n
    end
    function e.get_max_inventory_index() return 1 end
    function e.get_inventory(i)
        local inv = {}
        for k, s in ipairs(slots) do
            local stack = {valid_for_read = s.n > 0, name = s.item,
                           prototype = {type = "item"}, quality = {name = "normal"}}
            setmetatable(stack, {
                __index = function(_, key) if key == "count" then return s.n end end,
                __newindex = function(t, key, v)
                    if key == "count" then s.n = v else rawset(t, key, v) end
                end,
            })
            function stack.clear() s.n = 0 end
            inv[k] = stack
        end
        return inv
    end
    table.insert(world, e)
    return e
end
function count_at(x, y, item)
    for _, e in ipairs(world) do
        if e.position.x == x and e.position.y == y then return e.get_item_count(item) end
    end
end
received = 0
local surface = {
    find_entities_filtered = function(f)
        local out = {}
        for _, e in ipairs(world) do
            local b = e.bounding_box
            if (f.name == nil or f.name == e.name) and (f.force == nil or f.force == e.force)
                and b.left_top.x < f.area[2][1] and b.right_bottom.x > f.area[1][1]
                and b.left_top.y < f.area[2][2] and b.right_bottom.y > f.area[1][2] then
                table.insert(out, e)
            end
        end
        return out
    end,
}
player = {valid = true, surface = surface, force = player_force, position = {x = 0, y = 0}}
function player.can_reach_entity() return true end
function player.can_insert() return true end
function player.insert(stack) received = received + stack.count; return stack.count end
add("character", 0.5, 5.5)   -- the agent itself stands among the entities
storage = {actions = {}, utils = {
    ensure_valid_character = function() return player end,
    get_contents_compat = function(inv)
        local o = {}
        for _, s in pairs(inv) do if s.valid_for_read then o[s.name] = (o[s.name] or 0) + s.count end end
        return o
    end,
}}
function call(item, n, x, y, source_name)
    local ok, res = pcall(storage.actions.extract_item, 1, item, n, x, y, source_name)
    if ok then return "ok", res end
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


def _add(lua, name, x, y, **items):
    lua.globals().add(
        name, x, y, lua.table_from({k.replace("_", "-"): v for k, v in items.items()})
    )


def _extract(lua, item, n, x, y, source_name=None):
    out = lua.globals().call(item, n, x, y, source_name)
    if out[0] == "ok":
        return out[1]
    tool = object.__new__(ExtractItem)
    raise LookupError(Tool.get_error_message(tool, out[1]))


def _count(lua, x, y, item="iron-plate"):
    return lua.globals().count_at(x, y, item)


def test_takes_from_the_entity_at_the_position(lua):
    _add(lua, "stone-furnace", 0.0, -68.0, iron_plate=24)
    _add(lua, "wooden-chest", 2.5, -72.5, iron_plate=108)
    assert _extract(lua, "iron-plate", 50, 0.0, -68.0) == 24
    assert _count(lua, 0.0, -68.0) == 0
    assert _count(lua, 2.5, -72.5) == 108


def test_empty_entity_at_the_position_raises_and_neighbours_keep_their_items(lua):
    _add(lua, "stone-furnace", 0.0, -68.0, iron_ore=5)
    _add(lua, "wooden-chest", 2.5, -72.5, iron_plate=108)
    with pytest.raises(LookupError) as e:
        _extract(lua, "iron-plate", 10, 0.0, -68.0)
    assert "stone-furnace at (0, -68) has no iron-plate (it holds iron-ore:5)" in str(
        e.value
    )
    assert _count(lua, 2.5, -72.5) == 108
    assert lua.globals().received == 0


def test_no_entity_at_the_position_names_the_nearest_holders(lua):
    _add(lua, "wooden-chest", 4.5, -75.5, iron_plate=105)
    _add(lua, "wooden-chest", 2.5, -72.5, iron_plate=108)
    with pytest.raises(LookupError) as e:
        _extract(lua, "iron-plate", 10, 0.5, -70.5)
    msg = str(e.value)
    assert msg.startswith("No entity at (0.5, -70.5)")
    assert "wooden-chest at (2.5, -72.5) (108 iron-plate, 2.8 tiles away)" in msg
    assert msg.index("(2.5, -72.5)") < msg.index("(4.5, -75.5)")
    assert _count(lua, 2.5, -72.5) == 108 and _count(lua, 4.5, -75.5) == 105


def test_nothing_nearby_holds_the_item(lua):
    _add(lua, "wooden-chest", 4.5, -75.5, copper_plate=3)
    with pytest.raises(LookupError, match="Nothing within 10 tiles holds iron-plate"):
        _extract(lua, "iron-plate", 10, 0.5, -70.5)


def test_any_tile_of_a_machine_selects_it(lua):
    _add(lua, "assembling-machine-1", 3.5, 20.5, iron_plate=7)
    _add(lua, "wooden-chest", 5.5, 20.5, iron_plate=50)  # next to its east side
    assert _extract(lua, "iron-plate", 5, 4.9, 21.9) == 5  # its bottom-right tile
    assert _count(lua, 3.5, 20.5) == 2
    assert _count(lua, 5.5, 20.5) == 50


def test_shared_border_belongs_to_the_entity_on_the_right(lua):
    _add(lua, "wooden-chest", 0.5, 0.5, iron_plate=3)
    _add(lua, "wooden-chest", 1.5, 0.5, iron_plate=9)
    assert _extract(lua, "iron-plate", 20, 1.0, 0.5) == 9
    assert _count(lua, 0.5, 0.5) == 3


def test_entity_source_that_is_gone_raises(lua):
    # extract_item(item, chest) where that chest was removed: a furnace of another
    # name and a chest elsewhere are not used
    _add(lua, "wooden-chest", 3.5, 0.5, iron_plate=9)
    with pytest.raises(LookupError, match=r"No wooden-chest at \(0.5, 0.5\)"):
        _extract(lua, "iron-plate", 5, 0.5, 0.5, "wooden-chest")
    assert _count(lua, 3.5, 0.5) == 9


def test_entity_source_only_matches_its_name(lua):
    _add(lua, "wooden-chest", 0.5, 0.5, iron_plate=4)
    assert _extract(lua, "iron-plate", 5, 0.5, 0.5, "wooden-chest") == 4


def test_the_character_is_not_a_source(lua):
    with pytest.raises(LookupError, match=r"No entity at \(0.5, 5.5\)"):
        _extract(lua, "iron-plate", 5, 0.5, 5.5)
