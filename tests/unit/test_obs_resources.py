"""Resources section of the observation: patches near the factory (no server)."""

from fle.env.gym_env.observation import Observation
from fle.env.gym_env.observation_formatter import BasicObservationFormatter as B

RESOURCES = {
    "area": {"x1": -40.0, "y1": -30.0, "x2": 60.0, "y2": 50.0},
    "buildings": 120,
    "margin": 100.0,
    "radius": 1000.0,
    "truncated": False,
    "patches": [
        {
            "name": "iron-ore",
            "amount": 292213.0,
            "tiles": 310,
            "x1": 70.5,
            "y1": -60.5,
            "x2": 90.5,
            "y2": -44.5,
            "infinite": False,
            "clipped": False,
        },
        {
            "name": "iron-ore",
            "amount": 1512000.0,
            "tiles": 1240,
            "x1": -120.5,
            "y1": 10.5,
            "x2": -80.5,
            "y2": 52.5,
            "infinite": False,
            "clipped": True,
        },
        {
            "name": "crude-oil",
            "amount": 900000.0,
            "tiles": 3,
            "x1": -280.5,
            "y1": -313.5,
            "x2": -270.5,
            "y2": -300.5,
            "infinite": True,
            "normal": 300000.0,
            "clipped": False,
        },
    ],
}


def test_format_resources():
    text = B.format_resources(RESOURCES)
    assert text.startswith("### Resources\n")
    assert (
        "within 100 tiles of the area x -40..60, y -30..50 (your buildings and you)"
        in text
    )
    assert "- iron-ore: 2 patches, 1,804,213 total" in text
    lines = text.splitlines()
    big = lines.index(
        "  - 1,512,000 on 1,240 tiles, x -120.5..-80.5, y 10.5..52.5"
        " (continues past 1000 tiles from you; counted up to there)"
    )
    assert lines[big + 1] == "  - 292,213 on 310 tiles, x 70.5..90.5, y -60.5..-44.5"
    assert "- crude-oil: 1 field\n" in text
    assert "3 wells, yield 300% total (amount 900,000), x -280.5..-270.5" in text


def test_format_resources_unknown_and_empty():
    assert B.format_resources(None) == ""
    empty = dict(RESOURCES, patches=[], buildings=0)
    text = B.format_resources(empty)
    assert "(you)" in text and "- none" in text
    assert "search limit reached" in B.format_resources(dict(RESOURCES, truncated=True))


def test_resources_round_trip():
    obs = Observation.from_dict({"resources": RESOURCES})
    assert obs.resources == RESOURCES
    assert obs.to_dict()["resources"] == RESOURCES
    assert "resources" not in Observation.from_dict({}).to_dict()
