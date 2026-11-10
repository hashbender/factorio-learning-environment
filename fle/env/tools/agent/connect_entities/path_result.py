from typing import Dict, Union


class PathResult:
    """Encapsulates the result of a path finding operation"""

    def __init__(self, response: Union[Dict, str]):
        self.raw_response = response
        self.is_success = isinstance(response, dict)
        self.error_message = response if isinstance(response, str) else None
        self.entities = response.get("entities", {}) if self.is_success else {}
        self.connected = response.get("connected", False) if self.is_success else False

    @property
    def required_entities(self) -> int:
        return self.raw_response.get("number_of_entities", 0) if self.is_success else 0

    @property
    def planned(self) -> list:
        """Dry run: what would be placed, as {name, x, y, direction} in route order."""
        planned = self.raw_response.get("planned") if self.is_success else None
        if isinstance(planned, dict):
            return [planned[k] for k in sorted(planned, key=lambda k: int(k))]
        return list(planned or [])

    @property
    def would_turn(self) -> Union[Dict, None]:
        """Dry run: the existing belt the real call would turn, if any."""
        turn = self.raw_response.get("would_turn") if self.is_success else None
        return turn if isinstance(turn, dict) and turn else None
