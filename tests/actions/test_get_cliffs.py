import pytest

from fle.env.entities import BoundingBox, Position


@pytest.fixture()
def game(configure_game):
    return configure_game(inventory={}, merge=True)


def _game_cliffs(game, x, y, radius):
    response = game.instance.rcon_client.send_command(
        "/sc local o = {} for _, c in pairs(game.surfaces[1].find_entities_filtered"
        f"{{type = 'cliff', position = {{{x}, {y}}}, radius = {radius}}}) do "
        "o[#o + 1] = c.position.x .. ',' .. c.position.y end rcon.print(table.concat(o, ';'))"
    )
    return {
        (float(a), float(b))
        for a, b in (p.split(",") for p in response.split(";") if p)
    }


def test_get_cliffs_near_character(game):
    radius = 200
    cliffs = game._get_cliffs(radius=radius, limit=10000)
    position = game.player_location
    assert {(c.x, c.y) for c in cliffs} == _game_cliffs(
        game, position.x, position.y, radius
    )
    distances = [(c.x - position.x) ** 2 + (c.y - position.y) ** 2 for c in cliffs]
    assert distances == sorted(distances)


def test_get_cliffs_limit_and_area(game):
    assert len(game._get_cliffs(radius=200, limit=3)) <= 3
    area = BoundingBox(
        left_top=Position(x=-100, y=-100),
        right_bottom=Position(x=100, y=100),
        left_bottom=Position(x=-100, y=100),
        right_top=Position(x=100, y=-100),
    )
    for cliff in game._get_cliffs(area=area, limit=10000):
        assert -100 <= cliff.x <= 100 and -100 <= cliff.y <= 100
