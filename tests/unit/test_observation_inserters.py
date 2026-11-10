"""Inserters in the observation: pickup/drop targets and the held item (no server)."""

from fle.env.entities import (
    BurnerInserter,
    Dimensions,
    Direction,
    Inserter,
    Inventory,
    Position,
    TileDimensions,
)
from fle.env.gym_env.observation_formatter import TreeObservationFormatter as T


def _kw(**extra):
    return dict(
        position=Position(x=5.5, y=4.5),
        direction=Direction.NORTH,
        energy=0,
        dimensions=Dimensions(width=1, height=1),
        tile_dimensions=TileDimensions(tile_width=1, tile_height=1),
        health=100,
        pickup_position=Position(x=5.5, y=5.5),
        drop_position=Position(x=5.5, y=3.5),
        **extra,
    )


def test_targets_and_held_item_shown():
    ins = Inserter(
        name="inserter",
        pickup_target="transport-belt",
        drop_target="stone-furnace",
        held_item={"name": "iron-ore", "count": 1},
        **_kw(),
    )
    text = T.format_entities([ins.__dict__])
    assert "pickup_target=transport-belt" in text
    assert "drop_target=stone-furnace" in text
    assert "held=iron-ore:1" in text
    assert "pickup_position=(5.5, 5.5)" in text and "drop_position=(5.5, 3.5)" in text
    assert "held_item" not in text


def test_missing_targets_and_empty_hand():
    ins = BurnerInserter(name="burner-inserter", fuel=Inventory(coal=1), **_kw())
    text = T.format_entities([ins.__dict__])
    assert "pickup_target=none" in text and "drop_target=none" in text
    assert "held=empty" in text


def test_fields_parse_from_server_dict():
    # serialize.lua sends these keys; the model keeps them
    ins = Inserter(
        name="fast-inserter",
        **_kw(
            pickup_target="iron-chest",
            drop_target="assembling-machine-1",
            held_item={"name": "iron-gear-wheel", "count": 2},
        ),
    )
    assert ins.pickup_target == "iron-chest"
    assert ins.held_item["count"] == 2
    assert "held=iron-gear-wheel:2" in T.format_entities([ins.__dict__])
