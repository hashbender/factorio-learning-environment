"""place_tile and throw_cliff_explosives follow the game's rules. Server-free (lupa).

The fake prototypes use Factorio 2.0.73 values: landfill places the `landfill` tile, only on
the water tiles (tile_condition) and not on ground tiles (condition layer ground_tile);
stone brick places `stone-path`, not on water; character build distance 10; cliff-explosives
is a destroy-cliffs capsule with throw range 10 and radius 1.5.
"""

from pathlib import Path

import pytest

lupa = pytest.importorskip("lupa")

TOOLS = Path(__file__).resolve().parents[2] / "fle/env/tools/agent"

FAKE = """
local tiles, items, log = {}, {["landfill"] = 5, ["stone-brick"] = 5, ["cliff-explosives"] = 2}, {}
local function proto(name, layers, mineable)
    return {name = name, collision_mask = {layers = layers}, mineable_properties = mineable}
end
local TP = {
    water = proto("water", {water_tile = true, item = true, player = true}),
    ["grass-1"] = proto("grass-1", {ground_tile = true}),
    landfill = proto("landfill", {ground_tile = true}),
    ["stone-path"] = proto("stone-path", {ground_tile = true},
                           {minable = true, products = {{type = "item", name = "stone-brick", amount = 1}}}),
    concrete = proto("concrete", {ground_tile = true}),
}
local cliffs = {}
local surface = {}
function surface.get_tile(x, y)
    local name = tiles[math.floor(x) .. "," .. math.floor(y)] or "grass-1"
    return {name = name, prototype = TP[name], valid = true}
end
function surface.set_tiles(t) for _, tile in ipairs(t) do tiles[tile.position[1] .. "," .. tile.position[2]] = tile.name end end
function surface.find_entities_filtered(f)
    if f.type == "cliff" then
        local out = {}
        for _, c in ipairs(cliffs) do
            local dx, dy = c.position.x - f.position[1], c.position.y - f.position[2]
            if c.valid and math.sqrt(dx * dx + dy * dy) <= f.radius then table.insert(out, c) end
        end
        return out
    end
    return {}
end
function surface.create_entity(e) table.insert(log, "create " .. e.name) end
function surface.spill_item_stack(a) table.insert(log, "spill " .. a.stack.name) end
local player = {surface = surface, position = {x = 0, y = 0}, build_distance = 10, force = {}}
function player.get_item_count(n) return items[n] or 0 end
function player.remove_item(s) items[s.name] = items[s.name] - s.count return s.count end
function player.insert(s) items[s.name] = (items[s.name] or 0) + s.count return s.count end
local water_list = {{name = "water"}, {name = "deepwater"}}
prototypes = {
    item = {
        landfill = {place_as_tile_result = {result = {name = "landfill"}, condition_size = 1,
                    condition = {layers = {ground_tile = true}}, tile_condition = water_list}},
        ["stone-brick"] = {place_as_tile_result = {result = {name = "stone-path"}, condition_size = 1,
                    condition = {layers = {water_tile = true}}}},
        ["concrete"] = {place_as_tile_result = {result = {name = "concrete"}, condition_size = 1,
                    condition = {layers = {water_tile = true}}}},
        ["iron-plate"] = {},
        ["cliff-explosives"] = {capsule_action = {type = "destroy-cliffs", radius = 1.5,
                    attack_parameters = {range = 10}}},
    },
    tile = TP,
}
storage = {actions = {}, utils = {
    ensure_valid_character = function() return player end,
    format_inventory_for_error = function() return "{}" end,
}}
return {tiles = tiles, inv = items, log = log, cliffs = cliffs, player = player}
"""


@pytest.fixture()
def world():
    lua = lupa.LuaRuntime(unpack_returned_tuples=True)
    w = lua.execute(FAKE)
    lua.execute((TOOLS / "place_tile/server.lua").read_text())
    lua.execute((TOOLS / "throw_cliff_explosives/server.lua").read_text())
    place = lua.eval(
        "function(item, x, y) return pcall(storage.actions.place_tile, 1, item, x, y) end"
    )
    throw = lua.eval(
        "function(x, y) return pcall(storage.actions.throw_cliff_explosives, 1, x, y) end"
    )
    add_cliff = lua.eval(
        "function(cliffs, x, y) local c = {valid = true, position = {x = x, y = y}} "
        "function c.destroy(a) c.valid = false c.corrected = a.do_cliff_correction end "
        "table.insert(cliffs, c) return c end"
    )
    return w, place, throw, add_cliff


def test_landfill_on_water(world):
    w, place, _, _ = world
    w.tiles["3,4"] = "water"
    ok, result = place("landfill", 3.2, 4.7)
    assert ok, result
    assert (result.x, result.y) == (3.5, 4.5)
    assert w.tiles["3,4"] == "landfill"
    assert w.inv["landfill"] == 4


def test_landfill_not_on_land(world):
    w, place, _, _ = world
    ok, message = place("landfill", 3, 4)
    assert not ok and "Can't place landfill on grass-1" in message
    assert w.inv["landfill"] == 5


def test_brick_not_on_water(world):
    w, place, _, _ = world
    w.tiles["1,1"] = "water"
    ok, message = place("stone-brick", 1, 1)
    assert not ok and "Can't place stone-brick on water" in message


def test_out_of_build_distance(world):
    w, place, _, _ = world
    w.tiles["20,0"] = "water"
    ok, message = place("landfill", 20, 0)
    assert not ok and "too far away" in message and "max distance is 10" in message
    assert w.inv["landfill"] == 5


def test_not_in_inventory_and_not_a_tile(world):
    w, place, _, _ = world
    w.tiles["2,2"] = "water"
    w.inv["landfill"] = 0
    ok, message = place("landfill", 2, 2)
    assert not ok and "No landfill in inventory" in message
    ok, message = place("iron-plate", 2, 2)
    assert not ok and "can't be placed as a tile" in message


def test_building_over_a_placed_tile_returns_its_item(world):
    w, place, _, _ = world
    w.tiles["2,2"] = "stone-path"
    w.inv["concrete"] = 1
    ok, result = place("concrete", 2, 2)
    assert ok, result
    assert w.tiles["2,2"] == "concrete"
    assert w.inv["stone-brick"] == 6 and w.inv["concrete"] == 0


def test_throw_destroys_cliffs_in_radius(world):
    w, _, throw, add_cliff = world
    near = add_cliff(w.cliffs, 5, 1)
    far = add_cliff(w.cliffs, 5, 4)
    ok, result = throw(5, 0)
    assert ok, result
    assert result.destroyed == 1
    assert not near.valid and near.corrected and far.valid
    assert w.inv["cliff-explosives"] == 1


def test_throw_without_a_cliff_still_uses_the_item(world):
    w, _, throw, _ = world
    ok, result = throw(3, 3)
    assert ok and result.destroyed == 0
    assert w.inv["cliff-explosives"] == 1


def test_throw_out_of_range_or_without_item(world):
    w, _, throw, _ = world
    ok, message = throw(11, 0)
    assert not ok and "max throw range is 10" in message
    assert w.inv["cliff-explosives"] == 2
    w.inv["cliff-explosives"] = 0
    ok, message = throw(1, 0)
    assert not ok and "No cliff_explosives in inventory" in message
