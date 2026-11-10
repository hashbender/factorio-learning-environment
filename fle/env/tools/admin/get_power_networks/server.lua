-- Every electric network of the character's force on its surface, as the
-- power pole GUI shows it (storage.utils.electric_network_summaries).
storage.actions.get_power_networks = function(player_index)
    local player = storage.agent_characters[player_index]
    if not (player and player.valid) then
        error("\"No valid character\"")
    end
    local nets = storage.utils.electric_network_summaries(player.surface, player.force)
    local out = {}
    for _, n in pairs(nets) do
        table.insert(out, n)
    end
    table.sort(out, function(a, b) return a.id < b.id end)
    return {count = #out, networks = out}
end
