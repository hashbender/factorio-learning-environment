"""connect_entities, fluids: a Pump connects from its output port and to its input port, and an empty
StorageTank (a buffer) can be the source for a typed input such as a refinery's crude oil. Server-free.

Before: a Pump fell into the generic FluidHandler case, which builds its ports from `connection_points`,
never set for pumps ("pump ... has no fluid output to connect from"); an empty tank's ports were typed ""
and never matched the refinery's crude-oil input ("The source does not have fluid in it").
"""

import pytest

from fle.env.entities import (
    Direction,
    IndexedPosition,
    OilRefinery,
    Position,
    Pump,
    StorageTank,
)
from fle.env.tools.agent.connect_entities.resolvers.fluid_connection_resolver import (
    FluidConnectionResolver,
)


def _resolver():
    return FluidConnectionResolver(lambda *a, position=None, radius=None, **k: [])


def _pump(fluid=None):
    # a pump at (-184.5, -177.0) facing north: input below, output above (the game's pipe tiles)
    return Pump.model_construct(
        name="pump",
        position=Position(x=-184.5, y=-177.0),
        direction=Direction.UP,
        input_position=Position(x=-184.5, y=-175.5),
        output_position=Position(x=-184.5, y=-178.5),
        connection_points=[Position(x=-184.5, y=-175.5), Position(x=-184.5, y=-178.5)],
        fluid_box=[{"name": fluid, "amount": 10}] if fluid else [],
    )


def _tank(fluid=None):
    return StorageTank.model_construct(
        name="storage-tank",
        position=Position(x=10.5, y=10.5),
        direction=Direction.UP,
        connection_points=[Position(x=8.5, y=8.5), Position(x=12.5, y=12.5)],
        fluid_box=[{"name": fluid, "amount": 100}] if fluid else [],
    )


def _refinery():
    return OilRefinery.model_construct(
        name="oil-refinery",
        position=Position(x=30.5, y=10.5),
        direction=Direction.UP,
        recipe="basic-oil-processing",
        input_connection_points=[IndexedPosition(x=29.5, y=13.5, type="crude-oil")],
        output_connection_points=[IndexedPosition(x=30.5, y=7.5, type="petroleum-gas")],
    )


def test_pump_source_uses_its_output_port():
    pairs = _resolver().resolve(_pump(), Position(x=-184.5, y=-190.5))
    assert pairs and {(s.x, s.y) for s, _ in pairs} == {(-184.5, -178.5)}


def test_pump_target_uses_its_input_port():
    pairs = _resolver().resolve(Position(x=-184.5, y=-160.5), _pump())
    assert pairs and {(t.x, t.y) for _, t in pairs} == {(-184.5, -175.5)}


def test_empty_pump_feeds_a_refinery():
    pairs = _resolver().resolve(_pump(), _refinery())
    assert pairs and pairs[0][1].type == "crude-oil"


def test_pump_holding_water_into_crude_input_still_refused():
    with pytest.raises(Exception) as e:
        _resolver().resolve(_pump("water"), _refinery())
    assert "water" in str(e.value)


def test_empty_tank_feeds_a_refinery():
    pairs = _resolver().resolve(_tank(), _refinery())
    assert pairs
    assert {(t.x, t.y) for _, t in pairs} == {(29.5, 13.5)}


def test_tank_with_crude_still_matches_and_with_water_refused():
    assert _resolver().resolve(_tank("crude-oil"), _refinery())
    with pytest.raises(Exception) as e:
        _resolver().resolve(_tank("water"), _refinery())
    assert "water" in str(e.value)


def test_refinery_into_empty_tank_unchanged():
    pairs = _resolver().resolve(_refinery(), _tank())
    assert pairs and all(s.type == "petroleum-gas" for s, _ in pairs)


def test_empty_tank_to_empty_tank():
    a, b = _tank(), _tank()
    b.position = Position(x=40.5, y=10.5)
    b.connection_points = [Position(x=38.5, y=8.5)]
    assert _resolver().resolve(a, b)
