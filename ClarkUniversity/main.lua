#version 2

local BUILTIN = {"sledge", "spraycan", "extinguisher", "blowtorch", "shotgun", "plank",
                 "pipebomb", "gun", "bomb", "rocket", "wire", "booster", "leafblower",
                 "turbo", "explosive", "rifle", "steroid"}
local timer = 0

local function toolIds()
    local ids, seen = {}, {}
    for _, id in ipairs(BUILTIN) do
        ids[#ids + 1] = id
        seen[id] = true
    end
    local ok, keys = pcall(ListKeys, "game.tool")
    if ok and keys then
        for _, id in ipairs(keys) do
            if not seen[id] then
                ids[#ids + 1] = id
                seen[id] = true
            end
        end
    end
    return ids
end

local function giveTools()
    local ids = toolIds()
    for _, id in ipairs(ids) do
        pcall(SetBool, "game.tool." .. id .. ".enabled", true)
        pcall(SetFloat, "game.tool." .. id .. ".ammo", 9999)
    end
    local ok, players = pcall(GetAllPlayers)
    if ok and players then
        for _, p in ipairs(players) do
            for _, id in ipairs(ids) do
                pcall(SetToolEnabled, id, true, p)
                pcall(SetToolAmmo, id, 9999, p)
            end
        end
    end
end

function server.init()
    giveTools()
end

function server.tick(dt)
    timer = timer + dt
    if timer > 1 then
        timer = 0
        giveTools()
    end
end
