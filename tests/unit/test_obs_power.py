"""Electric network summaries in observations. Server-free.

Poles used to report flow_rate = the energy their network had consumed since
the game started (J), shown as "voltage", and a group was WORKING as soon as
anything had ever drawn power. Poles and power groups now carry the network
summary the power pole GUI shows, and the observation gets a Power section.
"""

from pathlib import Path

import pytest

from fle.env.entities import (
    Dimensions,
    ElectricityPole,
    EntityStatus,
    Position,
    TileDimensions,
)
from fle.env.game_types import Prototype
from fle.env.gym_env.observation import Observation
from fle.env.gym_env.observation_formatter import (
    POWER_NETWORKS_SHOWN,
    BasicObservationFormatter,
    TreeObservationFormatter,
    format_watts,
)
from fle.env.tools.agent.connect_entities.groupable_entities import (
    agglomerate_groupable_entities,
)

COMMON = dict(
    dimensions=Dimensions(width=1, height=1),
    tile_dimensions=TileDimensions(tile_width=1, tile_height=1),
    health=100,
    energy=0,
)

# Measured on a 2.0.73 world: one steam engine (900 kW) and four radars (300 kW each)
OVERLOADED = {
    "id": 1,
    "production": 900000.0,
    "consumption": 900000.0,
    "demand": 1200000.0,
    "generator_max": 900000.0,
    "satisfaction": 0.75,
    "accumulator_charge": 0,
    "accumulator_capacity": 0,
    "poles": 4,
    "generators": 1,
    "accumulators": 0,
    "consumers": 4,
    "low_power": 4,
    "no_power": 0,
}


def _poles(network, n=2, electrical_id=1):
    return [
        ElectricityPole(
            name="small-electric-pole",
            position=Position(x=0.5 + 3 * i, y=0.5),
            prototype=Prototype.SmallElectricPole,
            electrical_id=electrical_id,
            flow_rate=(network or {}).get("consumption", 0.0),
            network=network,
            **COMMON,
        )
        for i in range(n)
    ]


def test_group_carries_the_network_summary():
    (group,) = agglomerate_groupable_entities(_poles(OVERLOADED))
    assert group.electrical_id == 1
    assert group.demand == 1200000.0
    assert group.satisfaction == 0.75
    assert group.status == EntityStatus.LOW_POWER
    assert "voltage" not in repr(group)
    assert "satisfaction=75%" in repr(group)


@pytest.mark.parametrize(
    "change, status",
    [
        ({"low_power": 0, "satisfaction": 1.0, "demand": 900000.0}, "WORKING"),
        (
            {"production": 0.0, "consumption": 0.0, "low_power": 0, "no_power": 4},
            "NO_POWER",
        ),
        (
            {"consumption": 0.0, "low_power": 0, "demand": 0.0, "satisfaction": None},
            "NORMAL",
        ),
    ],
)
def test_group_status_follows_the_network(change, status):
    (group,) = agglomerate_groupable_entities(_poles({**OVERLOADED, **change}))
    assert group.status.name == status


def test_group_without_summary_keeps_the_old_rule():
    (group,) = agglomerate_groupable_entities(_poles(None))
    assert group.status == EntityStatus.NOT_PLUGGED_IN_ELECTRIC_NETWORK


def test_entities_text_shows_power_in_watts():
    (group,) = agglomerate_groupable_entities(_poles(OVERLOADED, n=9))
    text = TreeObservationFormatter.format_entities([group.__dict__])
    assert "demand=1.2 MW" in text and "production=900 kW" in text
    assert "satisfaction=75%" in text and "electrical_id=1" in text
    assert "status=LOW_POWER" in text
    assert "(3 more)" in text


def test_watts():
    assert format_watts(900000) == "900 kW"
    assert format_watts(1200000) == "1.2 MW"
    assert format_watts(60) == "60 W"


def test_power_section():
    text = BasicObservationFormatter.format_power([OVERLOADED])
    assert text.splitlines()[0] == "### Power"
    line = text.splitlines()[1]
    assert line.startswith("- network 1: production 900 kW (generators max 900 kW)")
    assert "consumption 900 kW, demand 1.2 MW, satisfaction 75%" in line
    assert "consumers 4 (low power 4, no power 0)" in line
    assert (
        BasicObservationFormatter.format_power([]) == "### Power\nNo electric networks."
    )
    assert BasicObservationFormatter.format_power(None) == ""


def test_power_section_is_capped():
    nets = [
        {**OVERLOADED, "id": i, "poles": i} for i in range(1, POWER_NETWORKS_SHOWN + 4)
    ]
    lines = BasicObservationFormatter.format_power(nets).splitlines()
    assert len(lines) == 1 + POWER_NETWORKS_SHOWN + 1
    assert lines[-1] == "- (3 more networks)"
    # biggest networks first
    assert lines[1].startswith(f"- network {POWER_NETWORKS_SHOWN + 3}:")


def test_power_networks_round_trip_into_the_observation_text():
    obs = Observation.from_dict({"power_networks": [OVERLOADED]})
    assert obs.power_networks == [OVERLOADED]
    assert obs.to_dict()["power_networks"] == [OVERLOADED]
    raw = TreeObservationFormatter(include_research=False).format(obs).raw_str
    assert "### Power\n- network 1:" in raw
    assert "power_networks" not in Observation.from_dict({}).to_dict()


def test_summary_lua_compiles():
    lupa = pytest.importorskip("lupa")
    root = Path(__file__).resolve().parents[2] / "fle/env"
    for rel in ("mods/serialize.lua", "tools/admin/get_power_networks/server.lua"):
        lupa.LuaRuntime().compile((root / rel).read_text())


STUB_LUA = """
defines = {
    entity_status = {working = 1, low_power = 14, no_power = 15, no_ingredients = 30},
    flow_precision_index = {five_seconds = 0},
    direction = {north = 0, east = 4, south = 8, west = 12},
    inventory = {}, wire_connector_id = {}, wire_type = {}, entity_status_diode = {},
}
game = {tick = 100}
storage = {utils = {}}
local function proto(t) return t end
local stats = {
    output_counts = {["steam-engine"] = 1}, input_counts = {radar = 1, inserter = 1},
    get_flow_count = function(p)
        -- J per tick
        local rates = {["steam-engine"] = 15000, radar = 14000, inserter = 1000}
        return rates[p.name]
    end,
}
local function radar(status, energy)
    return {type = "radar", electric_network_id = 1, electric_buffer_size = 5333, energy = energy,
            status = status, consumption_bonus = 0,
            prototype = proto({get_max_energy_usage = function() return 5000 end,
                               electric_energy_source_prototype = {drain = 0}})}
end
entities = {
    {type = "electric-pole", electric_network_id = 1, electric_network_statistics = stats},
    {type = "electric-pole", electric_network_id = 1, electric_network_statistics = stats},
    {type = "generator", electric_network_id = 1, prototype = proto({get_max_power_output = function() return 15000 end})},
    radar(14, 3750), radar(14, 3750), radar(14, 3750),
    -- an idle inserter: only its drain is demanded
    {type = "inserter", electric_network_id = 1, electric_buffer_size = 600, energy = 600, status = 30,
     prototype = proto({get_max_energy_usage = function() return 300 end,
                        electric_energy_source_prototype = {drain = 6.5}})},
    {type = "accumulator", electric_network_id = 1, energy = 1000000, electric_buffer_size = 5000000},
    -- a chest: no network
    {type = "container"},
    -- an unpowered second network
    {type = "electric-pole", electric_network_id = 2,
     electric_network_statistics = {output_counts = {}, input_counts = {}, get_flow_count = function() return 0 end}},
}
surface = {index = 1, find_entities_filtered = function() return entities end}
force = {name = "player"}
"""


def test_network_summary_lua_against_stub_entities():
    lupa = pytest.importorskip("lupa")
    lua = lupa.LuaRuntime()
    lua.execute(STUB_LUA)
    source = (
        Path(__file__).resolve().parents[2] / "fle/env/mods/serialize.lua"
    ).read_text()
    lua.execute(source)
    nets = lua.eval("storage.utils.electric_network_summaries(surface, force)")
    one, two = nets[1], nets[2]
    assert one.production == 15000 * 60
    assert one.consumption == 15000 * 60
    assert one.generator_max == 900000
    # 3 radars at 300 kW wanting power + the idle inserter's drain
    assert one.demand == pytest.approx(3 * 300000 + 6.5 * 60)
    assert one.satisfaction == pytest.approx(900000 / (900000 + 390))
    assert (one.poles, one.generators, one.consumers, one.low_power) == (2, 1, 4, 3)
    assert (one.accumulator_charge, one.accumulator_capacity) == (1000000, 5000000)
    assert two.poles == 1 and two.satisfaction is None
    # cached for the tick
    same = lua.eval(
        "function(t) return rawequal(t, storage.utils.electric_network_summaries(surface, force)) end"
    )
    assert same(nets)
