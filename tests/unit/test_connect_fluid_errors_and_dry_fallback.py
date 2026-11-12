"""connect_entities, fluids: the "no valid connections" error names its cause (no output
on the source, no input on the target, a port tile occupied and by what, a Position taken
as a nearby entity), and a dry run tries the oil refinery / chemical plant port fallback
the real call tries. Server-free.
"""

import pytest

from fle.env.entities import (
    Direction,
    IndexedPosition,
    OilRefinery,
    Pipe,
    Position,
    StorageTank,
)
from fle.env.game_types import Prototype
from fle.env.tools.agent.connect_entities.client import ConnectEntities
from fle.env.tools.agent.connect_entities.path_result import PathResult
from fle.env.tools.agent.connect_entities.resolver import ConnectionType
from fle.env.tools.agent.connect_entities.resolvers.fluid_connection_resolver import (
    FluidConnectionResolver,
)


def _tank(x, y, points, fluid=None):
    return StorageTank.model_construct(
        name="storage-tank",
        position=Position(x=x, y=y),
        connection_points=points,
        fluid_box=[{"name": fluid, "amount": 10}] if fluid else [],
        direction=Direction.UP,
    )


def _refinery(outputs, inputs=()):
    return OilRefinery.model_construct(
        name="oil-refinery",
        position=Position(x=0.5, y=0.5),
        output_connection_points=list(outputs),
        input_connection_points=list(inputs),
        direction=Direction.UP,
        recipe="basic-oil-processing",
    )


def _resolver(occupied=None):
    occupied = occupied or {}

    def get_entities(*args, position=None, radius=None, **kw):
        if position is None:
            return []
        return list(occupied.get((position.x, position.y), []))

    return FluidConnectionResolver(get_entities)


def test_target_without_a_fluid_input_is_named():
    target = _tank(10.5, 10.5, [])
    with pytest.raises(Exception) as e:
        _resolver().resolve(Position(x=0.5, y=0.5), target)
    msg = str(e.value)
    assert "storage-tank at (10.5, 10.5) has no fluid input to connect to" in msg
    assert "pipes from a fluid output of the source to a fluid input of the target" in msg


def test_source_without_a_fluid_output_is_named():
    with pytest.raises(Exception) as e:
        _resolver().resolve(_refinery([]), Position(x=20.5, y=0.5))
    assert "oil-refinery at (0.5, 0.5) has no fluid output to connect from" in str(e.value)


def test_occupied_input_port_tile_is_named_with_what_is_on_it():
    pipe = Pipe.model_construct(name="pipe", position=Position(x=12.5, y=10.5))
    target = _tank(10.5, 10.5, [Position(x=12.5, y=10.5)])
    resolver = _resolver({(12.5, 10.5): [pipe]})
    with pytest.raises(Exception) as e:
        resolver.resolve(Position(x=0.5, y=0.5), target)
    msg = str(e.value)
    assert "input port tile (12.5, 10.5) of storage-tank at (10.5, 10.5) is occupied by pipe at (12.5, 10.5)" in msg


def test_occupied_output_port_tile_is_named():
    pipe = Pipe.model_construct(name="pipe", position=Position(x=0.5, y=-2.5))
    source = _refinery([IndexedPosition(x=0.5, y=-2.5, type="petroleum-gas")])
    resolver = _resolver({(0.5, -2.5): [pipe]})
    with pytest.raises(Exception) as e:
        resolver.resolve(source, _tank(20.5, 0.5, [Position(x=18.5, y=0.5)]))
    assert "output port tile (petroleum-gas) (0.5, -2.5) of oil-refinery at (0.5, 0.5) is occupied by pipe" in str(e.value)


def test_a_position_taken_as_a_nearby_entity_is_said():
    tool = ConnectEntities.__new__(ConnectEntities)
    refinery = _refinery([IndexedPosition(x=0.5, y=-2.5, type="petroleum-gas")])
    tool._resolve_position_into_entity = lambda p: refinery
    tool._refresh_entity = lambda e: e

    class Failing:
        def resolve(self, s, t):
            raise Exception("Did not find any valid connections between source A and target B: x.")

    tool.resolvers = {ConnectionType.FLUID: Failing()}
    with pytest.raises(Exception) as e:
        tool._connect_pair_of_waypoints(
            Position(x=1.0, y=1.0), _tank(20.5, 0.5, []), connection_types={Prototype.Pipe}
        )
    msg = str(e.value)
    assert "Did not find any valid connections" in msg
    assert "The Position (1.0, 1.0) was taken as oil-refinery at (0.5, 0.5)" in msg


def test_dry_run_tries_the_refinery_port_fallback_like_the_real_call():
    tool = ConnectEntities.__new__(ConnectEntities)
    tool._protected_belts = None
    refinery = _refinery([IndexedPosition(x=0.5, y=-2.5, type="petroleum-gas")])
    tank = _tank(20.5, 0.5, [Position(x=18.5, y=0.5)])
    tool._refresh_entity = lambda e: e
    tool.resolvers = {ConnectionType.FLUID: _resolver()}
    tool._cliffs_between = lambda a, b: ""
    tool.get_error_message = lambda m: m

    def no_route(*a, **k):
        raise Exception("No pipe route")

    tool._create_connection = no_route
    seen = []
    plan = {"number_of_entities_required": 3, "number_of_entities_available": 9,
            "planned": [{"name": "pipe-to-ground", "x": 0.5, "y": -3.5, "direction": 0}],
            "would_turn": None, "note": None}

    def fallback(s, t, types, source_entity=None, target_entity=None, dry_run=False):
        seen.append(dry_run)
        return plan

    tool._create_modified_straight_connection = fallback
    leg = tool._connect_pair_of_waypoints(
        refinery, tank, connection_types={Prototype.Pipe, Prototype.UndergroundPipe}, dry_run=True
    )
    assert seen == [True] and leg is plan


def test_straight_line_fallback_in_a_dry_run_plans_all_three_parts_and_picks_nothing_up():
    tool = ConnectEntities.__new__(ConnectEntities)
    tool.inspect_inventory = lambda: {"pipe-to-ground": 10, "pipe": 50}
    tool._extend_collision_boxes = lambda *a: None
    tool._clear_collision_boxes = lambda *a: None
    picked = []
    tool.pickup_entities = lambda *a: picked.append(a)

    def part(name, x):
        return PathResult({"entities": {}, "number_of_entities": 1,
                           "planned": [{"name": name, "x": x, "y": 0.5, "direction": 0}]})

    def straight(entity, pos, offsets, margin, idx, n, offset_sign=1, dry_run=False):
        assert dry_run is True
        if isinstance(entity, OilRefinery):
            return {"success": True, "connection_position": Position(x=0.5, y=-6.5), "path": part("pipe-to-ground", 0.5)}
        return {"success": True, "connection_position": pos, "path": None}

    tool.create_straight_line_dict = straight
    tool.get_final_connection_pos = lambda d, o, e: d["connection_position"]
    tool._attempt_path_finding = lambda *a, **k: part("pipe", 5.5)
    refinery = _refinery([IndexedPosition(x=0.5, y=-2.5, type="petroleum-gas")])
    leg = tool._create_modified_straight_connection(
        Position(x=0.5, y=-2.5), Position(x=18.5, y=0.5), {Prototype.Pipe, Prototype.UndergroundPipe},
        source_entity=refinery, target_entity=_tank(20.5, 0.5, []), dry_run=True,
    )
    assert [p["name"] for p in leg["planned"]] == ["pipe-to-ground", "pipe"]
    assert leg["number_of_entities_required"] == 2
    assert picked == []


def test_empty_source_into_a_machine_names_what_the_machine_takes():
    refinery = _refinery(
        [IndexedPosition(x=0.5, y=-2.5, type="petroleum-gas")],
        [IndexedPosition(x=0.5, y=3.5, type="crude-oil")],
    )
    with pytest.raises(Exception) as e:
        _resolver().check_for_recipe_requirement(refinery, [])
    msg = str(e.value)
    assert "takes ['crude-oil']" in msg and "from a fluid output of the source" in msg
