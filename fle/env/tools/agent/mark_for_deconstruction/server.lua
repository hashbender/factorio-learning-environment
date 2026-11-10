-- Mark entities for deconstruction, as the game's deconstruction planner does. Construction
-- robots remove marked entities and take their items to the roboport network's storage.
-- Ghosts are removed at once, as the planner does.

local function find_listed(surface, w)
    for _, e in ipairs(surface.find_entities_filtered{position = {w.x, w.y}}) do
        if e.valid and (e.name == w.name or (e.type == "entity-ghost" and e.ghost_name == w.name)) then
            return e
        end
    end
    for _, e in ipairs(surface.find_entities_filtered{area = {{w.x - 0.6, w.y - 0.6}, {w.x + 0.6, w.y + 0.6}}}) do
        if e.valid and (e.name == w.name or (e.type == "entity-ghost" and e.ghost_name == w.name)) then
            return e
        end
    end
    return nil
end

local function why_not(e, force)
    if e.type == "character" then return "characters can't be deconstructed" end
    if e.force ~= force and e.force.name ~= "neutral" then return "it belongs to another force" end
    if not e.minable then return "it can't be mined" end
    return "the game did not mark it"
end

storage.actions.mark_for_deconstruction = function(player_index, x1, y1, x2, y2, wanted)
    local player = storage.utils.ensure_valid_character(player_index)
    local surface, force = player.surface, player.force
    local marked, by_name, not_marked = 0, {}, {}
    local already, ghosts_removed, not_marked_count = 0, 0, 0
    local function refuse(e, name, x, y, reason)
        not_marked_count = not_marked_count + 1
        if #not_marked < 20 then
            table.insert(not_marked, {name = name, x = x, y = y, reason = reason})
        end
    end
    local function count(e)
        marked = marked + 1
        by_name[e.name] = (by_name[e.name] or 0) + 1
    end

    if type(wanted) == "table" and next(wanted) ~= nil then
        for _, w in pairs(wanted) do
            local e = find_listed(surface, w)
            if not e then
                refuse(nil, w.name, w.x, w.y, "no such entity there")
            elseif e.type == "entity-ghost" then
                if e.force == force then
                    e.destroy()
                    ghosts_removed = ghosts_removed + 1
                else
                    refuse(e, w.name, w.x, w.y, "it belongs to another force")
                end
            elseif e.to_be_deconstructed() then
                already = already + 1
            elseif e.force ~= force and e.force.name ~= "neutral" then
                refuse(e, e.name, e.position.x, e.position.y, "it belongs to another force")
            elseif e.order_deconstruction(force) then
                count(e)
            else
                refuse(e, e.name, e.position.x, e.position.y, why_not(e, force))
            end
        end
    else
        if not (x1 and y1 and x2 and y2) then
            error("\"Give an area or a list of entities\"")
        end
        if x1 > x2 then x1, x2 = x2, x1 end
        if y1 > y2 then y1, y2 = y2, y1 end
        local area = {{x1, y1}, {x2, y2}}
        local before, was_marked = surface.find_entities_filtered{area = area}, {}
        local ghosts_before = 0
        for _, e in ipairs(before) do
            if e.to_be_deconstructed() then was_marked[e] = true; already = already + 1 end
            if e.type == "entity-ghost" and e.force == force then ghosts_before = ghosts_before + 1 end
        end
        surface.deconstruct_area{area = area, force = force, skip_fog_of_war = false}
        local ghosts_after = 0
        for _, e in ipairs(before) do
            if e.valid then
                if e.type == "entity-ghost" and e.force == force then ghosts_after = ghosts_after + 1 end
                if e.to_be_deconstructed() then
                    if not was_marked[e] then count(e) end
                elseif (e.force == force) and e.type ~= "character" and e.type ~= "entity-ghost" then
                    refuse(e, e.name, e.position.x, e.position.y, why_not(e, force))
                end
            end
        end
        ghosts_removed = ghosts_before - ghosts_after
    end
    return storage.utils.hex_json({marked = marked, marked_by_name = by_name, already_marked = already,
                                   ghosts_removed = ghosts_removed, not_marked_count = not_marked_count,
                                   not_marked = not_marked})
end
