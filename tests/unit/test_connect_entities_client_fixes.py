"""connect_entities client fixes, server-free.

- Substation is a pole connection type (was ValueError).
- The "available" count is the plain item of the set (it was whichever came last
  in the set, so it changed with PYTHONHASHSEED).
- An ElectricityGroup source starts from its pole nearest the target.
- The refinery/chemical-plant straight-line fallback no longer flips the shared
  offsets on each retry.
- The character walks the route before it is built; where it cannot walk to a tile
  (beyond a cliff), it stands as near as it can within reach.
"""

import math

from fle.env.entities import (
    Direction,
    ElectricityGroup,
    ElectricityPole,
    OilRefinery,
    Position,
)
from fle.env.game_types import Prototype
from fle.env.tools.agent.connect_entities.client import ConnectEntities
from fle.env.tools.agent.connect_entities.resolver import ConnectionType
from fle.env.tools.agent.connect_entities.resolvers.power_connection_resolver import (
    PowerConnectionResolver,
)


def test_substation_is_a_power_connection():
    assert (
        ConnectEntities._get_connection_type(None, Prototype.Substation)
        == ConnectionType.POWER
    )


def test_available_count_uses_the_plain_item_whatever_the_set_order():
    for types in (
        {Prototype.TransportBelt, Prototype.UndergroundBelt},
        {Prototype.UndergroundBelt, Prototype.TransportBelt},
        {Prototype.Pipe, Prototype.UndergroundPipe},
        {Prototype.FastUndergroundBelt, Prototype.FastTransportBelt},
    ):
        info = ConnectEntities._get_connection_info(None, types)
        assert "underground" not in info["last_connection_prototype"]
        assert "to-ground" not in info["last_connection_prototype"]


def test_group_source_starts_from_the_pole_nearest_the_target():
    poles = [
        ElectricityPole.model_construct(name="small-electric-pole", position=Position(x=x, y=0.5))
        for x in (0.5, 40.5, 20.5)
    ]
    group = ElectricityGroup.model_construct(poles=poles, position=Position(x=0, y=0))
    resolver = PowerConnectionResolver(lambda *a, **k: [])
    pairs = resolver.resolve(group, Position(x=100, y=0))
    assert [p[0].x for p in pairs] == [40.5, 20.5, 0.5]


def test_straight_line_offsets_are_not_flipped_in_place():
    seen = []

    class Fake:
        def get_straight_line_path(self, pos, offset, margin, run_idx, n):
            seen.append(dict(offset))
            return {"success": True, "connection_position": pos, "path": None}

    refinery = OilRefinery.model_construct(direction=Direction.UP, position=Position(x=0, y=0))
    offsets = {"UP": {"x": 0, "y": -1}}
    for _ in range(3):
        ConnectEntities.create_straight_line_dict(
            Fake(), refinery, Position(x=0, y=0), offsets, 3, 1, 10, offset_sign=-1
        )
    assert offsets == {"UP": {"x": 0, "y": -1}}
    assert seen == [{"x": 0, "y": 1}] * 3


def test_stand_points_start_on_the_tile_then_this_side_first():
    pts = ConnectEntities.stand_points((10.5, 0.5), (0.0, 0.0))
    assert pts[0] == (10.5, 0.5)
    assert all(math.dist(p, (10.5, 0.5)) <= 6.5 for p in pts)
    ring3 = pts[1:9]
    assert ring3[0][0] < 10.5, "the nearest side to the character first"
