-- Ghosts, deconstruction orders, roboport networks and recent blueprint placements of the
-- character's force, with what stops the robots (storage.utils.construction_status)
storage.actions.get_construction_status = function(player_index)
    local player = storage.utils.ensure_valid_character(player_index)
    return storage.utils.hex_json(storage.utils.construction_status(player.surface, player.force, player.position))
end
