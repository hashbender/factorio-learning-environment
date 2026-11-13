"""craft_item plans the whole recipe tree with shared intermediates. Server-free (Lua via lupa).

The lab needs iron gear wheels directly and inside its transport belts; the old code crafted the
lab's gears, then the belts used two of them, and the final check failed ("still missing
ingredients - iron-gear-wheel x2"). Recipes are Factorio 2.0's.
"""

from pathlib import Path

import pytest

lupa = pytest.importorskip("lupa")

CRAFT_LUA = (
    Path(__file__).resolve().parents[2] / "fle/env/tools/agent/craft_item/server.lua"
)

# name: (category, energy, product amount, {ingredient: amount}, enabled)
RECIPES = {
    "iron-plate": ("smelting", 3.2, 1, {"iron-ore": 1}, True),
    "copper-plate": ("smelting", 3.2, 1, {"copper-ore": 1}, True),
    "iron-gear-wheel": ("crafting", 0.5, 1, {"iron-plate": 2}, True),
    "copper-cable": ("crafting", 0.5, 2, {"copper-plate": 1}, True),
    "electronic-circuit": ("crafting", 0.5, 1, {"iron-plate": 1, "copper-cable": 3}, True),
    "transport-belt": ("crafting", 0.5, 2, {"iron-plate": 1, "iron-gear-wheel": 1}, True),
    "inserter": ("crafting", 0.5, 1, {"electronic-circuit": 1, "iron-gear-wheel": 1, "iron-plate": 1}, True),
    "lab": ("crafting", 2, 1, {"electronic-circuit": 10, "iron-gear-wheel": 10, "transport-belt": 4}, True),
    "assembling-machine-1": ("crafting", 0.5, 1, {"electronic-circuit": 3, "iron-gear-wheel": 5, "iron-plate": 9}, True),
    "electric-mining-drill": ("crafting", 2, 1, {"electronic-circuit": 3, "iron-gear-wheel": 5, "iron-plate": 10}, True),
    "automation-science-pack": ("crafting", 5, 1, {"copper-plate": 1, "iron-gear-wheel": 1}, True),
    "logistic-science-pack": ("crafting", 6, 1, {"inserter": 1, "transport-belt": 1}, True),
    "engine-unit": ("advanced-crafting", 10, 1, {"steel-plate": 1, "iron-gear-wheel": 1, "pipe": 2}, True),
    "car": ("crafting", 2, 1, {"engine-unit": 8, "iron-plate": 20, "steel-plate": 5}, True),
    "fast-inserter": ("crafting", 0.5, 1, {"electronic-circuit": 2, "iron-plate": 2, "inserter": 1}, False),
}

SETUP = """
inv = {}
recipes = {}
local function count(name) return inv[name] or 0 end
character = {
  prototype = {crafting_categories = {crafting = true}},
  position = {x = 0, y = 0},
  surface = {spill_item_stack = function() end},
  force = {recipes = recipes, technologies = {},
           get_item_production_statistics = function() return {on_flow = function() end} end},
}
function character.get_item_count(name) return count(name) end
function character.remove_item(st) inv[st.name] = count(st.name) - st.count; return st.count end
function character.insert(st) inv[st.name] = count(st.name) + st.count; return st.count end
function character.get_main_inventory()
  local slots = {}
  for i = 1, 80 do slots[i] = {valid_for_read = false} end
  return slots
end
prototypes = {item = setmetatable({}, {__index = function() return {stack_size = 100} end})}
game = {surfaces = {{}}}
storage = {actions = {}, fast = true, elapsed_ticks = 0, crafted_items = {},
           utils = {ensure_valid_character = function() return character end}}
"""


def _lua():
    lua = lupa.LuaRuntime(unpack_returned_tuples=True)
    lua.execute(SETUP)
    recipes = lua.globals().recipes
    for name, (cat, energy, amount, ings, enabled) in RECIPES.items():
        t = lua.table_from(
            {
                "name": name,
                "category": cat,
                "energy": energy,
                "enabled": enabled,
                "products": lua.table_from([lua.table_from({"name": name, "amount": amount, "type": "item"})]),
                "ingredients": lua.table_from(
                    [lua.table_from({"name": i, "amount": a}) for i, a in ings.items()]
                ),
            }
        )
        recipes[name] = t
    lua.execute(CRAFT_LUA.read_text())
    return lua


def _craft(lua, inv, name, count):
    g = lua.globals()
    for k in list(g.inv.keys()):
        g.inv[k] = None
    for k, v in inv.items():
        g.inv[k] = v
    ok, res = lua.eval(
        "function(n, c) return pcall(storage.actions.craft_item, 1, n, c) end"
    )(name, count)
    after = {k: v for k, v in g.inv.items() if v}
    return ok, res, after


def test_lab_from_plates_shared_gears():
    lua = _lua()
    ok, res, inv = _craft(lua, {"iron-plate": 36, "copper-plate": 15}, "lab", 1)
    assert ok, res
    assert inv == {"lab": 1}


def test_two_labs_exact_and_one_plate_short():
    lua = _lua()
    ok, res, inv = _craft(lua, {"iron-plate": 72, "copper-plate": 30}, "lab", 2)
    assert ok, res
    assert inv == {"lab": 2}
    ok, res, inv = _craft(lua, {"iron-plate": 71, "copper-plate": 30}, "lab", 2)
    assert not ok
    assert "iron-plate x1" in res and "Nothing was crafted" in res and "copper" not in res
    assert inv == {"iron-plate": 71, "copper-plate": 30}


def test_lab_uses_held_intermediates_first():
    lua = _lua()
    ok, res, inv = _craft(
        lua, {"iron-gear-wheel": 10, "electronic-circuit": 10, "iron-plate": 6}, "lab", 1
    )
    assert ok, res
    assert inv == {"lab": 1}


def test_shortage_lists_totals():
    lua = _lua()
    ok, res, inv = _craft(lua, {}, "lab", 1)
    assert not ok
    assert "still missing ingredients - " in res
    assert "iron-plate x36" in res and "copper-plate x15" in res
    assert inv == {}


@pytest.mark.parametrize(
    "name,count,inv,leftover",
    [
        ("assembling-machine-1", 1, {"iron-plate": 22, "copper-plate": 5}, {"copper-cable": 1}),
        ("electric-mining-drill", 2, {"iron-plate": 46, "copper-plate": 9}, {}),
        ("inserter", 3, {"iron-plate": 12, "copper-plate": 5}, {"copper-cable": 1}),
        ("transport-belt", 10, {"iron-plate": 15}, {}),
        ("automation-science-pack", 5, {"iron-plate": 10, "copper-plate": 5}, {}),
        ("logistic-science-pack", 2, {"iron-plate": 11, "copper-plate": 3}, {}),
    ],
)
def test_multi_level_exact(name, count, inv, leftover):
    lua = _lua()
    ok, res, after = _craft(lua, inv, name, count)
    assert ok, res
    want = {name: count}
    want.update({k: v for k, v in leftover.items() if v})
    assert after == want


def test_machine_only_intermediate_is_named():
    lua = _lua()
    ok, res, inv = _craft(lua, {"iron-plate": 20, "steel-plate": 5}, "car", 1)
    assert not ok
    assert "engine-unit x8 (" in res and "advanced-crafting" in res


def test_locked_recipe_message_unchanged():
    lua = _lua()
    ok, res, inv = _craft(lua, {"iron-plate": 100, "copper-plate": 100}, "fast-inserter", 1)
    assert not ok
    assert "not unlocked yet" in res
