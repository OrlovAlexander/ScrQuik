-- Overlay for analyzer setups (buy/sell/buy1/sell1/buy2/sell2) on M1 and M10.
-- CSV from: python -m analyzer --watch
-- Put this indicator on the price pane (same window as candles).

local RGB           = _G['RGB']
local TYPE_POINT    = _G['TYPE_POINT']
local SetValue      = _G['SetValue']
local os_time       = os.time
local isDark        = _G.isDarkTheme and _G.isDarkTheme()

local palette = isDark and {
    buy   = RGB(80, 230, 120),
    sell  = RGB(255, 90, 90),
    buy1  = RGB(80, 220, 230),
    sell1 = RGB(255, 170, 50),
    buy2  = RGB(200, 255, 80),
    sell2 = RGB(220, 90, 220),
} or {
    buy   = RGB(0, 170, 60),
    sell  = RGB(210, 30, 30),
    buy1  = RGB(0, 140, 170),
    sell1 = RGB(210, 120, 0),
    buy2  = RGB(130, 180, 0),
    sell2 = RGB(170, 40, 160),
}

_G.Settings = {
    Name        = "*AnalyzerMarks",
    MarksDir    = "",
    OnsetOnly   = 1,
    OffsetPct   = 0.15,
    ReloadSec   = 15,
    ReadTries   = 2,
    ReadRetryMs = 0,
    line = {
        {
            Name  = "buy",
            Color = palette.buy,
            Type  = TYPE_POINT,
            Width = 4
        },
        {
            Name  = "sell",
            Color = palette.sell,
            Type  = TYPE_POINT,
            Width = 4
        },
        {
            Name  = "buy1",
            Color = palette.buy1,
            Type  = TYPE_POINT,
            Width = 3
        },
        {
            Name  = "sell1",
            Color = palette.sell1,
            Type  = TYPE_POINT,
            Width = 3
        },
        {
            Name  = "buy2",
            Color = palette.buy2,
            Type  = TYPE_POINT,
            Width = 3
        },
        {
            Name  = "sell2",
            Color = palette.sell2,
            Type  = TYPE_POINT,
            Width = 3
        }
    }
}

local PlotLines = function(index) return index end
local MARKS_TF = { M1 = true, M10 = true }
local sleep = _G.sleep

local function retrySettings()
    local tries = tonumber(_G.Settings.ReadTries) or 5
    if tries < 1 then tries = 1 end
    local wait = tonumber(_G.Settings.ReadRetryMs) or 80
    if wait < 0 then wait = 0 end
    return tries, wait
end

local function openMarks(path, mode)
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
    local interval = tonumber(ds.interval)
    if interval == nil then
        return "NA"
    end
    if interval >= 1440 and interval % 1440 == 0 then
        local days = interval / 1440
        if days == 1 then return "D1" end
        if days == 7 then return "W1" end
        return "D"..tostring(days)
    end
    if interval >= 60 and interval % 60 == 0 then
        return "H"..tostring(interval / 60)
    end
    return "M"..tostring(interval)
end

local function marksDir()
    local dir = _G.Settings.MarksDir
    if dir ~= nil and dir ~= "" then
        return dir
    end
    return _G.getWorkingFolder().."\\LuaIndicators\\analyzer_marks"
end

local function marksPath()
    local ds = _G.getDataSourceInfo and _G.getDataSourceInfo() or {}
    local sec = ds.sec_code or "NA"
    local cls = ds.class_code or "TQBR"
    local tf = chartTfTag()
    local dir = marksDir()
    local names = { sec }
    local u = string.upper(sec)
    if string.sub(u, 1, 3) == "CNY" then
        names[#names + 1] = "CR"
    end
    if cls == "SPBFUT" and string.len(sec) > 2 then
        names[#names + 1] = string.sub(sec, 1, string.len(sec) - 2)
    end
    for i = 1, #names do
        local path = dir.."\\"..names[i].."_"..cls.."_"..tf..".csv"
        local fh = io.open(path, "r")
        if fh ~= nil then
            fh:close()
            return path
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

local function barKey(index)
    local t = _G.T and _G.T(index)
    if t == nil then
        return nil
    end
    return string.format(
        "%02d.%02d.%04d %02d:%02d:00",
        t.day or 0, t.month or 0, t.year or 0,
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

local function loadMarks(path)
    local byKey = {}
    local n = 0
    local lastDt = ""
    local fh = openMarks(path, "r")
    if fh == nil then
        return nil, 0, ""
    end
    fh:read("*l")
    for line in fh:lines() do
        local dt, setup, onset, code = string.match(line, "^([^;]+);([^;]+);([^;]+);([^;]+)")
        if dt ~= nil and setup ~= nil then
            local row = {
                setup = setup,
                onset = tonumber(onset) or 0,
                code = tonumber(code) or 0,
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

local function markerY(index, setup)
    local pct = tonumber(_G.Settings.OffsetPct) or 0.15
    pct = pct / 100.0
    if setup == "buy" or setup == "buy1" or setup == "buy2" then
        local lo = _G.L(index)
        if lo == nil then return nil end
        return lo * (1.0 - pct)
    end
    if setup == "sell" or setup == "sell1" or setup == "sell2" then
        local hi = _G.H(index)
        if hi == nil then return nil end
        return hi * (1.0 + pct)
    end
    return nil
end

local function valuesFor(index, byKey)
    local buy, sell, buy1, sell1, buy2, sell2 = nil, nil, nil, nil, nil, nil
    if byKey == nil then
        return buy, sell, buy1, sell1, buy2, sell2
    end
    local key = barKey(index)
    local row = key ~= nil and byKey[key] or nil
    if row == nil or row.setup == "none" then
        return buy, sell, buy1, sell1, buy2, sell2
    end
    local onsetOnly = tonumber(_G.Settings.OnsetOnly) or 1
    if onsetOnly ~= 0 and row.onset ~= 1 then
        return buy, sell, buy1, sell1, buy2, sell2
    end
    local y = markerY(index, row.setup)
    if y == nil then
        return buy, sell, buy1, sell1, buy2, sell2
    end
    if row.setup == "buy" then
        buy = y
    elseif row.setup == "sell" then
        sell = y
    elseif row.setup == "buy1" then
        buy1 = y
    elseif row.setup == "sell1" then
        sell1 = y
    elseif row.setup == "buy2" then
        buy2 = y
    elseif row.setup == "sell2" then
        sell2 = y
    end
    return buy, sell, buy1, sell1, buy2, sell2
end

local function paintBar(index, byKey)
    if SetValue == nil then
        return
    end
    local buy, sell, buy1, sell1, buy2, sell2 = valuesFor(index, byKey)
    SetValue(index, 1, buy)
    SetValue(index, 2, sell)
    SetValue(index, 3, buy1)
    SetValue(index, 4, sell1)
    SetValue(index, 5, buy2)
    SetValue(index, 6, sell2)
end

local function paintAll(byKey)
    if SetValue == nil or _G.Size == nil then
        return
    end
    local n = _G.Size()
    for i = 1, n do
        paintBar(i, byKey)
    end
end

local function Algo()
    local byKey = {}
    local loadedLast = ""
    local loadedTail = ""
    local lastCheck = 0
    local prevSize = 0

    local function refresh()
        local path = marksPath()
        local map, n, lastDt = loadMarks(path)
        if map == nil or (n == 0 and loadedLast ~= "") then
            return false
        end
        byKey = map
        loadedLast = lastDt
        loadedTail = peekLastLine(path) or lastDt
        return true
    end

    return function(index)
        if not MARKS_TF[chartTfTag()] then
            return nil, nil, nil, nil
        end
        if index == 1 then
            refresh()
            prevSize = _G.Size and _G.Size() or 0
        end
        local nBars = _G.Size and _G.Size() or 0
        if index == nBars and nBars > 0 then
            if prevSize > 0 and nBars > prevSize then
                for i = prevSize, nBars - 1 do
                    paintBar(i, byKey)
                end
            end
            prevSize = nBars
            local now = os_time()
            local wait = tonumber(_G.Settings.ReloadSec) or 15
            if wait < 1 then wait = 1 end
            if now - lastCheck >= wait then
                lastCheck = now
                local path = marksPath()
                local tail = peekLastLine(path)
                if tail ~= nil and tail ~= loadedTail then
                    if refresh() then
                        paintAll(byKey)
                    end
                end
            end
        end
        return valuesFor(index, byKey)
    end
end

function _G.Init()
    PlotLines = Algo()
    return 6
end

function _G.OnChangeSettings()
    _G.Init()
end

function _G.OnCalculate(index)
    return PlotLines(index)
end
