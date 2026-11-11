import json
import math
import time
from typing import Any, Dict, List, Optional, Union

from fle.env import DirectionInternal
from fle.env import entities as ent
from fle.env.game_types import Prototype, RecipeName
from fle.env.tools import Tool
from fle.env.tools.agent.move_to.client import MoveTo

MAX_ENTRIES = 1000
_ENTRY_KEYS = {"entity", "x", "y", "position", "direction", "recipe", "filter", "type"}
# Character running speed in vanilla: 0.15 tiles per tick, 9 tiles per second (for the estimate only)
_TILES_PER_SECOND = 0.15 * 60


def _name(value: Any, what: str) -> str:
    if isinstance(value, Prototype):
        return value.value[0]
    if isinstance(value, RecipeName):
        return value.value
    if isinstance(value, str) and value:
        return value
    raise ValueError(f"{what} must be a Prototype or a name, not {value!r}")


def _direction(value: Any) -> int:
    if value is None:
        return 0
    if not isinstance(value, (ent.Direction, DirectionInternal)):
        raise ValueError(f"direction must be a Direction, not {value!r}")
    return int(DirectionInternal.to_factorio_direction(value))


def _template(spec: Any, where: str, relative: bool) -> Dict[str, Any]:
    """One layout entry (or grid legend value) as plain data for the game."""
    if isinstance(spec, (tuple, list)):
        parts = list(spec)
        if relative:
            if len(parts) not in (3, 4):
                raise ValueError(
                    f"{where}: a tuple entry is (entity, x, y) or (entity, x, y, direction), not {spec!r}"
                )
            spec = dict(zip(("entity", "x", "y", "direction"), parts))
        else:
            if len(parts) not in (1, 2):
                raise ValueError(
                    f"{where}: a tuple legend value is (entity,) or (entity, direction), not {spec!r}"
                )
            spec = dict(zip(("entity", "direction"), parts))
    elif isinstance(spec, Prototype) and not relative:
        spec = {"entity": spec}
    if not isinstance(spec, dict):
        raise ValueError(f"{where}: expected a dict, not {spec!r}")
    unknown = set(spec) - _ENTRY_KEYS
    if unknown:
        raise ValueError(
            f"{where}: unknown key(s) {sorted(unknown)}; keys are {sorted(_ENTRY_KEYS)}"
        )
    if "entity" not in spec:
        raise ValueError(f"{where}: 'entity' is required")
    out: Dict[str, Any] = {"name": _name(spec["entity"], f"{where}: entity")}
    if relative:
        if "position" in spec:
            p = spec["position"]
            if isinstance(p, tuple):
                p = ent.Position(x=p[0], y=p[1])
            if not isinstance(p, ent.Position):
                raise ValueError(f"{where}: position must be a Position")
            out["x"], out["y"] = float(p.x), float(p.y)
        else:
            for k in ("x", "y"):
                v = spec.get(k, 0)
                if not isinstance(v, (int, float)) or isinstance(v, bool):
                    raise ValueError(f"{where}: {k} must be a number, not {v!r}")
                out[k] = float(v)
    elif "x" in spec or "y" in spec or "position" in spec:
        raise ValueError(f"{where}: a legend value has no position (the grid gives it)")
    out["dir"] = _direction(spec.get("direction"))
    if spec.get("recipe") is not None:
        out["recipe"] = _name(spec["recipe"], f"{where}: recipe")
    if spec.get("filter") is not None:
        out["filter"] = _name(spec["filter"], f"{where}: filter")
    if spec.get("type") is not None:
        if spec["type"] not in ("input", "output"):
            raise ValueError(f"{where}: type must be 'input' or 'output'")
        out["ugtype"] = spec["type"]
    return out


def _as_list(value: Any) -> list:
    if isinstance(value, dict):
        if not value:
            return []
        return [value[k] for k in sorted(value, key=lambda k: int(k))]
    return list(value or [])


def _as_dict(value: Any) -> Dict[str, int]:
    if not isinstance(value, dict):
        return {}
    return {str(k): int(v) for k, v in value.items()}


def _hex(payload: dict) -> str:
    return json.dumps(payload, separators=(",", ":")).encode("utf-8").hex()


def _decode(response: Any, error_message) -> dict:
    if isinstance(response, str):
        try:
            return json.loads(
                bytes.fromhex(response.strip().strip('"')).decode("utf-8")
            )
        except ValueError:
            pass
    raise Exception(f"Could not place layout - {error_message(str(response))}")


def _entry_model(e: dict) -> ent.LayoutEntry:
    d = e.get("dir")
    try:
        direction = ent.Direction(int(d)) if d is not None else None
    except ValueError:
        direction = None
    return ent.LayoutEntry(
        index=int(e.get("i", 0)),
        copy=int(e.get("copy", 1)),
        name=str(e.get("name", "")),
        position=ent.Position(x=float(e.get("x", 0)), y=float(e.get("y", 0))),
        direction=direction,
        status=str(e.get("status") or "not placed"),
        reason=str(e["reason"]) if e.get("reason") else None,
    )


class PlaceLayout(Tool):
    def __init__(self, connection, game_state):
        super().__init__(connection, game_state)
        self.move_to = MoveTo(connection, game_state)

    def _walker(self):
        """The namespace's move_to (the loaded tool, with the host's patches), else our own."""
        walker = getattr(self.game_state, "move_to", None)
        if callable(walker) and not isinstance(walker, type):
            return walker
        return self.move_to

    def _tick(self) -> Optional[int]:
        out = self.connection.rcon_client.send_command("/sc rcon.print(game.tick)")
        try:
            return int(str(out).strip())
        except (TypeError, ValueError):
            return None

    def __call__(
        self,
        layout: Union[List[Any], str],
        position: ent.Position,
        legend: Optional[Dict[str, Any]] = None,
        copies: int = 1,
        offset: Optional[ent.Position] = None,
        dry_run: bool = False,
        max_seconds: Optional[float] = None,
    ) -> ent.LayoutResult:
        """
        Builds a layout of entities from your inventory: checks every entity first, then walks to each
        stop and places the entities in reach there, as place_entity does.
        :param layout: list of entries (dicts with entity, x, y and optional direction, recipe, filter,
            type; or (entity, x, y[, direction]) tuples), x/y relative to position; or a text grid
            (one character per tile, '.' or space = nothing) with a legend
        :param position: anchor: entries are placed at position + (x, y); a grid's top-left tile is the
            tile containing position
        :param legend: for a grid: character -> Prototype, (Prototype, Direction) or dict like an entry
            without x/y
        :param copies: build the layout this many times, copy k shifted by k * offset
        :param offset: shift between copies (Position)
        :param dry_run: check and report only; nothing is built, no time passes
        :param max_seconds: stop before walking to a stop that would end after this many seconds
        :return: LayoutResult (True in an `if` when every entity stands as asked)
        """
        t0 = time.monotonic()
        if isinstance(position, tuple):
            position = ent.Position(x=position[0], y=position[1])
        if not isinstance(position, ent.Position):
            raise ValueError("position must be a Position")
        if not isinstance(copies, int) or isinstance(copies, bool) or copies < 1:
            raise ValueError("copies must be an integer >= 1")
        if offset is None:
            offset = ent.Position(x=0, y=0)
        if isinstance(offset, tuple):
            offset = ent.Position(x=offset[0], y=offset[1])
        if not isinstance(offset, ent.Position):
            raise ValueError("offset must be a Position")
        if copies > 1 and offset.x == 0 and offset.y == 0:
            raise ValueError("copies > 1 needs a non-zero offset")

        payload: Dict[str, Any] = {
            "anchor": {"x": float(position.x), "y": float(position.y)},
            "copies": copies,
            "offset": {"x": float(offset.x), "y": float(offset.y)},
        }
        if isinstance(layout, str):
            if not legend or not isinstance(legend, dict):
                raise ValueError(
                    "a text grid needs a legend: {character: Prototype, ...}"
                )
            rows = layout.split("\n")
            while rows and not rows[0].strip():
                rows.pop(0)
            while rows and not rows[-1].strip():
                rows.pop()
            if not rows:
                raise ValueError("the grid is empty")
            if not all(r.isascii() for r in rows):
                raise ValueError("grid characters must be ASCII")
            legend_out = {}
            for ch, spec in legend.items():
                if not isinstance(ch, str) or len(ch) != 1 or ch in " .\n":
                    raise ValueError(
                        f"legend key {ch!r}: one character, not space, '.' or newline"
                    )
                legend_out[ch] = _template(spec, f"legend[{ch!r}]", relative=False)
            used = {c for r in rows for c in r if c not in " ."}
            unknown = sorted(used - set(legend_out))
            if unknown:
                raise ValueError(f"grid character(s) {unknown} not in the legend")
            count = sum(1 for r in rows for c in r if c not in " .")
            payload["grid"] = {"rows": rows, "legend": legend_out}
        else:
            if not isinstance(layout, (list, tuple)) or not layout:
                raise ValueError(
                    "layout must be a non-empty list of entries or a text grid"
                )
            payload["entries"] = [
                _template(e, f"layout[{i}]", relative=True)
                for i, e in enumerate(layout)
            ]
            count = len(layout)
        if count * copies > MAX_ENTRIES:
            raise ValueError(
                f"the layout has up to {count * copies} entities; at most {MAX_ENTRIES} per call"
            )

        response, _ = self.execute(self.player_index, "plan", _hex(payload))
        plan = _decode(response, self.get_error_message)
        entries = {int(e["i"]): e for e in _as_list(plan.get("entries"))}
        stops = [
            {
                "x": float(s["x"]),
                "y": float(s["y"]),
                "entries": [int(i) for i in _as_list(s.get("entries"))],
            }
            for s in _as_list(plan.get("stops"))
        ]
        required = _as_dict(plan.get("required"))
        have = _as_dict(plan.get("have"))
        missing = _as_dict(plan.get("missing"))
        char = plan.get("character") or {}
        here = (float(char.get("x", 0)), float(char.get("y", 0)))

        # stops in walking order: nearest next, from where the character stands
        ordered, rest, at = [], list(stops), here
        while rest:
            nxt = min(rest, key=lambda s: math.hypot(s["x"] - at[0], s["y"] - at[1]))
            rest.remove(nxt)
            ordered.append(nxt)
            at = (nxt["x"], nxt["y"])
        walk, at = 0.0, here
        for s in ordered:
            walk += math.hypot(s["x"] - at[0], s["y"] - at[1])
            at = (s["x"], s["y"])

        problems = [e for e in entries.values() if e.get("reason")]
        can_build = not problems and not missing

        def result(
            ok: bool, reason: Optional[str], ticks: int = 0, where=None
        ) -> ent.LayoutResult:
            models = [_entry_model(entries[i]) for i in sorted(entries)]
            counts: Dict[str, int] = {}
            for m in models:
                counts[m.status] = counts.get(m.status, 0) + 1
            pos = where or here
            return ent.LayoutResult(
                ok=ok,
                dry_run=dry_run,
                total=len(models),
                placed=counts.get("placed", 0),
                already_built=counts.get("already built", 0),
                entries=models,
                problems=[m for m in models if m.reason and m.status != "placed"],
                warnings=[
                    m.reason for m in models if m.reason and m.status == "placed"
                ],
                required=required,
                in_inventory=have,
                missing=missing,
                stops=[ent.Position(x=s["x"], y=s["y"]) for s in ordered],
                walk_tiles_estimate=round(walk, 1),
                walk_seconds_estimate=round(walk / _TILES_PER_SECOND, 1),
                ticks=ticks,
                seconds=round(time.monotonic() - t0, 1),
                character_position=ent.Position(x=pos[0], y=pos[1]),
                reason=reason,
            )

        if not can_build or dry_run:
            for e in entries.values():
                if e.get("status") == "ok":
                    e["status"] = "would place"
        if not can_build:
            parts = []
            if problems:
                parts.append(
                    f"{len(problems)} of {len(entries)} entities cannot be placed"
                )
            if missing:
                parts.append(
                    "missing items: "
                    + ", ".join(f"{k} x{v}" for k, v in sorted(missing.items()))
                )
            return result(False, "nothing was placed: " + "; ".join(parts))
        if dry_run:
            return result(True, None)

        for e in entries.values():
            if e.get("status") == "ok":
                e["status"] = "not placed"
        tick0 = plan.get("tick")
        walker = self._walker()
        stop_reason = None
        where = here
        for n, s in enumerate(ordered):
            if max_seconds is not None:
                dist = math.hypot(s["x"] - where[0], s["y"] - where[1])
                if time.monotonic() - t0 + dist / _TILES_PER_SECOND > max_seconds:
                    stop_reason = f"stopped before stop {n + 1} of {len(ordered)}: max_seconds={max_seconds} reached"
                    break
            if math.hypot(s["x"] - where[0], s["y"] - where[1]) > 0.5:
                try:
                    p = walker(ent.Position(x=s["x"], y=s["y"]))
                    where = (float(p.x), float(p.y))
                except Exception as exc:  # noqa: BLE001
                    stop_reason = (
                        f"could not walk to stop {n + 1} at ({s['x']}, {s['y']}): {exc}"
                    )
                    break
            batch = [
                {
                    k: entries[i][k]
                    for k in (
                        "i",
                        "name",
                        "item",
                        "x",
                        "y",
                        "dir",
                        "recipe",
                        "filter",
                        "ugtype",
                    )
                    if entries[i].get(k) is not None
                }
                for i in s["entries"]
            ]
            try:
                response, _ = self.execute(
                    self.player_index, "place", _hex({"entries": batch})
                )
                done = _decode(response, self.get_error_message)
            except Exception as exc:  # noqa: BLE001
                stop_reason = f"placing at stop {n + 1} failed: {exc}"
                break
            for r in _as_list(done.get("entries")):
                e = entries[int(r["i"])]
                e["status"] = r.get("status") or "failed"
                e["reason"] = r.get("reason")
            c = done.get("character") or {}
            where = (float(c.get("x", where[0])), float(c.get("y", where[1])))
            self.game_state.player_location = ent.Position(x=where[0], y=where[1])
        if stop_reason:
            for e in entries.values():
                if e.get("status") == "not placed":
                    e["reason"] = stop_reason
        tick1 = self._tick()
        ticks = (tick1 - int(tick0)) if (tick1 is not None and tick0 is not None) else 0
        bad = [
            e
            for e in entries.values()
            if e.get("status") not in ("placed", "already built")
        ]
        reason = None
        if bad:
            reason = f"{len(bad)} of {len(entries)} entities were not placed" + (
                f" ({stop_reason})" if stop_reason else ""
            )
        return result(not bad, reason, ticks=ticks, where=where)
