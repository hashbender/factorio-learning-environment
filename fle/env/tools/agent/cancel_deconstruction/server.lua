-- Cancel deconstruction orders, as the deconstruction planner's cancel mode does
local function find_listed(surface, w)
    for _, e in ipairs(surface.find_entities_filtered{area = {{w.x - 0.6, w.y - 0.6}, {w.x + 0.6, w.y + 0.6}}, name = w.name}) do
        if e.valid then return e end
    end
    return nil
end

storage.actions.cancel_deconstruction = function(player_index, x1, y1, x2, y2, wanted)
    local player = storage.utils.ensure_valid_character(player_index)
    local surface, force = player.surface, player.force
    local cancelled, by_name, not_found = 0, {}, {}
    local function count(e)
        cancelled = cancelled + 1
        by_name[e.name] = (by_name[e.name] or 0) + 1
    end
    if type(wanted) == "table" and next(wanted) ~= nil then
        for _, w in pairs(wanted) do
            local e = find_listed(surface, w)
            if e and e.to_be_deconstructed() then
                e.cancel_deconstruction(force)
                if not e.to_be_deconstructed() then count(e) end
            elseif #not_found < 20 then
                table.insert(not_found, {name = w.name, x = w.x, y = w.y,
                                         reason = e and "not marked for deconstruction" or "no such entity there"})
            end
        end
    else
        if not (x1 and y1 and x2 and y2) then
            error("\"Give an area or a list of entities\"")
        end
        if x1 > x2 then x1, x2 = x2, x1 end
        if y1 > y2 then y1, y2 = y2, y1 end
        local area = {{x1, y1}, {x2, y2}}
        local before = surface.find_entities_filtered{area = area, to_be_deconstructed = true}
        surface.cancel_deconstruct_area{area = area, force = force, skip_fog_of_war = false}
        for _, e in ipairs(before) do
            if e.valid and not e.to_be_deconstructed() then count(e) end
        end
    end
    return storage.utils.hex_json({cancelled = cancelled, cancelled_by_name = by_name, not_cancelled = not_found})
end
