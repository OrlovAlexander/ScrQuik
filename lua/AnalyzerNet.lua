-- Separate window for python -m analyzer --net / --watch-net
-- CSV: LuaIndicators\analyzer_net\{SEC}_{CLASS}_{TF}.csv
-- Add as a NEW pane (not on price).
-- Impulse / pullback / regime flat / uncertain / rail 100 are not drawn.
-- Dashed ahead_flat = mean of ahead heads (ahead_up / ahead_down not drawn).
-- Do not stretch mix past the last CSV bar (live edge without rows stays empty).
-- buy_in / sell_in at 33 = M10 ahead head after mix agreement and impulse veto.
-- Re-add after lua replace.

local RGB           = _G['RGB']
local TYPE_LINE     = _G['TYPE_LINE']
local TYPE_DASH     = _G['TYPE_DASH'] or TYPE_LINE
local TYPE_POINT    = _G['TYPE_POINT']
local SetValue      = _G['SetValue']
local os_time       = os.time
local isDark        = _G.isDarkTheme and _G.isDarkTheme()
local message       = _G['message']

local palette = isDark and {
    rail      = RGB(90, 90, 90),
    buy_in    = RGB(80, 255, 160),
    sell_in   = RGB(255, 90, 90),
    ahead_flat= RGB(190, 170, 255),
} or {
    rail      = RGB(160, 160, 160),
    buy_in    = RGB(0, 140, 70),
    sell_in   = RGB(210, 30, 30),
    ahead_flat= RGB(120, 80, 180),
}

_G.Settings = {
    Name        = "*AnalyzerNet",
    NetDir      = "",
    ReloadSec   = 15,
    ReadTries   = 2,
    ReadRetryMs = 0,
    MinAction   = 52,
    ActionGap   = 10,
    line = {
        { Name = "0",         Color = palette.rail,      Type = TYPE_DASH,      Width = 1 },
        { Name = "buy_in",    Color = palette.buy_in,    Type = TYPE_POINT,     Width = 4 },
        { Name = "sell_in",   Color = palette.sell_in,   Type = TYPE_POINT,     Width = 4 },
        { Name = "ahead_flat",Color = palette.ahead_flat,Type = TYPE_DASH,      Width = 2 }
    }
}

local PlotLines = function(index) return index end
local NET_TF = { M1 = true, M10 = true, M30 = true, H4 = true, D1 = true }
local POINT_Y = 33
local sleep = _G.sleep
local warnedTf = false

local function retrySettings()
    local tries = tonumber(_G.Settings.ReadTries) or 5
    if tries < 1 then tries = 1 end
    local wait = tonumber(_G.Settings.ReadRetryMs) or 80
    if wait < 0 then wait = 0 end
    return tries, wait
end

local function openCsv(path, mode)
    local tries, wait = retrySettings()
    for i = 1, tries do
        local fh = io.open(path, mode or "r")
        if fh ~= nil then
            return fh
        end
        if i < tries and wait > 0 and type(sleep) == "function" then
            sleep(wait)
        end
    end
    return nil
end

local function chartTfTag()
    local ds = _G.getDataSourceInfo and _G.getDataSourceInfo() or {}
    local raw = ds.interval
    if type(raw) == "string" then
        local u = string.upper(raw)
        if u == "H4" then return "H4" end
        if u == "M30" then return "M30" end
        if u == "M10" then return "M10" end
        if u == "M1" then return "M1" end
        if u == "D1" then return "D1" end
    end
    local interval = tonumber(raw)
    if interval == nil then
        return "NA"
    end
    interval = math.floor(interval + 0.5)
    if interval >= 1400 and interval < 10080 then
        return "D1"
    end
    if interval >= 60 and interval % 60 == 0 then
        local hours = math.floor(interval / 60 + 0.5)
        if hours == 4 then return "H4" end
        return "H"..tostring(hours)
    end
    return "M"..tostring(interval)
end

local function netDir()
    local dir = _G.Settings.NetDir
    if dir ~= nil and dir ~= "" then
        return dir
    end
    return _G.getWorkingFolder().."\\LuaIndicators\\analyzer_net"
end

local peekLastLine, csvStamp

local function netPath()
    local ds = _G.getDataSourceInfo and _G.getDataSourceInfo() or {}
    local sec = ds.sec_code or "NA"
    local cls = ds.class_code or "TQBR"
    local tf = chartTfTag()
    local dir = netDir()
    local names = { sec }
    local u = string.upper(sec)
    if string.sub(u, 1, 3) == "CNY" or u == "CR" or u == "CRZ6" then
        names[#names + 1] = "CR"
        names[#names + 1] = "CRZ6"
        names[#names + 1] = "CNY12.26"
        names[#names + 1] = "CNY-12.26"
    end
    if cls == "SPBFUT" and string.len(sec) > 2 then
        names[#names + 1] = string.sub(sec, 1, string.len(sec) - 2)
    end
    local classes = { cls }
    if cls ~= "SPBFUT" and (string.sub(u, 1, 3) == "CNY" or u == "CR" or u == "CRZ6") then
        classes[#classes + 1] = "SPBFUT"
    end
    local seen = {}
    local bestPath, bestDt = nil, ""
    for i = 1, #names do
        if names[i] ~= nil and names[i] ~= "" and not seen[names[i]] then
            seen[names[i]] = true
            for c = 1, #classes do
                local path = dir.."\\"..names[i].."_"..classes[c].."_"..tf..".csv"
                local fh = io.open(path, "r")
                if fh ~= nil then
                    fh:close()
                    local dt = csvStamp(path)
                    if bestPath == nil or dt > bestDt then
                        bestPath, bestDt = path, dt
                    end
                end
            end
        end
    end
    return bestPath or (dir.."\\"..sec.."_"..cls.."_"..tf..".csv")
end

local function normKey(dt)
    if dt == nil then
        return nil
    end
    local d, hm = string.match(dt, "^(%d%d%.%d%d%.%d%d%d%d) (%d%d:%d%d)")
    if d ~= nil and hm ~= nil then
        return d.." "..hm..":00"
    end
    return dt
end

local function barYear(t)
    local y = tonumber(t and t.year) or 0
    if y < 100 then
        y = y + 2000
    elseif y < 1900 then
        y = y + 1900
    end
    return y
end

local function barKey(index)
    local t = _G.T and _G.T(index)
    if t == nil then
        return nil
    end
    return string.format(
        "%02d.%02d.%04d %02d:%02d:00",
        t.day or 0, t.month or 0, barYear(t),
        t.hour or 0, t.min or 0
    )
end

local function keyStamp(dt)
    if dt == nil then
        return nil
    end
    local d, m, y, h, mi = string.match(dt, "^(%d%d)%.(%d%d)%.(%d%d%d%d) (%d%d):(%d%d)")
    if y == nil then
        return nil
    end
    return y .. m .. d .. h .. mi
end

local function aheadFlatOnBar(index, row, lastDt, lastFlat)
    if row ~= nil then
        return row.ahead_flat
    end
    local lastStamp = keyStamp(lastDt)
    local stamp = keyStamp(barKey(index))
    if lastStamp ~= nil and stamp ~= nil and stamp <= lastStamp then
        return lastFlat
    end
    return nil
end

peekLastLine = function(path)
    local fh = io.open(path, "rb")
    if fh == nil then
        return nil
    end
    local size = fh:seek("end")
    if size == nil or size < 2 then
        fh:close()
        return nil
    end
    local back = 1024
    if back > size then
        back = size
    end
    fh:seek("end", -back)
    local chunk = fh:read("*a") or ""
    fh:close()
    local last = nil
    for line in string.gmatch(chunk, "[^\r\n]+") do
        last = line
    end
    return last
end

csvStamp = function(path)
    local line = peekLastLine(path)
    if line == nil then
        return ""
    end
    local d, mo, y, h, mi = string.match(line, "^(%d%d)%.(%d%d)%.(%d%d%d%d) (%d%d):(%d%d)")
    if d == nil then
        return ""
    end
    return string.format("%s%s%s%s%s", y, mo, d, h, mi)
end

local function loadNet(path)
    local byKey = {}
    local n = 0
    local lastDt = ""
    local fh = openCsv(path, "r")
    if fh == nil then
        return nil, 0, ""
    end
    fh:read("*l")
    for line in fh:lines() do
        local parts = {}
        for p in string.gmatch(line, "([^;]+)") do
            parts[#parts + 1] = p
        end
        local dt = parts[1]
        if dt ~= nil and parts[2] ~= nil and #parts >= 9 then
            local row = {
                impulse = tonumber(parts[2]),
                pullback = tonumber(parts[3]),
                flat = tonumber(parts[4]),
                buy_in = tonumber(parts[5]),
                sell_in = tonumber(parts[6]),
                buy_out = tonumber(parts[7]),
                sell_out = tonumber(parts[8]),
                action = parts[9],
                ahead_flat = tonumber(parts[10]),
                ahead_up = tonumber(parts[11]),
                ahead_down = tonumber(parts[12]),
            }
            byKey[dt] = row
            local key = normKey(dt)
            if key ~= nil then
                byKey[key] = row
            end
            local dk = string.match(dt, "^(%d%d%.%d%d%.%d%d%d%d)")
            if dk ~= nil then
                byKey[dk] = row
            end
            n = n + 1
            lastDt = dt
        end
    end
    fh:close()
    return byKey, n, lastDt
end

local function rowFor(index, byKey)
    if byKey == nil then
        return nil
    end
    local key = barKey(index)
    local row = key ~= nil and byKey[key] or nil
    if row == nil and key ~= nil then
        local tf = chartTfTag()
        if tf == "D1" or tf == "NA" or string.match(tf, "^D%d+$") then
            row = byKey[string.match(key, "^(%d%d%.%d%d%.%d%d%d%d)")]
        end
    end
    return row
end

local function actionPoint(row)
    if row == nil then
        return nil, nil
    end
    local tf = chartTfTag()
    if tf ~= "M10" then
        return nil, nil
    end
    local minA = tonumber(_G.Settings.MinAction) or 52
    local gap = tonumber(_G.Settings.ActionGap) or 10
    local action = row.action
    local function strong(p, other)
        p = tonumber(p) or 0
        other = tonumber(other) or 0
        return p >= minA and p >= other + gap
    end
    if action == "buy_in" and strong(row.buy_in, row.sell_in) then
        return POINT_Y, nil
    end
    if action == "sell_in" and strong(row.sell_in, row.buy_in) then
        return nil, POINT_Y
    end
    return nil, nil
end

local function paintAll(byKey, lastDt)
    if SetValue == nil or _G.Size == nil then
        return
    end
    local n = _G.Size()
    local lastAheadFlat = nil
    for i = 1, n do
        local row = rowFor(i, byKey)
        if row ~= nil then
            lastAheadFlat = row.ahead_flat
        end
        local buy_in, sell_in = nil, nil
        if row ~= nil then
            buy_in, sell_in = actionPoint(row)
        end
        local flat = aheadFlatOnBar(i, row, lastDt, lastAheadFlat)
        SetValue(i, 1, 0)
        SetValue(i, 2, buy_in)
        SetValue(i, 3, sell_in)
        SetValue(i, 4, flat)
    end
end

local function Algo()
    local byKey = {}
    local loadedLast = ""
    local loadedTail = ""
    local lastCheck = 0
    local prevSize = 0
    local lastAheadFlat = nil

    local function refresh()
        local path = netPath()
        local map, n, lastDt = loadNet(path)
        if map == nil or (n == 0 and loadedLast ~= "") then
            return false
        end
        byKey = map or {}
        loadedLast = lastDt
        loadedTail = peekLastLine(path) or lastDt
        return true
    end

    return function(index)
        local tf = chartTfTag()
        if not NET_TF[tf] then
            if not warnedTf and message then
                warnedTf = true
                message("*AnalyzerNet: M1, M10, M30, H4 or D1", 1)
            end
            return nil, nil, nil, nil
        end
        if index == 1 or loadedLast == "" then
            lastAheadFlat = nil
            refresh()
            paintAll(byKey, loadedLast)
            prevSize = _G.Size and _G.Size() or 0
        end
        local nBars = _G.Size and _G.Size() or 0
        if index == nBars and nBars > 0 then
            if prevSize ~= nBars then
                paintAll(byKey, loadedLast)
                prevSize = nBars
            end
            local now = os_time()
            local wait = tonumber(_G.Settings.ReloadSec) or 15
            if wait < 1 then wait = 1 end
            if now - lastCheck >= wait then
                lastCheck = now
                local path = netPath()
                local tail = peekLastLine(path)
                if tail ~= nil and tail ~= loadedTail then
                    if refresh() then
                        paintAll(byKey, loadedLast)
                    end
                end
            end
        end
        local row = rowFor(index, byKey)
        if row ~= nil then
            lastAheadFlat = row.ahead_flat
        end
        local buy_in, sell_in = nil, nil
        if row ~= nil then
            buy_in, sell_in = actionPoint(row)
        end
        local flat = aheadFlatOnBar(index, row, loadedLast, lastAheadFlat)
        return 0, buy_in, sell_in, flat
    end
end

function _G.Init()
    warnedTf = false
    PlotLines = Algo()
    return 4
end

function _G.OnChangeSettings()
    _G.Init()
end

function _G.OnCalculate(index)
    return PlotLines(index)
end
