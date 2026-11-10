"""preview_inserter: pickup / drop positions and targets before building (no server).

The action runs in Lua (lupa) against a stub surface with a belt west of the
tile and a furnace east of it."""

from pathlib import Path

import pytest

from fle.env.entities import Direction, InserterPreview, Position

SERVER_LUA = (
    Path(__file__).resolve().parents[2]
    / "fle/env/tools/agent/preview_inserter/server.lua"
)

STUB_LUA = """
defines = {direction = {north = 0, east = 4, south = 8, west = 12}}
prototypes = {entity = {
    ["burner-inserter"] = {type = "inserter",
        inserter_pickup_position = {0, -1}, inserter_drop_position = {0, 1.2}},
    ["iron-chest"] = {type = "container"},
}}
local function ent(name, type, x, y, w, inv)
    return {valid = true, name = name, type = type, position = {x = x, y = y}, w = w,
            get_max_inventory_index = function() return inv end}
end
local found = {
    ent("transport-belt", "transport-belt", 9.5, 4.5, 0.5, 1),
    ent("stone-furnace", "furnace", 12.0, 5.0, 1.0, 3),
    ent("character", "character", 10.5, 3.5, 0.5, 8),
}
local surface = {find_entities_filtered = function(f)
    local out = {}
    for _, e in ipairs(found) do
        if math.abs(f.position.x - e.position.x) < e.w and math.abs(f.position.y - e.position.y) < e.w then
            table.insert(out, e)
        end
    end
    return out
end}
storage = {actions = {}, agent_characters = {{surface = surface}}, utils = {
    -- place_entity's mapping for inserters: the requested direction is the drop side
    get_entity_direction = function(entity, d) return (d + 8) % 16 end,
}}
"""


def _run(direction, x=10.3, y=4.9, name="burner-inserter"):
    lupa = pytest.importorskip("lupa")
    lua = lupa.LuaRuntime()
    lua.execute(STUB_LUA)
    lua.execute(SERVER_LUA.read_text())
    return lua.eval("storage.actions.preview_inserter")(1, name, direction, x, y)


def _pos(t):
    return (t.x, t.y)


def test_drop_east_from_belt_into_furnace():
    r = _run(4)  # FLE RIGHT (Factorio east) -> built facing west
    assert _pos(r.position) == (10.5, 4.5)
    assert _pos(r.pickup_position) == (9.5, 4.5)
    assert r.pickup_target == '"transport-belt"'
    assert _pos(r.drop_position) == (11.5, 4.5)
    assert r.drop_target == '"stone-furnace"'
    assert _pos(r.drop_target_position) == (12.0, 5.0)


def test_nothing_there_and_character_ignored():
    r = _run(0)  # FLE UP: drops north, picks up south
    assert _pos(r.pickup_position) == (10.5, 5.5)
    assert _pos(r.drop_position) == (10.5, 3.5)
    assert r.drop_target is None  # only the character is there
    assert r.pickup_target is None


def test_not_an_inserter_is_an_error():
    lupa = pytest.importorskip("lupa")
    with pytest.raises(lupa.LuaError, match="is not an inserter"):
        _run(0, name="iron-chest")


def test_preview_repr():
    p = InserterPreview(
        position=Position(x=10.5, y=4.5),
        direction=Direction.RIGHT,
        pickup_position=Position(x=9.5, y=4.5),
        pickup_target="transport-belt",
        pickup_target_position=Position(x=9.5, y=4.5),
        drop_position=Position(x=11.5, y=4.5),
    )
    assert repr(p) == (
        "InserterPreview(position=(10.5, 4.5), direction=RIGHT, "
        "pickup_position=(9.5, 4.5), pickup_target=transport-belt at (9.5, 4.5), "
        "drop_position=(11.5, 4.5), drop_target=nothing)"
    )
