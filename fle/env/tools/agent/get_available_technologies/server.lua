-- Copy of set_research/server.lua's trigger_description (each tool's server.lua is
-- loaded on its own); tests/unit/test_get_available_technologies.py keeps them identical.
-- Describes a Factorio 2.0 research trigger (LuaTechnologyPrototype.research_trigger),
-- e.g. "craft 50 iron-plate". Returns nil for a technology researched in labs.
local function trigger_description(tech)
    local ok, trigger = pcall(function() return tech.prototype.research_trigger end)
    if not ok or type(trigger) ~= "table" then
        return nil
    end
    local function id(v)
        if type(v) == "table" then return tostring(v.name or "?") end
        return tostring(v)
    end
    local kind = tostring(trigger.type)
    if kind == "mine-entity" then
        return "mine " .. id(trigger.entity)
    elseif kind == "craft-item" then
        if (trigger.count or 1) > 1 then
            return "craft " .. trigger.count .. " " .. id(trigger.item)
        end
        return "craft " .. id(trigger.item)
    elseif kind == "craft-fluid" then
        return "craft " .. tostring(trigger.amount or "") .. " " .. id(trigger.fluid)
    elseif kind == "build-entity" then
        return "build " .. id(trigger.entity)
    elseif kind == "send-item-to-orbit" then
        return "send " .. id(trigger.item) .. " to orbit"
    elseif kind == "capture-spawner" then
        return "capture " .. (trigger.entity and id(trigger.entity) or "a spawner")
    elseif kind == "create-space-platform" then
        return "create a space platform"
    end
    return kind
end

-- The technologies the force can research right now, as the game's technology screen
-- shows them: enabled, not researched, every prerequisite researched. For each: the
-- science packs per unit, the unit count, the time per unit (seconds), and for a
-- trigger technology the game action that completes it. Sorted by name.
storage.actions.get_available_technologies = function(player_index)
    local force = storage.agent_characters[player_index].force
    local names = {}
    for name, tech in pairs(force.technologies) do
        if tech.enabled and not tech.researched then
            local ready = true
            for _, prerequisite in pairs(tech.prerequisites or {}) do
                if not prerequisite.researched then
                    ready = false
                    break
                end
            end
            if ready then table.insert(names, name) end
        end
    end
    table.sort(names)

    local result = {}
    for _, name in ipairs(names) do
        local tech = force.technologies[name]
        local entry = {name = "\"" .. name .. "\""}
        local trigger = trigger_description(tech)
        if trigger then
            entry.trigger = "\"" .. trigger .. "\""
            entry.unit_count = 0
            entry.unit_time = 0
            entry.ingredients = {}
        else
            local ingredients = {}
            for _, ingredient in pairs(tech.research_unit_ingredients or {}) do
                table.insert(ingredients, {name = "\"" .. ingredient.name .. "\"", count = ingredient.amount})
            end
            entry.ingredients = ingredients
            entry.unit_count = tech.research_unit_count or 0
            -- research_unit_energy is in ticks (60 per second)
            entry.unit_time = (tech.research_unit_energy or 0) / 60
        end
        table.insert(result, entry)
    end
    return result
end
