from fle.env.tools import Tool


class DeleteBlueprint(Tool):
    def __init__(self, connection, game_state):
        super().__init__(connection, game_state)

    def __call__(self, name: str) -> bool:
        """
        Delete a saved blueprint. Ghosts already placed from it stay.
        :param name: Blueprint name
        :return: True
        """
        response, _ = self.execute(self.player_index, str(name))
        if response is not True:
            raise Exception(
                f"Could not delete blueprint - {self.get_error_message(str(response))}"
            )
        return True
