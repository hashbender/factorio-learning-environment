"""connect_entities with pipe-to-ground: routes run underground wherever a straight run
allows, at the game's full reach (an exit up to max_underground_distance = 10 tiles past
its entrance), back to back; surface pipes stay at the ends, at turns and where the
pipe-to-ground held run out (the plan then says how many it had room for).
Prototype.UndergroundPipe alone is a straight line of pairs only. Prototype.Pipe alone
never uses pipe-to-ground. Server-free (lupa), plus the client's choice of route.
"""

from pathlib import Path

import pytest

from fle.env.entities import PipeGroup, Position
from fle.env.game_types import Prototype
from fle.env.tools.agent.connect_entities import client as client_module
from fle.env.tools.agent.connect_entities import dry_run as dr
from fle.env.tools.agent.connect_entities.client import ConnectEntities
from fle.env.tools.agent.connect_entities.path_result import PathResult

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
REACH = 10


def _lua():
    lua = lupa.LuaRuntime(unpack_returned_tuples=True)
    lua.execute(FAKE)
    lua.execute(SERVER_LUA)
    return lua


def _placements(plan):
    out = []
    for i in range(1, len(plan.placements) + 1):
        p = plan.placements[i]
        out.append((p.kind, (p.position.x, p.position.y), p.dir))
    return out


def _route(lua, start, goal, blocked=lambda x, y: False, max_jump=REACH, budget=0, fn="plan_pipe_route", **kw):
    opts = {
        "start": lua.table_from({"x": start[0], "y": start[1]}),
        "goal": lua.table_from({"x": goal[0], "y": goal[1]}),
        "free": lambda p: not blocked(p.x, p.y),
        "max_jump": max_jump,
        "underground_budget": budget,
    }
    opts.update(kw)
    res = lua.eval(f"storage.utils.{fn}")(lua.table_from(opts))
    plan, why = res if isinstance(res, tuple) else (res, None)
    if plan is None:
        return None, why
    return _placements(plan), plan


def _check(route, start, goal, max_jump, blocked=lambda x, y: False):
    """A connected pipe route: neighbours touch; every entrance is fed from straight
    behind and its exit (straight ahead, 1..max_jump tiles on) feeds straight ahead."""
    assert route[0][1] == start and route[-1][1] == goal
    assert route[0][0] == "pipe" and route[-1][0] == "pipe"
    spans = []
    i = 0
    while i < len(route) - 1:
        kind, (x, y), d = route[i]
        nkind, (nx, ny), nd = route[i + 1]
        if kind == "in":
            assert nkind == "out" and nd == d
            dx, dy = DIRS[d]
            k = round((nx - x) * dx + (ny - y) * dy)
            assert (nx, ny) == (x + dx * k, y + dy * k) and 1 <= k <= max_jump
            spans.append(k)
            px, py = route[i - 1][1]
            assert (x - px, y - py) == (dx, dy), "entrance fed from straight behind"
            ax, ay = route[i + 2][1]
            assert (ax - nx, ay - ny) == (dx, dy), "exit feeds straight ahead"
        else:
            assert abs(nx - x) + abs(ny - y) == 1, (route[i], route[i + 1])
        i += 1
    for kind, (x, y), _ in route:
        assert not blocked(x, y)
    return spans


def test_a_straight_run_is_underground_at_full_reach_back_to_back():
    lua = _lua()
    start, goal = (0.5, 0.5), (100.5, 0.5)
    route, plan = _route(lua, start, goal, budget=1000)
    spans = _check(route, start, goal, REACH)
    # 101 tiles: a pipe at each end, 99 tiles between = 9 pairs of 11 tiles
    assert plan.pipes == 2
    assert plan.undergrounds == 18
    assert spans == [REACH] * 9
    assert plan.short_pairs == 0


def test_turns_keep_one_surface_pipe_each():
    lua = _lua()
    start, goal = (0.5, 0.5), (60.5, 60.5)

    def wall(x, y):  # forces an L: only the row y=0.5 and the column x=60.5 are open
        return not (y == 0.5 or x == 60.5)

    route, plan = _route(lua, start, goal, blocked=wall, budget=1000)
    spans = _check(route, start, goal, REACH, wall)
    assert spans and max(spans) == REACH
    # ends + the corner + the few tiles that do not fill a whole pair
    assert plan.pipes <= 3 + 2 * 3
    assert plan.undergrounds >= 20


def test_running_out_of_pipe_to_ground_leaves_surface_pipe_and_is_counted():
    lua = _lua()
    start, goal = (0.5, 0.5), (100.5, 0.5)
    route, plan = _route(lua, start, goal, budget=6)
    _check(route, start, goal, REACH)
    assert plan.undergrounds == 6
    assert plan.short_pairs == 6  # the 6 more pairs the run had room for
    assert plan.pipes == 101 - 3 * 11


def test_without_pipe_to_ground_held_the_plan_is_all_pipe_and_says_what_it_had_room_for():
    lua = _lua()
    route, plan = _route(lua, (0.5, 0.5), (100.5, 0.5), budget=0)
    assert plan.undergrounds == 0 and plan.pipes == 101
    assert plan.short_pairs == 9


def test_no_reach_means_no_tunnels():
    lua = _lua()
    route, plan = _route(lua, (0.5, 0.5), (100.5, 0.5), max_jump=0, budget=1000)
    assert plan.undergrounds == 0 and plan.pipes == 101 and plan.short_pairs == 0


def test_crossings_beyond_what_is_held_fall_back_to_plain_pipes_when_possible():
    lua = _lua()

    def band(x, y):  # a band with a gap at x = 20.5
        return 10 <= y <= 12 and x != 20.5

    route, plan = _route(lua, (0.5, 0.5), (0.5, 30.5), blocked=band, budget=0, margin=30,
                         fn="plan_pipe_route_within_held")
    assert route is not None and plan.undergrounds == 0
    _check(route, (0.5, 0.5), (0.5, 30.5), REACH, band)
    assert plan.wanted_undergrounds >= 2  # what the route with the crossing would have used


def test_crossings_beyond_what_is_held_are_still_planned_when_there_is_no_other_way():
    lua = _lua()

    def band(x, y):
        return 10 <= y <= 12

    route, plan = _route(lua, (0.5, 0.5), (0.5, 30.5), blocked=band, budget=0, margin=10,
                         fn="plan_pipe_route_within_held")
    assert route is not None and plan.undergrounds == 2  # the item check names them


def test_crossings_within_what_is_held_are_used():
    lua = _lua()

    def band(x, y):
        return 10 <= y <= 12 and x != 20.5

    route, plan = _route(lua, (0.5, 0.5), (0.5, 30.5), blocked=band, budget=2, margin=30,
                         fn="plan_pipe_route_within_held")
    assert plan.undergrounds == 2
    assert all(x == 0.5 for _, (x, _y), _ in route), "straight through, under the band"


def test_reach_ten_crosses_nine_blocked_tiles():
    lua = _lua()

    def band(x, y):
        return 10 <= y <= 19  # 9 tiles: y = 10.5 .. 18.5

    route, plan = _route(lua, (0.5, 0.5), (0.5, 40.5), blocked=band, margin=5)
    assert route is not None, plan
    assert max(_check(route, (0.5, 0.5), (0.5, 40.5), REACH, band)) == REACH
    route, why = _route(lua, (0.5, 0.5), (0.5, 40.5), blocked=lambda x, y: 10 <= y <= 20, margin=5)
    assert route is None and "crosses at most 9 blocked tiles" in why


# --- Prototype.UndergroundPipe alone: a straight line of pairs ---------------------


def _line(lua, start, goal, crosses=None):
    opts = {
        "start": lua.table_from({"x": start[0], "y": start[1]}),
        "goal": lua.table_from({"x": goal[0], "y": goal[1]}),
        "reach": REACH,
    }
    if crosses:
        opts["crosses"] = crosses
    res = lua.eval("storage.utils.plan_pipe_to_ground_line")(lua.table_from(opts))
    plan, why = res if isinstance(res, tuple) else (res, None)
    if plan is None:
        return None, why
    return _placements(plan), plan


@pytest.mark.parametrize("d", [1, 2, 9, 10, 11, 12, 21, 22, 35, 100])
def test_pipe_to_ground_line_pairs_back_to_back_within_reach(d):
    lua = _lua()
    start, goal = (0.5, 0.5), (0.5 + d, 0.5)
    route, plan = _line(lua, start, goal)
    assert plan.pipes == 0
    assert route[0] == ("in", start, 4) and route[-1] == ("out", goal, 4)
    pairs = [(route[i], route[i + 1]) for i in range(0, len(route), 2)]
    assert len(pairs) == -(-(d + 1) // (REACH + 1))  # as few as the reach allows
    covered = 0
    for (ka, (ax, _), _), (kb, (bx, _), _) in pairs:
        assert ka == "in" and kb == "out" and 1 <= bx - ax <= REACH
        assert ax == 0.5 + covered  # back to back: each entrance right after the last exit
        covered += round(bx - ax) + 1
    assert covered == d + 1


def test_pipe_to_ground_line_goes_any_axis_direction():
    lua = _lua()
    route, _ = _line(lua, (5.5, 30.5), (5.5, 0.5))
    assert {d for _, _, d in route} == {0}
    assert route[0][1] == (5.5, 30.5) and route[-1][1] == (5.5, 0.5)


def test_pipe_to_ground_line_needs_a_straight_line():
    lua = _lua()
    route, why = _line(lua, (0.5, 0.5), (5.5, 3.5))
    assert route is None and "straight line" in why
    route, why = _line(lua, (0.5, 0.5), (0.5, 0.5))
    assert route is None


def test_pipe_to_ground_line_does_not_span_another_on_its_axis():
    lua = _lua()
    route, why = _line(lua, (0.5, 0.5), (8.5, 0.5), crosses=lambda p, axis: p.x == 4.5 and axis == 4)
    assert route is None and "(4.5, 0.5)" in why
    # one on the other axis (a crossing tunnel) is no obstacle
    route, _ = _line(lua, (0.5, 0.5), (8.5, 0.5), crosses=lambda p, axis: p.x == 4.5 and axis == 0)
    assert route is not None


def test_server_uses_the_game_reach_for_pipe_to_ground_everywhere():
    # the tile route's reach is the game's max_underground_distance, not one less
    assert "underground_pipe_reach(underground) - 1" not in SERVER_LUA
    assert "max_jump = underground and storage.utils.underground_pipe_reach(underground) or 0" in SERVER_LUA
    # the walking-path route's pipe-to-ground sections too
    assert 'range = storage.utils.underground_pipe_reach(underground_type)' in SERVER_LUA


def test_pipe_to_ground_alone_is_routed_as_a_line_in_the_action():
    assert "if is_pipe_to_ground_only(connection_types) then\n            return connect_pipe_to_ground_line(" in SERVER_LUA


# --- the client: which route each connection type asks for -----------------------


class _Exec:
    def __init__(self, answers):
        self.calls = []
        self.answers = list(answers)

    def __call__(self, *args):
        self.calls.append(args)
        return self.answers.pop(0), None


def _client(answers, inventory):
    tool = ConnectEntities.__new__(ConnectEntities)
    tool.player_index = 1
    tool._notes = []
    tool.execute = _Exec(answers)
    tool.inspect_inventory = lambda: inventory
    tool._extend_collision_boxes = lambda *a: None
    tool._clear_collision_boxes = lambda *a: None
    walked = []

    def path_finding(*args, **kw):
        walked.append(args)
        return PathResult({"entities": {}, "number_of_entities": 0, "planned": []})

    tool._attempt_path_finding = path_finding
    return tool, walked


def _ok(planned, **extra):
    return dict({"entities": {}, "connected": False, "number_of_entities": len(planned), "planned": planned}, **extra)


def test_plain_pipe_never_takes_the_pipe_to_ground_route():
    tool, walked = _client([], {"pipe": 50, "pipe-to-ground": 20})
    tool._create_connection(Position(x=0.5, y=0.5), Position(x=30.5, y=0.5), {Prototype.Pipe}, dry_run=True)
    assert tool.execute.calls == [] and len(walked) == 1
    names = walked[0][2]
    assert names == ["pipe"]


def test_pipe_with_underground_tries_the_tile_route_first():
    planned = [{"name": "pipe", "x": 0.5, "y": 0.5, "direction": 0}]
    tool, walked = _client([_ok(planned)], {"pipe": 50, "pipe-to-ground": 20})
    leg = tool._create_connection(
        Position(x=0.5, y=0.5), Position(x=30.5, y=0.5), {Prototype.Pipe, Prototype.UndergroundPipe}, dry_run=True
    )
    assert len(tool.execute.calls) == 1 and walked == []
    assert tool.execute.calls[0][5] == -1  # no game path
    assert set(tool.execute.calls[0][6].split(",")) == {"pipe", "pipe-to-ground"}
    assert leg["planned"] == planned and leg["note"] is None


def test_pipe_with_underground_falls_back_to_the_walking_path_when_the_tile_route_fails():
    tool, walked = _client(["No pipe route from (0.5, 0.5) to (30.5, 0.5): ..."], {"pipe": 50})
    tool._create_connection(
        Position(x=0.5, y=0.5), Position(x=30.5, y=0.5), {Prototype.Pipe, Prototype.UndergroundPipe}, dry_run=True
    )
    assert len(walked) == 1


def test_an_item_shortage_is_not_hidden_by_the_walking_path():
    message = "You do not have enough items in your inventory to complete this connection (pipe-to-ground: required 2, in inventory 0). Nothing was built."
    tool, walked = _client([message], {"pipe": 50})
    with pytest.raises(Exception, match="enough items"):
        tool._create_connection(
            Position(x=0.5, y=0.5), Position(x=30.5, y=0.5), {Prototype.Pipe, Prototype.UndergroundPipe}, dry_run=False
        )
    assert walked == []


def test_pipe_to_ground_alone_uses_only_the_line_and_never_the_walking_path():
    tool, walked = _client(["Prototype.UndergroundPipe alone connects two tiles in a straight line"], {"pipe-to-ground": 4})
    with pytest.raises(Exception, match="straight line"):
        tool._create_connection(
            Position(x=0.5, y=0.5), Position(x=5.5, y=3.5), {Prototype.UndergroundPipe}, dry_run=True
        )
    assert walked == [] and tool.execute.calls[0][6] == "pipe-to-ground"


def test_the_dry_run_leg_says_when_the_route_had_room_for_more_pairs():
    planned = [{"name": "pipe", "x": 0.5, "y": 0.5, "direction": 0}]
    tool, _ = _client([_ok(planned, underground_wanted=18, underground_used=6)], {"pipe": 200, "pipe-to-ground": 6})
    leg = tool._create_connection(
        Position(x=0.5, y=0.5), Position(x=100.5, y=0.5), {Prototype.Pipe, Prototype.UndergroundPipe}, dry_run=True
    )
    assert leg["note"] == (
        "pipe-to-ground: the route has room for 18 (9 pairs); you hold 6, so it uses 6 "
        "and the rest of the route is surface pipe"
    )
    plan = dr.success(dr.planned_entities(planned), {"pipe": 200}, 200, notes=[leg["note"]])
    assert plan.notes == [leg["note"]] and "notes=" in repr(plan)


def test_no_note_when_every_run_is_underground():
    assert client_module._underground_note(PathResult(_ok([], underground_wanted=0)), 10) is None
    assert client_module._underground_note(PathResult(_ok([])), 10) is None
    assert client_module._underground_note(PathResult("an error"), 10) is None


def test_pipe_group_shows_its_notes():
    group = PipeGroup.model_construct(id=1, position=Position(x=0, y=0), pipes=[], notes=["pipe-to-ground: x"])
    assert "notes=['pipe-to-ground: x']" in repr(group)
    plain = PipeGroup.model_construct(id=1, position=Position(x=0, y=0), pipes=[], notes=[])
    assert "notes" not in repr(plain)
