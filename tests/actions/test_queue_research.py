import pytest

from fle.env.game_types import Technology


@pytest.fixture()
def game(configure_game):
    return configure_game(all_technologies_researched=False)


def test_queue_research_appends_in_order(game):
    game.set_research(Technology.Automation)
    # Factorio 2.0: automation-2 needs automation, steel-processing and logistic-science-pack
    queue = game.queue_research(
        [
            Technology.Logistics,
            "logistic-science-pack",
            "steel-processing",
            "automation-2",
        ]
    )
    assert queue == [
        "automation",
        "logistics",
        "logistic-science-pack",
        "steel-processing",
        "automation-2",
    ]


def test_queue_research_returns_the_queue(game):
    game.set_research(Technology.Automation)
    assert game.queue_research([]) == ["automation"]


def test_queue_research_missing_prerequisite_queues_nothing(game):
    game.set_research(Technology.Logistics)
    with pytest.raises(Exception) as exc_info:
        game.queue_research(Technology.Automation2)
    assert str(exc_info.value) == (
        "Cannot queue automation-2. Missing prerequisites (not researched or queued): "
        "automation, logistic-science-pack, steel-processing"
    )
    assert game.queue_research([]) == ["logistics"]


def test_queue_research_trigger_technology(game):
    with pytest.raises(Exception) as exc_info:
        game.queue_research(Technology.OilProcessing)
    assert str(exc_info.value).startswith(
        "Cannot queue oil-processing. It is a trigger technology, "
        "completed by a game action instead of labs: mine crude-oil"
    )
