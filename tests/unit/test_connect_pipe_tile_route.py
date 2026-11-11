"""connect_entities with pipes: when the route along the game's walking path cannot be
built (it timed out, or led over a cliff, as on a 350-tile pumpjack-to-refinery
route), a tile-by-tile search routes the pipe, and pipe-to-ground carries it under
obstacles up to its reach. Server-free (lupa).
"""

import re
from pathlib import Path

import pytest

lupa = pytest.importorskip("lupa")

ROOT = Path(__file__).resolve().parents[2]
SERVER_LUA = (ROOT / "fle/env/tools/agent/connect_entities/server.lua").read_text()

FAKE = """
local surface = {}
function surface.find_entities_filtered(args) return {} end
function surface.find_entity() return nil end
function surface.can_place_entity() return true end
function surface.get_tile() return {name = "grass-1"} end
game = {surfaces = {[1] = surface}}
defines = {inventory = {character_main = 1}}
rendering = {draw_circle = function() end, draw_line = function() end}
storage = {actions = {}, paths = {}, elapsed_ticks = 0, agent_characters = {}, utils = {}}
"""

DIRS = {0: (0, -1), 4: (1, 0), 8: (0, 1), 12: (-1, 0)}


def _lua():
    lua = lupa.LuaRuntime(unpack_returned_tuples=True)
    lua.execute(FAKE)
    lua.execute(SERVER_LUA)
    return lua


def _route(lua, start, goal, blocked=lambda x, y: False, max_jump=0, budget=0, **kw):
    opts = {
        "start": lua.table_from({"x": start[0], "y": start[1]}),
        "goal": lua.table_from({"x": goal[0], "y": goal[1]}),
        "free": lambda p: not blocked(p.x, p.y),
        "max_jump": max_jump,
        "underground_budget": budget,
    }
    opts.update(kw)
    res = lua.eval("storage.utils.plan_pipe_route")(lua.table_from(opts))
    plan, why = res if isinstance(res, tuple) else (res, None)
    if plan is None:
        return None, why
    out = []
    for i in range(1, len(plan.placements) + 1):
        p = plan.placements[i]
        out.append((p.kind, (p.position.x, p.position.y), p.dir))
    return out, plan


def _check_connected(route, start, goal, max_jump, blocked):
    """Pipes on neighbouring tiles; each underground entrance is followed by its exit
    straight ahead within reach, with in-line tiles before and after."""
    assert route[0] == ("pipe", start, route[0][2])
    assert route[-1][0] == "pipe" and route[-1][1] == goal
    i = 0
    while i < len(route) - 1:
        kind, (x, y), d = route[i]
        nkind, (nx, ny), nd = route[i + 1]
        if kind == "in":
            assert nkind == "out" and nd == d
            dx, dy = DIRS[d]
            k = round((nx - x) * dx + (ny - y) * dy)
            assert (nx, ny) == (x + dx * k, y + dy * k) and 2 <= k <= max_jump
            px, py = route[i - 1][1]
            assert (x - px, y - py) == (dx, dy), "entrance fed from straight behind"
            ax, ay = route[i + 2][1]
            assert (ax - nx, ay - ny) == (dx, dy), "exit feeds straight ahead"
        else:
            assert abs(nx - x) + abs(ny - y) == 1, (route[i], route[i + 1])
        i += 1
    for kind, (x, y), _ in route:
        assert not blocked(x, y), f"{kind} on a blocked tile ({x}, {y})"


def test_straight_route_on_open_ground():
    lua = _lua()
    route, plan = _route(lua, (0.5, 0.5), (50.5, 0.5))
    assert len(route) == 51 and plan.undergrounds == 0
    _check_connected(route, (0.5, 0.5), (50.5, 0.5), 0, lambda x, y: False)


def test_the_350_tile_crude_oil_route():
    """Pumpjack (-280.5, -313.5) to refinery (-55.5, -65.5), with a cliff band beside
    the pumpjack that the walking path went 50 tiles round (and then over)."""
    lua = _lua()
    start, goal = (-278.5, -311.5), (-57.5, -67.5)

    def cliffs(x, y):  # a band across the whole search area: no way round
        return -500 <= x <= 200 and -300 <= y <= -297

    route, plan = _route(lua, start, goal, blocked=cliffs, max_jump=9, budget=24)
    assert route is not None, plan
    _check_connected(route, start, goal, 9, cliffs)
    manhattan = abs(goal[0] - start[0]) + abs(goal[1] - start[1])
    tiles_covered = manhattan + 1
    # the band is crossed underground in place, not walked round
    assert plan.pipes + plan.undergrounds <= tiles_covered
    assert plan.undergrounds <= 24
    crossings = [
        (route[i][1], route[i + 1][1])
        for i in range(len(route) - 1)
        if route[i][0] == "in" and route[i][1][1] < -300 and route[i + 1][1][1] > -297
    ]
    assert len(crossings) == 1, "the band is crossed underground"
    assert plan.expanded < 60000


def test_without_pipe_to_ground_a_band_wider_than_the_search_fails_with_a_reason():
    lua = _lua()

    def band(x, y):
        return 10 <= y <= 12

    route, why = _route(lua, (0.5, 0.5), (0.5, 30.5), blocked=band, margin=10)
    assert route is None
    assert "without pipe-to-ground" in why


def test_pipe_to_ground_crosses_a_band_up_to_its_reach():
    lua = _lua()

    def band(x, y):
        return 10 <= y <= 12

    route, plan = _route(lua, (0.5, 0.5), (0.5, 30.5), blocked=band, max_jump=9, margin=10)
    assert route is not None, plan
    _check_connected(route, (0.5, 0.5), (0.5, 30.5), 9, band)
    assert plan.undergrounds == 2


def test_an_obstacle_thicker_than_the_reach_is_not_crossed():
    lua = _lua()

    def band(x, y):
        return 10 <= y <= 20

    route, why = _route(lua, (0.5, 0.5), (0.5, 40.5), blocked=band, max_jump=9, margin=10)
    assert route is None
    assert "crosses at most 8 blocked tiles" in why


def test_held_pipe_to_ground_shortens_straight_runs():
    lua = _lua()
    route, plan = _route(lua, (0.5, 0.5), (40.5, 0.5), max_jump=9, budget=4)
    _check_connected(route, (0.5, 0.5), (40.5, 0.5), 9, lambda x, y: False)
    assert plan.undergrounds == 4
    assert plan.pipes == 41 - 2 * 9 - 2 * 1 + 0  # two pairs each replace 10 tiles by 2
    route0, plan0 = _route(lua, (0.5, 0.5), (40.5, 0.5), max_jump=9, budget=0)
    assert plan0.undergrounds == 0 and plan0.pipes == 41


def test_pipe_to_ground_reach_falls_back_to_the_game_value():
    lua = _lua()
    assert lua.eval("storage.utils.underground_pipe_reach")("pipe-to-ground") == 10


def test_fast_underground_belt_lays_fast_transport_belt():
    table = re.search(r"local default_connect_types = \{(.*?)\}", SERVER_LUA, re.S).group(1)
    assert "['fast-underground-belt'] = 'fast-transport-belt'" in table


def test_long_underground_routes_have_no_placement_cap():
    assert "MAX_INDEX_PLACEMENT" not in SERVER_LUA
