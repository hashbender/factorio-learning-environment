"""connect_entities stops trying further position pairs (and path box sizes) once a leg has
searched for _SEARCH_BUDGET_S seconds, and says so: an unreachable target (measured in a real
game: oil refinery -> storage tank behind out-of-map tiles, 362 s for one dry run) can no longer
use up a program's time limit."""

import pytest

from fle.env.entities import Position
from fle.env.game_types import Prototype
from fle.env.tools.agent.connect_entities import client as client_module
from fle.env.tools.agent.connect_entities.client import ConnectEntities, ConnectionType


class _Resolver:
    def resolve(self, source, target):
        return [(Position(x=i + 0.5, y=0.5), Position(x=i + 0.5, y=20.5)) for i in range(6)]


def test_a_leg_stops_after_its_search_budget_and_says_so(monkeypatch):
    clock = {"t": 1000.0}

    def tick():
        return clock["t"]

    monkeypatch.setattr(client_module, "_monotonic", tick)
    tool = ConnectEntities.__new__(ConnectEntities)
    tool._protected_belts = None
    tool.resolvers = {ConnectionType.FLUID: _Resolver()}
    tool._cliffs_between = lambda a, b: ""
    tool.get_error_message = lambda m: m
    tool._resolve_position_into_entity = lambda p: p
    tried = []

    def no_route(source_pos, target_pos, *a, **k):
        tried.append(source_pos.x)
        clock["t"] += 10  # each attempt takes 10 s
        raise Exception("No pipe route here")

    tool._create_connection = no_route
    with pytest.raises(Exception) as e:
        tool._connect_pair_of_waypoints(
            Position(x=0.5, y=0.5), Position(x=0.5, y=20.5), connection_types={Prototype.Pipe}, dry_run=True
        )
    assert len(tried) == 3  # 0, 10, 20 s: the third ends past 25 s
    assert f"stopped searching after {client_module._SEARCH_BUDGET_S} s; 3 of 6 position pairs were not tried" in str(e.value)


def test_path_box_sizes_stop_once_the_budget_is_used(monkeypatch):
    clock = {"t": 0.0}
    monkeypatch.setattr(client_module, "_monotonic", lambda: clock["t"])
    tool = ConnectEntities.__new__(ConnectEntities)
    tool.player_index = 1
    tool._give_up_at = 5.0
    sizes = []

    def request_path(**kw):
        sizes.append(kw["entity_size"])
        clock["t"] += 4
        return len(sizes)

    tool.request_path = request_path
    tool._wait_for_path = lambda h: "not_found"
    tool.execute = lambda *a: ("Failed to find a path.", 0)
    r = tool._attempt_path_finding(Position(x=0.5, y=0.5), Position(x=9.5, y=0.5), ["pipe"], 10)
    assert sizes == [1.5, 1] and not r.is_success


def test_a_real_call_whose_dry_leg_fails_raises_that_without_searching_again():
    tool = ConnectEntities.__new__(ConnectEntities)
    tool._snapshot_belts = lambda w: None
    tool._check_protected_belts = lambda: None
    calls = []

    def leg(source, target, connection_types=None, dry_run=False):
        calls.append(dry_run)
        raise Exception("No pipe route from (0.5, 0.5) to (9.5, 0.5): no buildable route")

    tool._connect_pair_of_waypoints = leg
    with pytest.raises(Exception, match="No pipe route"):
        tool(Position(x=0.5, y=0.5), Position(x=9.5, y=0.5), connection_type=Prototype.Pipe)
    assert calls == [True]  # the walk's dry leg only: no second search for the real call
