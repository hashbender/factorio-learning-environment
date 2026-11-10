-- Delete a saved blueprint (ghosts already placed from it stay)
storage.actions.delete_blueprint = function(player_index, name)
    local stack = storage.utils.get_blueprint_stack(name)
    local store = storage.utils.blueprint_store()
    stack.clear()
    store.names[name] = nil
    return true
end
