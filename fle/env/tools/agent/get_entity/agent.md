# get_entity

The `get_entity` tool allows you to get objects and update variables with their new versions. It is crucial to regularly get the newest variables at the start of every program to ensure no variables are stale

Inputs

- Prototype.X
- Position

Outputs
Entity object

## Basic Usage

Creating power connection
Assume the SolarPanel and ElectronicMiningDrill exist at the given positions

```python
# get the variables
solar_panel = get_entity(Prototype.SolarPanel, Position(x = 1, y = 2))
drill_1 = get_entity(Prototype.ElectricMiningDrill, Position(x = 10, y = 28))
# create the main connection
main_power_connection = connect_entities(solar_panel,
                                    drill_1,
                                    Prototype.SmallElectricPole)
```

Connecting one inserter to another (inserter_1 at Position(x = 12, y = 11) to inserter_2 at Position(x = 0, y = 0))

```python
# get the inserter entities
inserter_1 = get_entity(Prototype.BurnerInserter, position = Position(x = 12, y = 11))
inserter_2 = get_entity(Prototype.BurnerInserter, position = Position(x = 0, y = 0))
# connect the two inserters (source -> target). Passing in the entity will result in them being connected intelligently.
belts = connect_entities(
    inserter_1, #.drop_position,
    inserter_2, #.pickup_position,
    Prototype.TransportBelt
)
```

**Which entity is returned**

- `get_entity(prototype, position)` returns the entity of that prototype whose tiles contain `position`: its centre (`entity.position`) or any point on any of its tiles. It never returns a neighbouring entity.
- Tile (x, y) covers x <= px < x + 1 and y <= py < y + 1. A position exactly on the border between two adjacent entities of the same prototype belongs to the one with the larger x (or larger y). A position on an entity's outer border counts for that entity when no other entity of the prototype covers it.
- When no entity of that prototype covers the position, get_entity raises an error that lists up to 3 entities of that prototype within 30 tiles, nearest first (distance from the position to each entity's centre), e.g. `Could not get assembling-machine-1 at position (7.5, 1.5): no assembling-machine-1 covers that position. Nearest: assembling-machine-1 at (4.5, 1.5) 3.0 tiles away; assembling-machine-1 at (1.5, 1.5) 6.0 tiles away.`
- `Prototype.BeltGroup`, `Prototype.PipeGroup` and `Prototype.ElectricityGroup` are different: get_entity returns a group that get_entities finds around the position, or None when there is none.

**Outdated variables**

- Regularly update your variables using entity = get_entity(Prototype.X, entity.position)

**Status detail**

- When an entity's `status` has a concrete reason, `status_detail` gives it, as the game's entity window shows it: the missing ingredients with the count in the machine and the count one craft needs (`missing iron-plate (0 of 1 per craft)`), the electric network (`no power (electric network 7)`), the output contents (`output full (iron-gear-wheel 100)`), the fuel slot, the drop or pickup target (`waiting for space in iron-chest at (3.5, 4.5)`), or the mining area. Otherwise `status_detail` is None.
