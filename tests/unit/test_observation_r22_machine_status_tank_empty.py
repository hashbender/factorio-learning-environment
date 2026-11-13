"""r22: tests for harness_fle_machine_status_patch.py and harness_fle_tank_empty_patch.py, run against a PATCHED FLE
checkout: FLE_ROOT=/path/to/fle python -m pytest test_r22_harness_fle_formatter.py (skipped without FLE_ROOT).
Fixtures are entity __dict__s as the gym environment builds them (environment.py: [e.__dict__ for e in entities])."""
import os
import re
import sys

import pytest

# in the fork: this checkout (copied from tools/r22/test_r22_harness_fle_formatter.py of the harness repo)
FLE_ROOT = os.environ.get("FLE_ROOT") or os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, FLE_ROOT)

from fle.env.entities import (  # noqa: E402
    Dimensions,
    EntityStatus,
    Inserter,
    MiningDrill,
    Position,
    StorageTank,
    TileDimensions,
)
from fle.env.gym_env import observation_formatter as of  # noqa: E402
from fle.env.gym_env.entity_compact import STATUS_AND_POSITIONS, render_type  # noqa: E402
from fle.env.gym_env.observation_formatter import TreeObservationFormatter as T  # noqa: E402

WAIT = EntityStatus.WAITING_FOR_SOURCE_ITEMS
SPACE = EntityStatus.WAITING_FOR_SPACE_IN_DESTINATION


def _inserter(name, x, y, status=WAIT, detail=None):
    return Inserter(
        name=name,
        type="inserter",
        position=Position(x=x, y=y),
        energy=0,
        dimensions=Dimensions(width=1, height=1),
        tile_dimensions=TileDimensions(tile_width=1, tile_height=1),
        health=100,
        status=status,
        status_detail=detail,
        pickup_position=Position(x=x, y=y - 1),
        drop_position=Position(x=x, y=y + 1),
    ).__dict__


def _drill(x, y, detail):
    return MiningDrill(
        name="electric-mining-drill",
        type="mining-drill",
        position=Position(x=x, y=y),
        energy=0,
        dimensions=Dimensions(width=3, height=3),
        tile_dimensions=TileDimensions(tile_width=3, tile_height=3),
        health=300,
        status=SPACE,
        status_detail=detail,
        drop_position=Position(x=x, y=y + 2),
    ).__dict__


def _factory():
    """330 machines: every inserter waits on its own assembler / furnace (a target position per inserter, as
    serialize.lua detail_target writes it), drills wait on their own belts, scattered positions."""
    ents = []
    kinds = [("fast-inserter", 150), ("inserter", 100), ("long-handed-inserter", 40), ("burner-inserter", 20)]
    i = 0
    for name, n in kinds:
        for k in range(n):
            x, y = 0.5 + (i * 7) % 211, -40.5 + (i * 13) % 97
            if k % 3 == 0:
                d = f"waiting for space in stone-furnace at ({x + 1:g}, {y + 2:g})"
                ents.append(_inserter(name, x, y, SPACE, d))
            else:
                d = f"waiting for items from assembling-machine-1 at ({x + 0.5:g}, {y - 2:g})"
                ents.append(_inserter(name, x, y, WAIT, d))
            i += 1
    for k in range(20):
        x, y = 100.5 + 3 * k, 60.5 + (k % 4) * 9
        ents.append(_drill(x, y, f"waiting for space in transport-belt at ({x:g}, {y + 2:g})"))
    return ents


def test_patched():
    src = open(of.__file__).read()
    assert "r22: the lines that are listed share the room" in src
    assert hasattr(of, "MACHINE_LINE_CHARS") and hasattr(of, "MACHINE_DETAIL_POS_RES")


def test_every_type_listed_within_budget():
    text = T.format_machine_status(_factory())
    assert len(text) <= of.MACHINE_SECTION_CHARS
    for name in ("fast-inserter", "inserter", "long-handed-inserter", "burner-inserter", "electric-mining-drill"):
        assert f"\n- {name}: " in text, name
    assert "not listed)" not in text.splitlines()[-1]
    for line in text.splitlines()[1:]:
        assert len(line) <= of.MACHINE_LINE_CHARS


def test_target_positions_leave_the_group_key():
    text = T.format_machine_status(_factory())
    line = next(x for x in text.splitlines() if x.startswith("- inserter: "))
    # one state per reason: the 100 inserters are 2 groups, not 100
    assert re.match(r"- inserter: 100 \(\d+ waiting for items from assembling-machine-1 at \(", line), line
    assert line.count("waiting for items from assembling-machine-1 at ") == 1
    assert line.count("waiting for space in stone-furnace at ") == 1


def test_line_cap_says_how_many_positions_are_not_listed():
    ents = [
        _inserter("fast-inserter", 0.5 + (k * 7) % 301, 0.5 + (k * 11) % 151, WAIT,
                  f"waiting for items from assembling-machine-1 at ({k}.5, 3.5)")
        for k in range(400)
    ]
    text = T.format_machine_status(ents)
    line = text.splitlines()[1]
    assert len(line) <= of.MACHINE_LINE_CHARS
    m = re.search(r" \+(\d+) more positions\)$", line)
    assert m and 0 < int(m.group(1)) < 400, line
    assert line.startswith("- fast-inserter: 400 (400 waiting for items from assembling-machine-1 at (")


def test_many_states_are_counted_when_positions_are_not_enough():
    ents = [
        _inserter("inserter", 0.5 + k, 0.5, WAIT,
                  f"waiting for items from transport-belt at ({k}.5, 1.5); belt has iron-plate {k}, not taken now "
                  f"by assembling-machine-1 at ({k}.5, 3.5) (holds iron-plate {k + 10})")
        for k in range(200)
    ]
    line = T.format_machine_status(ents).splitlines()[1]
    assert len(line) <= of.MACHINE_LINE_CHARS
    assert re.search(r"\d+ more machines in \d+ other states\)$", line), line
    assert "assembling-machine-1 at (" not in line and "transport-belt at (" not in line


@pytest.mark.parametrize(
    "detail, state",
    [
        ("waiting for items from assembling-machine-1 at (12.5, -3.5)", "waiting for items from assembling-machine-1"),
        ("waiting for space in (3, 4): no entity there, iron-plate on the ground",
         "waiting for space in: no entity there, iron-plate on the ground"),
        ("no minable resources in the mining area (-2, -2) to (3, 3)", "no minable resources in the mining area"),
        ("output fluid box full (crude-oil 100); its output is connected to pipe at (1.5, 2.5), pipe at (2.5, 2.5)",
         "output fluid box full (crude-oil 100); its output is connected to pipe, pipe"),
        ("missing iron-plate (0 of 1 per craft)", "missing iron-plate (0 of 1 per craft)"),
        ("no power (electric network 3)", "no power (electric network 3)"),
    ],
)
def test_detail_without_target_positions(detail, state):
    text = T.format_machine_status([_inserter("inserter", 5.5, 6.5, WAIT, detail)])
    assert text == f"### Machine Status\n- inserter: 1 (1 {state} at (5.5, 6.5))"


def test_small_section_unchanged():
    ents = [_inserter("inserter", 0.5 + k, 4.5, EntityStatus.WORKING) for k in range(3)]
    assert T.format_machine_status(ents) == "### Machine Status\n- inserter: 3 (3 working)"


def _tank(x, fluid_box, detail=None, status=EntityStatus.WORKING):
    return StorageTank(
        name="storage-tank",
        type="storage-tank",
        position=Position(x=x, y=-42.5),
        energy=0,
        dimensions=Dimensions(width=3, height=3),
        tile_dimensions=TileDimensions(tile_width=3, tile_height=3),
        health=500,
        fluid_box=fluid_box,
        status=status,
        status_detail=detail,
    ).__dict__


WATER = [{"index": 1, "name": "water", "amount": 1234.5, "temperature": 15, "capacity": 25000, "type": "input-output"}]


def _tanks_group(ents):
    return T._entity_groups(ents)["storage-tank"]


def test_empty_tank_with_detail():
    out = render_type("storage-tank", _tanks_group([_tank(-90.5, [], "empty"), _tank(-58.5, {}, "empty")]),
                      STATUS_AND_POSITIONS)
    assert "  status: EMPTY 2" in out


def test_empty_tank_without_detail_and_full_tank():
    out = render_type("storage-tank", _tanks_group([_tank(-90.5, []), _tank(-58.5, {}), _tank(-30.5, WATER)]),
                      STATUS_AND_POSITIONS)
    assert "  status: EMPTY 2, WORKING 1" in out


def test_other_tank_status_kept():
    out = render_type("storage-tank", _tanks_group([_tank(-90.5, [], None, EntityStatus.NOT_CONNECTED)]),
                      STATUS_AND_POSITIONS)
    assert "  status: NOT_CONNECTED 1" in out


def test_fluid_amount_key():
    group = [{"position": "(1.5, 1.5)", "status": "WORKING", "fluid_amount": "0"},
             {"position": "(4.5, 1.5)", "status": "WORKING", "fluid_amount": "250.0", "fluid_box": "[]"}]
    assert "  status: EMPTY 1, WORKING 1" in render_type("storage-tank", group, STATUS_AND_POSITIONS)


def test_compact_section_shows_empty_tanks():
    ents = _factory() + [_tank(-90.5, [], "empty"), _tank(-58.5, {})]
    text = T.format_entities_compact(ents, 6000)
    block = text[text.index("- storage-tank: 2"):].split("\n- ", 1)[0]
    assert "EMPTY" in block and "WORKING" not in block, block
