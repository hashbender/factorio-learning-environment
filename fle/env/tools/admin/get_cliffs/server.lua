-- Cliffs near a position (default: the character), or inside an area, nearest
-- to the position first. Returns {x, y} of the position measured from and the
-- list of cliff positions.
storage.actions.get_cliffs = function(player_index, x, y, radius, limit, x1, y1, x2, y2)
    local player = storage.agent_characters[player_index]
    if not (player and player.valid) then
        error("\"No valid character\"")
    end
    local surface = player.surface
    if x == nil or y == nil then
        x, y = player.position.x, player.position.y
    end
    local filter = {type = "cliff"}
    if x1 ~= nil and y1 ~= nil and x2 ~= nil and y2 ~= nil then
        filter.area = {{x1, y1}, {x2, y2}}
    else
        filter.position = {x = x, y = y}
        filter.radius = radius or 40
    end
    local cliffs = {}
    for _, cliff in pairs(surface.find_entities_filtered(filter)) do
        local dx, dy = cliff.position.x - x, cliff.position.y - y
        table.insert(cliffs, {x = cliff.position.x, y = cliff.position.y, d = dx * dx + dy * dy})
    end
    table.sort(cliffs, function(a, b) return a.d < b.d end)
    local out = {}
    for i = 1, math.min(#cliffs, limit or 25) do
        out[i] = {x = cliffs[i].x, y = cliffs[i].y}
    end
    return {origin = {x = x, y = y}, count = #out, cliffs = out}
end
