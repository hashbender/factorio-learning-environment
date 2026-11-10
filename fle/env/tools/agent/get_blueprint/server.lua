-- One saved blueprint: counts, footprint, build cost and its entities relative to its centre
storage.actions.get_blueprint = function(player_index, name)
    local stack = storage.utils.get_blueprint_stack(name)
    return storage.utils.hex_json((storage.utils.blueprint_info(name, stack, true)))
end
