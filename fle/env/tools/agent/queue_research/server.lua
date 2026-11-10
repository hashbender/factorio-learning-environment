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

local function queue_names(force)
    local names = {}
    for _, tech in pairs(force.research_queue) do
        table.insert(names, tech.name)
    end
    return names
end

-- Appends technologies to the research queue in order. All or nothing: when one
-- can't be queued, the queue is restored and the reason is raised.
storage.actions.queue_research = function(player_index, technology_names)
    local player = storage.agent_characters[player_index]
    local force = player.force

    for _, name in ipairs(technology_names) do
        local tech = force.technologies[name]
        if not tech then
            error(string.format("\"Technology %s does not exist\"", name))
        end
        if tech.researched then
            error(string.format("\"Technology %s is already researched\"", name))
        end
        if not tech.enabled then
            error(string.format("\"Technology %s is not enabled\"", name))
        end
        local trigger = trigger_description(tech)
        if trigger then
            error(string.format(
                "\"Cannot queue %s. It is a trigger technology, completed by a game action instead of labs: %s\"",
                name,
                trigger
            ))
        end
    end

    local saved = queue_names(force)
    for _, name in ipairs(technology_names) do
        local queued = {}
        for _, n in ipairs(queue_names(force)) do
            queued[n] = true
        end
        -- A technology that is already queued keeps its place.
        if not queued[name] and not force.add_research(name) then
            local reason
            if #force.research_queue >= 7 then
                reason = "The research queue is full (7 technologies)"
            else
                local missing = {}
                for prerequisite_name, prerequisite in pairs(force.technologies[name].prerequisites) do
                    if not prerequisite.researched and not queued[prerequisite_name] then
                        table.insert(missing, prerequisite_name)
                    end
                end
                table.sort(missing)
                if #missing > 0 then
                    reason = "Missing prerequisites (not researched or queued): " .. table.concat(missing, ", ")
                else
                    reason = "The game refused it"
                end
            end
            force.research_queue = saved
            error(string.format("\"Cannot queue %s. %s\"", name, reason))
        end
    end

    local result = {}
    for _, n in ipairs(queue_names(force)) do
        table.insert(result, "\"" .. n .. "\"")
    end
    return result
end
