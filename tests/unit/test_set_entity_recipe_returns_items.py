"""set_entity_recipe gives the items a recipe change removes to the character. Server-free.

Runs the tool's server.lua in lupa against a fake character and machine. LuaEntity.set_recipe
returns the removed items (Factorio 2.0: an array of {name, count, quality}).
"""

from pathlib import Path

import pytest

lupa = pytest.importorskip("lupa")

SERVER_LUA = (
    Path(__file__).resolve().parents[2]
    / "fle/env/tools/agent/set_entity_recipe/server.lua"
).read_text()

FAKE_WORLD = """
local inserted, spilled = {}, {}
local capacity = CAPACITY
local recipes = {["iron-gear-wheel"] = {name = "iron-gear-wheel"}, ["copper-cable"] = {name = "copper-cable"}}
local machine = {type = "assembling-machine", position = {x = 0.5, y = 0.5}, recipe = recipes["iron-gear-wheel"]}
function machine.get_recipe() return machine.recipe end
function machine.set_recipe(name)
    machine.recipe = recipes[name]
    return REMOVED
end
local surface = {}
function surface.find_entities_filtered(_) return {machine} end
function surface.spill_item_stack(args)
    table.insert(spilled, args.stack.name .. ":" .. args.stack.count .. ":" .. tostring(args.enable_looted))
    return {}
end
local player = {surface = surface, position = {x = 2, y = 2}, force = {recipes = recipes}}
function player.can_reach_entity(_) return true end
function player.insert(stack)
    local n = math.min(stack.count, capacity)
    capacity = capacity - n
    if n > 0 then table.insert(inserted, stack.name .. ":" .. n .. ":" .. tostring(stack.quality)) end
    return n
end
storage = {
    actions = {},
    agent_characters = {[1] = player},
    utils = {serialize_entity = function(e) return {name = "assembling-machine-1", recipe = e.recipe.name} end},
}
helpers = {table_to_json = function(_) return "{}" end}
return {inserted = inserted, spilled = spilled}
"""


def run(removed: str, capacity: int = 1000):
    runtime = lupa.LuaRuntime(unpack_returned_tuples=True)
    log = runtime.execute(
        FAKE_WORLD.replace("REMOVED", removed).replace("CAPACITY", str(capacity))
    )
    runtime.execute(SERVER_LUA)
    ok, result = runtime.eval(
        "function() return pcall(storage.actions.set_entity_recipe, 1, 'copper-cable', 0.5, 0.5) end"
    )()
    assert ok, result
    assert result["recipe"] == "copper-cable"
    return list(log["inserted"].values()), list(log["spilled"].values())


def test_removed_items_go_to_the_character():
    inserted, spilled = run(
        "{{name = 'iron-plate', count = 12, quality = 'normal'},"
        " {name = 'iron-gear-wheel', count = 3, quality = 'normal'}}"
    )
    assert inserted == ["iron-plate:12:normal", "iron-gear-wheel:3:normal"]
    assert spilled == []


def test_overflow_is_spilled_at_the_character():
    inserted, spilled = run(
        "{{name = 'iron-plate', count = 12, quality = 'normal'}}", capacity=5
    )
    assert inserted == ["iron-plate:5:normal"]
    assert spilled == ["iron-plate:7:true"]


def test_factorio_1_1_shape_is_accepted():
    inserted, _ = run("{['iron-plate'] = 4}")
    assert inserted == ["iron-plate:4:nil"]


def test_nothing_removed():
    assert run("{}") == ([], [])
    assert run("nil") == ([], [])
