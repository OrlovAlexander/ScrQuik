-- Archive overlay: --odds evolved into --net / *AnalyzerNet. Do not extend.
-- Outcome odds from python -m analyzer --odds / --watch-odds (lead TF ? M1).
-- CSV: LuaIndicators\analyzer_odds\{SEC}_{CLASS}_{TF}.csv
-- Only M10, M30 and H4. Put on the price pane; bind lines to the LEFT scale (0…100).

local RGB           = _G['RGB']
local TYPE_LINE     = _G['TYPE_LINE']
local TYPE_DASH     = _G['TYPE_DASH'] or TYPE_LINE
local SetValue      = _G['SetValue']
local os_time       = os.time
local isDark        = _G.isDarkTheme and _G.isDarkTheme()
local message       = _G['message']

local palette = isDark and {
    up    = RGB(80, 230, 120),
    down  = RGB(255, 90, 90),
    flat  = RGB(80, 170, 255),
    rail  = RGB(90, 90, 90),
} or {
    up    = RGB(0, 170, 60),
    down  = RGB(210, 30, 30),
    flat  = RGB(20, 90, 210),
    rail  = RGB(160, 160, 160),
}

_G.Settings = {
    Name        = "*AnalyzerOdds",
    OddsDir     = "",
    ReloadSec   = 15,
    ReadTries   = 2,
    ReadRetryMs = 0,
    line = {
        {
            Name  = "up",
            Color = palette.up,
            Type  = TYPE_LINE,
            Width = 2
        },
        {
            Name  = "down",
            Color = palette.down,
            Type  = TYPE_LINE,
            Width = 2
        },
        {
            Name  = "flat",
            Color = palette.flat,
            Type  = TYPE_LINE,
            Width = 2
        },
        {
            Name  = "100",
            Color = palette.rail,
            Type  = TYPE_DASH,
            Width = 1
        },
        {
            Name  = "0",
            Color = palette.rail,
            Type  = TYPE_DASH,
            Width = 1
        }
    }
}

local PlotLines = function(index) return index end
local ODDS_TF = { M10 = true, M30 = true, H4 = true }
local SCALE = 100
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
    end
    local interval = tonumber(raw)
    if interval == nil then
        return "NA"
    end
    interval = math.floor(interval + 0.5)
    if interval >= 60 and interval % 60 == 0 then
        return "H"..tostring(math.floor(interval / 60 + 0.5))
    end
    return "M"..tostring(interval)
end

local function oddsDir()
    local dir = _G.Settings.OddsDir
    if dir ~= nil and dir ~= "" then
        return dir
    end
    return _G.getWorkingFolder().."\\LuaIndicators\\analyzer_odds"
end

local function oddsPath()
    local ds = _G.getDataSourceInfo and _G.getDataSourceInfo() or {}
    local sec = ds.sec_code or "NA"
    local cls = ds.class_code or "TQBR"
    local tf = chartTfTag()
    local dir = oddsDir()
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
    for i = 1, #names do
        if names[i] ~= nil and names[i] ~= "" and not seen[names[i]] then
            seen[names[i]] = true
            for c = 1, #classes do
                local path = dir.."\\"..names[i].."_"..classes[c].."_"..tf..".csv"
                local fh = io.open(path, "r")
                if fh ~= nil then
                    fh:close()
                    return path
                end
            end
        end
    end
    return dir.."\\"..sec.."_"..cls.."_"..tf..".csv"
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

local function peekLastLine(path)
    local fh = io.open(path, "rb")
    if fh == nil then
        return nil
    end
    local size = fh:seek("end")
    if size == nil or size < 2 then
        fh:close()
        return nil
    end
    local back = 512
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

local function loadOdds(path)
    local byKey = {}
    local n = 0
    local lastDt = ""
    local fh = openCsv(path, "r")
    if fh == nil then
        return nil, 0, ""
    end
    fh:read("*l")
    for line in fh:lines() do
        local dt, up, down, flat = string.match(line, "^([^;]+);([^;]+);([^;]+);([^;]+)")
        if dt ~= nil and up ~= nil then
            local row = {
                up = tonumber(up),
                down = tonumber(down),
                flat = tonumber(flat),
            }
            byKey[dt] = row
            local key = normKey(dt)
            if key ~= nil then
                byKey[key] = row
            end
            n = n + 1
            lastDt = dt
        end
    end
    fh:close()
    return byKey, n, lastDt
end

local function valuesFor(index, byKey)
    if not ODDS_TF[chartTfTag()] then
        return nil, nil, nil, nil, nil
    end
    local up, down, flat = nil, nil, nil
    if byKey ~= nil then
        local key = barKey(index)
        local row = key ~= nil and byKey[key] or nil
        if row ~= nil then
            up = row.up
            down = row.down
            flat = row.flat
        end
    end
    return up, down, flat, SCALE, 0
end

local function paintAll(byKey)
    if SetValue == nil or _G.Size == nil then
        return
    end
    local n = _G.Size()
    local lastUp, lastDown, lastFlat = nil, nil, nil
    for i = 1, n do
        local up, down, flat = valuesFor(i, byKey)
        if up ~= nil then
            lastUp, lastDown, lastFlat = up, down, flat
        end
        SetValue(i, 1, lastUp)
        SetValue(i, 2, lastDown)
        SetValue(i, 3, lastFlat)
        SetValue(i, 4, SCALE)
        SetValue(i, 5, 0)
    end
end

local function Algo()
    local byKey = {}
    local loadedLast = ""
    local loadedTail = ""
    local lastCheck = 0
    local prevSize = 0
    local lastUp, lastDown, lastFlat = nil, nil, nil

    local function refresh()
        local path = oddsPath()
        local map, n, lastDt = loadOdds(path)
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
        if not ODDS_TF[tf] then
            if not warnedTf and message then
                warnedTf = true
                message("*AnalyzerOdds: only M10, M30 and H4", 1)
            end
            return nil, nil, nil, nil, nil
        end
        if index == 1 or loadedLast == "" then
            lastUp, lastDown, lastFlat = nil, nil, nil
            refresh()
            paintAll(byKey)
            prevSize = _G.Size and _G.Size() or 0
        end
        local nBars = _G.Size and _G.Size() or 0
        if index == nBars and nBars > 0 then
            if prevSize ~= nBars then
                paintAll(byKey)
                prevSize = nBars
            end
            local now = os_time()
            local wait = tonumber(_G.Settings.ReloadSec) or 15
            if wait < 1 then wait = 1 end
            if now - lastCheck >= wait then
                lastCheck = now
                local path = oddsPath()
                local tail = peekLastLine(path)
                if tail ~= nil and tail ~= loadedTail then
                    if refresh() then
                        paintAll(byKey)
                    end
                end
            end
        end
        local up, down, flat = valuesFor(index, byKey)
        if up ~= nil then
            lastUp, lastDown, lastFlat = up, down, flat
        end
        return lastUp, lastDown, lastFlat, SCALE, 0
    end
end

function _G.Init()
    warnedTf = false
    PlotLines = Algo()
    return 5
end

function _G.OnChangeSettings()
    _G.Init()
end

function _G.OnCalculate(index)
    return PlotLines(index)
end
