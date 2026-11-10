# connect_entities

The `connect_entities` tool provides functionality to connect different types of Factorio entities using various connection types like transport belts, pipes and power poles. This document outlines how to use the tool effectively.

## Core Concepts

The connect_entities tool can connect:

- Transport belts (including underground belts)
- Pipes (including underground pipes)
- Power poles
- Walls

For each connection type, the tool handles:

- Pathing around obstacles
- Proper entity rotation and orientation
- Network/group management
- Resource requirements verification
- Connection point validation

## Basic Usage

### General Pattern

```python
# Basic connection between two positions or entities
connection = connect_entities(source, target, connection_type=Prototype.X)

# Connection with multiple waypoints
connection = connect_entities(pos1, pos2, pos3, pos4, connection_type=Prototype.X)
```

### Source/Target Types

The source and target can be:

- Positions
- Entities
- Entity Groups

### Connection Types

You must specify a connection type prototype:

```python
# Single connection type
connection_type=Prototype.TransportBelt

# Multiple compatible connection types
# If you have UndergroundBelts in inventory, use them to simplify above-ground structures
connection_type={Prototype.TransportBelt, Prototype.UndergroundBelt}
```

## Transport Belt Connections

```python
# Connect mining drill output to a furnace inserter
belts = connect_entities(
    drill,
    furnace_inserter,
    connection_type=Prototype.TransportBelt
)

# Belt groups are returned for management
print(f"Created belt line with {len(belts.belts)} belts")
```

Key points:

- Always use inserters between belts and machines/chests
- Use underground belts for crossing other belts
- Belt groups maintain direction and flow information
- Belts already on the map keep their direction, type and position. A route that would change one fails with an error naming that belt, and nothing is built. Connecting from a belt line starts in front of its last belt. Pass `allow_belt_changes=True` to let the tool turn the end belt of an existing line

## Pipe Connections

Pipes connect fluid-handling entities:

```python
# Connect water flow with over and underground pipes
water_pipes = connect_entities(offshore_pump, boiler, {Prototype.Pipe, Prototype.UndergroundPipe})
print(f"Connected offshore_pump at {offshore_pump.position} to boiler at {boiler.position} with {water_pipes}")
```

Key points:

- Respects fluid input/output connection points
- Underground pipes have limited range
- Pipe groups track fluid system IDs

## Power Pole Connections

To add power to entities, you need to connect the target entity (drill, assembling machine, oil refinery etc) to a working power source (steam engine, solar panel etc)

```python
# Connect power
poles = connect_entities(
    steam_engine,
    drill,
    Prototype.SmallElectricPole
)
print(f"Created the connection to power drill at {drill.position} with steam engine at {steam_engine.position}: {poles}")
```

Key points:

- Automatically spaces poles based on wire reach
- Creates electrical networks
- Handles pole to entity connections
- Power groups track network IDs

## Best Practices

1. **Pre-check Resources**

```python
inventory = inspect_inventory()
# use get_connection_amount to see if you have enough
required_count = get_connection_amount(source.position, target.position, connection_type=Prototype.TransportBelt)
assert inventory[Prototype.TransportBelt] >= required_count
```

3. **Entity Groups**

```python
# Work with entity groups
belt_group = connect_entities(source, target, Prototype.TransportBelt)
for belt in belt_group.belts:
    print(f"Belt at {belt.position} flowing {belt.direction}")
```

## Common Patterns

### Many-to-One Connections

When you need to connect multiple sources to a single target with transport belts

1. Establish sources and target
2. Create the main connection by connecting one source to the target with transport belts
3. Connect all remaining sources to the main connection with transport belts

Example: Connecting multiple source inserters to one target inserter

```python
# get the inserter variables
source_inserter_1 = get_entity(Prototype.BurnerInserter, Position(x = 1, y = 2))
source_inserter_2 = get_entity(Prototype.BurnerInserter, Position(x = 3, y = 2))
source_inserter_3 = get_entity(Prototype.BurnerInserter, Position(x = 5, y = 2))
target_inserter = get_entity(Prototype.BurnerInserter, Position(x = 10, y = 28))
# log your general idea what you will do next
print(f"I will create a connection from the inserters at [{source_inserter_1.position}, {source_inserter_2.position}, {source_inserter_3.position}] to the inserter at {target_inserter.position}")
# create the main connection
main_connection = connect_entities(source_inserter_1,
                                    target_inserter,
                                    Prototype.TransportBelt)
# Print out the whole connection for logs
print(f"Created the main connection between inserter at {source_inserter_1.position} to inserter at {target_inserter.position}: {main_connection}")

# Connect source_inserter_2 and source_inserter_3 to the main connection
secondary_sources = [source_inserter_2, source_inserter_3]
for source in secondary_sources:
    # connect the source to main connection
    # Use the first beltgroup from the main connection to connect to
    # Also override the main_connection to get the newest belt groups
    main_connection = connect_entities(source,
                                    main_connection,
                                    Prototype.TransportBelt)
    print(f"Extended main connection to include inserter at {source.position}: {main_connection}")
print(f"Final connection after connecting all inserters to target: {main_connection}")
```

When you want to connect entities to existing power pole groups, similar rules apply.

Assume in this example there is a steam engine at Position(x = 1, y = 2) and the drills are at Position(x = 10, y = 28) and Position(x = 16, y = 28)

```python
steam_engine = get_entity(Prototype.SteamEngine, Position(x = 1, y = 2))
drill_1 = get_entity(Prototype.ElectricMiningDrill, Position(x = 10, y = 28))
drill_2 = get_entity(Prototype.ElectricMiningDrill, Position(x = 16, y = 28))
# create the main connection
main_power_connection = connect_entities(steam_engine,
                                    drill_1,
                                    Prototype.SmallElectricPole)
# Print out the whole connection for logs
print(f"Created the main connection to power drill at {drill_1.position} with steam engine at {steam_engine.position}: {main_power_connection}")

# connect the secondary source to the main power connection
# Use the first ElectricityGroup from the main connection to connect to
# Also override the main_power_connection to get the newest ElectricityGroups
main_power_connection = connect_entities(drill_2,
                                main_power_connection,
                                Prototype.SmallElectricPole)
```

## Troubleshooting

Common issues and solutions:

### 1. Connection Failures

- Verify inventory has required entities
- Ensure compatible connection types

### 3. Entity Groups

- Update stale group references
- Handle group merging properly
- Track network IDs
- Clean up disconnected groups

## Dry run

`connect_entities(..., dry_run=True)` asks whether the connection can be built, without building it. It takes the same arguments as the real call and uses the same route search and the same build check for every placement.

A dry run places nothing, turns nothing, uses no items, takes no game time and leaves you where you are. It needs none of the connecting items in your inventory. It does not raise when the route fails: the failure is in the result.

```python
plan = connect_entities(Position(x=3.5, y=1.5), Position(x=3.5, y=6.5), Prototype.TransportBelt, dry_run=True)
print(plan)
# ConnectDryRun(route_found=True, required={'transport-belt': 6}, in_inventory={'transport-belt': 4}, missing={'transport-belt': 2}, entities=[transport-belt at (3.5, 1.5) DOWN, transport-belt at (3.5, 2.5) DOWN, ...])
```

The result is a `ConnectDryRun`. Its fields can be read as attributes (`plan.route_found`) or like a dict (`plan["route_found"]`):

- `route_found`: True when the game found a route and every placement on it passed the build check
- `entities`: what would be placed, in route order, each with `name`, `position` and `direction` (None for entities without one); printing the result shows the first 40
- `required`: the count of each item the route places, by name
- `in_inventory`: how many of each of those you hold now
- `missing`: the items you are short of, by name (empty when you hold enough); `enough_in_inventory` is True when it is empty
- `belt_changes`: belts already on the map that the route would turn (only possible with `allow_belt_changes=True`)
- `reason`: when `route_found` is False, the message the real call would fail with
- `blocked_at`: the position that message names as blocked, when it names one, else None
- `number_of_entities_required`, `number_of_entities_available`: the total count to place (None when no route was found), and how many of the connecting item you hold

```python
plan = connect_entities(Position(x=3.5, y=1.5), Position(x=3.5, y=6.5), Prototype.Pipe, dry_run=True)
print(plan)
# ConnectDryRun(route_found=False, blocked_at=(3.5, 4.5), reason="Failed to connect {'Pipe'} from x=3.5 y=1.5 to x=3.5 y=6.5. Cannot connect: cannot place pipe at (3.5, 4.5): blocked by stone-furnace")
```

What a dry run does and does not cover:

- The route is the one found on the map as it is now, with the items you hold now. With underground belts or pipes in the connection types, the real call uses as many underground sections as your inventory allows, and so does the dry run.
- With two waypoints, the dry run and the real call use the same route search on the same map.
- With more than two waypoints, each leg is checked separately on the map as it is now, and a tile two legs share is listed once. The real call builds leg by leg and starts each later leg from what the leg before built, so its later legs can use other tiles than the dry run lists.
- With electric poles, `entities` lists a pole at each step of the route that is not already covered; the real call stops placing poles once the target is connected and can add one pole at the target, so its count can differ.
- With belts, the real call refuses a route that would change a belt already on the map unless `allow_belt_changes=True`. The dry run reports a belt at the start of the route that would be turned; other changes to existing belts are only found by the real call, which then builds nothing.
- The real call has no reach rule (it walks the route), and neither has the dry run.
