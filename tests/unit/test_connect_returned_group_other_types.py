"""connect_entities: the server returns the whole belt line / pole network after
building, and it can hold entities of types the call did not request (a splitter
on the belt line, a faster belt, another pole type). The client looked each one
up among the requested types only and raised "Failed to create splitter object
from response" although the belts had been built. Now: other groupable types are
built by their own prototype, anything else (a splitter) is left out, and the
call never fails on them. Server-free."""

import pytest

from fle.env.entities import ElectricityPole, TransportBelt
from fle.env.game_types import Prototype
from fle.env.tools.agent.connect_entities.client import ConnectEntities
from fle.env.tools.agent.connect_entities.groupable_entities import (
    agglomerate_groupable_entities,
)


class _Result:
    def __init__(self, entities):
        self.entities = {i + 1: e for i, e in enumerate(entities)}
        self.raw_response = "<raw>"


def _client():
    return ConnectEntities.__new__(ConnectEntities)


def _belt_dict(name, x, uid):
    return {
        "name": name,
        "id": uid,
        "position": {"x": x, "y": 0.5},
        "direction": 4,
        "input_position": {"x": x - 1, "y": 0.5},
        "output_position": {"x": x + 1, "y": 0.5},
        "dimensions": {"width": 1, "height": 1},
        "tile_dimensions": {"tile_width": 1, "tile_height": 1},
        "health": 150,
        "energy": 0,
        "inventory": {"left": {}, "right": {}},
        "warnings": {},
    }


def _splitter_dict(x):
    # what serialize_entity gives for a splitter on the line (not a belt)
    return {
        "name": "splitter",
        "position": {"x": x, "y": 1.0},
        "direction": 4,
        "dimensions": {"width": 1, "height": 2},
        "tile_dimensions": {"tile_width": 1, "tile_height": 2},
        "health": 170,
        "warnings": {},
    }


def _info(types):
    return ConnectEntities._get_connection_info(None, types)


def test_splitter_in_returned_belt_line_does_not_raise():
    info = _info({Prototype.TransportBelt})
    result = _Result(
        [_belt_dict("transport-belt", x + 0.5, x + 1) for x in range(4)]
        + [_splitter_dict(4.5)]
        + [_belt_dict("transport-belt", x + 0.5, x + 1) for x in range(5, 8)]
    )
    groupable, path = _client()._get_groupable_entities(
        result, info["metaclasses"], info["names_to_types"]
    )
    assert path == []
    assert len(groupable) == 7
    assert all(isinstance(e, TransportBelt) for e in groupable)
    assert {e.name for e in groupable} == {"transport-belt"}
    # and the belts still group
    assert agglomerate_groupable_entities(groupable)


def test_other_belt_tier_is_built_by_its_own_prototype():
    info = _info({Prototype.TransportBelt, Prototype.UndergroundBelt})
    result = _Result(
        [_belt_dict("transport-belt", 0.5, 1), _belt_dict("fast-transport-belt", 1.5, 2)]
    )
    groupable, _ = _client()._get_groupable_entities(
        result, info["metaclasses"], info["names_to_types"]
    )
    assert [e.prototype for e in groupable] == [
        Prototype.TransportBelt,
        Prototype.FastTransportBelt,
    ]


def _pole_dict(name, x, uid):
    return {
        "name": name,
        "id": uid,
        "position": {"x": x, "y": 0.5},
        "direction": 0,
        "dimensions": {"width": 1, "height": 1},
        "tile_dimensions": {"tile_width": 1, "tile_height": 1},
        "health": 100,
        "energy": 0,
        "electrical_id": 7,
        "flow_rate": 0,
        "warnings": {},
    }


def test_other_pole_type_in_returned_network_does_not_raise():
    # Nov 10: the same failure on a pole network holding another pole type
    info = _info({Prototype.SmallElectricPole})
    result = _Result(
        [
            _pole_dict("small-electric-pole", 0.5, 1),
            _pole_dict("medium-electric-pole", 6.5, 2),
            _pole_dict("small-electric-pole", 12.5, 3),
        ]
    )
    groupable, path = _client()._get_groupable_entities(
        result, info["metaclasses"], info["names_to_types"]
    )
    assert path == []
    assert all(isinstance(e, ElectricityPole) for e in groupable)
    assert [e.prototype for e in groupable] == [
        Prototype.SmallElectricPole,
        Prototype.MediumElectricPole,
        Prototype.SmallElectricPole,
    ]


def test_a_broken_requested_entity_still_raises():
    info = _info({Prototype.TransportBelt})
    result = _Result([{"name": "transport-belt", "position": "nonsense", "warnings": {}}])
    with pytest.raises(Exception, match="Failed to create transport-belt object"):
        _client()._get_groupable_entities(
            result, info["metaclasses"], info["names_to_types"]
        )


def test_pickup_never_touches_unrequested_entities():
    picked = []
    c = _client()
    c.pickup_entity = picked.append
    info = _info({Prototype.Pipe})
    c.pickup_entities(
        _Result([_splitter_dict(0.5)]), info["metaclasses"], info["names_to_types"]
    )
    assert picked == []
