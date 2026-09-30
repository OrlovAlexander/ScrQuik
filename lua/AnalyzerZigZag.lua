-- Overlay: zigzag legs from python -m analyzer --waves / --watch-waves
-- CSV: LuaIndicators\analyzer_waves\{SEC}_{CLASS}_{TF}.csv
-- Put this indicator on the price pane (same window as candles). M1, M10, M30.

local RGB           = _G['RGB']
local TYPE_LINE     = _G['TYPE_LINE']
local TYPE_DASH     = _G['TYPE_DASH'] or TYPE_LINE
local TYPE_POINT    = _G['TYPE_POINT']
local SetValue      = _G['SetValue']
local CandleExist   = _G['CandleExist']
local os_time       = os.time
local isDark        = _G.isDarkTheme and _G.isDarkTheme()

local palette = isDark and {
    zz = RGB(192, 192, 192),
} or {
    zz = RGB(160, 160, 160),
}

_G.Settings = {
    Name         = "*AnalyzerZigZag",
    WavesDir     = "",
    ConfirmedOnly = 0,
    ReloadSec    = 15,
    ReadTries    = 2,
    ReadRetryMs  = 0,
    line = {
        {
            Name  = "zz",
            Color = palette.zz,
            Type  = TYPE_LINE,
            Width = 1
        },
        {
            Name  = "zz_off1",
            Color = palette.zz,
            Type  = TYPE_LINE,
            Width = 1
        },
        {
            Name  = "zz_off2",
            Color = palette.zz,
            Type  = TYPE_LINE,
            Width = 1
        },
        {
            Name  = "zz_off3",
            Color = palette.zz,
            Type  = TYPE_LINE,
            Width = 1
        },
        {
            Name  = "zz_off4",
            Color = palette.zz,
            Type  = TYPE_LINE,
            Width = 1
        },
        {
            Name  = "zz_off5",
            Color = palette.zz,
            Type  = TYPE_LINE,
            Width = 1
        }
    }
}

local PlotLines = function(index) return index end
local WAVE_TF = { M1 = true, M10 = true, M30 = true }
local sleep = _G.sleep

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
    local interval = tonumber(ds.interval)
    if interval == nil then
        return "NA"
    end
    interval = math.floor(interval + 0.5)
    if interval >= 1440 and interval % 1440 == 0 then
        local days = math.floor(interval / 1440 + 0.5)
        if days == 1 then return "D1" end
        if days == 7 then return "W1" end
        return "D"..tostring(days)
    end
    if interval >= 60 and interval % 60 == 0 then
        return "H"..tostring(math.floor(interval / 60 + 0.5))
    end
    return "M"..tostring(interval)
end

local function wavesDir()
    local dir = _G.Settings.WavesDir
    if dir ~= nil and dir ~= "" then
        return dir
    end
    return _G.getWorkingFolder().."\\LuaIndicators\\analyzer_waves"
end

local function wavesPath(suffix)
    suffix = suffix or ""
    local ds = _G.getDataSourceInfo and _G.getDataSourceInfo() or {}
    local sec = ds.sec_code or "NA"
    local cls = ds.class_code or "TQBR"
    local tf = chartTfTag()
    local dir = wavesDir()
    local names = { sec }
    local u = string.upper(sec)
    if string.sub(u, 1, 3) == "CNY" then
        names[#names + 1] = "CR"
    end
    if cls == "SPBFUT" and string.len(sec) > 2 then
        names[#names + 1] = string.sub(sec, 1, string.len(sec) - 2)
    end
    for i = 1, #names do
        local path = dir.."\\"..names[i].."_"..cls.."_"..tf..suffix..".csv"
        local fh = io.open(path, "r")
        if fh ~= nil then
            fh:close()
            return path
        end
    end
    return dir.."\\"..sec.."_"..cls.."_"..tf..suffix..".csv"
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

local function loadPivots(path)
    local pivots = {}
    local lastDt = ""
    local fh = openCsv(path, "r")
    if fh == nil then
        return nil, ""
    end
    fh:read("*l")
    for line in fh:lines() do
        local dt, kind, price, conf = string.match(line, "^([^;]+);([^;]+);([^;]+);([^;]+)")
        if dt ~= nil and kind ~= nil then
            pivots[#pivots + 1] = {
                dt = dt,
                key = normKey(dt),
                kind = kind,
                price = tonumber(price),
                confirmed = (tonumber(conf) or 0) ~= 0,
            }
            lastDt = dt
        end
    end
    fh:close()
    return pivots, lastDt
end

local function loadTargets(path)
    local rows = {}
    local lastDt = ""
    local fh = openCsv(path, "r")
    if fh == nil then
        return {}, ""
    end
    fh:read("*l")
    for line in fh:lines() do
        local dt1, px1, dt4, px4, dt5, px5, side, kind, status = string.match(
            line,
            "^([^;]+);([^;]+);([^;]+);([^;]+);([^;]*);([^;]*);([^;]*);([^;]*);([^;]*)"
        )
        if dt1 ~= nil and dt4 ~= nil then
            rows[#rows + 1] = {
                dt1 = dt1,
                key1 = normKey(dt1),
                px1 = tonumber(px1),
                dt4 = dt4,
                key4 = normKey(dt4),
                px4 = tonumber(px4),
                dt5 = dt5,
                key5 = normKey(dt5),
                px5 = tonumber(px5),
                side = side,
                kind = kind,
                status = status,
            }
            lastDt = dt4
        end
    end
    fh:close()
    return rows, lastDt
end

local function barMap()
    local map = {}
    if _G.Size == nil then
        return map
    end
    local n = _G.Size()
    for i = 1, n do
        if CandleExist == nil or CandleExist(i) then
            local key = barKey(i)
            if key ~= nil then
                map[key] = i
            end
        end
    end
    return map
end

local function clearAll(n)
    if SetValue == nil then
        return
    end
    for i = 1, n do
        SetValue(i, 1, nil)
        SetValue(i, 2, nil)
        SetValue(i, 3, nil)
        SetValue(i, 4, nil)
        SetValue(i, 5, nil)
        SetValue(i, 6, nil)
    end
end

local function drawSegment(lineNum, fromBar, toBar, fromVal, toVal)
    if fromVal == nil or toVal == nil or fromBar == nil or toBar == nil then
        return
    end
    local lo = math.min(fromBar, toBar)
    local hi = math.max(fromBar, toBar)
    if lo == hi then
        SetValue(lo, lineNum, fromVal)
        return
    end
    local span = hi - lo
    for b = lo, hi do
        if CandleExist == nil or CandleExist(b) then
            local t = (b - lo) / span
            SetValue(b, lineNum, fromVal + (toVal - fromVal) * t)
        end
    end
end

local function targetStopBar(i1, i4, i5, nEnd)
    local stop = i4
    if i5 ~= nil then
        stop = math.max(i5, i4)
    end
    if nEnd ~= nil and stop > nEnd then
        stop = nEnd
    end
    return stop
end

local function drawTarget14(lineNum, i1, i4, p1, p4, i5, nEnd)
    if i1 == nil or i4 == nil or p1 == nil or p4 == nil then
        return
    end
    if i4 == i1 then
        return
    end
    local stop = targetStopBar(i1, i4, i5, nEnd)
    if stop < i1 then
        return
    end
    local span = i4 - i1
    for b = i1, stop do
        if CandleExist == nil or CandleExist(b) then
            local t = (b - i1) / span
            SetValue(b, lineNum, p1 + (p4 - p1) * t)
        end
    end
end

local function paintTargets(targets)
    if targets == nil or #targets < 1 or _G.Size == nil then
        return
    end
    local n = _G.Size()
    local map = barMap()
    for i = 1, #targets do
        local w = targets[i]
        local i1 = map[w.key1] or map[w.dt1]
        local i4 = map[w.key4] or map[w.dt4]
        local i5 = nil
        if w.key5 ~= nil then
            i5 = map[w.key5] or map[w.dt5]
        end
        local lineNum = 5
        if w.side == "sell" then
            lineNum = 6
        end
        drawTarget14(lineNum, i1, i4, w.px1, w.px4, i5, n)
    end
end

local function paintLegs(pivots)
    local n = _G.Size and _G.Size() or 0
    clearAll(n)
    if pivots == nil or #pivots < 2 or n < 1 then
        return
    end
    local map = barMap()
    local confirmedOnly = tonumber(_G.Settings.ConfirmedOnly) or 0
    local lastI = nil
    local lastPx = nil
    local lastConf = true
    for i = 1, #pivots do
        local p = pivots[i]
        if p.price ~= nil then
            local idx = map[p.key] or map[p.dt]
            if idx ~= nil then
                if lastI ~= nil then
                    local forming = (not lastConf) or (not p.confirmed)
                    if not (confirmedOnly ~= 0 and forming) then
                        drawSegment(1, lastI, idx, lastPx, p.price)
                    end
                end
                lastI = idx
                lastPx = p.price
                lastConf = p.confirmed
            else
                lastI = nil
            end
        end
    end
end

local function paintAndCache(pivots)
    local zz = {}
    paintLegs(pivots)
    local map = barMap()
    local confirmedOnly = tonumber(_G.Settings.ConfirmedOnly) or 0
    if pivots ~= nil then
        local lastI, lastPx, lastConf = nil, nil, true
        for i = 1, #pivots do
            local p = pivots[i]
            if p.price ~= nil then
                local idx = map[p.key] or map[p.dt]
                if idx ~= nil then
                    if lastI ~= nil then
                        local isForming = (not lastConf) or (not p.confirmed)
                        if not (confirmedOnly ~= 0 and isForming) then
                            local lo = math.min(lastI, idx)
                            local hi = math.max(lastI, idx)
                            local span = hi - lo
                            for b = lo, hi do
                                local t = 0
                                if span > 0 then
                                    t = (b - lo) / span
                                end
                                zz[b] = lastPx + (p.price - lastPx) * t
                            end
                        end
                    end
                    lastI = idx
                    lastPx = p.price
                    lastConf = p.confirmed
                else
                    lastI = nil
                end
            end
        end
    end
    return zz
end

local function Algo()
    local pivots = {}
    local zz = {}
    local loadedLast = ""
    local loadedTail = ""
    local lastCheck = 0
    local prevSize = 0

    local function refresh()
        local path = wavesPath("")
        local rows, lastDt = loadPivots(path)
        if rows == nil or (#rows == 0 and loadedLast ~= "") then
            return false
        end
        pivots = rows
        loadedLast = lastDt
        loadedTail = peekLastLine(path) or lastDt
        zz = paintAndCache(pivots)
        return true
    end

    return function(index)
        if not WAVE_TF[chartTfTag()] then
            return nil, nil, nil, nil, nil, nil
        end
        if index == 1 then
            refresh()
            prevSize = _G.Size and _G.Size() or 0
        end
        local nBars = _G.Size and _G.Size() or 0
        if index == nBars and nBars > 0 then
            if prevSize > 0 and nBars > prevSize then
                zz = paintAndCache(pivots)
            end
            prevSize = nBars
            local now = os_time()
            local wait = tonumber(_G.Settings.ReloadSec) or 15
            if wait < 1 then wait = 1 end
            if now - lastCheck >= wait then
                lastCheck = now
                local path = wavesPath("")
                local tail = peekLastLine(path)
                if tail ~= nil and tail ~= loadedTail then
                    refresh()
                end
            end
        end
        return zz[index], nil, nil, nil, nil, nil
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
