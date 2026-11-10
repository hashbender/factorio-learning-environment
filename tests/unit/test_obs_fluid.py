"""Fluid facts in observations: pipe groups, fluidboxes, pump flow. Server-free.

Factorio 2.0 removed the per-pipe flow reading, so pipes used to report
flow_rate=0 and every pipe group holding fluid read FULL_OUTPUT. Pipe groups
now carry the fluid, the amount in their pipes and the pipes' capacity, and
fluidboxes show amount/capacity and whether they are inputs or outputs.
"""

from pathlib import Path

import pytest

from fle.env.entities import (
    Boiler,
    Dimensions,
    EntityStatus,
    OffshorePump,
    Pipe,
    Position,
    TileDimensions,
)
from fle.env.game_types import Prototype
from fle.env.gym_env.observation_formatter import TreeObservationFormatter
from fle.env.tools.agent.connect_entities.groupable_entities import (
    agglomerate_groupable_entities,
)

COMMON = dict(
    dimensions=Dimensions(width=1, height=1),
    tile_dimensions=TileDimensions(tile_width=1, tile_height=1),
    health=100,
    energy=0,
)


def _pipes(n, amount, segment=1, fluid="water"):
    return [
        Pipe(
            name="pipe",
            position=Position(x=0.5, y=0.5 + i),
            prototype=Prototype.Pipe,
            fluidbox_id=segment,
            contents=amount * n,
            amount=amount,
            capacity=100,
            fluid=fluid if amount else None,
            **COMMON,
        )
        for i in range(n)
    ]


def test_pipe_group_reports_fluid_amount_and_capacity():
    (group,) = agglomerate_groupable_entities(_pipes(4, 75))
    assert group.fluid == "water"
    assert group.amount == 300
    assert group.capacity == 400
    # no flow reading in 2.0: a filled group is not "full output"
    assert group.status == EntityStatus.NORMAL
    assert "amount=300/400" in repr(group)


def test_empty_pipe_group_is_empty():
    (group,) = agglomerate_groupable_entities(_pipes(3, 0))
    assert group.status == EntityStatus.EMPTY
    assert group.amount == 0
    assert group.fluid is None


def test_pipe_flow_rate_is_not_a_false_zero():
    assert _pipes(1, 50)[0].flow_rate is None


def test_pipe_group_positions_are_capped_with_a_count():
    (group,) = agglomerate_groupable_entities(_pipes(10, 100))
    text = TreeObservationFormatter.format_entities([group.__dict__])
    shown = TreeObservationFormatter.GROUP_POSITIONS_SHOWN
    assert f"({10 - shown} more)" in text
    assert "(0.5, 0.5)" in text and "(0.5, 9.5)" not in text
    assert "amount=1000" in text and "capacity=1000" in text and "fluid=water" in text
    assert "FULL_OUTPUT" not in text


def test_fluidboxes_show_amount_capacity_temperature_and_type():
    boiler = Boiler(
        name="boiler",
        position=Position(x=0, y=0.5),
        prototype=Prototype.Boiler,
        fluid_box=[
            {
                "index": 1,
                "name": "water",
                "amount": 200,
                "temperature": 15,
                "capacity": 200,
                "type": "input",
            },
            {
                "index": 2,
                "name": "steam",
                "amount": 120.4,
                "temperature": 165,
                "capacity": 200,
                "type": "output",
            },
        ],
        **COMMON,
    )
    text = TreeObservationFormatter.format_entities([boiler.__dict__])
    assert "fluid_box=[water 200/200 input, steam 120/200 165C output]" in text


def test_offshore_pump_flow_rate_is_shown():
    pump = OffshorePump(
        name="offshore-pump",
        position=Position(x=0.5, y=0.5),
        prototype=Prototype.OffshorePump,
        flow_rate=1200.0,
        fluid_box=[{"name": "water", "amount": 100, "temperature": 15}],
        **COMMON,
    )
    text = TreeObservationFormatter.format_entities([pump.__dict__])
    assert "flow_rate=1200" in text
    # older servers send no capacity/type: name and amount still show
    assert "fluid_box=[water 100]" in text


def test_serialize_lua_compiles():
    lupa = pytest.importorskip("lupa")
    source = (
        Path(__file__).resolve().parents[2] / "fle/env/mods/serialize.lua"
    ).read_text()
    lupa.LuaRuntime().compile(source)
