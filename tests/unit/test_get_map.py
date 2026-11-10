"""get_map: the client renders the server's grid with axes and a legend
(execute stubbed); the action is run in Lua (lupa) against a stub surface."""

from pathlib import Path

import pytest

from fle.env.entities import Position, TileMap
from fle.env.tools.agent.get_map.client import GetMap, column_header

SERVER_LUA = (
    Path(__file__).resolve().parents[2] / "fle/env/tools/agent/get_map/server.lua"
)


def _tool(response, sent=None):
    tool = object.__new__(GetMap)
    tool.player_index = 1

    def execute(*args):
        if sent is not None:
            sent.append(args)
        return response, 0

    tool.execute = execute
    return tool


RESP = {
    "x0": -1,
    "x1": 1,
    "y0": 9,
    "y1": 11,
    "player_x": 0,
    "player_y": 10,
    "rows": {1: "..S", 2: "e@>", 3: "~~i"},
    "legend": {
        1: {"symbol": "S", "text": "stone-furnace (1)"},
        2: {"symbol": "INSERTER", "text": "inserter, pointing at the side it drops on: inserter 1"},
        3: {"symbol": "i", "text": "iron-ore (1 tiles)"},
    },
}


def test_renders_axes_rows_and_legend():
    out = _tool(RESP)(Position(x=0, y=10), radius=1)
    assert isinstance(out, TileMap)
    assert (out.x0, out.y0, out.x1, out.y1) == (-1, 9, 1, 11)
    assert out.rows == ["..S", "→@>", "~~i"]
    assert out.legend["S"] == "stone-furnace (1)"
    assert out.at(1.5, 9.2) == "S" and out.at(-1, 11) == "~" and out.at(0, 10) == "@"
    assert out.at(2, 9) is None and out.at(0, 12) is None
    lines = str(out).splitlines()
    assert lines[0].startswith("Map x -1..1, y 9..11 (3 x 3 tiles), one character per tile.")
    assert "its centre is Position(x + 0.5, y + 0.5)" in lines[0]
    assert lines[1] == "You are on tile x=0, y=10."
    # x of each column, top to bottom: sign row, then the digit
    assert lines[2:4] == ["   -  ", "   101"]
    assert lines[4:7] == [" 9 ..S", "10 →@>", "11 ~~i"]
    assert lines[7] == "Legend:"
    assert "  S stone-furnace (1)" in lines
    assert "  ↑ → ↓ ← inserter, pointing at the side it drops on: inserter 1" in lines


def test_column_header_reads_top_to_bottom():
    assert column_header(-12, -9) == ["----", "111 ", "2109"]
    assert column_header(8, 11) == ["  11", "8901"]
    assert column_header(98, 101) == ["  11", "9900", "8901"]
    # every column spells its own x
    lines = column_header(-3, 104)
    for i, x in enumerate(range(-3, 105)):
        column = "".join(line[i] for line in lines).replace(" ", "")
        assert int(column) == x


def test_area_sent_to_the_server():
    sent = []
    _tool(RESP, sent)(Position(x=0.5, y=10.5), radius=1)
    assert sent[-1] == (1, -1, 9, 1, 11, None)
    _tool(RESP, sent)(radius=7)
    assert sent[-1] == (1, None, None, None, None, 7)
    _tool(RESP, sent)(
        left_top=Position(x=-20.5, y=5), right_bottom=Position(x=10.2, y=25.9)
    )
    assert sent[-1] == (1, -21, 5, 10, 25, None)
    # 64 x 64 is the largest box
    _tool(RESP, sent)(left_top=Position(x=0, y=0), right_bottom=Position(x=63, y=63))
    assert sent[-1] == (1, 0, 0, 63, 63, None)


def test_size_cap_and_argument_errors():
    with pytest.raises(ValueError) as e:
        _tool({})(left_top=Position(x=0, y=0), right_bottom=Position(x=64, y=10))
    assert str(e.value) == (
        "The map area is 65 x 11 tiles; the most one call returns is 64 x 64 tiles"
    )
    with pytest.raises(ValueError):
        _tool({})(radius=0)
    with pytest.raises(ValueError) as e:
        _tool({})(radius=32)
    assert "64 x 64 tiles" in str(e.value)
    with pytest.raises(ValueError):
        _tool({})(left_top=Position(x=0, y=0))
    with pytest.raises(ValueError):
        _tool({})(
            Position(x=0, y=0),
            left_top=Position(x=0, y=0),
            right_bottom=Position(x=1, y=1),
        )
    with pytest.raises(ValueError):
        _tool({})(position=(1, 2))


def test_server_error_is_reported():
    with pytest.raises(Exception) as e:
        _tool('[string "x"]:3: "boom"')(radius=3)
    assert str(e.value) == "Could not get map: boom"


def test_prints_as_a_grid():
    resp = {"x0": 0, "x1": 1, "y0": 0, "y1": 1, "rows": [".@", ".."], "legend": []}
    out = _tool(resp)(radius=1)
    assert "\\n" not in repr((out,))
    assert repr(out) == str(out) == out.text


def test_survives_being_rebuilt_field_by_field():
    """A process boundary that rebuilds FLE data models from their fields keeps the map printable."""
    out = _tool(RESP)(Position(x=0, y=10), radius=1)
    rebuilt = TileMap.model_construct(**dict(out.__dict__))
    assert repr(rebuilt) == repr(out) and rebuilt.at(0, 10) == "@"


# --- the action, in Lua ----------------------------------------------------------------------------

STUB_LUA = """
defines = {direction = {north = 0, east = 4, south = 8, west = 12}}
local function ent(name, type, x, y, w, h, extra)
    local e = {valid = true, name = name, type = type, position = {x = x, y = y},
               bounding_box = {left_top = {x = x - w / 2, y = y - h / 2},
                               right_bottom = {x = x + w / 2, y = y + h / 2}}}
    for k, v in pairs(extra or {}) do e[k] = v end
    return e
end
world = {
    ent("iron-ore", "resource", 2.5, 0.5, 0.8, 0.8),
    ent("iron-ore", "resource", 3.5, 0.5, 0.8, 0.8),
    ent("stone-furnace", "furnace", 2.0, 2.0, 1.6, 1.6),
    ent("transport-belt", "transport-belt", 0.5, 0.5, 0.8, 0.8, {direction = 4}),
    ent("transport-belt", "transport-belt", 1.5, 0.5, 0.8, 0.8, {direction = 8}),
    ent("burner-inserter", "inserter", 1.5, 3.5, 0.3, 0.3, {drop_position = {x = 1.5, y = 2.3}}),
    ent("pipe", "pipe", 3.5, 2.5, 0.6, 0.6),
    ent("small-electric-pole", "electric-pole", 3.5, 1.5, 0.3, 0.3),
    ent("electric-mining-drill", "mining-drill", 2.5, 0.5, 0.8, 0.8),
    ent("character", "character", 0.5, 3.5, 0.4, 0.4),
    ent("tree-01", "tree", 3.5, 3.5, 0.4, 0.4),
    ent("cliff", "cliff", 40.5, 0.5, 0.9, 0.9),
}
local surface = {
    find_tiles_filtered = function(f)
        return {{name = "water", position = {x = 0, y = 1}}, {name = "grass-1", position = {x = 1, y = 1}},
                {name = "deepwater", position = {x = 40, y = 1}}}
    end,
    is_chunk_generated = function(chunk) return chunk.x == 0 end,
    find_entities_filtered = function(f)
        local out = {}
        for _, e in ipairs(world) do
            if e.position.x >= f.area[1][1] and e.position.x < f.area[2][1]
                and e.position.y >= f.area[1][2] and e.position.y < f.area[2][2] then
                table.insert(out, e)
            end
        end
        return out
    end,
}
-- chunk x = 0 is generated; chunk x = 1 (tiles 32..63) is neither generated nor charted
local force = {is_chunk_charted = function(s, chunk) return false end}
local player = {valid = true, position = {x = 0.5, y = 3.5}, surface = surface, force = force}
storage = {actions = {}, utils = {ensure_valid_character = function() return player end}}
"""


def _run(*args):
    lupa = pytest.importorskip("lupa")
    lua = lupa.LuaRuntime()
    lua.execute(STUB_LUA)
    lua.execute(SERVER_LUA.read_text())
    return lua, lua.eval("storage.actions.get_map")(1, *args)


def _rows(result):
    return [result.rows[i].strip('"') for i in range(1, len(result.rows) + 1)]


def _legend(result):
    return {
        result.legend[i].symbol.strip('"'): result.legend[i].text.strip('"')
        for i in range(1, len(result.legend) + 1)
    }


def test_action_rows_and_legend():
    _, result = _run(0, 0, 3, 3, None)
    rows = _rows(result)
    assert rows[0] == ">vEi"
    assert rows[1] == "~SS|"
    assert rows[2] == ".SS="
    assert rows[3] == "@n.%"
    legend = _legend(result)
    assert legend["S"] == "stone-furnace (1)"
    assert legend["E"] == "electric-mining-drill (1)"
    assert legend["^ > v <"] == "belt, pointing the way it moves items: transport-belt 2"
    assert legend["INSERTER"] == "inserter, pointing at the side it drops on: burner-inserter 1"
    assert legend["="] == "pipe: pipe 1"
    assert legend["|"] == "electric pole: small-electric-pole 1"
    assert legend["i"] == "iron-ore (2 tiles)"
    assert legend["~"] == "water (1 tiles)"
    assert legend["%"] == "tree (1)"
    assert legend["@"] == "you"
    assert "?" not in legend
    assert (result.player_x, result.player_y) == (0, 3)


def test_action_radius_around_the_character():
    _, result = _run(None, None, None, None, 2)
    assert (result.x0, result.y0, result.x1, result.y1) == (-2, 1, 2, 5)


def test_action_uncharted_tiles_show_nothing():
    _, result = _run(30, 0, 41, 1, None)
    rows = _rows(result)
    assert rows[0] == ".." + "?" * 10
    assert rows[1] == ".." + "?" * 10  # the cliff and water out there are not reported
    legend = _legend(result)
    assert legend["?"] == "not generated or charted (20 tiles)"
    assert "#" not in legend and "~" not in legend


def test_action_refuses_more_than_64_tiles():
    lupa = pytest.importorskip("lupa")
    with pytest.raises(lupa.LuaError) as e:
        _run(0, 0, 64, 10, None)
    assert "The map area is 65 x 11 tiles; the most one call returns is 64 x 64 tiles" in str(e.value)
    _run(0, 0, 63, 63, None)  # 64 x 64 is allowed


def test_inserter_letters_are_never_resources():
    lua, _ = _run(0, 0, 3, 3, None)
    lua.execute(
        """
        world = {}
        for i, name in ipairs({"nickel-ore", "sand", "water-ore", "eel"}) do
            table.insert(world, {valid = true, name = name, type = "resource",
                position = {x = i - 0.5, y = 0.5},
                bounding_box = {left_top = {x = i - 1, y = 0}, right_bottom = {x = i, y = 1}}})
        end
        """
    )
    result = lua.eval("storage.actions.get_map")(1, 0, 0, 3, 0, None)
    row = _rows(result)[0]
    assert not set(row) & set("nesw")
    assert len(set(row)) == 4
