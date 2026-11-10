from typing import Any, Dict, List

from fle.env.tools import Tool

# Numbers every network summary carries (missing ones read as 0)
NETWORK_FIELDS = (
    "id",
    "production",
    "consumption",
    "demand",
    "generator_max",
    "accumulator_charge",
    "accumulator_capacity",
    "poles",
    "generators",
    "accumulators",
    "consumers",
    "low_power",
    "no_power",
)


class GetPowerNetworks(Tool):
    def __init__(self, connection, game_state):
        super().__init__(connection, game_state)

    def __call__(self) -> List[Dict[str, Any]]:
        """
        Summarise every electric network of the character's force, as the power
        pole GUI shows it. Powers are in W, energies in J.
        :return: One dict per network, by network id: production, consumption
            (5 s averages), demand (rated power of the consumers that are
            working or waiting for power, plus the drain of idle ones),
            generator_max, satisfaction (consumption / demand, at most 1; None
            without demand), accumulator_charge, accumulator_capacity, and
            counts of poles, generators, accumulators, consumers and of
            consumers with low_power / no_power
        """
        response, _ = self.execute(self.player_index)
        if not isinstance(response, dict):
            raise Exception(
                f"Could not get power networks: {self.get_error_message(str(response))}"
            )
        networks = response.get("networks") or {}
        if isinstance(networks, dict):
            networks = [networks[k] for k in sorted(networks)]
        result = []
        for n in networks:
            entry = {k: n.get(k, 0) or 0 for k in NETWORK_FIELDS}
            entry["id"] = int(entry["id"])
            entry["satisfaction"] = n.get("satisfaction")
            result.append(entry)
        return sorted(result, key=lambda n: n["id"])
