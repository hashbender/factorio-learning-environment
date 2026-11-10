"""Keep connect_entities from changing belts that were already on the map.

Before a belt connection is built, the belts around the waypoints are recorded.
Afterwards they are compared: if a belt that was there before has a different
direction, name or underground pairing, or is gone, everything the call placed
is removed again, the old belts are put back, and the call fails naming the belt.
"""

from typing import Dict, Iterable, List, NamedTuple, Optional, Tuple

BELT_TYPES = ("transport-belt", "underground-belt", "splitter", "loader", "linked-belt")
# Routes can wander around obstacles; record this far beyond the waypoints.
MARGIN = 30

_DIRECTIONS = {0: "UP", 4: "RIGHT", 8: "DOWN", 12: "LEFT"}

Key = Tuple[float, float]


class BeltState(NamedTuple):
    name: str
    direction: int
    # underground belts: "input" or "output", and the paired belt's position ("-" if none)
    io_type: str = "-"
    neighbour: str = "-"


def bounding_box(positions: Iterable[Tuple[float, float]], margin: float = MARGIN):
    xs, ys = zip(*positions)
    return min(xs) - margin, min(ys) - margin, max(xs) + margin, max(ys) + margin


def snapshot_command(player_index: int, box) -> str:
    x0, y0, x1, y1 = box
    types = ",".join(f"'{t}'" for t in BELT_TYPES)
    return (
        "/sc local r = {} "
        f"for _, e in pairs(game.surfaces[1].find_entities_filtered{{area = {{{{{x0}, {y0}}}, {{{x1}, {y1}}}}}, type = {{{types}}}}}) do "
        "local t, n = '-', '-' "
        "if e.type == 'underground-belt' then t = e.belt_to_ground_type "
        "local nb = e.neighbours if nb then n = nb.position.x .. ':' .. nb.position.y end end "
        "r[#r + 1] = e.position.x .. ',' .. e.position.y .. ',' .. e.name .. ',' .. e.direction .. ',' .. t .. ',' .. n end "
        "rcon.print('belts:' .. table.concat(r, ';'))"
    )


def parse_snapshot(reply) -> Optional[Dict[Key, BeltState]]:
    text = str(reply or "").strip()
    if not text.startswith("belts:"):
        return None
    belts = {}
    for item in filter(None, text[len("belts:") :].split(";")):
        x, y, name, direction, io_type, neighbour = item.split(",")
        belts[(float(x), float(y))] = BeltState(
            name, int(direction), io_type, neighbour
        )
    return belts


def changed_belts(
    before: Dict[Key, BeltState], after: Dict[Key, BeltState]
) -> List[Tuple[Key, BeltState, Optional[BeltState]]]:
    """Belts that were there before and now differ (None: the belt is gone)."""
    return [
        (pos, old, after.get(pos))
        for pos, old in before.items()
        if after.get(pos) != old
    ]


def new_belts(before: Dict[Key, BeltState], after: Dict[Key, BeltState]):
    return [(pos, state) for pos, state in after.items() if pos not in before]


def direction_name(direction: int) -> str:
    return _DIRECTIONS.get(direction, str(direction))


def describe_change(pos: Key, old: BeltState, new: Optional[BeltState]) -> str:
    where = f"{old.name} at ({pos[0]}, {pos[1]}) facing {direction_name(old.direction)}"
    if new is None:
        return f"{where} would be removed"
    if new.name != old.name:
        return f"{where} would be replaced by {new.name}"
    if new.direction != old.direction or new.io_type != old.io_type:
        return f"{where} would be turned to face {direction_name(new.direction)}"
    return f"{where} would be paired with a different underground belt"


def rollback_command(player_index: int, before, after) -> str:
    """Lua that removes the belts this call placed (back into the inventory) and restores the old ones."""
    ops = []
    for (x, y), state in new_belts(before, after):
        ops.append(
            f"do local e = s.find_entity('{state.name}', {{{x}, {y}}}) "
            f"if e then e.destroy() c.insert{{name = '{state.name}', count = 1}} end end"
        )
    for (x, y), old, new in changed_belts(before, after):
        if new is not None and new.name == old.name:
            ops.append(
                f"do local e = s.find_entity('{old.name}', {{{x}, {y}}}) if e then "
                f"if e.type == 'underground-belt' and e.belt_to_ground_type ~= '{old.io_type}' then e.rotate() end "
                f"if e.direction ~= {old.direction} then e.direction = {old.direction} end end end"
            )
            continue
        if new is not None:
            ops.append(
                f"do local e = s.find_entity('{new.name}', {{{x}, {y}}}) "
                f"if e then e.destroy() c.insert{{name = '{new.name}', count = 1}} end end"
            )
        io = f", type = '{old.io_type}'" if old.io_type != "-" else ""
        ops.append(
            f"do local e = s.create_entity{{name = '{old.name}', position = {{{x}, {y}}}, "
            f"direction = {old.direction}, force = c.force{io}}} "
            f"if e and c.get_item_count('{old.name}') > 0 then c.remove_item{{name = '{old.name}', count = 1}} end end"
        )
    return (
        f"/sc local c = storage.agent_characters[{player_index}] local s = game.surfaces[1] "
        + " ".join(ops)
    )


def conflict_message(changes, rolled_back: bool) -> str:
    listed = "; ".join(describe_change(*c) for c in changes[:3])
    more = f" (and {len(changes) - 3} more)" if len(changes) > 3 else ""
    undone = (
        "Nothing was built: the belts this call placed were picked up and the existing belts were restored."
        if rolled_back
        else "The existing belts could not all be restored."
    )
    return (
        f"This connection would change existing belts: {listed}{more}. {undone} "
        "Existing belts are only changed when allow_belt_changes=True is passed."
    )
