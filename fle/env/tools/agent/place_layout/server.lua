-- Build a whole layout of entities from the character's inventory, the way place_entity builds one.
--
-- storage.actions.place_layout(player_index, mode, payload_hex)
--   mode "plan":  payload {anchor, entries | grid, copies, offset}. Expands the layout, checks every entry
--                 (the game's build check, overlaps inside the layout, recipes, filters, the map), adds up the
--                 items, and splits the entries into stops: a free tile to stand on with every entry of the
--                 stop within reach. Builds nothing, takes no game time, leaves the character where it is.
--   mode "place": payload {entries} (entries of one stop, as the plan returned them). Builds them from where
--                 the character stands, with place_entity's rules: in reach, item in the inventory, the game's
--                 build check. One item is used per entity. Recipes and filters are set as the GUI sets them.
-- Both return hex-encoded JSON (storage.utils.hex_json).
local MAX_ENTRIES = 1000
local MARGIN = 1          -- a stop is chosen with every entry within reach - MARGIN
local SEARCH = 5          -- tiles searched around a group's centre for a place to stand

local function quoted(s) return "\"" .. tostring(s) .. "\"" end
local function fail(msg) error(quoted(msg)) end

local function unhex(s)
    return (s:gsub("..", function(h) return string.char(tonumber(h, 16)) end))
end

local function num(v)
    if v == math.floor(v) then return string.format("%d", v) end
    return string.format("%g", v)
end
local function at(x, y) return "(" .. num(x) .. ", " .. num(y) .. ")" end

-- Where the game puts the centre of an entity `size` tiles wide asked for at `v` (as can_place_entity)
local function snap(v, size)
    if size % 2 == 1 then return math.floor(v) + 0.5 end
    return math.floor(v + 0.5)
end

local function mask_layers(prototype)
    local ok, layers = pcall(function() return prototype.collision_mask.layers end)
    if ok and type(layers) == "table" then return layers end
    return nil
end

local function masks_collide(a, b)
    if not a or not b then return true end
    for layer in pairs(a) do
        if b[layer] then return true end
    end
    return false
end

local DIR_NAMES = {[0] = "UP", [4] = "RIGHT", [8] = "DOWN", [12] = "LEFT"}
local NOT_IN_THE_WAY = {["character"] = true, ["item-entity"] = true, ["corpse"] = true,
    ["character-corpse"] = true, ["entity-ghost"] = true, ["tile-ghost"] = true, ["highlight-box"] = true,
    ["flying-text"] = true, ["resource"] = true}

-- entity prototype and the item that builds it, from an entity or item name
local function resolve(name)
    local entity, item = name, nil
    if prototypes.entity[name] == nil then
        local it = prototypes.item and prototypes.item[name]
        if it and it.place_result then
            entity, item = it.place_result.name, name
        else
            return nil, nil, name .. " isn't an entity or an item that places one"
        end
    end
    if not item then
        item = storage.utils.build_item(entity)
        if not item then return nil, nil, "no item builds " .. entity .. ", so it cannot be placed by hand" end
    end
    return entity, item, nil
end

local function footprint(prototype, entity_direction)
    local box = prototype.collision_box
    local w = prototype.tile_width or math.ceil(math.abs(box.right_bottom.x - box.left_top.x))
    local h = prototype.tile_height or math.ceil(math.abs(box.right_bottom.y - box.left_top.y))
    if entity_direction == 4 or entity_direction == 12 then w, h = h, w end
    return w, h
end

local function tiles_of(e)
    local left = math.floor(e.x - e.w / 2 + 0.01)
    local top = math.floor(e.y - e.h / 2 + 0.01)
    return left, top, left + e.w - 1, top + e.h - 1
end

local function key(tx, ty) return tx .. "," .. ty end

-- Fluids the entity would connect, for a pipe-like entity the game refused with nothing in the way: the game does
-- not build a fluid entity that would connect two different fluids. Only the fluid boxes it would really join count:
-- a neighbour's connection that faces one of the new entity's own connection points, and for a pipe-to-ground the
-- one pipe-to-ground its underground connection would pair with. nil, or text naming the fluids and where they are.
local MIX_TYPES = {["pipe"] = true, ["pipe-to-ground"] = true, ["storage-tank"] = true, ["pump"] = true}
local DIR_VEC = {[0] = {0, -1}, [4] = {1, 0}, [8] = {0, 1}, [12] = {-1, 0}}
local function tile_of(p) return math.floor(p.x), math.floor(p.y) end
local function box_fluid(other, k)
    local f = other.fluidbox[k]
    if f and f.name then return f.name end
    local ok, seg = pcall(other.fluidbox.get_fluid_segment_contents, k)
    if ok and type(seg) == "table" then
        for name, amount in pairs(seg) do
            if amount and amount > 0 then return name end
        end
    end
    return nil
end
local function fluid_mix(surface, prototype, position, direction)
    if not MIX_TYPES[prototype.type] then return nil end
    local seen, names = {}, {}
    local function add(other, k)
        local name = box_fluid(other, k)
        if name and not seen[name] then
            seen[name] = other.name .. " at (" .. other.position.x .. ", " .. other.position.y .. ")"
            table.insert(names, name)
        end
    end
    local d = direction or 0
    for _, fb in pairs(prototype.fluidbox_prototypes or {}) do
        for _, c in pairs(fb.pipe_connections or {}) do
            local off = c.positions and c.positions[d / 4 + 1]
            local cdir = ((c.direction or 0) + d) % 16
            local v = DIR_VEC[cdir]
            if off and v then
                local ox, oy = math.floor(position.x + off.x), math.floor(position.y + off.y)
                if c.connection_type == "normal" then
                    -- a neighbour connects when one of its own connection points sits on the tile this connection
                    -- faces and points back at this connection's tile
                    local tx, ty = ox + v[1], oy + v[2]
                    for _, other in pairs(surface.find_entities_filtered{area = {{tx + 0.1, ty + 0.1}, {tx + 0.9, ty + 0.9}}}) do
                        if other.valid and other.fluidbox then
                            for k = 1, #other.fluidbox do
                                local ok, conns = pcall(other.fluidbox.get_pipe_connections, k)
                                for _, oc in pairs(ok and conns or {}) do
                                    if oc.connection_type == "normal" and oc.position and oc.target_position then
                                        local px, py = tile_of(oc.position)
                                        local qx, qy = tile_of(oc.target_position)
                                        if px == tx and py == ty and qx == ox and qy == oy then add(other, k) end
                                    end
                                end
                            end
                        end
                    end
                elseif c.connection_type == "underground" then
                    -- the first pipe-to-ground on this axis within reach decides: it pairs when its underground
                    -- connection points back here; one facing away blocks (crossing ones and pipes do not)
                    for step = 1, (c.max_underground_distance or 10) do
                        local tx, ty = ox + v[1] * step, oy + v[2] * step
                        local stop = false
                        for _, other in pairs(surface.find_entities_filtered{area = {{tx + 0.1, ty + 0.1}, {tx + 0.9, ty + 0.9}},
                                                                            type = "pipe-to-ground"}) do
                            if other.valid and other.fluidbox then
                                for k = 1, #other.fluidbox do
                                    local ok, conns = pcall(other.fluidbox.get_pipe_connections, k)
                                    for _, oc in pairs(ok and conns or {}) do
                                        if oc.connection_type == "underground" and oc.position and oc.target_position then
                                            local px, py = tile_of(oc.position)
                                            local qx, qy = tile_of(oc.target_position)
                                            local ax, ay = qx - px, qy - py
                                            if ax == -v[1] and ay == -v[2] then add(other, k); stop = true
                                            elseif ax == v[1] and ay == v[2] then stop = true end
                                        end
                                    end
                                end
                            end
                        end
                        if stop then break end
                    end
                end
            end
        end
    end
    if #names < 2 then return nil end
    local parts = {}
    for k, n in ipairs(names) do
        if k > 3 then break end
        table.insert(parts, n .. " (" .. seen[n] .. ")")
    end
    return "it would connect fluid boxes holding different fluids: " .. table.concat(parts, ", ")
        .. "; the game does not join two fluids"
end

-- What is in the way of `e` (entities and tiles its collision mask collides with), as text
local function blockers(surface, prototype, e)
    local left, top, right, bottom = tiles_of(e)
    local own = mask_layers(prototype)
    local found, count = {}, 0
    local area = {{left + 0.01, top + 0.01}, {right + 0.99, bottom + 0.99}}
    for _, other in pairs(surface.find_entities_filtered{area = area}) do
        if other.valid and not NOT_IN_THE_WAY[other.type] and masks_collide(own, mask_layers(other.prototype)) then
            count = count + 1
            if #found < 3 then table.insert(found, other.name .. " at " .. at(other.position.x, other.position.y)) end
        end
    end
    for ty = top, bottom do
        for tx = left, right do
            local tile = surface.get_tile(tx, ty)
            if tile and tile.valid then
                local collides = false
                if own then
                    for layer in pairs(own) do
                        local ok, hit = pcall(tile.collides_with, layer)
                        if ok and hit then collides = true; break end
                    end
                else
                    collides = string.find(tile.name, "water", 1, true) ~= nil
                end
                if collides then
                    count = count + 1
                    if #found < 3 then table.insert(found, tile.name .. " at " .. at(tx, ty)) end
                end
            end
        end
    end
    if count > 0 then
        local text = "blocked by " .. table.concat(found, ", ")
        if count > #found then text = text .. " and " .. (count - #found) .. " more" end
        return text
    end
    if prototype.type == "mining-drill" then
        return e.name .. " must be placed on a resource it can mine; there is none under it"
    end
    if prototype.type == "offshore-pump" then
        return e.name .. " must be placed at the edge of water, facing the water"
    end
    local mix = fluid_mix(surface, prototype, {x = e.x, y = e.y}, e.dir)
    if mix then return "the game does not allow " .. e.name .. " here: " .. mix end
    return "the game does not allow " .. e.name .. " here; no colliding entity or tile was found"
end

-- An entity the game's build check would let `e` replace (a fast-replace, e.g. a belt over an underground
-- belt): nil, or text naming it. place_layout builds only on free tiles.
local function replaces(surface, prototype, e)
    local left, top, right, bottom = tiles_of(e)
    local own = mask_layers(prototype)
    local area = {{left + 0.01, top + 0.01}, {right + 0.99, bottom + 0.99}}
    for _, other in pairs(surface.find_entities_filtered{area = area}) do
        if other.valid and not NOT_IN_THE_WAY[other.type] and masks_collide(own, mask_layers(other.prototype)) then
            local what = other.name
            if other.type == "underground-belt" then what = what .. " (" .. other.belt_to_ground_type .. ")" end
            return "would replace " .. what .. " at " .. at(other.position.x, other.position.y)
                .. "; place_layout does not replace entities"
        end
    end
    return nil
end

-- The game's build check (the one place_entity uses), with the character stepped aside if it
-- stands in the footprint (place_entity moves it out of the way too)
local function game_fits(player, e)
    local function check()
        return storage.utils.can_place_entity(player, e.name, {x = e.x, y = e.y}, e.dir) and true or false
    end
    local fits = check()
    if not fits then
        local left, top, right, bottom = tiles_of(e)
        local p = player.position
        if p.x > left - 1 and p.x < right + 2 and p.y > top - 1 and p.y < bottom + 2 then
            local home = {x = p.x, y = p.y}
            player.teleport({x = right + 3.5, y = bottom + 3.5})
            local ok, answer = pcall(check)
            player.teleport(home)
            if not ok then error(answer) end
            fits = answer
        end
    end
    return fits
end

-- An entity of the same kind already standing exactly there, as asked: nil, or (entity, mismatch text)
local function existing(surface, e)
    for _, other in pairs(surface.find_entities_filtered{position = {e.x, e.y}, name = e.name}) do
        if other.valid and math.abs(other.position.x - e.x) < 0.01 and math.abs(other.position.y - e.y) < 0.01 then
            local same_dir = other.direction == e.dir or other.type == "assembling-machine"
                or not other.supports_direction
            local same_type = not e.ugtype or other.belt_to_ground_type == e.ugtype
            if same_dir and same_type then return other, nil end
            return other, "a " .. e.name .. " facing " .. (DIR_NAMES[other.direction] or tostring(other.direction))
                .. (other.type == "underground-belt" and (" (" .. other.belt_to_ground_type .. ")") or "")
                .. " already stands there"
        end
    end
    return nil, nil
end

local function check_settings(player, prototype, e)
    if e.recipe then
        if prototype.type ~= "assembling-machine" then
            return e.name .. " has no recipe to set (only assembling machines do)"
        end
        local recipe = player.force.recipes[e.recipe]
        if not recipe then return "there is no recipe called " .. e.recipe end
        if not recipe.enabled then return "recipe " .. e.recipe .. " is not unlocked yet (research needed)" end
        if not prototype.crafting_categories[recipe.category] then
            return e.name .. " cannot craft " .. e.recipe .. " (recipe category " .. recipe.category .. ")"
        end
    end
    if e.filter then
        if prototype.type ~= "inserter" or (prototype.filter_count or 0) == 0 then
            return e.name .. " has no filter slots"
        end
        if not (prototypes.item and prototypes.item[e.filter]) then return "there is no item called " .. e.filter end
    end
    if e.ugtype then
        if prototype.type ~= "underground-belt" then
            return "type (input/output) is only for underground belts, not " .. e.name
        end
        if e.ugtype ~= "input" and e.ugtype ~= "output" then
            return "type must be \"input\" or \"output\", not " .. tostring(e.ugtype)
        end
    end
    return nil
end

local function apply_settings(player, built, e)
    if e.recipe then
        local current = built.get_recipe()
        if not (current and current.name == e.recipe) then built.set_recipe(e.recipe) end
    end
    if e.filter then
        built.use_filters = true
        built.set_filter(1, e.filter)
    end
end

-- Layout expansion: a list of entries, or a text grid with a legend, copied `copies` times
local function expand(payload)
    local anchor = payload.anchor
    local copies = math.max(1, math.floor(payload.copies or 1))
    local off = payload.offset or {x = 0, y = 0}
    local base = {}
    if payload.grid then
        local rows, legend = payload.grid.rows, payload.grid.legend
        local ax, ay = math.floor(anchor.x), math.floor(anchor.y)
        local claimed = {}
        local function char(r, c)
            local row = rows[r]
            if not row or c > #row then return nil end
            return row:sub(c, c)
        end
        for r = 1, #rows do
            for c = 1, #rows[r] do
                local ch = char(r, c)
                if ch ~= " " and ch ~= "." and not claimed[key(c, r)] then
                    local t = legend[ch]
                    if not t then fail("grid character '" .. ch .. "' (column " .. (c - 1) .. ", row " .. (r - 1) .. ") is not in the legend") end
                    local w, h = 1, 1
                    local entity = resolve(t.name)
                    if entity then
                        local d = storage.utils.get_entity_direction(entity, t.dir or 0)
                        w, h = footprint(prototypes.entity[entity], d)
                    end
                    -- the entity's top-left tile is this cell; the rest of its footprint may repeat the character
                    for dy = 0, h - 1 do
                        for dx = 0, w - 1 do
                            if char(r + dy, c + dx) == ch then claimed[key(c + dx, r + dy)] = true end
                        end
                    end
                    table.insert(base, {name = t.name, x = ax + (c - 1) + w / 2, y = ay + (r - 1) + h / 2,
                        dir = t.dir, recipe = t.recipe, filter = t.filter, ugtype = t.ugtype,
                        cell = "column " .. (c - 1) .. ", row " .. (r - 1)})
                end
            end
        end
    else
        for _, t in ipairs(payload.entries or {}) do
            table.insert(base, {name = t.name, x = anchor.x + (t.x or 0), y = anchor.y + (t.y or 0), dir = t.dir,
                recipe = t.recipe, filter = t.filter, ugtype = t.ugtype})
        end
    end
    if #base * copies > MAX_ENTRIES then
        fail("the layout has " .. (#base * copies) .. " entities; at most " .. MAX_ENTRIES .. " per call")
    end
    local out = {}
    for k = 0, copies - 1 do
        for j, t in ipairs(base) do
            table.insert(out, {i = #out + 1, copy = k + 1, entry = j, name = t.name, x = t.x + k * off.x,
                y = t.y + k * off.y, dir = t.dir or 0, recipe = t.recipe, filter = t.filter, ugtype = t.ugtype,
                cell = t.cell})
        end
    end
    return out
end

local function standable(surface, planned, tx, ty)
    if planned[key(tx, ty)] then return false end
    local tile = surface.get_tile(tx, ty)
    if not (tile and tile.valid) then return false end
    local ok, hit = pcall(tile.collides_with, "player")
    if ok and hit then return false end
    for _, other in pairs(surface.find_entities_filtered{area = {{tx + 0.05, ty + 0.05}, {tx + 0.95, ty + 0.95}}}) do
        if other.valid and not NOT_IN_THE_WAY[other.type] then return false end
    end
    return true
end

-- Split entries into stops: a tile to stand on with every entry of the stop within reach - MARGIN.
-- A group that no tile covers is split in two along its longer side, down to single entries.
local function make_stops(surface, planned, list, reach)
    local stops, unreachable = {}, {}
    local limit = reach - MARGIN
    local function covers(px, py, group)
        for _, e in ipairs(group) do
            local dx, dy = e.x - px, e.y - py
            if dx * dx + dy * dy > limit * limit then return false end
        end
        return true
    end
    local function search(cx, cy, radius, group)
        local tx0, ty0 = math.floor(cx), math.floor(cy)
        for r = 0, radius do
            local best, best_d = nil, math.huge
            for dy = -r, r do
                for dx = -r, r do
                    if math.max(math.abs(dx), math.abs(dy)) == r then
                        local tx, ty = tx0 + dx, ty0 + dy
                        local px, py = tx + 0.5, ty + 0.5
                        local d = (px - cx) ^ 2 + (py - cy) ^ 2
                        if d < best_d and covers(px, py, group) and standable(surface, planned, tx, ty) then
                            best, best_d = {x = px, y = py}, d
                        end
                    end
                end
            end
            if best then return best end
        end
        return nil
    end
    local function place_group(group)
        local sx, sy = 0, 0
        for _, e in ipairs(group) do sx = sx + e.x; sy = sy + e.y end
        local cx, cy = sx / #group, sy / #group
        local spot = search(cx, cy, #group == 1 and math.floor(limit) or SEARCH, group)
        if spot then
            local ids = {}
            for _, e in ipairs(group) do table.insert(ids, e.i) end
            table.insert(stops, {x = spot.x, y = spot.y, entries = ids})
            return
        end
        if #group == 1 then
            table.insert(unreachable, group[1])
            return
        end
        -- split in two halves along the longer side of the group's extent
        local x1, y1, x2, y2 = math.huge, math.huge, -math.huge, -math.huge
        for _, e in ipairs(group) do
            x1 = math.min(x1, e.x); x2 = math.max(x2, e.x); y1 = math.min(y1, e.y); y2 = math.max(y2, e.y)
        end
        local axis = (x2 - x1) >= (y2 - y1) and "x" or "y"
        local other = axis == "x" and "y" or "x"
        local sorted = {}
        for _, e in ipairs(group) do table.insert(sorted, e) end
        table.sort(sorted, function(p, q)
            if p[axis] ~= q[axis] then return p[axis] < q[axis] end
            if p[other] ~= q[other] then return p[other] < q[other] end
            return p.i < q.i
        end)
        local half = math.floor(#sorted / 2)
        local parts = {{}, {}}
        for n, e in ipairs(sorted) do table.insert(n <= half and parts[1] or parts[2], e) end
        for _, p in ipairs(parts) do if #p > 0 then place_group(p) end end
    end
    if #list > 0 then place_group(list) end
    return stops, unreachable
end

local function plan(player, payload)
    local surface = player.surface
    local entries = expand(payload)
    local reach = player.reach_distance or player.build_distance or 10
    local tiles = {}
    local required, have, missing = {}, {}, {}
    local problems = 0
    local to_visit = {}
    for _, e in ipairs(entries) do
        local entity, item, err = resolve(e.name)
        local prototype
        if entity then
            e.name, e.item = entity, item
            prototype = prototypes.entity[entity]
            e.dir = storage.utils.get_entity_direction(entity, e.dir or 0)
            e.w, e.h = footprint(prototype, e.dir)
            e.x, e.y = snap(e.x, e.w), snap(e.y, e.h)
            err = check_settings(player, prototype, e)
        end
        if err then
            e.status, e.reason = "invalid", err
        else
            local left, top, right, bottom = tiles_of(e)
            -- inside the layout: one entity per tile
            for ty = top, bottom do
                for tx = left, right do
                    local other = tiles[key(tx, ty)]
                    if other and not e.reason then
                        e.status = "blocked"
                        e.reason = "overlaps layout entry " .. other.i .. " (" .. other.name .. " at " .. at(other.x, other.y) .. ")"
                    end
                end
            end
            if not e.reason then
                for ty = top, bottom do
                    for tx = left, right do tiles[key(tx, ty)] = e end
                end
                for ty = top, bottom do
                    for tx = left, right do
                        local chunk = {x = math.floor(tx / 32), y = math.floor(ty / 32)}
                        if not e.reason and not (player.force.is_chunk_charted(surface, chunk) or surface.is_chunk_generated(chunk)) then
                            e.status = "blocked"
                            e.reason = "tile " .. at(tx, ty) .. " is in a part of the map that has not been generated or charted"
                        end
                    end
                end
            end
            if not e.reason then
                local found, mismatch = existing(surface, e)
                if found and not mismatch then
                    e.status = "already built"
                    if e.recipe or e.filter then table.insert(to_visit, e) end
                elseif mismatch then
                    e.status, e.reason = "blocked", mismatch
                elseif game_fits(player, e) then
                    local rep = replaces(surface, prototype, e)
                    if rep then
                        e.status, e.reason = "blocked", rep
                    else
                        e.status = "ok"
                        required[e.item] = (required[e.item] or 0) + 1
                        table.insert(to_visit, e)
                    end
                else
                    e.status, e.reason = "blocked", blockers(surface, prototype, e)
                end
            end
        end
        if e.reason then problems = problems + 1 end
    end
    local planned = {}
    for k in pairs(tiles) do planned[k] = true end
    local stops, unreachable = make_stops(surface, planned, to_visit, reach)
    for _, e in ipairs(unreachable) do
        if e.status == "ok" then required[e.item] = required[e.item] - 1 end
        e.status, e.reason = "blocked", "no free tile to stand on within reach of it"
        problems = problems + 1
    end
    local any_missing = false
    for item, n in pairs(required) do
        local count = player.get_item_count(item)
        have[item] = count
        if count < n then missing[item] = n - count; any_missing = true end
    end
    local out = {}
    for _, e in ipairs(entries) do
        table.insert(out, {i = e.i, copy = e.copy, entry = e.entry, cell = e.cell, name = e.name, item = e.item,
            x = e.x, y = e.y, dir = e.dir, recipe = e.recipe, filter = e.filter, ugtype = e.ugtype,
            status = e.status, reason = e.reason})
    end
    return {entries = out, stops = stops, required = required, have = have, missing = missing,
        any_missing = any_missing, problems = problems, reach = reach,
        character = {x = player.position.x, y = player.position.y}, tick = game.tick}
end

local function place(player, payload)
    local surface = player.surface
    local reach = player.reach_distance or player.build_distance or 10
    local results = {}
    for _, e in ipairs(payload.entries or {}) do
        local prototype = prototypes.entity[e.name]
        e.dir = e.dir or 0
        e.w, e.h = footprint(prototype, e.dir)
        local r = {i = e.i}
        local dx, dy = player.position.x - e.x, player.position.y - e.y
        local distance = math.sqrt(dx * dx + dy * dy)
        local found, mismatch = existing(surface, e)
        if found and not mismatch then
            if distance <= reach then
                apply_settings(player, found, e)
                r.status = "already built"
            else
                r.status, r.reason = "failed", "already built, but out of reach to set its recipe or filter (distance "
                    .. string.format("%.2f", distance) .. ", reach " .. num(reach) .. ")"
            end
        elseif mismatch then
            r.status, r.reason = "failed", mismatch
        elseif distance > reach then
            r.status, r.reason = "failed", "out of reach (distance " .. string.format("%.2f", distance) .. ", reach " .. num(reach) .. ")"
        elseif player.get_item_count(e.item) < 1 then
            r.status, r.reason = "failed", "no " .. e.item .. " in the inventory"
        else
            -- the game's build check; the character steps out of the footprint if it stands in it
            local fits = storage.utils.can_place_entity(player, e.name, {x = e.x, y = e.y}, e.dir)
            if not fits then
                local left, top, right, bottom = tiles_of(e)
                local p = player.position
                if p.x > left - 1 and p.x < right + 2 and p.y > top - 1 and p.y < bottom + 2 then
                    local spot = surface.find_non_colliding_position("character", {x = right + 1.5, y = p.y}, 3, 0.5)
                    if spot then player.teleport(spot) end
                    fits = storage.utils.can_place_entity(player, e.name, {x = e.x, y = e.y}, e.dir)
                end
            end
            local rep = fits and replaces(surface, prototype, e)
            if not fits then
                r.status, r.reason = "failed", blockers(surface, prototype, e)
            elseif rep then
                r.status, r.reason = "failed", rep
            else
                local built = storage.utils.revive_ghost(player, e.name, {x = e.x, y = e.y})
                if not built then
                    local spec = {name = e.name, position = {x = e.x, y = e.y}, direction = e.dir, force = player.force}
                    if e.ugtype then spec.type = e.ugtype end
                    built = surface.create_entity(spec)
                end
                if built and built.valid then
                    player.remove_item{name = e.item, count = 1}
                    apply_settings(player, built, e)
                    r.status = "placed"
                    if built.type == "assembling-machine" and built.direction ~= e.dir then
                        r.reason = e.name .. " was placed facing north (it takes a direction only while its recipe uses a fluid)"
                    end
                else
                    r.status, r.reason = "failed", "the game did not build it: " .. blockers(surface, prototype, e)
                end
            end
        end
        table.insert(results, r)
    end
    return {entries = results, character = {x = player.position.x, y = player.position.y}, tick = game.tick}
end

storage.actions.place_layout = function(player_index, mode, payload_hex)
    local player = storage.utils.ensure_valid_character(player_index)
    local payload = helpers.json_to_table(unhex(payload_hex))
    if type(payload) ~= "table" then fail("bad layout payload") end
    if mode == "plan" then
        return storage.utils.hex_json(plan(player, payload))
    elseif mode == "place" then
        return storage.utils.hex_json(place(player, payload))
    end
    fail("unknown mode " .. tostring(mode))
end
