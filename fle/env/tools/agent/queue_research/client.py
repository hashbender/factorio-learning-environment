import re
from typing import List, Union

from fle.env.game_types import Technology
from fle.env.technology_names import closest_technology_names
from fle.env.tools import Tool

MAX_QUEUE_REQUEST = 50
_ERROR_PREFIX = re.compile(r'^\s*(?:\[string "[^"]*"\]:\d+:\s*)?')


class QueueResearch(Tool):
    def __init__(self, connection, game_state):
        super().__init__(connection, game_state)

    def __call__(
        self,
        technologies: Union[Technology, str, List[Union[Technology, str]]],
    ) -> List[str]:
        """
        Append technologies to the end of the research queue, in the order given.
        :param technologies: A Technology or technology name, or a list of them
        :return: The research queue after the call (technology names, current research first)
        """
        if isinstance(technologies, (list, tuple)):
            items = list(technologies)
        else:
            items = [technologies]
        if len(items) > MAX_QUEUE_REQUEST:
            raise ValueError(
                f"Cannot queue more than {MAX_QUEUE_REQUEST} technologies in one call"
            )
        names = [t.value if hasattr(t, "value") else str(t) for t in items]

        response, elapsed = self.execute(self.player_index, names)

        if isinstance(response, str):
            result = _ERROR_PREFIX.sub("", response).replace('"', "").strip()
            if not result:
                raise Exception(f"Could not queue research - {response}")
            for name in names:
                if result == f"Technology {name} does not exist":
                    close = closest_technology_names(name)
                    if close:
                        result += ". Closest technology names: " + ", ".join(close)
            raise Exception(result)

        if isinstance(response, dict):  # an empty Lua table: the queue is empty
            return [str(v) for _, v in sorted(response.items())]
        return [str(name) for name in response]
