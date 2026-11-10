"""get_map client: renders the server's grid and legend (execute stubbed)."""

import pytest

from fle.env.entities import Position
from fle.env.tools.agent.get_map.client import GetMap


def _tool(response):
    tool = object.__new__(GetMap)
    tool.player_index = 1
    tool.execute = lambda *args: (response, 0)
    return tool


def test_renders_rows_and_legend():
    resp = {
        "x0": -1,
        "x1": 1,
        "y0": 9,
        "y1": 11,
        "rows": {1: "..S", 2: ".@>", 3: "~~i"},
        "legend": {
            1: {"symbol": "S", "text": "stone-furnace (1)"},
            2: {"symbol": "i", "text": "iron-ore (1 tiles)"},
        },
    }
    out = _tool(resp)(Position(x=0, y=10), radius=1)
    lines = out.splitlines()
    assert lines[0].startswith("Map x -1..1 (left to right), y 9..11")
    assert lines[1:4] == [" 9 ..S", "10 .@>", "11 ~~i"]
    assert "  S stone-furnace (1)" in lines


def test_radius_bounds():
    with pytest.raises(ValueError):
        _tool({})(radius=0)
    with pytest.raises(ValueError):
        _tool({})(radius=33)


def test_server_error_is_reported():
    with pytest.raises(Exception) as e:
        _tool('[string "x"]:3: "boom"')(radius=3)
    assert str(e.value) == "Could not get map: boom"


def test_prints_as_a_grid():
    resp = {"x0": 0, "x1": 1, "y0": 0, "y1": 1, "rows": [".@", ".."], "legend": []}
    out = _tool(resp)(radius=1)
    assert "\\n" not in repr((out,))
    assert repr(out) == str(out)
