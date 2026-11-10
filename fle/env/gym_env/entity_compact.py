"""Compact, size-bounded rendering of the observation's entity section.

Used when the full tree listing would not fit a character budget. Nothing is
dropped silently: entities with identical state are listed once with all their
positions, and when the budget forces it, values are summarised (and the text
says so) instead of lines being cut.

Input: entity groups as produced by TreeObservationFormatter, i.e.
``{entity_type: [ {key: formatted_value_str, ...}, ... ]}``.
"""

import re
from collections import Counter
from typing import Dict, List, Optional, Tuple

POS_RE = re.compile(r"\((-?\d+(?:\.\d+)?), (-?\d+(?:\.\d+)?)\)")
RECIPE_RE = re.compile(r"^name='([^']+)'")
RESOURCE_RE = re.compile(r"name='([^']+)' count=(\d+)(?: type=\w+)?")

# Detail levels per entity type, least to most compact:
# LOSSLESS: every value;
# SUMMARISE_LONG: per-belt contents as counts (lane totals stay); static size
#   fields (STATIC_KEYS) and empty values not listed;
# SUMMARISE_VARYING: values with more than 3 distinct values become ranges,
#   except KEEP_KEYS (connections, recipe, status, ...) and the positions of a
#   group's belts, ends, pipes and poles (ABSOLUTE_KEYS);
# KEY_VALUES_ONLY: values that differ, outside KEEP_KEYS and ABSOLUTE_KEYS,
#   are not listed; long pipe / pole position lists become counts and areas
#   (belt positions stay);
# STATUS_AND_POSITIONS: status counts and positions;
# COUNTS_ONLY: status counts and the area.
(
    LOSSLESS,
    SUMMARISE_LONG,
    SUMMARISE_VARYING,
    KEY_VALUES_ONLY,
    STATUS_AND_POSITIONS,
    COUNTS_ONLY,
) = range(6)
MAX_LEVEL = COUNTS_ONLY

# Prototype size fields, the same for every entity of a type
STATIC_KEYS = {"dimensions", "tile_dimensions", "health"}
# Empty values, left out from SUMMARISE_LONG on
EMPTY_VALUES = {"[]", "{}"}
LEFT_OUT_NOTE = (
    "dimensions, tile_dimensions, health and empty values ([] / {}) not listed"
)
# Kept per entity down to KEY_VALUES_ONLY
KEEP_KEYS = {
    "status",
    "recipe",
    "direction",
    "pickup_target",
    "drop_target",
    "pickup_position",
    "drop_position",
    "held",
    "fluid",
    "research",
    "lanes",
}

# At SUMMARISE_LONG, list values longer than this (belt contents, positions of
# belts / pipes / poles) are replaced by their counts and area
LONG_VALUE_CHARS = 120

# Values that describe a group of entities (belt groups, pipe groups, power
# networks): their positions stay absolute instead of relative to the group
ABSOLUTE_KEYS = {"belt_positions", "holding", "inputs", "outputs", "pipes", "poles"}

NOTE = (
    "(compact listing to fit the size limit: values shared by a group are shown "
    "once, then where its entities are; +(dx, dy) is relative to the entity's own "
    "position; 'varies' marks values summarized to fit)"
)


def _num(v: float) -> str:
    return str(int(v)) if v == int(v) else f"{v:g}"


def _parse_pos(value: str) -> Optional[Tuple[float, float]]:
    m = POS_RE.fullmatch(value.strip()) if value else None
    return (float(m.group(1)), float(m.group(2))) if m else None


def _clean(key: str, value: str) -> str:
    """Shorten long object reprs to the facts they carry."""
    if key == "recipe":
        m = RECIPE_RE.match(value)
        if m:
            return m.group(1)
    if "name='" in value and "count=" in value:
        return RESOURCE_RE.sub(lambda m: f"{m.group(1)}:{m.group(2)}", value)
    return value


def _relative(value: str, origin: Tuple[float, float]) -> str:
    """Rewrite every (x, y) in a value as an offset from the entity's position."""

    def rel(m):
        dx = float(m.group(1)) - origin[0]
        dy = float(m.group(2)) - origin[1]
        return f"+({_num(round(dx, 2))}, {_num(round(dy, 2))})"

    return POS_RE.sub(rel, value)


def prepare(
    entity: Dict[str, str],
) -> Tuple[Optional[Tuple[float, float]], Dict[str, str]]:
    """Split an entity into its position and its state (geometry made relative)."""
    pos = _parse_pos(entity.get("position", ""))
    state = {}
    for key, value in entity.items():
        if key == "position":
            continue
        value = _clean(key, str(value))
        if pos is not None and key not in ABSOLUTE_KEYS:
            value = _relative(value, pos)
        state[key] = value
    return pos, state


def _runs(values: List[float]) -> List[str]:
    """Sorted numbers as 'a..b by s' runs (3+ evenly spaced) or single values."""
    values = sorted(set(values))
    out, i = [], 0
    while i < len(values):
        j = i
        if i + 2 < len(values):
            step = values[i + 1] - values[i]
            while j + 1 < len(values) and abs(values[j + 1] - values[j] - step) < 1e-6:
                j += 1
        if j - i >= 2:
            out.append(f"{_num(values[i])}..{_num(values[j])} by {_num(step)}")
            i = j + 1
        else:
            out.append(_num(values[i]))
            i += 1
    return out


def _diagonals(
    points: List[Tuple[float, float]],
) -> Tuple[List[str], List[Tuple[float, float]]]:
    """Diagonal lines of 3+ points one tile apart in x and y (belt staircases),
    as "(x0, y0)..(x1, y1) step (1, dy)"; and the points left over."""
    left = set(points)
    parts = []
    for x, y in sorted(points):
        for dy in (1, -1):
            if (x, y) not in left or (x - 1, y - dy) in left:
                continue
            chain = [(x, y)]
            while (chain[-1][0] + 1, chain[-1][1] + dy) in left:
                chain.append((chain[-1][0] + 1, chain[-1][1] + dy))
            if len(chain) >= 3:
                (x0, y0), (x1, y1) = chain[0], chain[-1]
                parts.append(
                    f"({_num(x0)}, {_num(y0)})..({_num(x1)}, {_num(y1)}) step (1, {dy})"
                )
                left -= set(chain)
    return parts, sorted(left)


def positions_text(positions: List[Tuple[float, float]]) -> str:
    """Positions as evenly spaced runs: rows or columns (whichever is shorter),
    and lines with the same runs merged, e.g. (0.5..4.5 by 1, 3.5..15.5 by 6)
    for a 5 x 3 grid; diagonal lines one tile apart as
    (x0, y0)..(x1, y1) step (1, dy) when that is shorter."""
    if not positions:
        return ""

    def encode(points, by_row: bool) -> str:
        lines: Dict[float, List[float]] = {}
        for x, y in points:
            key, other = (y, x) if by_row else (x, y)
            lines.setdefault(key, []).append(other)
        same: Dict[str, List[float]] = {}
        for key in sorted(lines):
            for run in _runs(lines[key]):
                same.setdefault(run, []).append(key)
        parts = []
        for run, keys in same.items():
            for key_run in _runs(keys):
                parts.append(f"({run}, {key_run})" if by_row else f"({key_run}, {run})")
        return " ".join(parts)

    def best(points) -> str:
        a, b = encode(points, True), encode(points, False)
        return a if len(a) <= len(b) else b

    plain = best(positions)
    diagonal, rest = _diagonals(list(set(positions)))
    if diagonal:
        mixed = " ".join(([best(rest)] if rest else []) + diagonal)
        if len(mixed) < len(plain):
            return mixed
    return plain


def _bbox(positions: List[Tuple[float, float]]) -> str:
    xs = [p[0] for p in positions]
    ys = [p[1] for p in positions]
    return f"x {_num(min(xs))}..{_num(max(xs))}, y {_num(min(ys))}..{_num(max(ys))}"


def _kv(d: Dict[str, str]) -> str:
    return ", ".join(f"{k}={v}" for k, v in sorted(d.items()))


ITEMS_RE = re.compile(r"^\[((?:[\w-]+:-?\d+(?:\.\d+)?(?:, )?)*)\]$")


def _summary(values: List[str]) -> str:
    """'varies' plus what is known: a numeric range, per-item count ranges for
    inventories, or the number of distinct values."""
    nums = []
    for v in values:
        try:
            nums.append(float(v))
        except ValueError:
            pass
    if len(nums) == len(values) and nums:
        return f"varies {_num(min(nums))}..{_num(max(nums))}"
    matches = [ITEMS_RE.match(v.strip()) for v in values]
    if all(matches):
        ranges: Dict[str, List[float]] = {}
        empty = 0
        for m in matches:
            body = m.group(1)
            if not body:
                empty += 1
                continue
            for part in body.split(", "):
                name, _, count = part.rpartition(":")
                ranges.setdefault(name, []).append(float(count))
        parts = [
            f"{name} {_num(min(c))}..{_num(max(c))} in {len(c)}"
            for name, c in sorted(ranges.items())
        ]
        if empty:
            parts.append(f"empty in {empty}")
        return "varies [" + "; ".join(parts) + "]"
    return f"varies ({len(set(values))} values)"


NUM = r"-?\d+(?:\.\d+)?"
DIAG_RE = re.compile(rf"\(({NUM}), ({NUM})\)\.\.\(({NUM}), ({NUM})\) step \(1, (-?1)\)")
RUN_RE = re.compile(rf"({NUM})\.\.({NUM}) by ({NUM})")
POINT_RE = re.compile(
    rf"\(({NUM}(?:\.\.{NUM} by {NUM})?), ({NUM}(?:\.\.{NUM} by {NUM})?)\)"
)


def _expand(text: str) -> List[float]:
    m = RUN_RE.fullmatch(text)
    if not m:
        return [float(text)]
    a, b, step = (float(g) for g in m.groups())
    n = int(round((b - a) / step)) + 1 if step else 1
    return [a + i * step for i in range(max(n, 1))]


def _points(value: str) -> List[Tuple[float, float]]:
    """Every absolute position in a value, runs ("(0.5..4.5 by 1, 3.5)") and
    diagonal lines ("(0, 0)..(2, 2) step (1, 1)") expanded."""
    out = []
    for m in DIAG_RE.finditer(value):
        x0, y0, x1, _, dy = (float(g) for g in m.groups())
        out.extend((x0 + i, y0 + i * dy) for i in range(int(round(x1 - x0)) + 1))
    value = DIAG_RE.sub("", value)
    for m in POINT_RE.finditer(value):
        if m.start() > 0 and value[m.start() - 1] == "+":
            continue  # relative offset, not a position
        xs, ys = _expand(m.group(1)), _expand(m.group(2))
        out.extend((x, y) for x in xs for y in ys)
    return out


def _short(key: str, value: str) -> Optional[str]:
    """A long value as counts, or None to keep it as it is. Only per-belt
    contents are shortened (the group's lane totals stay in lanes); positions
    of belts, pipes and poles are kept."""
    if len(value) <= LONG_VALUE_CHARS or key != "holding":
        return None
    n = value.split(" ", 1)[0]
    return f"{n} belts hold items (per-belt contents not listed; lane totals in lanes)"


# A type with this many differing groups lists their keys once, as columns
TABLE_MIN_ROWS = 3

LEVEL_TEXT = {
    STATUS_AND_POSITIONS: "status and positions only",
    COUNTS_ONLY: "count, status and area only",
}


def describe(
    entity_type: str, n: int, level: int, keys: List[str]
) -> Optional[Tuple[str, str]]:
    """(category, "type xN") or (category, "type xN (keys)") for what render_type
    left out of a type, or None when nothing was."""
    if level in LEVEL_TEXT:
        return LEVEL_TEXT[level], entity_type
    if keys and level >= KEY_VALUES_ONLY:
        return "differing values not listed", entity_type
    if keys:
        return "values summarized", f"{entity_type} x{n} ({', '.join(sorted(keys))})"
    return None


def render_type(entity_type: str, entities: List[Dict[str, str]], level: int) -> str:
    return render_type_noted(entity_type, entities, level)[0]


def render_type_noted(
    entity_type: str, entities: List[Dict[str, str]], level: int
) -> Tuple[str, Optional[Tuple[str, str]]]:
    """The type's lines at this detail level, and what was summarised (or None)."""
    prepared = [prepare(e) for e in entities]
    for _, state in prepared:
        if state.get("name") == entity_type:
            del state["name"]  # the type is the header
    n = len(prepared)
    lines = [f"- {entity_type}: {n}"]
    positions = [p for p, _ in prepared if p is not None]
    unplaced = n - len(positions)

    if level >= STATUS_AND_POSITIONS:
        statuses = Counter(s.get("status", "") for _, s in prepared)
        status = ", ".join(f"{k or 'none'} {v}" for k, v in sorted(statuses.items()))
        lines.append(f"  status: {status}")
        if positions:
            where = (
                _bbox(positions) if level == COUNTS_ONLY else positions_text(positions)
            )
            label = "area" if level == COUNTS_ONLY else "at"
            lines.append(f"  {label}: {where}")
        return "\n".join(lines), describe(entity_type, n, level, [])

    noted = set()
    if level >= SUMMARISE_LONG:
        for _, state in prepared:
            for key in list(state):
                if key in STATIC_KEYS or state[key] in EMPTY_VALUES:
                    del state[key]  # stated once in the section header
                    continue
                short = _short(key, state[key])
                if short is not None:
                    state[key] = short
                    noted.add(key)

    if level >= KEY_VALUES_ONLY:
        for _, state in prepared:
            for key in ("pipes", "poles"):
                value = state.get(key)
                if value and len(value) > LONG_VALUE_CHARS:
                    pts = _points(value)
                    if pts:
                        state[key] = (
                            f"{len(pts)} positions in {_bbox(pts)} (not listed)"
                        )
                        noted.add(key)

    keys = set().union(*(s.keys() for _, s in prepared)) if prepared else set()
    shared = {}
    for key in keys:
        vals = {s.get(key) for _, s in prepared}
        if len(vals) == 1 and None not in vals:
            shared[key] = vals.pop()
    varying = sorted(keys - set(shared))

    summarised, dropped = {}, set()
    if level >= SUMMARISE_VARYING:
        for key in varying:
            if key in KEEP_KEYS or key in ABSOLUTE_KEYS:
                continue
            vals = [s.get(key, "") for _, s in prepared]
            if level >= KEY_VALUES_ONLY:
                dropped.add(key)
            elif len(set(vals)) > 3:
                summarised[key] = _summary(vals)
    noted |= set(summarised)
    if shared or summarised:
        lines.append(f"  all: {_kv({**shared, **summarised})}")

    part_keys = [k for k in varying if k not in summarised and k not in dropped]
    partitions: Dict[Tuple, List[Optional[Tuple[float, float]]]] = {}
    order = []
    for pos, state in prepared:
        sig = tuple((k, state.get(k, "-")) for k in part_keys)
        if sig not in partitions:
            partitions[sig] = []
            order.append(sig)
        partitions[sig].append(pos)
    if part_keys:
        order.sort(key=lambda s: -len(partitions[s]))
        # 3+ rows: the keys once as columns, then the values per row
        table = len(order) >= TABLE_MIN_ROWS
        if table:
            lines.append(f"  - columns: {' | '.join(part_keys)}")
        for sig in order:
            group = partitions[sig]
            placed = [p for p in group if p is not None]
            where = positions_text(placed)
            missing = len(group) - len(placed)
            if missing:
                where = (
                    where + " " if where else ""
                ) + f"({missing} without a position)"
            values = " | ".join(v for _, v in sig) if table else _kv(dict(sig))
            lines.append(f"  - {len(group)}: {values} at {where}")
    elif positions or unplaced:
        where = positions_text(positions)
        if unplaced:
            where = (where + " " if where else "") + f"({unplaced} without a position)"
        lines.append(f"  at: {where}")
    if dropped:
        lines.append(f"  (not listed, they differ: {', '.join(sorted(dropped))})")
    return "\n".join(lines), describe(entity_type, n, level, sorted(noted | dropped))


def compact_section(groups: Dict[str, List[Dict[str, str]]], budget_chars: int) -> str:
    """The entity section within ``budget_chars``. Every type starts lossless;
    detail is reduced one level at a time for all types alike; among the types
    at the lowest level, the reductions that remove the least text while
    making the section fit go first (several small ones before one big one). Entities are never
    left out: the section names each type that was summarised and how. If even
    counts do not fit, the counts are given anyway (over the budget)."""
    if not groups:
        return "### Entities\nNone found"
    types = sorted(groups)
    level = {t: LOSSLESS for t in types}
    rendered = {t: render_type_noted(t, groups[t], LOSSLESS) for t in types}

    def section() -> str:
        by_category: Dict[str, List[str]] = {}
        for t in types:
            note = rendered[t][1]
            if note:
                by_category.setdefault(note[0], []).append(note[1])

        def which(items: List[str]) -> str:
            names = [i.split(" x", 1)[0] for i in items]
            others = [t for t in types if t not in names]
            if len(others) < len(items) and all(" (" not in i for i in items):
                return "all types" + (f" except {', '.join(others)}" if others else "")
            return ", ".join(items)

        reduced = [t for t in types if level[t] >= SUMMARISE_LONG]
        parts = [f"{c}: {which(items)}" for c, items in by_category.items()]
        if reduced:
            parts.append(f"{LEFT_OUT_NOTE}: {which(reduced)}")
        header = "### Entities " + NOTE
        if parts:
            header += f"\nSummarized to fit {budget_chars} chars: " + "; ".join(parts)
        return header + "\n" + "\n".join(rendered[t][0] for t in types)

    cache: Dict[Tuple[str, int], Tuple[str, Optional[Tuple[str, str]]]] = {}

    def at(t: str, lvl: int):
        if (t, lvl) not in cache:
            cache[(t, lvl)] = render_type_noted(t, groups[t], lvl)
        return cache[(t, lvl)]

    out = section()
    while len(out) > budget_chars:
        open_types = [t for t in types if level[t] < MAX_LEVEL]
        if not open_types:
            break
        low = min(level[t] for t in open_types)
        candidates = [t for t in open_types if level[t] == low]
        saving = {t: len(rendered[t][0]) - len(at(t, low + 1)[0]) for t in candidates}
        need = len(out) - budget_chars
        enough = [t for t in candidates if saving[t] >= need]
        smaller = [t for t in candidates if 0 < saving[t] < need]
        # the least detail removed: several small reductions when together
        # they are enough, else the smallest single one that is, else the biggest
        if sum(saving[t] for t in smaller) >= need:
            t = min(smaller, key=lambda k: (saving[k], k))
        elif enough:
            t = min(enough, key=lambda k: (saving[k], k))
        else:
            t = max(candidates, key=lambda k: (saving[k], k))
        level[t] += 1
        rendered[t] = at(t, level[t])
        out = section()

    if len(out) > budget_chars:
        # Every type is at counts only and it still does not fit: one line per type
        line = ", ".join(f"{t}: {len(groups[t])}" for t in types)
        out = (
            "### Entities (counts only, to fit the size limit: positions and "
            f"values of all {sum(len(g) for g in groups.values())} entities not listed)\n{line}"
        )
    return out
