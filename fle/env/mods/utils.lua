-- utils.lua
storage.utils.remove_enemies = function ()
    game.forces["enemy"].kill_all_units()  -- Removes all biters
    game.map_settings.enemy_expansion.enabled = false  -- Stops biters from expanding
    game.map_settings.enemy_evolution.enabled = false  -- Stops biters from evolving
    local surface = game.surfaces[1]
    for _, entity in pairs(surface.find_entities_filtered({type="unit-spawner"})) do
        entity.destroy()
    end
end

local directions = {'north', 'northeast', 'east', 'southeast', 'south', 'southwest', 'west', 'northwest'}

storage.utils.get_direction = function(from_position, to_position)
    local dx = to_position.x - from_position.x
    local dy = to_position.y - from_position.y
    local adx = math.abs(dx)
    local ady = math.abs(dy)
    local diagonal_threshold = 0.5

    -- Factorio 2.0 direction values: north=0, northeast=2, east=4, southeast=6, south=8, southwest=10, west=12, northwest=14
    if adx > ady then
        if dx > 0 then
            return (ady / adx > diagonal_threshold) and (dy > 0 and 6 or 2) or 4  -- southeast/northeast or east
        else
            return (ady / adx > diagonal_threshold) and (dy > 0 and 10 or 14) or 12  -- southwest/northwest or west
        end
    else
        if dy > 0 then
            return (adx / ady > diagonal_threshold) and (dx > 0 and 6 or 10) or 8  -- southeast/southwest or south
        else
            return (adx / ady > diagonal_threshold) and (dx > 0 and 2 or 14) or 0  -- northeast/northwest or north
        end
    end
end

storage.utils.get_direction_with_diagonals = function(from_pos, to_pos)
    local dx = to_pos.x - from_pos.x
    local dy = to_pos.y - from_pos.y

    if dx == 0 and dy == 0 then
        return nil
    end

    -- Check for cardinal directions first
    local cardinal_margin = 0.20 --0.25
    if math.abs(dx) < cardinal_margin then
        return dy > 0 and defines.direction.south or defines.direction.north
    elseif math.abs(dy) < cardinal_margin then
        return dx > 0 and defines.direction.east or defines.direction.west
    end

    -- Handle diagonal directions
    if dx > 0 then
        return dy > 0 and defines.direction.southeast or defines.direction.northeast
    else
        return dy > 0 and defines.direction.southwest or defines.direction.northwest
    end
end


storage.utils.get_closest_entity = function(player, position)
    local closest_distance = math.huge
    local closest_entity = nil
    local entities = player.surface.find_entities_filtered{
        position = position,
        force = "player",
        radius = 5  -- Increased from 3 to 5 to better handle large entities like 3x3 drills
    }

    for _, entity in ipairs(entities) do
        if entity.name ~= 'character' and entity.name ~= 'laser-beam' then
            local distance = ((position.x - entity.position.x) ^ 2 + (position.y - entity.position.y) ^ 2) ^ 0.5
            if distance < closest_distance then
                closest_distance = distance
                closest_entity = entity
            end
        end
    end

    return closest_entity
end

storage.utils.calculate_movement_ticks = function(player, from_pos, to_pos)
    -- Calculate distance between points
    local dx = to_pos.x - from_pos.x
    local dy = to_pos.y - from_pos.y
    local distance = math.sqrt(dx * dx + dy * dy)

    -- Get player's walking speed (tiles per tick)
    -- Character base speed is 0.15 tiles/tick
    local walking_speed = player.character_running_speed
    if not walking_speed or walking_speed == 0 then
        walking_speed = 0.15  -- Default walking speed
    end

    -- Calculate ticks needed for movement
    return math.ceil(distance / walking_speed)
end

-- Wrapper around LuaSurface.can_place_entity that replicates all checks LuaPlayer.can_place_entity performs.
-- This allows our code to validate placement without relying on an actual LuaPlayer instance.
-- extra_params can be provided by callers to pass additional flags (e.g. fast_replace) if needed.
storage.utils.can_place_entity = function(player, entity_name, position, direction, extra_params)
    local params = extra_params or {}
    params.name = entity_name
    params.position = position
    params.direction = direction
    params.force = player.force
    -- Use the manual build-check path so the engine applies the same rules as when a human player builds.
    params.build_check_type = defines.build_check_type.manual
    return player.surface.can_place_entity(params)
end

storage.utils.avoid_entity = function(player_index, entity, position, direction)
    local player = storage.agent_characters[player_index]
    local player_position = player.position
    for i=0, 10 do
        local can_place = player.surface.can_place_entity{
            name = entity,
            force = "player",
            position = position,
            direction = storage.utils.get_entity_direction(entity, direction)
        }
        if can_place then
            return true
        end
        player.teleport({player_position.x + i, player_position.y + i})
    end
    player.teleport(player_position)
    return false
end

storage.crafting_queue = {}

script.on_event(defines.events.on_tick, function(event)
  -- Iterate over the crafting queue and update the remaining ticks
  for i, task in ipairs(storage.crafting_queue) do
    task.remaining_ticks = task.remaining_ticks - 1

    -- If the crafting is finished, consume the ingredients, insert the crafted entity, and remove the task from the queue
    if task.remaining_ticks <= 0 then
      for _, ingredient in pairs(task.recipe.ingredients) do
        task.player.remove_item({name = ingredient.name, count = ingredient.amount * task.count})
      end
      task.player.insert({name = task.entity_name, count = task.count})
      table.remove(storage.crafting_queue, i)
    end
  end
end)

-- Utility function to ensure a valid character exists for a given player index
-- Call this before any operation that needs the character
-- Returns the valid character entity, or creates a new one if invalid/missing
storage.utils.ensure_valid_character = function(player_index)
    if not storage.agent_characters then
        storage.agent_characters = {}
    end

    local char = storage.agent_characters[player_index]

    -- If character is missing or invalid, create a new one
    if not char or not char.valid then

        --if not char then
        --    error("Character not available")
        --end
        --if char.position and not char.valid then
        --    error("Character at: x="..char.position.x..", y="..char.position.y)
        --end
        --if not char.valid then
        --    error("Character not valid")
        --end

        local spawn_position = {x = 0, y = (player_index - 1) * 2}

        local new_char = game.surfaces[1].create_entity{
            name = "character",
            position = spawn_position,
            force = game.forces.player
        }

        if new_char then
            storage.agent_characters[player_index] = new_char
            return new_char
        else
            error("Failed to create agent character " .. player_index)
        end
    end

    return char
end

-- Serializes a value to the same format the Python client parses.
-- Accumulates parts in a table and concatenates once: repeated `s = s .. x`
-- reallocates the whole string per append, which made serializing large
-- tool responses (e.g. save_entity_state on big factories) O(N^2).
function dump(o)
   local parts = {}
   local function walk(v)
      if type(v) == 'table' then
         parts[#parts + 1] = '{ '
         for k, item in pairs(v) do
            if type(k) ~= 'number' then k = '"'..k..'"' end
            parts[#parts + 1] = '['..k..'] = '
            walk(item)
            parts[#parts + 1] = ','
         end
         parts[#parts + 1] = '} '
      else
         parts[#parts + 1] = tostring(v)
      end
   end
   walk(o)
   return table.concat(parts)
end

function storage.utils.inspect(player, radius, position)
    local surface = player.surface
    local bounding_box = {
        left_top = {x = position.x - radius, y = position.y - radius},
        right_bottom = {x = position.x + radius, y = position.y + radius}
    }

    local entities = surface.find_entities_filtered({bounding_box, force = "player"})
    local entity_data = {}

    for _, entity in ipairs(entities) do
        if entity.name ~= 'character' then
            local data = {
                name = entity.name:gsub("-", "_"),
                position = entity.position,
                direction = entity.direction,--directions[entity.direction+1],
                health = entity.health,
                force = entity.force.name,
                energy = entity.energy,
                status = entity.status,
                --crafted_items = entity.crafted_items or nil
            }

            -- Get entity contents if it has an inventory
            if entity.get_inventory(defines.inventory.chest) then
                local inventory = storage.utils.get_contents_compat(entity.get_inventory(defines.inventory.chest))
                data.contents = inventory
            end

            data.warnings = storage.utils.get_issues(entity)

            -- Get entity orientation if it has an orientation attribute
            if entity.type == "train-stop" or entity.type == "car" or entity.type == "locomotive" then
                data.orientation = entity.orientation
            end

            -- Get connected entities for pipes and transport belts
            if entity.type == "pipe" or entity.type == "transport-belt" then
                local path_ends = find_path_ends(entity)
                data.path_ends = {}
                for _, path_end in pairs(path_ends) do
                    local path_position = {x=path_end.position.x - player.position.x, y=path_end.position.y - player.position.y}
                    table.insert(data.path_ends, {name = path_end.name:gsub("-", "_"), position = path_position, unit_number = path_end.unit_number})
                end
            end

            table.insert(entity_data, data)
        else
            local data = {
                name = "player_character",
                position = entity.position,
                direction = directions[(entity.direction/2)+1],  -- Factorio 2.0 direction values are 0,2,4,6,8,10,12,14
            }
            table.insert(entity_data, data)
        end
    end

    -- Sort entities with path_ends by the length of path_ends in descending order
    table.sort(entity_data, function(a, b)
        if a.path_ends and b.path_ends then
            return #a.path_ends > #b.path_ends
        elseif a.path_ends then
            return true
        else
            return false
        end
    end)

    -- Remove entities that exist in the path_ends of other entities
    local visited_paths = {}
    local filtered_entity_data = {}
    for _, data in ipairs(entity_data) do
        if data.path_ends then
            local should_add = true
            for _, path_end in ipairs(data.path_ends) do
                if visited_paths[path_end.unit_number] then
                    should_add = false
                    break
                end
            end
            if should_add then
                for _, path_end in ipairs(data.path_ends) do
                    visited_paths[path_end.unit_number] = true
                end
                table.insert(filtered_entity_data, data)
            else
                data.path_ends = nil
                --table.insert(filtered_entity_data, data)
            end
        else
            table.insert(filtered_entity_data, data)
        end
    end
    entity_data = filtered_entity_data

    return entity_data
end

-- Format player inventory contents for error messages
storage.utils.format_inventory_for_error = function(player)
    local main_inv = player.get_inventory(defines.inventory.character_main)
    if not main_inv then
        return "empty"
    end

    local contents = storage.utils.get_contents_compat(main_inv)
    if not contents or next(contents) == nil then
        return "empty"
    end

    local items = {}
    for name, count in pairs(contents) do
        table.insert(items, name .. "=" .. count)
    end

    -- Limit to first 10 items to avoid overly long error messages
    if #items > 10 then
        local truncated = {}
        for i = 1, 10 do
            truncated[i] = items[i]
        end
        return table.concat(truncated, ", ") .. " (and " .. (#items - 10) .. " more)"
    end

    return table.concat(items, ", ")
end

-- Factorio 2.0 builds assembling machines 2 and 3 facing north unless their
-- recipe uses a fluid (fluid_boxes_off_when_no_fluid_recipe), and machines
-- without fluid boxes (assembling-machine-1, centrifuge) always face north, so
-- the requested direction can be dropped by the game. Say so on the result
-- rather than return a machine that silently faces another way.
storage.utils.note_dropped_direction = function(serialized, placed, requested_direction)
    if type(serialized) ~= "table" or not (placed and placed.valid) then
        return serialized
    end
    if placed.type ~= "assembling-machine" or placed.direction == requested_direction then
        return serialized
    end
    local msg
    if #placed.prototype.fluidbox_prototypes == 0 then
        msg = placed.name .. " was placed facing north: it has no fluid connections, so it always faces north"
    else
        msg = placed.name .. " was placed facing north: it takes a direction only while its recipe uses a fluid"
    end
    if type(serialized.warnings) ~= "table" then
        serialized.warnings = {}
    end
    table.insert(serialized.warnings, "\"" .. msg .. "\"")
    return serialized
end

-- Blueprints, ghosts and construction robots ------------------------------------------------
-- Blueprints are real blueprint items held in a script inventory (game.create_inventory), so
-- they are saved with the map. Ghosts are built only by construction robots, by the game.

storage.utils.BLUEPRINT_LIMIT = 20
storage.utils.BLUEPRINT_ENTITY_LIMIT = 500
storage.utils.PLACEMENTS_KEPT = 10

-- A table as JSON, hex encoded: dump() writes strings unquoted, so this survives the reply
storage.utils.hex_json = function(t)
    local json = helpers.table_to_json(t)
    return "\"" .. (json:gsub(".", function(c) return string.format("%02x", c:byte()) end)) .. "\""
end

storage.utils.blueprint_store = function()
    local s = storage.fmg_blueprints
    if not (s and s.inventory and s.inventory.valid) then
        s = {inventory = game.create_inventory(storage.utils.BLUEPRINT_LIMIT), names = {},
             placements = {}, next_placement = 1}
        storage.fmg_blueprints = s
    end
    if not (s.scratch and s.scratch.valid) then
        s.scratch = game.create_inventory(1)
    end
    return s
end

storage.utils.blueprint_names = function(store)
    local names = {}
    for name in pairs(store.names) do table.insert(names, name) end
    table.sort(names)
    return names
end

storage.utils.get_blueprint_stack = function(name)
    local store = storage.utils.blueprint_store()
    local slot = store.names[name]
    local stack = slot and store.inventory[slot]
    if not (stack and stack.valid_for_read and stack.is_blueprint) then
        local names = storage.utils.blueprint_names(store)
        error("\"No blueprint named " .. tostring(name) .. ". Saved blueprints: " ..
              (#names > 0 and table.concat(names, ", ") or "none") .. "\"")
    end
    return stack
end

-- Tile footprint of an entity facing a direction (16-direction values)
storage.utils.entity_footprint = function(name, direction)
    local p = prototypes.entity[name]
    local w, h = 1, 1
    if p then w, h = p.tile_width or 1, p.tile_height or 1 end
    if direction == 4 or direction == 12 then w, h = h, w end
    return w, h
end

-- The item a robot (or a player) uses to build an entity
storage.utils.build_item = function(name)
    local p = prototypes.entity[name]
    local items = p and p.items_to_place_this
    if items and items[1] then
        return items[1].name, items[1].count or 1
    end
    return nil, 0
end

-- Entities, counts, footprint and build cost of a blueprint; positions relative to its centre
storage.utils.blueprint_info = function(name, stack, with_entities)
    local ents = stack.get_blueprint_entities() or {}
    local counts, items = {}, {}
    local x1, y1, x2, y2 = math.huge, math.huge, -math.huge, -math.huge
    for _, e in ipairs(ents) do
        counts[e.name] = (counts[e.name] or 0) + 1
        local item, n = storage.utils.build_item(e.name)
        if item then items[item] = (items[item] or 0) + n end
        local w, h = storage.utils.entity_footprint(e.name, e.direction or 0)
        x1 = math.min(x1, e.position.x - w / 2); x2 = math.max(x2, e.position.x + w / 2)
        y1 = math.min(y1, e.position.y - h / 2); y2 = math.max(y2, e.position.y + h / 2)
    end
    if #ents == 0 then x1, y1, x2, y2 = 0, 0, 0, 0 end
    local info = {name = name, entity_count = #ents, entities = counts, items = items,
                  width = x2 - x1, height = y2 - y1}
    if with_entities then
        local cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
        local list = {}
        for _, e in ipairs(ents) do
            table.insert(list, {name = e.name, x = e.position.x - cx, y = e.position.y - cy,
                                direction = e.direction or 0, recipe = e.recipe})
        end
        info.entity_list = list
    end
    return info, ents, {x1, y1, x2, y2}
end

-- Why the construction robots aren't building or removing an entity, or nil if nothing stops them
storage.utils.robot_blocker = function(entity, force, item)
    local nets = entity.surface.find_logistic_networks_by_construction_area(entity.position, force)
    if #nets == 0 then
        return "not in the construction area of any roboport"
    end
    local robots, material = false, item == nil
    for _, n in ipairs(nets) do
        if n.all_construction_robots > 0 then robots = true end
        if item and n.get_item_count(item) > 0 then material = true end
    end
    if not robots then
        return "no construction robots in the roboport network"
    end
    if not material then
        return "no " .. item .. " in the roboport network's storage"
    end
    return nil
end

-- Ghosts, deconstruction orders, robot networks and recent blueprint placements of a force
storage.utils.construction_status = function(surface, force, origin)
    local out = {networks = {}, ghosts = 0, ghosts_waiting = {}, deconstruction = 0,
                 deconstruction_waiting = {}, placements = {}}
    for _, n in ipairs((force.logistic_networks or {})[surface.name] or {}) do
        local roboports, unpowered, low = 0, 0, 0
        for _, cell in ipairs(n.cells) do
            local owner = cell.owner
            if owner and owner.valid and owner.type == "roboport" then
                roboports = roboports + 1
                if owner.status == defines.entity_status.no_power then unpowered = unpowered + 1
                elseif owner.status == defines.entity_status.low_power then low = low + 1 end
            end
        end
        local contents = n.get_contents() or {}
        table.sort(contents, function(a, b) return a.count > b.count end)
        local storage_items = {}
        for i = 1, math.min(#contents, 10) do
            storage_items[contents[i].name] = (storage_items[contents[i].name] or 0) + contents[i].count
        end
        if roboports > 0 then
            table.insert(out.networks, {
                id = n.network_id, roboports = roboports, roboports_no_power = unpowered,
                roboports_low_power = low,
                construction_robots = n.all_construction_robots,
                construction_robots_idle = n.available_construction_robots,
                logistic_robots = n.all_logistic_robots,
                logistic_robots_idle = n.available_logistic_robots,
                storage = storage_items, storage_item_types = #contents})
        end
    end
    local function nearest_first(list)
        if origin then
            table.sort(list, function(a, b)
                local ax, ay, bx, by = a.position.x - origin.x, a.position.y - origin.y, b.position.x - origin.x, b.position.y - origin.y
                return ax * ax + ay * ay < bx * bx + by * by
            end)
        end
        return list
    end
    local function group(list, item_of, into)
        local by_reason, checked = {}, 0
        for _, e in ipairs(nearest_first(list)) do
            if checked >= 200 then break end
            checked = checked + 1
            local reason = storage.utils.robot_blocker(e, force, item_of(e))
            if reason then
                local g = by_reason[reason]
                if not g then
                    g = {reason = reason, count = 0, x = e.position.x, y = e.position.y}
                    by_reason[reason] = g
                    table.insert(into, g)
                end
                g.count = g.count + 1
            end
        end
    end
    local ghosts = surface.find_entities_filtered{type = "entity-ghost", force = force}
    out.ghosts = #ghosts
    group(ghosts, function(g) return (storage.utils.build_item(g.ghost_name)) end, out.ghosts_waiting)
    local marked = {}
    for _, e in ipairs(surface.find_entities_filtered{to_be_deconstructed = true}) do
        if e.force == force or e.force.name == "neutral" then table.insert(marked, e) end
    end
    out.deconstruction = #marked
    group(marked, function() return nil end, out.deconstruction_waiting)
    local store = storage.fmg_blueprints
    for _, p in ipairs(store and store.placements or {}) do
        local waiting, built = 0, 0
        for _, g in ipairs(p.ghosts) do
            local here = surface.find_entities_filtered{position = {g.x, g.y}, force = force}
            local state
            for _, e in ipairs(here) do
                if e.type == "entity-ghost" and e.ghost_name == g.name then state = "ghost"
                elseif e.name == g.name and state == nil then state = "built" end
            end
            if state == "ghost" then waiting = waiting + 1 elseif state == "built" then built = built + 1 end
        end
        table.insert(out.placements, {id = p.id, blueprint = p.blueprint, x = p.x, y = p.y,
                                      ghosts_placed = #p.ghosts, ghosts_waiting = waiting, built = built})
    end
    return out
end

-- Building an entity where its own ghost stands: the game revives the ghost, keeping the
-- ghost's direction and settings (recipe...). Returns the built entity, or nil if no ghost.
storage.utils.revive_ghost = function(player, entity_name, position)
    local ghosts = player.surface.find_entities_filtered{
        type = "entity-ghost", ghost_name = entity_name, force = player.force,
        area = {{position.x - 0.75, position.y - 0.75}, {position.x + 0.75, position.y + 0.75}}}
    for _, ghost in ipairs(ghosts) do
        if math.abs(ghost.position.x - position.x) <= 0.75 and math.abs(ghost.position.y - position.y) <= 0.75 then
            local _, revived = ghost.revive{raise_revive = true}
            if revived then return revived end
        end
    end
    return nil
end
