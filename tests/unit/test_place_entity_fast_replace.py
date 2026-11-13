"""place_entity builds as a player does: the pre-check (build_check_type manual) accepts a fast-replace
spot (a belt onto an underground belt or a splitter), so the build uses fast_replace too, and the
replaced entity's item goes back to the character (it is not a LuaPlayer, so the game would not give it).
Before: create_entity had no fast_replace and returned nil ("create_entity returned nil ... blocking=
underground-belt"). The helpers run in lupa against a small map. Server-free.
"""

from pathlib import Path

import pytest

lupa = pytest.importorskip("lupa")

ROOT = Path(__file__).resolve().parents[2]
UTILS = (ROOT / "fle/env/mods/utils.lua").read_text()
PLACE = (ROOT / "fle/env/tools/agent/place_entity/server.lua").read_text()


def _helpers():
    a = UTILS.index("storage.utils.fast_replace_victims = function")
    b = UTILS.index("storage.utils.avoid_entity = function")
    return UTILS[a:b]


MAP = """
storage = {utils = {}}
defines = {direction = {north = 0, east = 4, south = 8, west = 12}}
GROUPS = {["transport-belt"] = "transport-belt", ["underground-belt"] = "transport-belt",
          splitter = "transport-belt", pipe = "pipe", ["pipe-to-ground"] = "pipe", ["iron-chest"] = "container"}
BOX = {splitter = {left_top = {x = -0.9, y = -0.4}, right_bottom = {x = 0.9, y = 0.4}}}
prototypes = {entity = setmetatable({}, {__index = function(_, n)
  return {fast_replaceable_group = GROUPS[n], collision_box = BOX[n] or {left_top = {x = -0.4, y = -0.4}, right_bottom = {x = 0.4, y = 0.4}},
          items_to_place_this = {{name = n, count = 1}}}
end})}
ents = {}
spills = {}
function add(name, x, y)
  local e = {valid = true, name = name, type = name, position = {x = x, y = y}}
  e.prototype = prototypes.entity[name]
  ents[#ents + 1] = e
  return e
end
surface = {}
function surface.can_fast_replace(t)
  for _, e in ipairs(ents) do
    if e.valid and math.abs(e.position.x - t.position.x) < 1 and math.abs(e.position.y - t.position.y) < 0.5
       and GROUPS[e.name] == GROUPS[t.name] then return true end
  end
  return false
end
function surface.find_entities_filtered(f)
  local r = {}
  for _, e in ipairs(ents) do
    local x, y = e.position.x, e.position.y
    local bx = BOX[e.name] and 0.9 or 0.4
    if e.valid and x + bx > f.area[1][1] and x - bx < f.area[2][1] and y + 0.4 > f.area[1][2] and y - 0.4 < f.area[2][2] then
      r[#r + 1] = e
    end
  end
  return r
end
function surface.spill_item_stack(t) spills[#spills + 1] = t.stack.name .. " x" .. t.stack.count end
inv = {}
room = 100
character = {position = {x = 0, y = 0}, surface = surface}
function character.insert(st) local n = math.min(st.count, room); room = room - n; inv[st.name] = (inv[st.name] or 0) + n; return n end
"""


def _lua():
    lua = lupa.LuaRuntime(unpack_returned_tuples=True)
    lua.execute(MAP)
    lua.execute(_helpers())
    return lua


def _victims(lua, name, x, y):
    return lua.eval(
        "function(n, x, y) local v = storage.utils.fast_replace_victims(surface, n, {x = x, y = y}, 0, 'player')"
        " local out = {} for i, e in ipairs(v) do out[i] = e.name end return out end"
    )(name, x, y)


def test_belt_onto_underground_and_splitter_are_victims():
    lua = _lua()
    lua.execute("add('underground-belt', 55.5, -55.5); add('splitter', -18, -12.5); add('iron-chest', 5.5, 5.5)")
    assert list(_victims(lua, "transport-belt", 55.5, -55.5).values()) == ["underground-belt"]
    assert list(_victims(lua, "transport-belt", -18.5, -12.5).values()) == ["splitter"]
    # another group, or nothing there: no victims
    assert len(_victims(lua, "transport-belt", 5.5, 5.5)) == 0
    assert len(_victims(lua, "pipe", 55.5, -55.5)) == 0
    assert len(_victims(lua, "transport-belt", 70.5, 70.5)) == 0


def test_replaced_item_goes_back_or_is_spilled():
    lua = _lua()
    lua.execute("ug = add('underground-belt', 1.5, 1.5)")
    notes = lua.eval(
        "function() local v = storage.utils.fast_replace_victims(surface, 'transport-belt', {x = 1.5, y = 1.5}, 0, 'player')"
        " ug.valid = false return storage.utils.return_replaced(character, v) end"
    )()
    assert list(notes.values()) == ["replaced underground-belt at (1.5, 1.5) (as in the game); its underground-belt went back to your inventory"]
    assert lua.eval("inv['underground-belt']") == 1
    lua.execute("room = 0; sp = add('splitter', 4, 1.5)")
    notes = lua.eval(
        "function() local v = storage.utils.fast_replace_victims(surface, 'transport-belt', {x = 3.5, y = 1.5}, 0, 'player')"
        " sp.valid = false return storage.utils.return_replaced(character, v) end"
    )()
    assert "spilled at your feet" in list(notes.values())[0]
    assert list(lua.eval("spills").values()) == ["splitter x1"]


def test_still_standing_victim_gives_nothing():
    lua = _lua()
    lua.execute("add('underground-belt', 1.5, 1.5)")
    notes = lua.eval(
        "function() local v = storage.utils.fast_replace_victims(surface, 'transport-belt', {x = 1.5, y = 1.5}, 0, 'player')"
        " return storage.utils.return_replaced(character, v) end"
    )()
    assert len(notes) == 0 and lua.eval("inv['underground-belt']") is None


def test_build_spec_matches_the_pre_check():
    spec = PLACE[PLACE.index("local function build_spec(at, no_replace)"):]
    spec = spec[: spec.index("return spec")]
    assert "build_check_type = defines.build_check_type.manual" in spec and "fast_replace = true" in spec
    # the exact placement replaces and hands the item back; a nearby spot never replaces
    assert "storage.utils.return_replaced(player, victims)" in PLACE
    assert "create_entity(build_spec(new_position, true))" in PLACE
    assert "storage.utils.can_place_entity(player, entity, position, entity_direction)" in PLACE


def test_can_place_entity_says_place_entity_would_replace():
    from fle.env.tools.agent.can_place_entity.client import placement_check

    src = (ROOT / "fle/env/tools/agent/can_place_entity/server.lua").read_text()
    assert "place_entity does not build over or replace another entity" not in src
    assert 'return finish(true, "place_entity would replace "' in src
    note = '"place_entity would replace underground-belt (input) at (1.5, 1.5), as in the game; its item goes back to your inventory"'
    base = {"fits": True, "in_reach": True, "in_inventory": 3, "position": {"x": 1.5, "y": 1.5}, "reason": note}
    pc = placement_check("transport-belt", None, base)
    assert pc.can_place and pc.fits and pc.reason == note.strip('"')
    pc = placement_check("transport-belt", None, dict(base, in_inventory=0))
    assert not pc.can_place and pc.reason.startswith("fits, but no transport-belt in your inventory; place_entity would replace")
    pc = placement_check("transport-belt", None, dict(base, reason=None))
    assert pc.can_place and pc.reason is None
