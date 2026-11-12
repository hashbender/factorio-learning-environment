# place_layout

`place_layout(layout, position, legend=None, copies=1, offset=None, dry_run=False, max_seconds=None)` builds many entities in one call, from your inventory, with the same rules as `place_entity`: each entity uses one item from your inventory, needs the game's build check to pass and must be within your reach when it is placed. It sets the recipes and filters you give. It connects, fuels and fills nothing.

The layout is a list of entries, with `x`, `y` relative to `position` (entity `position + (x, y)`, given as for `place_entity`):

```python
layout = [
    {"entity": Prototype.WoodenChest, "x": 0, "y": 0},
    {"entity": Prototype.AssemblingMachine1, "x": 3, "y": 0, "recipe": Prototype.IronGearWheel},
    (Prototype.TransportBelt, 0, 2, Direction.RIGHT),        # tuple form: (entity, x, y[, direction])
]
result = place_layout(layout, Position(x=10.5, y=4.5), copies=3, offset=Position(x=0, y=4))
print(result)
```

Entry keys: `entity` (Prototype, required), `x`, `y` (default 0) or `position` (relative Position), `direction` (Direction, default UP), `recipe` (assembling machines; Prototype or RecipeName), `filter` (inserters with filter slots; an item Prototype), `type` (underground belts: `"input"` or `"output"`; `direction` is the belt's travel direction for both). For pipe-to-ground there is no `type`; `direction` is the side its underground connection faces, as with `place_entity`.

Or a text grid, one character per tile, with a `legend`. The grid's top-left tile is the tile containing `position`; `.` and space are empty tiles; empty lines before the first row and after the last are ignored. A legend character marks an entity's top-left tile; the rest of its footprint may repeat the same character or be empty (`"FF\nFF"` is one 2x2 furnace). Legend values: a Prototype, `(Prototype, Direction)`, or a dict like an entry without `x`/`y`.

```python
place_layout("FF.\nFF>", Position(x=0, y=0), legend={"F": Prototype.StoneFurnace, ">": (Prototype.TransportBelt, Direction.RIGHT)})
```

`copies=N` builds the layout N times, copy k shifted by `k * offset`. At most 1000 entities per call.

## What happens

1. **Check (no game time, nothing built).** Every entity is checked: the game's build check against the map as it is, overlaps with other entities of the same layout, the map being generated or charted, recipe/filter/type valid (recipe unlocked, machine can craft it), and the items needed against your inventory. Entities already standing exactly as asked (same entity, position, direction) count as `already built` and use no item.
2. If anything fails, **nothing is placed**: `ok=False`, `reason` and `problems` list each failing entity with its reason, `missing` gives the items you lack (item: count).
3. With `dry_run=True` it stops here: `ok=True` means a real call would start building; `stops` and `walk_seconds_estimate` (straight-line walk at running speed) are given.
4. **Build.** The entities are split into stops: a free tile from which every entity of the stop is within reach. You walk to each stop in turn (as `move_to`, real game time) and the entities in reach are placed there; entities are placed instantly, as with `place_entity`. The walk is the time cost. You end at the last stop (`character_position`).

Placement after the check is **not atomic**. If the walk to a stop fails, that stop's entities are not placed (each one's `reason` names the stop and the walk error) and the call goes on to the next stop; the result's `reason` lists the stops it could not reach. If `max_seconds` is reached, building stops. If the map changed since the check, that entity fails. Everything placed so far stays. The result lists every entity with its status and reason. Calling `place_layout` again with the same arguments skips what is already built and places the rest.

`max_seconds`: before walking to a stop, the call stops if the time used so far plus the straight-line walk to that stop exceeds this. The call runs inside your program and counts against its time limit.

## Result

`LayoutResult` (True in an `if` when `ok`): `ok`, `dry_run`, `total`, `placed`, `already_built`, `entries` (every entity: `index`, `copy`, `name`, `position`, `direction`, `status`, `reason`), `problems` (entries not placed, with reasons), `warnings` (e.g. an assembling machine placed facing north), `required`, `in_inventory`, `missing`, `stops`, `walk_tiles_estimate`, `walk_seconds_estimate`, `ticks` (game ticks the call took), `seconds`, `character_position`, `reason`. Positions in `entries` are where the game puts each entity's centre. Entry `status`: `placed`, `already built`, `would place` (passed the check, not built), `blocked` or `invalid` (failed the check), `failed` (refused when placing), `not placed` (building stopped before it).

`reason` texts of entries include: `blocked by stone-furnace at (3, 4.5)`, `blocked by water at (9, 3)`, `overlaps layout entry 2 (stone-furnace at (1, 1))`, `tile (140, -62) is in a part of the map that has not been generated or charted`, `burner-mining-drill must be placed on a resource it can mine; there is none under it`, `recipe X is not unlocked yet (research needed)`, `no free tile to stand on within reach of it`, `out of reach (...)`, `could not walk to stop 2 at (x, y): ...`.

Errors are raised (nothing checked or placed) for malformed input: unknown keys, a grid character missing from the legend, `copies > 1` without an offset, more than 1000 entities.
