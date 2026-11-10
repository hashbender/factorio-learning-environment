import math
from time import sleep

from fle.env.entities import Position
from fle.env.instance import NONE
from fle.env.game_types import Prototype
from fle.env.tools.admin.get_path.client import GetPath
from fle.env.tools.admin.request_path.client import RequestPath
from fle.env.tools import Tool
from fle.env.lua_manager import LuaScriptManager


class MoveTo(Tool):
    def __init__(self, connection: LuaScriptManager, game_state):
        super().__init__(connection, game_state)
        # self.observe = ObserveAll(connection, game_state)
        self.request_path = RequestPath(connection, game_state)
        self.get_path = GetPath(connection, game_state)

    def _free_start(self, start: Position):
        """The nearest spot within 2 tiles of start where a 1x1 box fits (None if there is none),
        with the character moved there."""
        out = self.connection.rcon_client.send_command(
            f"/sc local c = storage.agent_characters[{self.player_index}]; "
            f"local p = c.surface.find_non_colliding_position('iron-chest', "
            f"{{{float(start.x)}, {float(start.y)}}}, 2, 0.5, true); "
            "if p then c.teleport(p); rcon.print(p.x .. ',' .. p.y) end"
        )
        try:
            px, py = (float(v) for v in str(out).strip().split(","))
        except (TypeError, ValueError):
            return None
        if (px, py) == (float(start.x), float(start.y)):
            return None
        return Position(x=px, y=py)

    def __call__(
        self, position: Position, laying: Prototype = None, leading: Prototype = None
    ) -> Position:
        """
        Move to a position.
        :param position: Position to move to.
        :return: Your final position
        """

        X_OFFSET, Y_OFFSET = 0, 0  # 0.5, 0

        x, y = (
            math.floor(position.x * 4) / 4 + X_OFFSET,
            math.floor(position.y * 4) / 4 + Y_OFFSET,
        )
        nposition = Position(x=x, y=y)

        # The path must start where the character is. move_to teleports the character along
        # the path from its first point, so a stale start moved it there for free and then
        # charged the walk from there.
        cached = Position(
            x=self.game_state.player_location.x, y=self.game_state.player_location.y
        )
        start = self.character_position()
        if start is None:
            start = Position(
                x=self.game_state.player_location.x, y=self.game_state.player_location.y
            )
        else:
            self.game_state.player_location = start

        path_handle = self.request_path(
            start=start,
            finish=nposition,
            allow_paths_through_own_entities=True,
            resolution=-1,
        )

        # Wait for path to be computed using get_path with backoff polling
        # This fixes the race condition where move_to was called before path was ready
        try:
            self.get_path(path_handle)
        except Exception as e:
            # The character can stand where the pathfinder's start box collides (at a
            # water edge, or next to an entity it just placed). Start from the nearest
            # free spot instead, as request_path does for the goal, and try once more.
            snapped = self._free_start(start) if "not_found" in str(e) else None
            if snapped is None and "not_found" in str(e) and cached != start:
                snapped = cached  # as before: the last position move_to reached
            if snapped is None:
                raise Exception(f"Could not get path to ({x}, {y}): {e}")
            start = snapped
            self.game_state.player_location = start
            path_handle = self.request_path(
                start=start,
                finish=nposition,
                allow_paths_through_own_entities=True,
                resolution=-1,
            )
            try:
                self.get_path(path_handle)
            except Exception as e2:
                raise Exception(f"Could not get path to ({x}, {y}): {e2}")

        # Track elapsed ticks for fast forward
        ticks_before = self.game_state.instance.get_elapsed_ticks()

        try:
            if laying is not None:
                entity_name = laying.value[0]
                response, execution_time = self.execute(
                    self.player_index, path_handle, entity_name, 1
                )
            elif leading:
                entity_name = leading.value[0]
                response, execution_time = self.execute(
                    self.player_index, path_handle, entity_name, 0
                )
            else:
                response, execution_time = self.execute(
                    self.player_index, path_handle, NONE, NONE
                )

            # Sleep for the appropriate real-world time based on elapsed ticks
            ticks_after = self.game_state.instance.get_elapsed_ticks()
            ticks_added = ticks_after - ticks_before
            if ticks_added > 0:
                game_speed = self.game_state.instance.get_speed()
                real_world_sleep = (
                    ticks_added / 60 / game_speed if game_speed > 0 else 0
                )
                sleep(real_world_sleep)

            if isinstance(response, int) and response == 0:
                raise Exception("Could not move.")

            if isinstance(response, str):
                raise Exception(f"Could not move. {response}")

            if response == "trailing" or response == "leading":
                raise Exception("Could not lay entity, perhaps a typo?")

            if response and isinstance(response, dict):
                self.game_state.player_location = Position(
                    x=response["x"], y=response["y"]
                )

            # If `fast` is turned off - we need to long poll the game state to ensure the player has moved
            if not self.game_state.instance.fast:
                remaining_steps = self.connection.rcon_client.send_command(
                    f"/silent-command rcon.print(storage.actions.get_walking_queue_length({self.player_index}))"
                )
                while remaining_steps != "0":
                    sleep(0.5)
                    remaining_steps = self.connection.rcon_client.send_command(
                        f"/silent-command rcon.print(storage.actions.get_walking_queue_length({self.player_index}))"
                    )
                self.game_state.player_location = Position(x=position.x, y=position.y)

            return Position(x=response["x"], y=response["y"])  # , execution_time
        except Exception as e:
            if response:
                raise Exception(f"Cannot move. {e} - {response}")
            raise Exception(f"Cannot move. {e}")
