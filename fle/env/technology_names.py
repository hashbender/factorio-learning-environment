from difflib import get_close_matches

# Technology members whose value is a Factorio 1.1 technology that 2.0 does not have
LEGACY_TECHNOLOGY_NAMES = frozenset(
    {"barrel-filling", "character-inventory-slots", "rocket-control-unit"}
)


def closest_technology_names(name: str, limit: int = 8) -> list[str]:
    """Technology names closest to `name`, for error messages about unknown technologies.

    Lists the same name written as an enum member (e.g. "BulkInserter"), then the levels
    of a leveled technology (e.g. "research-speed" -> "research-speed-1", ...), then the
    most similar names. Only technologies the game has are listed.
    """
    from fle.env.game_types import technology_by_name

    names = sorted(n for n in technology_by_name if n not in LEGACY_TECHNOLOGY_NAMES)
    low = str(name).strip().lower()
    key = low.replace("-", "").replace("_", "").replace(" ", "")
    close = [t for t in names if t.replace("-", "") == key]
    close += [t for t in names if t.startswith(low + "-")]
    close += get_close_matches(low, names, n=5, cutoff=0.6)
    return list(dict.fromkeys(close))[:limit]
