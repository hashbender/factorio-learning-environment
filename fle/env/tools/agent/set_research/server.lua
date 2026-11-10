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

storage.actions.set_research = function(player_index, technology_name)
    local player = storage.agent_characters[player_index]
    local force = player.force

    local tech = force.technologies[technology_name]
    if not tech then
        error(string.format("\"Technology %s does not exist\"", technology_name))
    end

    if tech.researched then
        error(string.format("\"Technology %s is already researched\"", technology_name))
    end

    if not tech.enabled then
        error(string.format("\"Technology %s is not enabled\"", technology_name))
    end

    local missing_prerequisites = {}
    for _, prerequisite in pairs(tech.prerequisites or {}) do
        if not prerequisite.researched then
            table.insert(missing_prerequisites, prerequisite.name)
        end
    end
    table.sort(missing_prerequisites)

    -- Trigger technologies have no research units: add_research() would just return false.
    local trigger = trigger_description(tech)
    if trigger then
        local message = string.format(
            "Cannot start research for %s. It is a trigger technology, completed by a game action instead of labs: %s",
            technology_name,
            trigger
        )
        if #missing_prerequisites > 0 then
            message = message .. ". Missing prerequisites: " .. table.concat(missing_prerequisites, ", ")
        end
        error("\"" .. message .. "\"")
    end

    if #missing_prerequisites > 0 then
        table.sort(missing_prerequisites)
        error(string.format(
            "\"Cannot start research for %s. Missing prerequisites: %s\"",
            technology_name,
            table.concat(missing_prerequisites, ", ")
        ))
    end

    -- Only switch away from valid current research after validation succeeds.
    force.cancel_current_research()

    local success = force.add_research(technology_name)
    if not success then
        error(string.format("\"Failed to start research for %s\"", technology_name))
    end

    -- Collect and return the research ingredients
    local ingredients = {}
    local units_required = tech.research_unit_count

    for _, ingredient in pairs(tech.research_unit_ingredients) do
        table.insert(ingredients, {
            name = "\""..ingredient.name.."\"",
            count = ingredient.amount * units_required,
            type = ingredient.type
        })
    end

    return ingredients
end
