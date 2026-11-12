-- The rocket silo at the given position (a silo's footprint is 9x9: anything within 5 tiles of its centre)
local function find_rocket_silo(surface, position)
    local best, best_d = nil, nil
    for _, s in pairs(surface.find_entities_filtered{type = "rocket-silo", position = position, radius = 5}) do
        if s.valid then
            local dx, dy = s.position.x - position.x, s.position.y - position.y
            local d = dx * dx + dy * dy
            if not best_d or d < best_d then best, best_d = s, d end
        end
    end
    return best
end

local function silo_state(silo)
    local st = silo.rocket_silo_status
    for k, v in pairs(defines.rocket_silo_status) do
        if v == st then return k end
    end
    return tostring(st)
end

storage.actions.launch_rocket = function(player_index, x, y)
    local player = storage.utils.ensure_valid_character(player_index)
    local surface = player.surface
    local position = {x = tonumber(x), y = tonumber(y)}
    local silo = find_rocket_silo(surface, position)
    if not silo then
        error("No rocket silo at (" .. position.x .. ", " .. position.y .. ") (searched within 5 tiles)")
    end
    local state = silo_state(silo)
    if silo.rocket_silo_status ~= defines.rocket_silo_status.rocket_ready then
        local parts_required = silo.prototype.rocket_parts_required or 100
        error("No rocket is ready to launch at the rocket silo at (" .. silo.position.x .. ", " .. silo.position.y
            .. "): rocket silo status " .. state .. ", rocket parts " .. (silo.rocket_parts or 0) .. " of "
            .. parts_required)
    end
    local ok = silo.launch_rocket()
    if not ok then
        error("The game did not launch the rocket at the rocket silo at (" .. silo.position.x .. ", "
            .. silo.position.y .. ") (rocket silo status " .. silo_state(silo) .. ")")
    end
    return {launched = true, x = silo.position.x, y = silo.position.y}
end
