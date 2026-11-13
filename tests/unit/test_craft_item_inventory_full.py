"""craft_item with a full inventory never uses ingredients and loses the product. Server-free (Lua via lupa).

Before: the space check covered only the final product. An intermediate that did not fit went to
`spill_item_stack(position, stack)`, the Factorio 1.x two-argument form, which errors in 2.0 after the
step's ingredients had been removed: the ingredients and the intermediate were gone. Now every step's
slot use is checked before anything is crafted, and a step whose product still does not fit is undone.
"""

from pathlib import Path

import pytest

lupa = pytest.importorskip("lupa")

CRAFT_LUA = (
    Path(__file__).resolve().parents[2] / "fle/env/tools/agent/craft_item/server.lua"
)

# name: (product amount, {ingredient: amount})
RECIPES = {
    "iron-gear-wheel": (1, {"iron-plate": 2}),
    "copper-cable": (2, {"copper-plate": 1}),
    "electronic-circuit": (1, {"iron-plate": 1, "copper-cable": 3}),
    "transport-belt": (2, {"iron-plate": 1, "iron-gear-wheel": 1}),
    "pipe": (1, {"iron-plate": 1}),
    "electric-mining-drill": (1, {"electronic-circuit": 3, "iron-gear-wheel": 5, "iron-plate": 10}),
}

# An inventory of SLOTS slots holding whole stacks of STACK items: slot use is ceil(count / STACK)
# per item, as the game fills part-filled stacks first.
SETUP = """
inv = {}
recipes = {}
spills = {}
SLOTS = 10
STACK = 10
insert_cap = {}   -- name -> max items an insert may add (simulates a surprise the plan did not see)
local function count(name) return inv[name] or 0 end
local function used()
  local n = 0
  for _, c in pairs(inv) do if c > 0 then n = n + math.ceil(c / STACK) end end
  return n
end
character = {
  prototype = {crafting_categories = {crafting = true}},
  position = {x = 0, y = 0},
  force = {recipes = recipes, technologies = {},
           get_item_production_statistics = function() return {on_flow = function() end} end},
}
character.surface = {spill_item_stack = function(t, extra)
  -- the Factorio 2.0 form: one table {position=..., stack={name=..., count=...}}
  if extra ~= nil or type(t) ~= "table" or t.stack == nil then
    error("Arguments count error for 'spill_item_stack': Expected 1 argument but 2 were given")
  end
  spills[#spills + 1] = t.stack.name .. " x" .. t.stack.count
end}
function character.get_item_count(name) return count(name) end
function character.remove_item(st) inv[st.name] = count(st.name) - st.count; return st.count end
function character.insert(st)
  local room = (SLOTS - used()) * STACK + ((STACK - count(st.name) % STACK) % STACK)
  local n = math.min(st.count, room)
  if insert_cap[st.name] then n = math.min(n, insert_cap[st.name]) end
  inv[st.name] = count(st.name) + n
  return n
end
function character.get_main_inventory()
  local slots = {}
  local i = 0
  for name, c in pairs(inv) do
    local left = c
    while left > 0 do
      i = i + 1
      slots[i] = {valid_for_read = true, name = name, count = math.min(left, STACK)}
      left = left - STACK
    end
  end
  for j = i + 1, SLOTS do slots[j] = {valid_for_read = false} end
  return slots
end
prototypes = {item = setmetatable({}, {__index = function() return {stack_size = STACK} end})}
game = {surfaces = {{}}}
storage = {actions = {}, fast = true, elapsed_ticks = 0, crafted_items = {},
           utils = {ensure_valid_character = function() return character end}}
"""


def _lua():
    lua = lupa.LuaRuntime(unpack_returned_tuples=True)
    lua.execute(SETUP)
    recipes = lua.globals().recipes
    for name, (amount, ings) in RECIPES.items():
        recipes[name] = lua.table_from(
            {
                "name": name,
                "category": "crafting",
                "energy": 0.5,
                "enabled": True,
                "products": lua.table_from([lua.table_from({"name": name, "amount": amount, "type": "item"})]),
                "ingredients": lua.table_from([lua.table_from({"name": i, "amount": a}) for i, a in ings.items()]),
            }
        )
    lua.execute(CRAFT_LUA.read_text())
    return lua


def _craft(lua, inv, name, count, cap=None):
    g = lua.globals()
    for k, v in inv.items():
        g.inv[k] = v
    for k, v in (cap or {}).items():
        g.insert_cap[k] = v
    ok, res = lua.eval("function(n, c) return pcall(storage.actions.craft_item, 1, n, c) end")(name, count)
    after = {k: v for k, v in g.inv.items() if v}
    return ok, res, after, list(g.spills.values())


def test_full_inventory_with_intermediates_crafts_nothing_and_uses_nothing():
    lua = _lua()
    # 10 slots: 4 iron-plate stacks (40), 1 copper (10), 4 of stone: 1 free, enough for the drill itself.
    # On the way the cables take that slot and the circuits need one more: the old check passed here.
    inv = {"iron-plate": 40, "copper-plate": 10, "stone": 40}
    ok, res, after, spills = _craft(lua, inv, "electric-mining-drill", 1)
    assert not ok
    assert "Inventory is full - crafting electronic-circuit on the way needs 1 more free slot" in res
    assert "Nothing was crafted" in res
    assert after == inv  # nothing used
    assert spills == []


def test_fits_when_ingredients_free_their_slots():
    lua = _lua()
    # 1 free slot, exactly the plates needed: each step's ingredients free the slots its product takes
    inv = {"iron-plate": 23, "copper-plate": 5, "stone": 50}
    ok, res, after, spills = _craft(lua, inv, "electric-mining-drill", 1)
    assert ok, res
    assert after == {"electric-mining-drill": 1, "copper-cable": 1, "stone": 50}
    assert spills == []


def test_surprise_overflow_undoes_the_step_and_keeps_everything():
    lua = _lua()
    # the plan fits, but the game takes only 1 of the 2 belts of the last step (a surprise):
    # that step is undone (its gear and plate come back), the gear crafted before stays
    inv = {"iron-plate": 3}
    ok, res, after, spills = _craft(lua, inv, "transport-belt", 2, cap={"transport-belt": 1})
    assert not ok
    assert "no room for 2 transport-belt" in res and "undone" in res
    assert "The craft step before it was done" in res
    assert after == {"iron-gear-wheel": 1, "iron-plate": 1}
    assert spills == []


def test_final_product_check_unchanged():
    lua = _lua()
    inv = {"iron-plate": 100}  # 10 slots full of plates: 30 pipes need 3 more slots (plates free them only later)
    ok, res, after, _ = _craft(lua, inv, "pipe", 30)
    assert not ok and "Inventory is full - requires 3 slots but only 0 available" in res
    assert after == inv


def test_no_two_argument_spill_call_left():
    src = CRAFT_LUA.read_text()
    assert "spill_item_stack(player.position" not in src
