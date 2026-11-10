"""harvest_resource on rocks: the game rolls each product's amount. Server-free (Lua via lupa).

A Factorio 2.0 huge-rock has two products with amount_min/amount_max and no
fixed amount (stone 24-50, coal 24-50). The mock entity behaves like the game:
mine{inventory=...} puts the rolled amounts into the inventory and the entity
becomes invalid, so any further API call on it raises.
"""

from pathlib import Path

import pytest

lupa = pytest.importorskip("lupa")

HARVEST_LUA = (
    Path(__file__).resolve().parents[2]
    / "fle/env/tools/agent/harvest_resource/server.lua"
)

MOCKS = """
script = {on_nth_tick = function() end}
local function new_inventory()
    local inv = {items = {}}
    function inv.insert(self, stack)
        self.items[stack.name] = (self.items[stack.name] or 0) + stack.count
        return stack.count
    end
    function inv.can_insert(self, stack) return true end
    function inv.destroy(self) end
    return inv
end
spilled = {}
stats = {}
local surface = {}
game = {
    surfaces = {surface},
    create_inventory = function(size) return new_inventory() end,
}
local main = new_inventory()
local function guard(entity)
    return setmetatable({}, {__index = function(_, key)
        if not entity.valid and key ~= "valid" then
            error("LuaEntity API call when LuaEntity was invalid.")
        end
        return entity[key]
    end})
end
local rock = {
    valid = true, minable = true, type = "simple-entity", name = "huge-rock",
    position = {x = 10.5, y = 0.5},
    prototype = {mineable_properties = {mining_time = 2, products = {
        {type = "item", name = "stone", amount_min = 24, amount_max = 50, probability = 1},
        {type = "item", name = "coal", amount_min = 24, amount_max = 50, probability = 1},
    }}},
}
rock.mine = function(opts)
    if opts.inventory then
        opts.inventory:insert({name = "stone", count = 37})
        opts.inventory:insert({name = "coal", count = 29})
    end
    rock.valid = false
    return true
end
rock_proxy = guard(rock)
function surface.find_entities_filtered(filter)
    if not rock.valid then return {} end
    if filter.type == "simple-entity" or (type(filter.type) == "table") then
        return {rock_proxy}
    end
    return {}
end
player = {
    position = {x = 9, y = 0.5}, resource_reach_distance = 2.7, surface = surface,
    force = {get_item_production_statistics = function(s)
        return {on_flow = function(name, n) stats[name] = (stats[name] or 0) + n end}
    end},
    get_main_inventory = function() return main end,
    insert = function(stack) return main:insert(stack) end,
}
surface.spill_item_stack = function(args) spilled[#spilled + 1] = args end
main_inventory = main
storage = {
    actions = {}, fast = false, harvested_items = {},
    agent_characters = {player},
    utils = {get_contents_compat = function(inv) return inv.items end},
}
"""


@pytest.fixture
def lua():
    runtime = lupa.LuaRuntime()
    runtime.execute(MOCKS)
    runtime.execute(HARVEST_LUA.read_text())
    return runtime


def test_huge_rock_gives_the_rolled_amounts(lua):
    result = lua.eval("storage.actions.harvest_resource(1, 10.5, 0.5, 50, 10)")
    assert result == 66
    assert lua.eval("main_inventory.items.stone") == 37
    assert lua.eval("main_inventory.items.coal") == 29
    assert lua.eval("stats.stone") == 37 and lua.eval("stats.coal") == 29
    assert lua.eval("#spilled") == 0


def test_items_that_do_not_fit_are_spilled(lua):
    lua.execute("player.insert = function(stack) return math.min(stack.count, 10) end")
    lua.eval("storage.actions.harvest_resource(1, 10.5, 0.5, 50, 10)")
    spilled = {
        lua.eval(f"spilled[{i}].stack.name"): lua.eval(f"spilled[{i}].stack.count")
        for i in (1, 2)
    }
    assert spilled == {"stone": 27, "coal": 19}
