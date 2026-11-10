-- Create a blueprint of the character's own entities in an area (or of a list of them), as the
-- game's blueprint tool does (LuaItemStack.create_blueprint), and keep it under a name.
local function check_name(name)
    if type(name) ~= "string" or #name == 0 or #name > 64 or name:find("[\"\\%c]") then
        error("\"A blueprint name is 1 to 64 characters, without quotes, backslashes or control characters\"")
    end
end

storage.actions.create_blueprint = function(player_index, name, x1, y1, x2, y2, wanted)
    local player = storage.utils.ensure_valid_character(player_index)
    check_name(name)
    local store = storage.utils.blueprint_store()
    local slot = store.names[name]
    if not slot then
        if #storage.utils.blueprint_names(store) >= storage.utils.BLUEPRINT_LIMIT then
            error("\"There are already " .. storage.utils.BLUEPRINT_LIMIT ..
                  " blueprints (the limit). Delete one or reuse a name: " ..
                  table.concat(storage.utils.blueprint_names(store), ", ") .. "\"")
        end
        for i = 1, #store.inventory do
            if not store.inventory[i].valid_for_read then slot = i break end
        end
    end

    local surface, force = player.surface, player.force
    local keep = nil
    if type(wanted) == "table" and next(wanted) ~= nil then
        -- the area around the listed entities; only those entities are kept
        keep = {}
        x1, y1, x2, y2 = math.huge, math.huge, -math.huge, -math.huge
        for _, w in pairs(wanted) do
            local fw, fh = storage.utils.entity_footprint(w.name, 0)
            local r = math.max(fw, fh) / 2
            x1 = math.min(x1, w.x - r); x2 = math.max(x2, w.x + r)
            y1 = math.min(y1, w.y - r); y2 = math.max(y2, w.y + r)
            keep[#keep + 1] = w
        end
    end
    if not (x1 and y1 and x2 and y2) then
        error("\"Give an area or a list of entities\"")
    end
    if x1 > x2 then x1, x2 = x2, x1 end
    if y1 > y2 then y1, y2 = y2, y1 end

    local stack = store.scratch[1]
    stack.set_stack{name = "blueprint"}
    local mapping = stack.create_blueprint{surface = surface, force = force, area = {{x1, y1}, {x2, y2}},
                                           always_include_tiles = false, include_entities = true,
                                           include_modules = true, include_station_names = true,
                                           include_trains = false, include_fuel = false}
    local ents = stack.get_blueprint_entities() or {}
    if keep then
        local kept, missing = {}, {}
        local function matches(e, w)
            return e and e.valid and (e.name == w.name or (e.type == "entity-ghost" and e.ghost_name == w.name))
                   and math.abs(e.position.x - w.x) < 0.6 and math.abs(e.position.y - w.y) < 0.6
        end
        local used = {}
        for _, w in ipairs(keep) do
            local found = false
            for _, be in ipairs(ents) do
                if not used[be.entity_number] and matches(mapping[be.entity_number], w) then
                    used[be.entity_number] = true
                    table.insert(kept, be)
                    found = true
                    break
                end
            end
            if not found then table.insert(missing, w.name .. " at (" .. w.x .. ", " .. w.y .. ")") end
        end
        if #missing > 0 then
            stack.clear()
            error("\"These are not entities of yours: " .. table.concat(missing, ", ", 1, math.min(#missing, 10)) .. "\"")
        end
        stack.set_blueprint_entities(kept)
        ents = kept
    end
    if #ents == 0 then
        stack.clear()
        error("\"No entities of yours in the area (" .. x1 .. ", " .. y1 .. ") to (" .. x2 .. ", " .. y2 .. ")\"")
    end
    if #ents > storage.utils.BLUEPRINT_ENTITY_LIMIT then
        stack.clear()
        error("\"The blueprint would have " .. #ents .. " entities; the limit is " ..
              storage.utils.BLUEPRINT_ENTITY_LIMIT .. "\"")
    end
    stack.label = name
    store.inventory[slot].set_stack(stack)
    stack.clear()
    store.names[name] = slot
    return storage.utils.hex_json(storage.utils.blueprint_info(name, store.inventory[slot], false))
end
