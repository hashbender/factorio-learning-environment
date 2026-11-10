-- The saved blueprints, by name
storage.actions.list_blueprints = function(player_index)
    local store = storage.utils.blueprint_store()
    local out = {}
    for _, name in ipairs(storage.utils.blueprint_names(store)) do
        local stack = store.inventory[store.names[name]]
        if stack and stack.valid_for_read and stack.is_blueprint then
            table.insert(out, (storage.utils.blueprint_info(name, stack, false)))
        end
    end
    return storage.utils.hex_json({blueprints = out, limit = storage.utils.BLUEPRINT_LIMIT})
end
