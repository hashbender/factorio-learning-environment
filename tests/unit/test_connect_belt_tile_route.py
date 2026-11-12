"""connect_entities with belts: the game's path search treats belts already on the map
as walls, so a belt route could not cross another belt line and failed with a bare
"Failed to find a path.". When the walking-path route fails, the route is now searched
tile by tile: with an underground belt among the connection types an underground pair
carries the line under what is in its way (up to the underground belt's reach); the
error, when there is no route, names the blocked tile nearest the target and what is on
it, and whether underground belts were allowed and held. Server-free (lupa).
"""

from pathlib import Path

import pytest

from fle.env.entities import Position
from fle.env.game_types import Prototype
from fle.env.tools.agent.connect_entities.client import ConnectEntities
from fle.env.tools.agent.connect_entities.path_result import PathResult

lupa = pytest.importorskip("lupa")

ROOT = Path(__file__).resolve().parents[2]
SERVER_LUA = (ROOT / "fle/env/tools/agent/connect_entities/server.lua").read_text()

DIRS = {0: (0, -1), 4: (1, 0), 8: (0, 1), 12: (-1, 0)}

# A small map: entities on tiles, a character with an inventory.
FAKE = """
local ents = {}
local next_unit = 1
local function key(x, y) return x .. "," .. y end
local function match(v, want)
    if want == nil then return true end
    if type(want) == "table" then
        for _, w in pairs(want) do if w == v then return true end end
        return false
    end
    return v == want
end
local function corner(c) return c.x or c[1], c.y or c[2] end
local surface = {}
function surface.find_entities_filtered(a)
    local out = {}
    for _, e in pairs(ents) do
        local ok = e.valid and match(e.name, a.name) and match(e.type, a.type)
        if ok and a.area then
            local x0, y0 = corner(a.area[1] or a.area.left_top)
            local x1, y1 = corner(a.area[2] or a.area.right_bottom)
            ok = e.position.x + 0.4 > x0 and e.position.x - 0.4 < x1 and e.position.y + 0.4 > y0 and e.position.y - 0.4 < y1
        end
        if ok and a.position then
            local r = a.radius or 0.5
            ok = math.abs(e.position.x - a.position.x) <= r and math.abs(e.position.y - a.position.y) <= r
        end
        if ok then table.insert(out, e) end
    end
    return out
end
function surface.find_entity(name, p)
    local e = ents[key(p.x, p.y)]
    if e and e.name == name then return e end
    return nil
end
function surface.can_place_entity(a) return ents[key(a.position.x, a.position.y)] == nil end
function surface.get_tile(x, y) return {valid = true, name = "grass-1", collides_with = function() return false end} end
function surface.find_non_colliding_position(name, p) return p end
function surface.create_entity(a)
    local p = a.position
    if ents[key(p.x, p.y)] then return nil end
    local e = {valid = true, name = a.name, direction = a.direction or 0, position = {x = p.x, y = p.y},
               unit_number = next_unit, new = true}
    next_unit = next_unit + 1
    e.type = a.name:find("underground") and "underground-belt" or "transport-belt"
    if e.type == "underground-belt" then e.belt_to_ground_type = a.type or "input" end
    ents[key(p.x, p.y)] = e
    return e
end
function add_entity(name, x, y, dir, io)
    local e = surface.create_entity{name = name, position = {x = x, y = y}, direction = dir, type = io}
    e.new = nil
    return e
end
function pair(a, b) a.neighbours = b; b.neighbours = a end
function entity_at(x, y) return ents[key(x, y)] end
function new_entities()
    local out = {}
    for _, e in pairs(ents) do
        if e.new then table.insert(out, e) end
    end
    return out
end
function existing_snapshot()
    local out = {}
    for _, e in pairs(ents) do
        if not e.new then table.insert(out, e.name .. "@" .. e.position.x .. "," .. e.position.y .. ":" .. e.direction) end
    end
    table.sort(out)
    return table.concat(out, ";")
end
local inv = {}
function set_held(name, n) inv[name] = n end
function held(name) return inv[name] or 0 end
local inventory = {get_item_count = function(name) return inv[name] or 0 end}
player = {valid = true, surface = surface, force = "player", position = {x = 0, y = 0}}
player.teleport = function(p) end
player.get_inventory = function(i) return inventory end
player.remove_item = function(s) inv[s.name] = (inv[s.name] or 0) - (s.count or 1) end
game = {surfaces = {[1] = surface}}
defines = {inventory = {character_main = 1}, direction = {north = 0, east = 4, south = 8, west = 12}}
rendering = {draw_circle = function() end, draw_line = function() end}
prototypes = {entity = {}}
storage = {actions = {}, paths = {}, elapsed_ticks = 0, agent_characters = {[1] = player}, utils = {}}
storage.utils.get_entity_direction = function(name, d) return d end
storage.utils.serialize_entity = function(e) return {name = e.name, position = e.position, direction = e.direction} end
storage.utils.get_closest_entity = function() return nil end
storage.utils.can_place_entity = function(pl, name, position, dir) return pl.surface.can_place_entity{name = name, position = position} end
"""


def _lua():
    lua = lupa.LuaRuntime(unpack_returned_tuples=True)
    lua.execute(FAKE)
    lua.execute(SERVER_LUA)
    return lua


def _wall(lua, x, y0=-60, y1=60, name="transport-belt", direction=8):
    """A belt line down column x (a whole wall within the search margin)."""
    for y in range(y0, y1 + 1):
        lua.eval("add_entity")(name, x + 0.5, y + 0.5, direction)


def _act(lua, types, dry, start=(0.5, 0.5), goal=(10.5, 0.5), handle=-1):
    act = lua.eval("storage.actions.connect_entities")
    return act(1, start[0], start[1], goal[0], goal[1], handle, types, dry, 0)


def _planned(result):
    out = []
    for i in range(1, len(result.planned) + 1):
        p = result.planned[i]
        out.append((p.name.strip('"'), (p.x, p.y), p.direction, (p.type or "").strip('"') or None))
    return out


def _route(lua, start, goal, blocked=lambda x, y: False, max_jump=5, **kw):
    opts = {
        "start": lua.table_from({"x": start[0], "y": start[1]}),
        "goal": lua.table_from({"x": goal[0], "y": goal[1]}),
        "free": lambda p: not blocked(p.x, p.y),
        "max_jump": max_jump,
    }
    fn = kw.pop("fn", "plan_belt_route")
    opts.update(kw)
    res = lua.eval(f"storage.utils.{fn}")(lua.table_from(opts))
    plan, why, at = (tuple(res) + (None, None))[:3] if isinstance(res, tuple) else (res, None, None)
    if plan is None:
        return None, (why, (at.x, at.y) if at is not None else None)
    out = []
    for i in range(1, len(plan.placements) + 1):
        p = plan.placements[i]
        out.append((p.kind, (p.position.x, p.position.y), p.dir))
    return out, plan


def _check(route, start, goal, max_jump, blocked=lambda x, y: False):
    """A belt line that carries items from start to goal: each belt faces the next tile;
    an entrance is fed from straight behind (unless it is the start), its exit is
    straight ahead within reach and sends the items straight on (unless it is the goal)."""
    assert route[0][1] == start and route[-1][1] == goal
    spans = []
    for i, (kind, (x, y), d) in enumerate(route[:-1]):
        nkind, (nx, ny), nd = route[i + 1]
        dx, dy = DIRS[d]
        if kind == "in":
            assert nkind == "out" and nd == d
            k = round((nx - x) * dx + (ny - y) * dy)
            assert (nx, ny) == (x + dx * k, y + dy * k) and 2 <= k <= max_jump
            spans.append(k)
            if i > 0:
                px, py = route[i - 1][1]
                assert (x - px, y - py) == (dx, dy), "entrance fed from straight behind"
        else:
            assert (nx - x, ny - y) == (dx, dy), ("faces the next tile", route[i], route[i + 1])
            if kind == "out":
                assert i == 0 or route[i - 1][0] == "in"
    for kind, (x, y), _ in route:
        assert not blocked(x, y)
    return spans


# --- the bug, as it was ---------------------------------------------------------------


def test_the_walking_path_route_fails_bare_when_the_game_finds_no_path():
    """What Astra got (turn 2221): the game's path search treats belts as walls; with
    no path the walking-path route said only "Failed to find a path."."""
    lua = _lua()
    _wall(lua, 5)
    lua.execute('storage.paths[7] = "not_found"')
    lua.eval("set_held")("transport-belt", 50)
    lua.eval("set_held")("underground-belt", 10)
    with pytest.raises(Exception) as e:
        _act(lua, "transport-belt,underground-belt", True, handle=7)
    assert "Failed to find a path." in str(e.value)
    assert "blocked" not in str(e.value)


def test_the_game_path_search_treats_belts_as_walls():
    request_path = (ROOT / "fle/env/tools/admin/request_path/server.lua").read_text()
    assert "transport_belt = true" in request_path


# --- the planner --------------------------------------------------------------------


def test_a_belt_line_in_the_way_is_crossed_with_one_underground_pair():
    lua = _lua()
    wall = lambda x, y: x == 5.5  # noqa: E731
    route, plan = _route(lua, (0.5, 0.5), (10.5, 0.5), wall, max_jump=5)
    spans = _check(route, (0.5, 0.5), (10.5, 0.5), 5, wall)
    assert len(spans) == 1 and plan.undergrounds == 2
    (ix, iy), (ox, oy) = [p[1] for p in route if p[0] in ("in", "out")]
    assert iy == oy == 0.5 and ix < 5.5 < ox


def test_reach_five_crosses_four_blocked_tiles_and_no_more():
    lua = _lua()
    four = lambda x, y: 3 <= x <= 7  # noqa: E731  (x 3.5 .. 6.5: four tiles)
    route, _ = _route(lua, (0.5, 0.5), (12.5, 0.5), four, max_jump=5)
    assert _check(route, (0.5, 0.5), (12.5, 0.5), 5, four) == [5]
    five = lambda x, y: 3 <= x <= 8  # noqa: E731
    route, (why, at) = _route(lua, (0.5, 0.5), (12.5, 0.5), five, max_jump=5)
    assert route is None and "no route" in why


def test_without_underground_belts_a_wall_has_no_route_and_the_nearest_blocked_tile_is_named():
    lua = _lua()
    wall = lambda x, y: x == 5.5  # noqa: E731
    route, (why, at) = _route(lua, (0.5, 0.5), (10.5, 0.5), wall, max_jump=0)
    assert route is None and "no route within" in why
    assert at == (5.5, 0.5)


def test_a_tunnel_never_passes_an_underground_belt_of_the_same_name():
    lua = _lua()
    wall = lambda x, y: x == 5.5  # noqa: E731
    route, (why, at) = _route(
        lua, (0.5, 0.5), (10.5, 0.5), wall, max_jump=5, has_underground=lambda p: p.x == 5.5
    )
    assert route is None


def test_a_pair_the_map_forbids_is_not_used():
    lua = _lua()
    wall = lambda x, y: x == 5.5  # noqa: E731
    seen = []

    def can_jump(a, b, d):
        seen.append(((a.x, a.y), (b.x, b.y), d))
        return a.y != 0.5  # not on this row

    route, _ = _route(lua, (0.5, 0.5), (10.5, 0.5), wall, max_jump=5, can_jump=can_jump)
    _check(route, (0.5, 0.5), (10.5, 0.5), 5, wall)
    assert seen
    assert all(p[1][1] != 0.5 for p in route if p[0] in ("in", "out"))


def test_a_free_route_uses_no_underground_belt_and_faces_each_belt_to_the_next():
    lua = _lua()
    route, plan = _route(lua, (0.5, 0.5), (3.5, 2.5), max_jump=5)
    _check(route, (0.5, 0.5), (3.5, 2.5), 5)
    assert plan.undergrounds == 0 and all(k == "belt" for k, _, _ in route)
    # the last belt faces the way it was reached
    assert route[-1][2] == {(1, 0): 4, (0, 1): 8}[
        (route[-1][1][0] - route[-2][1][0], route[-1][1][1] - route[-2][1][1])
    ]


def test_an_empty_start_and_goal_may_be_the_entrance_and_exit():
    # turn 2169: a 3-tile crossing, (6.5, 40.5) to (6.5, 37.5), belts on the two tiles between
    lua = _lua()
    wall = lambda x, y: x == 6.5 and y in (38.5, 39.5)  # noqa: E731
    boxed = lambda x, y: wall(x, y) or (x != 6.5)  # noqa: E731  (no way round)
    route, _ = _route(lua, (6.5, 40.5), (6.5, 37.5), boxed, max_jump=5, start_open=True, goal_open=True)
    assert route == [("in", (6.5, 40.5), 0), ("out", (6.5, 37.5), 0)]
    route, _ = _route(lua, (6.5, 40.5), (6.5, 37.5), boxed, max_jump=5)
    assert route is None


def test_too_few_underground_belts_held_takes_a_detour_when_there_is_one():
    lua = _lua()
    short_wall = lambda x, y: x == 5.5 and -3 <= y <= 3  # noqa: E731
    route, plan = _route(
        lua, (0.5, 0.5), (10.5, 0.5), short_wall, max_jump=5, underground_budget=0, fn="plan_belt_route_within_held"
    )
    _check(route, (0.5, 0.5), (10.5, 0.5), 5, short_wall)
    assert plan.undergrounds == 0
    wall = lambda x, y: x == 5.5  # noqa: E731
    route, plan = _route(
        lua, (0.5, 0.5), (10.5, 0.5), wall, max_jump=5, underground_budget=0, fn="plan_belt_route_within_held"
    )
    assert plan.undergrounds == 2  # no other way: the item check names them


# --- the action, on a small map -------------------------------------------------------


def test_the_tile_route_crosses_a_belt_line_dry_run_equals_real_call():
    lua = _lua()
    _wall(lua, 5)
    lua.eval("set_held")("transport-belt", 50)
    lua.eval("set_held")("underground-belt", 10)
    before = lua.eval("existing_snapshot")()

    dry = _act(lua, "transport-belt,underground-belt", True)
    planned = _planned(dry)
    unders = [p for p in planned if p[0] == "underground-belt"]
    assert [p[3] for p in unders] == ["input", "output"]
    (ix, iy), (ox, oy) = unders[0][1], unders[1][1]
    assert iy == oy == 0.5 and ix < 5.5 < ox and ox - ix <= 5 and unders[0][2] == unders[1][2] == 4
    belts = sum(1 for p in planned if p[0] == "transport-belt")
    assert belts == 11 - (ox - ix + 1)  # tiles 0.5 .. 10.5, less the tunnel
    assert lua.eval("new_entities")() is not None and len(lua.eval("new_entities")()) == 0

    _act(lua, "transport-belt,underground-belt", False)
    built = lua.eval("new_entities")()
    got = sorted(
        (e.name, (e.position.x, e.position.y), e.direction, e.belt_to_ground_type) for e in built.values()
    )
    assert got == sorted(planned)
    assert lua.eval("existing_snapshot")() == before  # the line it crossed is unchanged
    assert lua.eval("held")("underground-belt") == 8 and lua.eval("held")("transport-belt") == 50 - belts


def test_no_route_names_the_blocked_tile_and_that_underground_belts_were_not_allowed():
    lua = _lua()
    _wall(lua, 5)
    lua.eval("set_held")("transport-belt", 50)
    with pytest.raises(Exception) as e:
        _act(lua, "transport-belt", True)
    msg = str(e.value)
    assert msg.startswith("Failed to find a path.") or "Failed to find a path." in msg
    assert "cannot place transport-belt at (5.5, 0.5): blocked by transport-belt facing DOWN" in msg
    assert "Underground belts: not allowed" in msg


def test_no_route_says_which_underground_belt_was_allowed_its_reach_and_how_many_are_held():
    lua = _lua()
    for x in range(3, 9):  # six columns: more than an underground belt crosses
        _wall(lua, x)
    lua.eval("set_held")("transport-belt", 50)
    lua.eval("set_held")("underground-belt", 4)
    with pytest.raises(Exception) as e:
        _act(lua, "transport-belt,underground-belt", True, goal=(12.5, 0.5))
    msg = str(e.value)
    # the search reaches x = 2.5 and looks at most 5 tiles on (x = 7.5)
    assert "cannot place transport-belt at (7.5, 0.5): blocked by transport-belt facing DOWN" in msg
    assert "Underground belts: underground-belt allowed (an exit at most 5 tiles past its entrance" in msg
    assert "you hold 4" in msg


def test_a_crossing_needs_the_underground_belts_in_hand():
    lua = _lua()
    _wall(lua, 5)
    lua.eval("set_held")("transport-belt", 50)
    dry = _act(lua, "transport-belt,underground-belt", True)
    assert sum(1 for p in _planned(dry) if p[0] == "underground-belt") == 2
    with pytest.raises(Exception) as e:
        _act(lua, "transport-belt,underground-belt", False)
    assert "underground-belt: required 2, in inventory 0" in str(e.value)
    assert len(lua.eval("new_entities")()) == 0  # nothing was built


def test_the_route_does_not_step_in_front_of_a_belt_that_ends_there():
    lua = _lua()
    lua.eval("add_entity")("transport-belt", 5.5, -0.5, 8)  # outputs onto (5.5, 0.5)
    lua.eval("set_held")("transport-belt", 50)
    planned = _planned(_act(lua, "transport-belt", True))
    assert all(p[1] != (5.5, 0.5) for p in planned)
    assert planned[0][1] == (0.5, 0.5) and planned[-1][1] == (10.5, 0.5)


def test_a_pair_never_stands_inside_a_tunnel_of_the_same_underground_belt():
    lua = _lua()
    _wall(lua, 6)
    # an existing underground pair along row y = 0.5, under the wall
    a = lua.eval("add_entity")("underground-belt", 3.5, 0.5, 4, "input")
    b = lua.eval("add_entity")("underground-belt", 8.5, 0.5, 4, "output")
    lua.eval("pair")(a, b)
    lua.eval("set_held")("transport-belt", 80)
    lua.eval("set_held")("underground-belt", 10)
    before = lua.eval("existing_snapshot")()
    # the cheapest route would be a pair (5.5, 0.5) -> (7.5, 0.5), inside that tunnel
    planned = _planned(_act(lua, "transport-belt,underground-belt", True, start=(4.5, 0.5), goal=(7.5, 0.5)))
    unders = [p for p in planned if p[0] == "underground-belt"]
    assert len(unders) == 2
    for name, (x, y), d, io in unders:
        assert not (y == 0.5 and 3.5 < x < 8.5 and d in (4, 12))
    _act(lua, "transport-belt,underground-belt", False, start=(4.5, 0.5), goal=(7.5, 0.5))
    assert lua.eval("existing_snapshot")() == before


def test_the_tile_route_is_only_for_belts_without_a_path():
    assert (
        "if path_handle == -1 and is_belt_route(connection_types) then\n"
        "            return connect_belts_by_tiles(" in SERVER_LUA
    )


# --- the client: when the tile route is asked for --------------------------------------


class _Exec:
    def __init__(self, answers):
        self.calls = []
        self.answers = list(answers)

    def __call__(self, *args):
        self.calls.append(args)
        return self.answers.pop(0), None


def _client(answers, path_answers):
    tool = ConnectEntities.__new__(ConnectEntities)
    tool.player_index = 1
    tool._notes = []
    tool.execute = _Exec(answers)
    tool.inspect_inventory = lambda: {"transport-belt": 50, "underground-belt": 10}
    walked = []
    path_answers = list(path_answers)

    def path_finding(*args, **kw):
        walked.append(args)
        return PathResult(path_answers.pop(0))

    tool._attempt_path_finding = path_finding
    tool._adjust_belt_position = lambda pos, entity: pos
    return tool, walked


BELTS = {Prototype.TransportBelt, Prototype.UndergroundBelt}
A, B = Position(x=0.5, y=0.5), Position(x=10.5, y=0.5)


def _ok(planned):
    return {"entities": {}, "connected": False, "number_of_entities": len(planned), "planned": planned}


def test_with_an_underground_belt_the_tile_route_goes_first():
    planned = [{"name": "underground-belt", "x": 4.5, "y": 0.5, "direction": 4, "type": "input"}]
    tool, walked = _client([_ok(planned)], [])
    leg = tool._create_connection(A, B, BELTS, dry_run=True)
    assert walked == [] and tool.execute.calls[0][5] == -1
    assert set(tool.execute.calls[0][6].split(",")) == {"transport-belt", "underground-belt"}
    assert leg["planned"] == planned


def test_with_an_underground_belt_the_walking_path_is_the_fallback():
    planned = [{"name": "transport-belt", "x": 0.5, "y": 0.5, "direction": 4}]
    tool, walked = _client(["Failed to find a path. No belt route ..."], [_ok(planned)])
    leg = tool._create_connection(A, B, BELTS, dry_run=True)
    assert len(walked) == 1 and leg["planned"] == planned


def test_when_both_fail_the_tile_routes_reason_is_the_error():
    reason = "Failed to find a path. No belt route ...: cannot place transport-belt at (5.5, 0.5): blocked by stone-wall."
    tool, walked = _client([reason], ["Failed to find a path.", "Failed to find a path."])
    with pytest.raises(Exception) as e:
        tool._create_connection(A, B, BELTS, dry_run=True)
    assert "cannot place transport-belt at (5.5, 0.5)" in str(e.value) and len(walked) == 2


def test_belts_alone_follow_the_walking_path_first():
    tool, walked = _client([], [_ok([{"name": "transport-belt", "x": 0.5, "y": 0.5, "direction": 4}])])
    tool._create_connection(A, B, {Prototype.TransportBelt}, dry_run=True)
    assert len(walked) == 1 and tool.execute.calls == []


def test_belts_alone_the_game_cannot_route_are_searched_tile_by_tile():
    tool, walked = _client([_ok([])], ["Failed to find a path.", "Failed to find a path."])
    tool._create_connection(A, B, {Prototype.TransportBelt}, dry_run=True)
    assert len(walked) == 2 and tool.execute.calls[0][5] == -1


def test_the_tile_routes_reason_is_the_error():
    reason = (
        "Failed to find a path. No belt route from (0.5, 0.5) to (10.5, 0.5): no route within 34 tiles "
        "of the straight line. The blocked tile nearest the target that the search reached: cannot place "
        "transport-belt at (5.5, 0.5): blocked by transport-belt facing DOWN. Underground belts: not allowed "
        "(connection_type has no underground belt)."
    )
    tool, _ = _client([reason], ["Failed to find a path.", "Failed to find a path."])
    with pytest.raises(Exception) as e:
        tool._create_connection(A, B, {Prototype.TransportBelt}, dry_run=True)
    assert "cannot place transport-belt at (5.5, 0.5)" in str(e.value)


def test_an_item_shortage_is_not_replaced_by_another_route():
    short = "You do not have enough items in your inventory to complete this connection (underground-belt: required 2, in inventory 0). Nothing was built."
    tool, walked = _client([short], [])
    with pytest.raises(Exception, match="enough items"):
        tool._create_connection(A, B, BELTS, dry_run=False)
    assert walked == []
    tool, _ = _client([], [short, short])
    with pytest.raises(Exception, match="enough items"):
        tool._create_connection(A, B, {Prototype.TransportBelt}, dry_run=False)
    assert tool.execute.calls == []


def test_a_timed_out_path_search_goes_straight_to_the_tile_route():
    timeout = "The game's path search timed out for this route from (0.5, 0.5) to (10.5, 0.5). Split it with waypoints closer together."
    tool, walked = _client([_ok([])], [timeout])
    tool._create_connection(A, B, {Prototype.TransportBelt}, dry_run=True)
    assert len(walked) == 1 and tool.execute.calls[0][5] == -1
