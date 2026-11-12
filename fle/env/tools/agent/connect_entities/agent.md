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
- How a belt route is found. With an underground belt among the connection types, the route is first searched tile by tile (below); if that finds none, it follows the game's walking path. With belts only, it first follows the game's walking path, and is searched tile by tile if that gives no route. The game's walking path treats belts already on the map as walls: it goes round them (however far), never across. The tile-by-tile search:
  - New belts go only on buildable tiles that no existing belt outputs onto (a belt there would join that line).
  - With an underground belt among the connection types (e.g. `{Prototype.TransportBelt, Prototype.UndergroundBelt}`), an underground pair carries the line under whatever is in its way (other belts, buildings, water). The exit is at most the game's maximum distance past its entrance: 5 tiles for UndergroundBelt (4 tiles crossed), 7 for FastUndergroundBelt, 9 for ExpressUndergroundBelt. The entrance is fed from straight behind and the exit sends the items straight on; an empty start tile can be the entrance and an empty end tile the exit.
  - Underground belts are used only for these crossings. If the crossings need more than you hold and a route without them exists, that route is used; if not, the route with them is returned and the item check names what is missing.
  - A pair never spans or stands inside a tunnel of the same underground belt on the same axis (the game would re-pair it).
  - With an underground belt alone as the connection type, the surface tiles of the route get the matching transport belt.
  - With several belt tiers listed, the surface belts are the lowest tier listed. With several underground belts listed, one kind is used: the one of the same tier as the surface belts if you hold 2 or more, else the first other listed kind (lowest tier first) you hold 2 or more of.
  - The dry run takes the same route as the real call.
- When there is no belt route, the error starts with "Failed to find a path." and names the blocked tile nearest the target that the search reached and what is on it (or the existing belt that outputs onto it), and says whether underground belts were allowed and how many you hold

## Pipe Connections

Pipes connect fluid-handling entities:

```python
# Connect water flow with over and underground pipes
water_pipes = connect_entities(offshore_pump, boiler, {Prototype.Pipe, Prototype.UndergroundPipe})
print(f"Connected offshore_pump at {offshore_pump.position} to boiler at {boiler.position} with {water_pipes}")
```

Key points:

- Respects fluid input/output connection points
- Pipe groups track fluid system IDs
- What each connection type builds:
  - `Prototype.Pipe`: pipes only. Pipe-to-ground in your inventory is not used. The route follows the game's walking path; if that cannot be built (it leads over a cliff, the path search times out, or there is none), the tool searches a route tile by tile.
  - `{Prototype.Pipe, Prototype.UndergroundPipe}`: the route is searched tile by tile (if that finds none, it follows the game's walking path, as with `Prototype.Pipe`). Every straight run of the route becomes pipe-to-ground pairs, back to back, each exit up to 10 tiles past its entrance (the game's maximum), as long as the pipe-to-ground you hold last. Surface pipes remain at the two ends, at each turn, on straight runs shorter than 4 tiles, and wherever the pipe-to-ground you hold have run out. A pair also carries the pipe under anything in its way (cliffs, water, trees, buildings, other pipes).
  - `Prototype.UndergroundPipe` alone: pipe-to-ground pairs only, back to back, in a straight line from the start tile to the end tile (both must have the same x or the same y), as few pairs as the 10-tile reach allows. The first entrance connects above ground only to the tile behind it (on the side away from the end tile), and the last exit only to the tile in front of it (beyond the end tile).
- The tile-by-tile search puts pipes only on tiles where a pipe can be built, and not beside pipes of another fluid system.
- A route uses no more pipe-to-ground than you hold, except when crossing an obstacle needs more and no route of plain pipes is found: then nothing is built, and the error (or the dry run's `missing`) says how many pipe-to-ground the route needs.
- When a route has room for more pipe-to-ground pairs than you hold, the returned PipeGroup's `notes` (and the dry run's `notes`) say how many it has room for, how many you hold, and how many it uses.

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

- Poles go in a near-straight line from the source to the target, each as far from the last as the wire reach allows (small 7.5 tiles, medium 9, big 30, substation 18), on a tile where the pole can be built. The line only bends round tiles where a pole cannot be built (trees, rocks, water, cliffs, buildings).
- If no tile within reach gets the line closer to the target (e.g. a lake wider than the reach), the poles follow the game's walking path round it instead.
- A connection from a pole group starts from the group's pole nearest the target. A source that is not a pole but is already powered by one starts from that pole.
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

## Walking, items and time

- The real call first walks the character along the route with `move_to`, in game time, so that every entity it builds is within reach on the way (it walks to the start of the route first). Then it builds the whole connection. The character ends where the walk ended, near the end of the route. If it cannot walk to a part of the route, the call fails there and builds nothing more.
- Every item the route places must be in your inventory, counted per item (e.g. pipes and pipe-to-ground separately). If any item is short, nothing is built and the error says what is required and what you hold.

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

A dry run places nothing, turns nothing, uses no items, takes no game time and leaves you where you are. It needs none of the connecting items in your inventory. It does not walk the route, as the real call does. It does not raise when the route fails: the result says why.

```python
plan = connect_entities(Position(x=3.5, y=1.5), Position(x=3.5, y=6.5), Prototype.TransportBelt, dry_run=True)
print(plan)
# ConnectDryRun(route_found=True, required={'transport-belt': 6}, in_inventory={'transport-belt': 4}, missing={'transport-belt': 2}, entities=[transport-belt at (3.5, 1.5) DOWN, transport-belt at (3.5, 2.5) DOWN, ...])
# or
# ConnectDryRun(route_found=False, blocked_at=(3.5, 4.5), reason="Failed to connect {'TransportBelt'} from x=3.5 y=1.5 to x=3.5 y=6.5. Cannot connect: cannot place transport-belt at (3.5, 4.5): blocked by stone-furnace")
```

The `ConnectDryRun` has (as attributes, or like a dict: `plan["route_found"]`):

- `route_found`: True when the game found a route and every placement on it passed the build check
- `entities`: what would be placed, in route order, each with `name`, `position` and `direction` (None for entities without one), and for underground belts and pipe-to-ground `type`: "input" for the entrance, "output" for the exit. `direction` is the one to pass to `place_entity` or `place_layout` to build that same entity. Printing shows the first 40
- `required`, `in_inventory`, `missing`: per item name, how many the route places, how many you hold, and how many you are short of; `enough_in_inventory` is True when nothing is missing
- `belt_changes`: belts already on the map that the route would turn (only possible with `allow_belt_changes=True`)
- `notes`: facts about the route, e.g. that it has room for more pipe-to-ground pairs than you hold
- `reason`: when `route_found` is False, the message the real call would fail with; `blocked_at`: the position that message names, else None
- `number_of_entities_required` (None when no route was found), `number_of_entities_available`: the total to place, and how many of the connecting item you hold

What a dry run covers:

- Each leg (between two waypoints) stops searching after 25 seconds: further position pairs and path searches are not tried, and the error says so and how many pairs were not tried. The dry run and the real call each have this limit.
- The route is found on the map as it is now, with the items you hold now: with `Prototype.UndergroundPipe` among the connection types, it uses as many underground sections as your inventory allows, as the real call does; underground belts are used as described under Transport Belt Connections.
- With two waypoints, the dry run and the real call use the same route search on the same map.
- With more than two waypoints, each leg is checked separately on the map as it is now, and a tile two legs share is listed once. The real call builds leg by leg and starts each later leg from what the leg before built, so its later legs can use other tiles than the dry run lists.
- With electric poles, `entities` lists every pole the real call places. The real call stops early if a pole it places joins the target pole's network, and can add one pole next to a target machine the line did not cover, so its count can differ by that.
- A pipe connection to or from an oil refinery or chemical plant with `{Prototype.Pipe, Prototype.UndergroundPipe}` has one more fallback: a short underground run out of the machine's port, then a route between the ends of those runs. A dry run tries it too, building nothing.
- With belts, the real call refuses a route that would change a belt already on the map unless `allow_belt_changes=True`. The dry run reports a belt at the start of the route that would be turned; other changes to existing belts are only found by the real call, which then builds nothing.
