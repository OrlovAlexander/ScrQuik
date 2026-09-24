
_G.load   = _G.loadfile or _G.load
local maLib = load(_G.getWorkingFolder().."\\Luaindicators\\maLib.lua")()

local logFile = nil
-- Disk log on every bar stalls QUIK. Set true only to debug (also needs Div_Log=1).
local ENABLE_FILE_LOG = false

local message               = _G['message']
local number                = _G['number']
local RGB                   = _G['RGB']
local TYPE_LINE             = _G['TYPE_LINE']
local TYPE_DASH             = _G['TYPE_DASH'] or TYPE_LINE
local TYPE_HISTOGRAM        = _G['TYPE_HISTOGRAM']
local TYPE_POINT            = _G['TYPE_POINT']
local SetValue              = _G['SetValue']
local isDark                = _G.isDarkTheme()
local os_time	            = os.time

-- ???????: histUp/histDw ? ????? ??? ???? ??????????; ????? RPM ?? ???????????
local palette = isDark and {
    histUp   = RGB(130, 210, 100),
    histDw   = RGB(230, 150, 110),
    zero     = RGB(160, 165, 175),
    rpmSmall = RGB(180, 140, 255),
    emaSmall = RGB(150, 110, 230),
    rpmMiddle = RGB(255, 130, 130),
    emaMiddle = RGB(255, 110, 170),
    rpmUp    = RGB( 90, 170, 255),
    emaUp    = RGB( 60, 130, 220),
} or {
    histUp   = RGB(120, 200,  95),
    histDw   = RGB(240, 165, 125),
    zero     = RGB(140, 145, 155),
    rpmSmall = RGB(130,  80, 210),
    emaSmall = RGB(100,  55, 175),
    rpmMiddle = RGB(255, 125, 125),
    emaMiddle = RGB(255, 145, 185),
    rpmUp    = RGB( 80, 155, 255),
    emaUp    = RGB(105, 175, 245),
}

palette.divSmall = palette.rpmSmall
palette.divMiddle = palette.rpmMiddle
palette.divUp    = palette.rpmUp

_G.Settings= {
    Name 		        = "*RPM_TF_Up_5",
    ["1_Small_TF"]          = "Mn20",
    ["1_Small_Period"]      = 1,
    ["1_Small_PeriodSlow"]  = 40,
    ["1_Small_Draw"]        = 1,
    ["1_Small_HistDraw"]    = 0,
    ["1_Small_DivDraw"]     = 1,
    ["2_Middle_TF"]          = "Mn15",
    ["2_Middle_Period"]      = 20,
    ["2_Middle_PeriodSlow"]  = 40,
    ["2_Middle_Draw"]        = 0,
    ["2_Middle_HistDraw"]    = 0,
    ["2_Middle_DivDraw"]     = 0,
    ["3_Up_TF"]             = "Mn30",
    ["3_Up_Period"]         = 20,
    ["3_Up_PeriodSlow"]     = 40,
    ["3_Up_Draw"]           = 0,
    ["3_Up_HistDraw"]       = 0,
    ["3_Up_DivDraw"]        = 0,
    ["Div_SegPeriod"]       = 2,
    ["Div_SegsMax"]         = 80,
    ["Div_PivotSpanMax"]    = 1,
    ["Div_DrawHidden"]      = 1,
    ["Div_DrawWeak"]        = 1,
    ["Div_Log"]             = 0,
    ["1_Small_LabelDraw"]   = 1,
    ["2_Middle_LabelDraw"]   = 0,
    ["3_Up_LabelDraw"]      = 0,
    line = {
        {
            Name  = 'UpUP',
            Color = palette.histUp,
            Type  = TYPE_HISTOGRAM,
            Width = 2
        },
        {
            Name  = 'UpDW',
            Color = palette.histDw,
            Type  = TYPE_HISTOGRAM,
            Width = 2
        },
        {
            Name  = 'SmallUP',
            Color = palette.histUp,
            Type  = TYPE_HISTOGRAM,
            Width = 2
        },
        {
            Name  = 'SmallDW',
            Color = palette.histDw,
            Type  = TYPE_HISTOGRAM,
            Width = 2
        },
        {
            Name  = 'MiddleUP',
            Color = palette.histUp,
            Type  = TYPE_HISTOGRAM,
            Width = 2
        },
        {
            Name  = 'MiddleDW',
            Color = palette.histDw,
            Type  = TYPE_HISTOGRAM,
            Width = 2
        },
        {
            Name = "zero_line",
            Color = palette.zero,
            Type  = TYPE_LINE,
            Width = 1
        },
        {
            Name = "rpmMiddle",
            Color = palette.rpmMiddle,
            Type  = TYPE_LINE,
            Width = 2
        },
        {
            Name = "rpmUp",
            Color = palette.rpmUp,
            Type  = TYPE_LINE,
            Width = 2
        },
        {
            Name = "emaMiddle",
            Color = palette.emaMiddle,
            Type  = TYPE_LINE,
            Width = 1
        },
        {
            Name = "emaUp",
            Color = palette.emaUp,
            Type  = TYPE_LINE,
            Width = 1
        },
        {
            Name = "rpmSmall",
            Color = palette.rpmSmall,
            Type  = TYPE_LINE,
            Width = 2
        },
        {
            Name = "emaSmall",
            Color = palette.emaSmall,
            Type  = TYPE_LINE,
            Width = 1
        },
        {
            Name = "divSmall1",
            Color = palette.divSmall,
            Type  = TYPE_DASH,
            Width = 1
        },
        {
            Name = "divSmall2",
            Color = palette.divSmall,
            Type  = TYPE_DASH,
            Width = 1
        },
        {
            Name = "divSmall3",
            Color = palette.divSmall,
            Type  = TYPE_DASH,
            Width = 1
        },
        {
            Name = "divSmall4",
            Color = palette.divSmall,
            Type  = TYPE_DASH,
            Width = 1
        },
        {
            Name = "divMiddle1",
            Color = palette.divMiddle,
            Type  = TYPE_DASH,
            Width = 1
        },
        {
            Name = "divMiddle2",
            Color = palette.divMiddle,
            Type  = TYPE_DASH,
            Width = 1
        },
        {
            Name = "divMiddle3",
            Color = palette.divMiddle,
            Type  = TYPE_DASH,
            Width = 1
        },
        {
            Name = "divMiddle4",
            Color = palette.divMiddle,
            Type  = TYPE_DASH,
            Width = 1
        },
        {
            Name = "divUp1",
            Color = palette.divUp,
            Type  = TYPE_DASH,
            Width = 1
        },
        {
            Name = "divUp2",
            Color = palette.divUp,
            Type  = TYPE_DASH,
            Width = 1
        },
        {
            Name = "divUp3",
            Color = palette.divUp,
            Type  = TYPE_DASH,
            Width = 1
        },
        {
            Name = "divUp4",
            Color = palette.divUp,
            Type  = TYPE_DASH,
            Width = 1
        },
        {
            Name = "markSmallHi",
            Color = palette.rpmSmall,
            Type  = TYPE_POINT,
            Width = 3
        },
        {
            Name = "markSmallLo",
            Color = palette.rpmSmall,
            Type  = TYPE_POINT,
            Width = 3
        },
        {
            Name = "markMiddleHi",
            Color = palette.rpmMiddle,
            Type  = TYPE_POINT,
            Width = 3
        },
        {
            Name = "markMiddleLo",
            Color = palette.rpmMiddle,
            Type  = TYPE_POINT,
            Width = 3
        },
        {
            Name = "markUpHi",
            Color = palette.rpmUp,
            Type  = TYPE_POINT,
            Width = 3
        },
        {
            Name = "markUpLo",
            Color = palette.rpmUp,
            Type  = TYPE_POINT,
            Width = 3
        }
    }
}

local function log_tostring(...)
    local n = select('#', ...)
    if n == 1 then
        return tostring(select(1, ...))
    end
    local t = {}
    for i = 1, n do
        t[#t + 1] = tostring((select(i, ...)))
    end
    return table.concat(t, " ")
end

local function myLog(...)
	if logFile==nil then return end
    logFile:write(tostring(os.date("%c",os_time())).." "..log_tostring(...).."\n");
    logFile:flush();
end

local function closeCalcLog()
    if logFile ~= nil then
        logFile:close()
        logFile = nil
    end
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

local function instrumentHeader()
    local ds = _G.getDataSourceInfo and _G.getDataSourceInfo() or {}
    local classCode = ds.class_code or "?"
    local secCode = ds.sec_code or "?"
    local interval = ds.interval or "?"
    local nBars = _G.Size and _G.Size() or "?"
    return classCode, secCode, interval, nBars
end

local logsDirCached = nil

local function logsDir()
    if logsDirCached ~= nil then
        return logsDirCached
    end
    local dir = _G.getWorkingFolder().."\\LuaIndicators\\logs"
    local probe = io.open(dir.."\\._dir", "a")
    if probe ~= nil then
        probe:close()
    else
        os.execute('mkdir "'..dir..'" >nul 2>&1')
    end
    logsDirCached = dir
    return dir
end

local function reopenCalcLog()
    closeCalcLog()
    if not ENABLE_FILE_LOG then
        return
    end
    local tf = chartTfTag()
    logFile = io.open(logsDir().."\\RPM_TF_Up_5."..tf..".txt", "w")
    if logFile == nil then
        return
    end
    local classCode, secCode, interval, nBars = instrumentHeader()
    myLog("=== RPM_TF_Up_5 log session ===")
    myLog("INSTR", classCode, secCode, "tf=", tf, "interval=", interval, "bars=", nBars)
end

local function getSetting(settings, ...)
    local n = select('#', ...)
    local default = select(n, ...)
    for i = 1, n - 1 do
        local v = settings[select(i, ...)]
        if v ~= nil then
            return v
        end
    end
    return default
end

local function toYYYYMMDDHHMMSS(datetime)
	 if type(datetime) ~= "table" then
		return ""
	 else
		local Res = tostring(datetime.year)
		if #Res == 1 then Res = "000"..Res end
		Res = Res.."."
		local month = tostring(datetime.month)
		if #month == 1 then Res = Res.."0"..month else Res = Res..month end
		Res = Res.."."
		local day = tostring(datetime.day)
		if #day == 1 then Res = Res.."0"..day else Res = Res..day end
		Res = Res.." "
		local hour = tostring(datetime.hour)
		if #hour == 1 then Res = Res.."0"..hour else Res = Res..hour end
		Res = Res..":"
		local minute = tostring(datetime.min)
		if #minute == 1 then Res = Res.."0"..minute else Res = Res..minute end
		Res = Res..":"
		local sec = tostring(datetime.sec);
		if #sec == 1 then Res = Res.."0"..sec else Res = Res..sec end
		return Res
	 end
end

-- --- div log (Div_Log=1 -> LuaIndicators\logs\RPM_TF_Up_5_div.{TF}.log) ---
local divLogEnabled       = false
local divLogFile          = nil
local divLogOpened        = false

local function fmtNum(v)
    if v == nil then return "nil" end
    return string.format("%.6f", v)
end

local function formatBarIdx(idx)
    if idx == nil then
        return "?"
    end
    local barTfn = _G['T']
    local barT = barTfn and barTfn(idx)
    if barT then
        return tostring(idx).."("..toYYYYMMDDHHMMSS(barT)..")"
    end
    return tostring(idx)
end

local function divLog(...)
    if not divLogEnabled or divLogFile == nil then
        return
    end
    divLogFile:write(os.date("%Y-%m-%d %H:%M:%S").." "..log_tostring(...).."\n")
    divLogFile:flush()
end

local function divLogLayer(layer, ...)
    if not divLogEnabled then
        return
    end
    divLog("["..(layer and layer.name or "?").."]", ...)
end

local function initDivLog(settings)
    if divLogFile ~= nil then
        divLogFile:close()
        divLogFile = nil
        divLogOpened = false
    end
    divLogEnabled = false
    if not ENABLE_FILE_LOG then
        return
    end
    if getSetting(settings or {}, "Div_Log", 0) ~= 1 then
        return
    end
    divLogEnabled = true
    local tf = chartTfTag()
    divLogFile = io.open(logsDir().."\\RPM_TF_Up_5_div."..tf..".log", "w")
    if divLogFile == nil then
        return
    end
    divLogOpened = true
    local classCode, secCode, interval, nBars = instrumentHeader()
    divLog("=== RPM_TF_Up_5 divergence log session ===")
    divLog("INSTR", classCode, secCode, "tf=", tf, "interval=", interval, "bars=", nBars)
    divLog("Div_SegPeriod=", settings.Div_SegPeriod or DIV_SEG_PERIOD,
        "Div_SegsMax=", settings.Div_SegsMax or DIV_SEGS_MAX,
        "Div_PivotSpanMax=", settings.Div_PivotSpanMax or DIV_PIVOT_SPAN_MAX,
        "Div_DrawHidden=", getSetting(settings, "Div_DrawHidden", "DivDrawHidden", 0),
        "Div_DrawWeak=", getSetting(settings, "Div_DrawWeak", "DivDrawWeak", 0))
end

local function closeDivLog()
    if divLogFile ~= nil then
        divLog("=== log closed ===")
        divLogFile:close()
        divLogFile = nil
        divLogOpened = false
    end
end

local PlotLines     = function(index) return index end
local error_log     = {}

local floor 		        = math.floor

local Size  		= _G['Size']
local T  			= _G['T']
local C  			= _G['C']
local L  			= _G['L']
local O  			= _G['O']
local H  			= _G['H']

-- ???????????? ???????? ?? ? ????? (H1=1, H2=2, ...)
local HOUR_TF_SLOT = {
    H1 = 1,
    H2 = 2,
    H3 = 3,
    H4 = 4,
    H6 = 6,
    H8 = 8,
    H12 = 12,
}

local function hourSlot(hour, tf)
    local n = HOUR_TF_SLOT[tf]
    if not n then
        return nil
    end
    if n == 1 then
        return hour
    end
    return floor(hour / n)
end

local function isHourTf(tf)
    return HOUR_TF_SLOT[tf] ~= nil
end

local function isMinuteTf(tf)
    return type(tf) == "string" and string.sub(tf, 1, 2) == "Mn"
end

-- Mn* ? H*: ?????? ?????? ?? ?????? ???????? ?????? (~2x ?????? ????????)
local function halfHistoryStart()
    return floor(Size() / 2) + 1
end

local function usesHalfHistory(tf)
    return isMinuteTf(tf) or isHourTf(tf)
end

local function aggLayerActive(index, tf)
    if not usesHalfHistory(tf) then
        return true
    end
    return index >= halfHistoryStart()
end

-- ?????? ??????? ???????? ?? (min == 0 ? hour ?????? N)
local function isHourBoundary(crT, tf)
    if not crT or crT.min ~= 0 then
        return false
    end
    local n = HOUR_TF_SLOT[tf]
    if not n then
        return false
    end
    if n == 1 then
        return true
    end
    return crT.hour % n == 0
end

-- ????? ??? ???????? ??: ????? ???????????? ??? ??? ?????? ???? ???????
local function isNewHourlyBar(tf, upT, crT)
    if not HOUR_TF_SLOT[tf] then
        return false
    end
    if upT.year ~= crT.year or upT.month ~= crT.month or upT.day ~= crT.day then
        return true
    end
    return hourSlot(upT.hour, tf) ~= hourSlot(crT.hour, tf)
end

-- ???????? ???????; ??? ??????? ?? ????? ??????
local function cleanBarTime(dt, tf)
    if dt then
        dt.sec = 0
        if isHourTf(tf) then
            dt.min = 0
        end
    end
    return dt
end

-- ???????????????? ????? ?? UpTF ?????? ?????
-- tf - ????????? ???????, ????? ??? "H4"
-- tfds - ??????? ???????? ??????????
-- index - ?????? ???????? ???? ?? ??????? ??????????
-- ds ????????? ???????
local function setFirstTime(tf, tfds, index, ds)

    local status, res = pcall(function()

        local crT = T(index);
        if (crT == nil) then
            myLog('setFirstTime; tf:'..tf..' crT == nil');
            return;
        end
        myLog('setFirstTime; tf:'..tf,' index:'..index,' ds len:'..tostring(Size()),' time:'..toYYYYMMDDHHMMSS(crT));
        local setFirstBar = false;
        if (tf == "Mn2" and crT.min % 2 == 0) then
            setFirstBar = true;
        end
        if (tf == "Mn3" and crT.min % 3 == 0) then
            setFirstBar = true;
        end
        if (tf == "Mn4" and crT.min % 4 == 0) then
            setFirstBar = true;
        end
        if (tf == "Mn5" and crT.min % 5 == 0) then
            setFirstBar = true;
        end
        if (tf == "Mn6" and crT.min % 6 == 0) then
            setFirstBar = true;
        end
        if (tf == "Mn10" and crT.min % 10 == 0) then
            setFirstBar = true;
        end
        if (tf == "Mn15" and crT.min % 15 == 0) then
            setFirstBar = true;
        end
        if (tf == "Mn20" and crT.min % 20 == 0) then
            setFirstBar = true;
        end
        if (tf == "Mn30" and crT.min % 30 == 0) then
            setFirstBar = true;
        end
        if isHourBoundary(crT, tf) then
            setFirstBar = true;
        end
        if (tf == "D1") then
            setFirstBar = true;
        end
        if (tf == "W1") then
            setFirstBar = true;
        end
        if (tf == "M1") then
            setFirstBar = true;
        end
        if setFirstBar then
            tfds[1] = { O=O(index); H=H(index); L=L(index); C=C(index); T=cleanBarTime(crT, tf) }
            myLog('setFirstTime; tf:'..tf..' '..toYYYYMMDDHHMMSS(tfds[1].T));
        end

    end)
    if not status then
        if not error_log[tostring(res)] then
            error_log[tostring(res)] = true
            myLog(tostring(res))
            message(tostring(res))
        end
        return nil
    end
    return
end

-- ???????? Price ? ???????? tfds
-- tf - ????????? ???????, ????? ??? "H4"
-- tfds - ??????? ???????? ??????????
-- index - ?????? ???????? ???? ?? ??????? ??????????
-- ds ????????? ???????
local function setPrice(tf, tfds, index, ds)
    local status, res = pcall(function()

        -- ???? - ???????? ????? ??? ? ??????? tfds
        local addNewBarInTfds = false;
        -- ???? - ????? ?????
        local newMonth = false;
        -- ???? - ????? ????
        local newDay = false;
        -- ???? - ????? ???
        local newHour = false;

        -- ???????????????? UpTF ?????? ?????
        if (#tfds == 0) then
            myLog('setPrice; tf:'..tf..' ??????? ?????????? ?????? ???');
            setFirstTime(tf, tfds, index, ds);
            -- ????? ?????????? ?????? ?? ??????? ?? ??? ?????????
            -- ??????? ???? ?? ??????? ??
            if (#tfds == 1) then
                myLog('setPrice; tf:'..tf..' ?????? ??? ??????????');
            end
            -- ???? ????? ??? ??? ?? ???????????, ????? 
            -- ????? ??????? ?????? ?? ?????????
            if (#tfds == 0) then
                myLog('setPrice; tf:'..tf..' ?????? ??? ?? ??????????');
            end
            return;
        end

        local upT = tfds[#tfds].T;
        local crT = T(index);
        myLog('setPrice; tf:'..tf..' upT:'..toYYYYMMDDHHMMSS(upT)..' crT:'..toYYYYMMDDHHMMSS(crT));
        cleanBarTime(upT, tf);
        cleanBarTime(crT, tf);
        local upTfSec = os_time(upT);
        local crTfSec = os_time(crT)
        -- ??????? ????? (crTfSec) ?????? ?????? ???? ?????? ??? ????? ??????? Up ???? (upTfSec)
        if (crTfSec < upTfSec) then
            local newLen = #tfds + 1;
            tfds[newLen] = { O=O(index); H=H(index); L=L(index); C=C(index); T=crT }
            myLog('setPrice; tf:'..tf..' add new bar');
            return;
        end
        -- ???? - ??????????? ?????? ???? ???
        if (upT.hour ~= crT.hour) then
            newHour = true;
        end
        -- ???? - ??????????? ?????? ???
        if (upT.day ~= crT.day) then
            newDay = true;
        end
        if (upT.month ~= crT.month) then
            newMonth = true;
        end
        -- m1
        -- myLog('setPrice; tf:'..tf..' upT.month: '..upT.month..', crT.month: '..crT.month);
        if (tf == "M1" and newMonth) then
            addNewBarInTfds = true;
        end
        -- w1
        -- myLog('setPrice; tf:'..tf..' upT.week_day: '..upT.week_day..', crT.week_day: '..crT.week_day);
        if (tf == "W1" and crT.week_day == 1 and newDay) then
            addNewBarInTfds = true;
        end
        -- d1
        if (tf == "D1" and newDay) then
            addNewBarInTfds = true;
        end
        -- h1, h2, h3, h4, h6, h8, h12 ? ????????? ?????? ???????
        if isNewHourlyBar(tf, upT, crT) then
            addNewBarInTfds = true;
        end
        if (tf == "Mn2" and (newHour == true or crT.min % 2 == 0)) then
            upTfSec = upTfSec + 1 * 60; -- ? ????????
            if (upTfSec < crTfSec) then
                addNewBarInTfds = true;
            end
        end
        if (tf == "Mn3" and (newHour == true or crT.min % 3 == 0)) then
            upTfSec = upTfSec + 1 * 60; -- ? ????????
            if (upTfSec < crTfSec) then
                addNewBarInTfds = true;
            end
        end
        if (tf == "Mn4" and (newHour == true or crT.min % 4 == 0)) then
            upTfSec = upTfSec + 1 * 60; -- ? ????????
            if (upTfSec < crTfSec) then
                addNewBarInTfds = true;
            end
        end
        if (tf == "Mn5" and (newHour == true or crT.min % 5 == 0)) then
            upTfSec = upTfSec + 1 * 60; -- ? ????????
            if (upTfSec < crTfSec) then
                addNewBarInTfds = true;
            end
        end
        if (tf == "Mn6" and (newHour == true or crT.min % 6 == 0)) then
            upTfSec = upTfSec + 1 * 60; -- ? ????????
            if (upTfSec < crTfSec) then
                addNewBarInTfds = true;
            end
        end
        if (tf == "Mn10" and (newHour == true or crT.min % 10 == 0)) then
            upTfSec = upTfSec + 1 * 60; -- ? ????????
            if (upTfSec < crTfSec) then
                addNewBarInTfds = true;
            end
        end
        if (tf == "Mn15" and (newHour == true or crT.min % 15 == 0)) then
            upTfSec = upTfSec + 1 * 60; -- ? ????????
            if (upTfSec < crTfSec) then
                addNewBarInTfds = true;
            end
        end
        if (tf == "Mn20" and (newHour == true or crT.min % 20 == 0)) then
            upTfSec = upTfSec + 1 * 60; -- ? ????????
            if (upTfSec < crTfSec) then
                addNewBarInTfds = true;
            end
        end
        if (tf == "Mn30" and (newHour == true or crT.min % 30 == 0)) then
            upTfSec = upTfSec + 1 * 60; -- ? ????????
            if (upTfSec < crTfSec) then
                addNewBarInTfds = true;
            end
        end
        if (addNewBarInTfds) then
            local newLen = #tfds + 1;
            tfds[newLen] = { O=O(index); H=H(index); L=L(index); C=C(index); T=crT }
            myLog('setPrice; tf:'..tf..' add new bar');
            return;
        end
        local upHg = tfds[#tfds].H;
        local upLw = tfds[#tfds].L;
        local crHg = H(index);
        local crLw = L(index);
        local crCs = C(index);
        if (upHg < crHg) then
            tfds[#tfds].H = crHg;
        end
        if (upLw > crLw) then
            tfds[#tfds].L = crLw;
        end
        tfds[#tfds].C = crCs;

        myLog('setPrice; tf:'..tf..' ???????? ??????? ???:'..#tfds..'; time:'..toYYYYMMDDHHMMSS(T(index)));

    end)
    if not status then
        if not error_log[tostring(res)] then
            error_log[tostring(res)] = true
            myLog(tostring(res))
            message(tostring(res))
        end
        return nil
    end
    return
end

local function RpmValue(index, ds)
    local row = ds[index];
    local rpm = (row.C * 2 + row.L + row.H) / 4;
    return rpm;
end

local function RPMTFUpTransform(index, ds)
    local s1 = RpmValue(index - 0, ds) *  1.6 + RpmValue(index - 1, ds) *  1.6;
    local s2 = RpmValue(index - 2, ds) *  1.4 + RpmValue(index - 3, ds) *  1.4;
    local s3 = RpmValue(index - 4, ds) *  0.5 + RpmValue(index - 5, ds) *  0.5;
    local s4 = RpmValue(index - 6, ds) * -1.5 + RpmValue(index - 7, ds) * -1.5;
    local s5 = RpmValue(index - 8, ds) * -1.0 + RpmValue(index - 9, ds) * -1.0;
    local s6 = RpmValue(index - 10, ds) * -1.0 + RpmValue(index - 11, ds) * -1.0;
    return (s1 + s2 + s3 + s4 + s5 + s6) / 12
end

-- --- ??????????? RPM ---
-- kind (??????????? ???????):
--   bear / bull          ? ???????????? (????????)
--   hidden_bear / hidden_bull ? ??????? (???????????)
--   extended_bear / extended_bull ? ??????????? (??????? ???????/???)
--   weak_bear / weak_bull ? ??? III: ???? ???????, RPM ????? flat
-- strength (???? ???????????, ??????? I/II/III):
--   I   ? ??????? (???????????? bear/bull)
--   II  ? ??????? (extended_*)
--   III ? ?????? (weak_*)
-- pivotSpan: 1 = ???????? pivots, 2 = ????? ????, 3 = ????? ???
-- zero-cross: ???????? ? RPM < 0 ????? ?????????; ????? ? RPM > 0 ????? ?????????
local DIV_SLOTS             = 4
local DIV_SEG_PERIOD        = 2
local DIV_SEGS_MAX          = 80   -- max confirmedSegs per layer; 0 = no limit
local DIV_PIVOT_SPAN_MAX    = 1
local divSegsMax            = DIV_SEGS_MAX
local DIV_EXTENDED_PCT      = 0.003   -- ~0.3% ? ????? ???????? ??? ???? II
local DIV_WEAK_RPM_PCT      = 0.015   -- ~1.5% ? RPM ?????? ?? ??????????
local DIV_WEAK_PRICE_PCT    = 0.005   -- ~0.5% ? ???? ???????? ?????? ?????????

-- ?????? ????? ? return OnCalculate (??????? ??? ? Init)
local LINE = {
    divSmall1   = 14, divSmall2   = 15, divSmall3   = 16, divSmall4   = 17,
    divMiddle1   = 18, divMiddle2   = 19, divMiddle3   = 20, divMiddle4   = 21,
    divUp1      = 22, divUp2      = 23, divUp3      = 24, divUp4      = 25,
    markSmallHi = 26, markSmallLo = 27,
    markMiddleHi = 28, markMiddleLo = 29,
    markUpHi    = 30, markUpLo    = 31,
}

local function relChange(v1, v2)
    if v1 == nil or v2 == nil or v1 == 0 then
        return nil
    end
    return math.abs(v2 - v1) / math.abs(v1)
end

local function rpmRangeStats(layer, idx1, idx2)
    local stats = {
        fromIdx = nil,
        toIdx = nil,
        count = 0,
        min = nil,
        max = nil,
        minIdx = nil,
        maxIdx = nil,
        belowZero = 0,
        aboveZero = 0,
        atZero = 0,
        firstBelowIdx = nil,
        firstAboveIdx = nil,
    }
    if idx1 == nil or idx2 == nil or idx1 == idx2 then
        return stats
    end
    local fromIdx, toIdx = idx1, idx2
    if fromIdx > toIdx then
        fromIdx, toIdx = toIdx, fromIdx
    end
    stats.fromIdx = fromIdx
    stats.toIdx = toIdx
    local rpmSeries = layer.rpmSeries
    if rpmSeries == nil then
        return stats
    end
    for bar = fromIdx, toIdx do
        local v = rpmSeries[bar]
        if v ~= nil then
            stats.count = stats.count + 1
            if stats.min == nil or v < stats.min then
                stats.min = v
                stats.minIdx = bar
            end
            if stats.max == nil or v > stats.max then
                stats.max = v
                stats.maxIdx = bar
            end
            if v < 0 then
                stats.belowZero = stats.belowZero + 1
                if stats.firstBelowIdx == nil then
                    stats.firstBelowIdx = bar
                end
            elseif v > 0 then
                stats.aboveZero = stats.aboveZero + 1
                if stats.firstAboveIdx == nil then
                    stats.firstAboveIdx = bar
                end
            else
                stats.atZero = stats.atZero + 1
            end
        end
    end
    return stats
end

local function rpmWentBelowZeroBetween(layer, idx1, idx2)
    return rpmRangeStats(layer, idx1, idx2).belowZero > 0
end

local function rpmWentAboveZeroBetween(layer, idx1, idx2)
    return rpmRangeStats(layer, idx1, idx2).aboveZero > 0
end

local function logRpmRange(layer, tag, idx1, idx2)
    local s = rpmRangeStats(layer, idx1, idx2)
    divLogLayer(layer, tag,
        "range", formatBarIdx(s.fromIdx)..".."..formatBarIdx(s.toIdx),
        "bars=", s.count,
        "rpmMin=", fmtNum(s.min), "@", formatBarIdx(s.minIdx),
        "rpmMax=", fmtNum(s.max), "@", formatBarIdx(s.maxIdx),
        "below0=", s.belowZero, "firstBelow=", formatBarIdx(s.firstBelowIdx),
        "above0=", s.aboveZero, "firstAbove=", formatBarIdx(s.firstAboveIdx))
    return s
end

local function logSegPivot(layer, side, seg, segIndex)
    if side == "high" then
        divLogLayer(layer, "PIVOT-H", "seg#", segIndex, "segId=", seg.segId,
            "rpmMaxIdx=", formatBarIdx(seg.rpmMaxIdx), "rpmMax=", fmtNum(seg.rpmMax),
            "priceMax=", fmtNum(seg.priceMax), "priceMaxIdx=", formatBarIdx(seg.priceMaxIdx))
    else
        divLogLayer(layer, "PIVOT-L", "seg#", segIndex, "segId=", seg.segId,
            "rpmMinIdx=", formatBarIdx(seg.rpmMinIdx), "rpmMin=", fmtNum(seg.rpmMin),
            "priceMin=", fmtNum(seg.priceMin), "priceMinIdx=", formatBarIdx(seg.priceMinIdx))
    end
end

local function clearArray(arr)
    for i = #arr, 1, -1 do
        arr[i] = nil
    end
end

local function resetSegLayer(layer)
    layer.curSeg = nil
    layer.confirmedSegs = {}
    layer.lastSegId = 0
    layer.markHi = {}
    layer.markLo = {}
    layer.divBuf = {}
    layer.divSlot = 0
    layer.divDrawn = {}
end

local function newSegLayer()
    return {
        curSeg        = nil,
        confirmedSegs = {},
        divBuf        = {},
        divSlot       = 0,
        divDrawn      = {},
        lastSegId     = 0,
        markHi        = {},
        markLo        = {},
    }
end

local function trimConfirmedSegs(layer)
    if divSegsMax == nil or divSegsMax <= 0 then
        return
    end
    local removed = 0
    while #layer.confirmedSegs > divSegsMax do
        table.remove(layer.confirmedSegs, 1)
        removed = removed + 1
    end
    if removed > 0 and divLogEnabled then
        divLogLayer(layer, "TRIM segs", "removed=", removed, "kept=", #layer.confirmedSegs)
    end
end

local function confirmCurrentSegment(layer, endIndex)
    local cur = layer.curSeg
    if cur == nil or cur.confirmed then
        return
    end

    cur.endIndex = endIndex
    cur.confirmed = true
    layer.confirmedSegs[#layer.confirmedSegs + 1] = {
        segId        = cur.segId,
        startIndex   = cur.startIndex,
        endIndex     = endIndex,
        rpmMax       = cur.rpmMax,
        rpmMaxIdx    = cur.rpmMaxIdx,
        rpmMin       = cur.rpmMin,
        rpmMinIdx    = cur.rpmMinIdx,
        priceMax     = cur.priceMax,
        priceMaxIdx  = cur.priceMaxIdx,
        priceMin     = cur.priceMin,
        priceMinIdx  = cur.priceMinIdx,
    }
    trimConfirmedSegs(layer)
end

local function beginSegment(layer, index, segId, rpmVal, hi, lo)
    layer.curSeg = {
        segId        = segId,
        startIndex   = index,
        endIndex     = index,
        confirmed    = false,
        rpmMax       = rpmVal,
        rpmMaxIdx    = index,
        rpmMin       = rpmVal,
        rpmMinIdx    = index,
        priceMax     = hi,
        priceMaxIdx  = index,
        priceMin     = lo,
        priceMinIdx  = index,
    }
end

local function updateOpenSegment(layer, index, rpmVal, hi, lo)
    local cur = layer.curSeg
    if cur == nil then
        return
    end
    cur.endIndex = index
    if rpmVal ~= nil and cur.rpmMax ~= nil and rpmVal > cur.rpmMax then
        cur.rpmMax = rpmVal
        cur.rpmMaxIdx = index
    end
    if rpmVal ~= nil and cur.rpmMin ~= nil and rpmVal < cur.rpmMin then
        cur.rpmMin = rpmVal
        cur.rpmMinIdx = index
    end
    if hi ~= nil and cur.priceMax ~= nil and hi > cur.priceMax then
        cur.priceMax = hi
        cur.priceMaxIdx = index
    end
    if lo ~= nil and cur.priceMin ~= nil and lo < cur.priceMin then
        cur.priceMin = lo
        cur.priceMinIdx = index
    end
end

local function trackSegmentLayer(layer, index, segId, rpmVal, hi, lo)
    if rpmVal == nil or hi == nil or lo == nil then
        return false
    end

    local confirmed = false
    if layer.curSeg == nil then
        beginSegment(layer, index, segId, rpmVal, hi, lo)
    elseif segId ~= layer.curSeg.segId then
        confirmCurrentSegment(layer, index - 1)
        beginSegment(layer, index, segId, rpmVal, hi, lo)
        confirmed = true
    else
        updateOpenSegment(layer, index, rpmVal, hi, lo)
    end

    layer.lastSegId = segId
    return confirmed
end

local function segPivotHigh(layer, segs, i, period)
    if i <= period or i > #segs - period then
        return false
    end
    local v = segs[i].rpmMax
    if v == nil or v <= 0 then
        return false
    end
    for j = i - period, i + period do
        if j ~= i then
            local other = segs[j].rpmMax
            if other ~= nil and other > 0 and other >= v then
                return false
            end
        end
    end
    return true
end

local function segPivotLow(layer, segs, i, period)
    if i <= period or i > #segs - period then
        return false
    end
    local v = segs[i].rpmMin
    if v == nil or v >= 0 then
        return false
    end
    for j = i - period, i + period do
        if j ~= i then
            local other = segs[j].rpmMin
            if other ~= nil and other < 0 and other <= v then
                return false
            end
        end
    end
    return true
end

local function isSamePriceLevel(v1, v2)
    local ch = relChange(v1, v2)
    return ch ~= nil and ch <= DIV_EXTENDED_PCT
end

local function isRpmFlat(r1, r2)
    local ch = relChange(r1, r2)
    return ch ~= nil and ch <= DIV_WEAK_RPM_PCT
end

local function isPriceActiveMove(p1, p2)
    local ch = relChange(p1, p2)
    return ch ~= nil and ch >= DIV_WEAK_PRICE_PCT
end

local function strengthForKind(kind)
    if kind == "bear" or kind == "bull" then
        return "I"
    end
    if kind == "extended_bear" or kind == "extended_bull" then
        return "II"
    end
    if kind == "weak_bear" or kind == "weak_bull" then
        return "III"
    end
    return nil
end

local function applyDivEntryToChart(entry, lineNo)
    if SetValue == nil or lineNo == nil or entry == nil then
        return
    end
    if entry.idx1 == nil or entry.idx2 == nil or entry.idx2 == entry.idx1 then
        return
    end
    for bar = entry.idx1, entry.idx2 do
        local val = entry.rpm1 + (entry.rpm2 - entry.rpm1) * (bar - entry.idx1) / (entry.idx2 - entry.idx1)
        SetValue(bar, lineNo, val)
    end
end

local function clearDivEntryFromChart(entry, lineNo)
    if SetValue == nil or lineNo == nil or entry == nil then
        return
    end
    if entry.idx1 == nil or entry.idx2 == nil or entry.idx2 == entry.idx1 then
        return
    end
    for bar = entry.idx1, entry.idx2 do
        SetValue(bar, lineNo, nil)
    end
end

local function clearDivLinesOnChart(layer)
    if layer.divLines == nil or layer.divDrawn == nil then
        return
    end
    for slot = 1, DIV_SLOTS do
        local drawn = layer.divDrawn[slot]
        if drawn then
            clearDivEntryFromChart(drawn, layer.divLines[slot])
            layer.divDrawn[slot] = nil
        end
    end
end

local function shouldDrawDivKind(layer, kind)
    if kind == "hidden_bear" or kind == "hidden_bull" then
        return layer.divDrawHidden == 1
    end
    if kind == "weak_bear" or kind == "weak_bull" then
        return layer.divDrawWeak == 1
    end
    return true
end

local function sameDivChartEntry(a, b)
    return a.kind == b.kind and a.idx1 == b.idx1 and a.idx2 == b.idx2
end

local function collectDivEntry(candidates, entry)
    entry.pivotSpan = entry.pivotSpan or 1
    entry.strength = entry.strength or strengthForKind(entry.kind)
    for i = 1, #candidates do
        if sameDivChartEntry(candidates[i], entry) then
            return
        end
    end
    candidates[#candidates + 1] = entry
end

local function makeDivEntry(s1, s2, pivotSpan, useHigh)
    if useHigh then
        return {
            pivotSpan = pivotSpan,
            segId1    = s1.segId,
            segId2    = s2.segId,
            idx1      = s1.rpmMaxIdx,
            rpm1      = s1.rpmMax,
            idx2      = s2.rpmMaxIdx,
            rpm2      = s2.rpmMax,
            price1    = s1.priceMax,
            price2    = s2.priceMax,
        }
    end
    return {
        pivotSpan = pivotSpan,
        segId1    = s1.segId,
        segId2    = s2.segId,
        idx1      = s1.rpmMinIdx,
        rpm1      = s1.rpmMin,
        idx2      = s2.rpmMinIdx,
        rpm2      = s2.rpmMin,
        price1    = s1.priceMin,
        price2    = s2.priceMin,
    }
end

local function pickHighDivKind(layer, p1, p2, r1, r2)
    if p2 < p1 and r2 > r1 then
        return layer.divDrawHidden == 1 and "hidden_bear" or nil
    end
    if isSamePriceLevel(p1, p2) and r2 < r1 then
        return "extended_bear"
    end
    if p2 > p1 and r2 < r1 and not isRpmFlat(r1, r2) then
        return "bear"
    end
    if p2 > p1 and isPriceActiveMove(p1, p2) and isRpmFlat(r1, r2)
        and not isSamePriceLevel(p1, p2) and layer.divDrawWeak == 1 then
        return "weak_bear"
    end
    return nil
end

local function pickLowDivKind(layer, p1, p2, r1, r2)
    if p2 > p1 and r2 < r1 then
        return layer.divDrawHidden == 1 and "hidden_bull" or nil
    end
    if isSamePriceLevel(p1, p2) and r2 > r1 then
        return "extended_bull"
    end
    if p2 < p1 and r2 > r1 and not isRpmFlat(r1, r2) then
        return "bull"
    end
    if p2 < p1 and isPriceActiveMove(p1, p2) and isRpmFlat(r1, r2)
        and not isSamePriceLevel(p1, p2) and layer.divDrawWeak == 1 then
        return "weak_bull"
    end
    return nil
end

local function checkHighDivergences(layer, candidates, s1, s2, pivotSpan, segIdx1, segIdx2)
    if s1.priceMax == nil or s2.priceMax == nil
        or s1.rpmMax == nil or s2.rpmMax == nil then
        divLogLayer(layer, "CHECK-H SKIP", "missing data", "span=", pivotSpan,
            "seg", segIdx1, "->", segIdx2)
        return
    end
    if s1.rpmMaxIdx == nil or s2.rpmMaxIdx == nil then
        divLogLayer(layer, "CHECK-H SKIP", "missing rpmMaxIdx", "span=", pivotSpan,
            "seg", segIdx1, "->", segIdx2)
        return
    end

    divLogLayer(layer, "CHECK-H", "span=", pivotSpan, "seg", segIdx1, "->", segIdx2)
    logSegPivot(layer, "high", s1, segIdx1)
    logSegPivot(layer, "high", s2, segIdx2)
    divLogLayer(layer, "CHECK-H price", "p1=", fmtNum(s1.priceMax), "p2=", fmtNum(s2.priceMax),
        "r1=", fmtNum(s1.rpmMax), "r2=", fmtNum(s2.rpmMax))

    local range = logRpmRange(layer, "CHECK-H zero", s1.rpmMaxIdx, s2.rpmMaxIdx)
    if range.belowZero == 0 then
        divLogLayer(layer, "CHECK-H REJECT", "no RPM<0 between peaks")
        return
    end

    local kind = pickHighDivKind(layer, s1.priceMax, s2.priceMax, s1.rpmMax, s2.rpmMax)
    if kind == nil then
        divLogLayer(layer, "CHECK-H REJECT", "no div kind matched")
        return
    end
    local entry = makeDivEntry(s1, s2, pivotSpan, true)
    entry.kind = kind
    divLogLayer(layer, "CHECK-H ACCEPT", "kind=", kind,
        "idx1=", formatBarIdx(entry.idx1), "idx2=", formatBarIdx(entry.idx2),
        "rpm1=", fmtNum(entry.rpm1), "rpm2=", fmtNum(entry.rpm2))
    collectDivEntry(candidates, entry)
end

local function checkLowDivergences(layer, candidates, s1, s2, pivotSpan, segIdx1, segIdx2)
    if s1.priceMin == nil or s2.priceMin == nil
        or s1.rpmMin == nil or s2.rpmMin == nil then
        divLogLayer(layer, "CHECK-L SKIP", "missing data", "span=", pivotSpan,
            "seg", segIdx1, "->", segIdx2)
        return
    end
    if s1.rpmMinIdx == nil or s2.rpmMinIdx == nil then
        divLogLayer(layer, "CHECK-L SKIP", "missing rpmMinIdx", "span=", pivotSpan,
            "seg", segIdx1, "->", segIdx2)
        return
    end

    divLogLayer(layer, "CHECK-L", "span=", pivotSpan, "seg", segIdx1, "->", segIdx2)
    logSegPivot(layer, "low", s1, segIdx1)
    logSegPivot(layer, "low", s2, segIdx2)
    divLogLayer(layer, "CHECK-L price", "p1=", fmtNum(s1.priceMin), "p2=", fmtNum(s2.priceMin),
        "r1=", fmtNum(s1.rpmMin), "r2=", fmtNum(s2.rpmMin))

    local range = logRpmRange(layer, "CHECK-L zero", s1.rpmMinIdx, s2.rpmMinIdx)
    if range.aboveZero == 0 then
        divLogLayer(layer, "CHECK-L REJECT", "no RPM>0 between troughs")
        return
    end

    local kind = pickLowDivKind(layer, s1.priceMin, s2.priceMin, s1.rpmMin, s2.rpmMin)
    if kind == nil then
        divLogLayer(layer, "CHECK-L REJECT", "no div kind matched")
        return
    end
    local entry = makeDivEntry(s1, s2, pivotSpan, false)
    entry.kind = kind
    divLogLayer(layer, "CHECK-L ACCEPT", "kind=", kind,
        "idx1=", formatBarIdx(entry.idx1), "idx2=", formatBarIdx(entry.idx2),
        "rpm1=", fmtNum(entry.rpm1), "rpm2=", fmtNum(entry.rpm2))
    collectDivEntry(candidates, entry)
end

local function applyPivotHighMark(layer, seg, markLineHi)
    if seg == nil or seg.rpmMaxIdx == nil then
        return
    end
    layer.markHi[seg.rpmMaxIdx] = seg.rpmMax
    if markLineHi and SetValue then
        SetValue(seg.rpmMaxIdx, markLineHi, seg.rpmMax)
    end
end

local function applyPivotLowMark(layer, seg, markLineLo)
    if seg == nil or seg.rpmMinIdx == nil then
        return
    end
    layer.markLo[seg.rpmMinIdx] = seg.rpmMin
    if markLineLo and SetValue then
        SetValue(seg.rpmMinIdx, markLineLo, seg.rpmMin)
    end
end

local function findPrevPivotHighIndex(segs, layer, i, period)
    for p = i - 1, 1 + period, -1 do
        if segPivotHigh(layer, segs, p, period) then
            return p
        end
    end
    return nil
end

local function findPrevPivotLowIndex(segs, layer, i, period)
    for p = i - 1, 1 + period, -1 do
        if segPivotLow(layer, segs, p, period) then
            return p
        end
    end
    return nil
end

local function tryMarkSegmentPivot(layer, segs, i, period, markLineHi, markLineLo)
    if i <= period or i > #segs - period then
        return
    end
    if segPivotHigh(layer, segs, i, period) then
        local seg = segs[i]
        local prevI = findPrevPivotHighIndex(segs, layer, i, period)
        if prevI == nil then
            divLogLayer(layer, "MARK-H skip", "seg#", i, "no prev pivot high")
        else
            local prevSeg = segs[prevI]
            logRpmRange(layer, "MARK-H zero", prevSeg.rpmMaxIdx, seg.rpmMaxIdx)
            if prevSeg.rpmMaxIdx ~= nil and seg.rpmMaxIdx ~= nil
                and rpmWentBelowZeroBetween(layer, prevSeg.rpmMaxIdx, seg.rpmMaxIdx) then
                divLogLayer(layer, "MARK-H ok", "seg#", prevI, "and", i,
                    "idx", formatBarIdx(prevSeg.rpmMaxIdx), "->", formatBarIdx(seg.rpmMaxIdx))
                applyPivotHighMark(layer, prevSeg, markLineHi)
                applyPivotHighMark(layer, seg, markLineHi)
            else
                divLogLayer(layer, "MARK-H reject", "seg#", prevI, "->", i,
                    "no RPM<0 between peaks")
            end
        end
    end
    if segPivotLow(layer, segs, i, period) then
        local seg = segs[i]
        local prevI = findPrevPivotLowIndex(segs, layer, i, period)
        if prevI == nil then
            divLogLayer(layer, "MARK-L skip", "seg#", i, "no prev pivot low")
        else
            local prevSeg = segs[prevI]
            logRpmRange(layer, "MARK-L zero", prevSeg.rpmMinIdx, seg.rpmMinIdx)
            if prevSeg.rpmMinIdx ~= nil and seg.rpmMinIdx ~= nil
                and rpmWentAboveZeroBetween(layer, prevSeg.rpmMinIdx, seg.rpmMinIdx) then
                divLogLayer(layer, "MARK-L ok", "seg#", prevI, "and", i,
                    "idx", formatBarIdx(prevSeg.rpmMinIdx), "->", formatBarIdx(seg.rpmMinIdx))
                applyPivotLowMark(layer, prevSeg, markLineLo)
                applyPivotLowMark(layer, seg, markLineLo)
            else
                divLogLayer(layer, "MARK-L reject", "seg#", prevI, "->", i,
                    "no RPM>0 between troughs")
            end
        end
    end
end

local function onSegmentConfirmed(layer, period, markLineHi, markLineLo)
    local n = #layer.confirmedSegs
    if n < 2 + period * 2 then
        return
    end
    tryMarkSegmentPivot(layer, layer.confirmedSegs, n - period, period, markLineHi, markLineLo)
end

local function flushAllPivotMarks(layer, period, markLineHi, markLineLo)
    if markLineHi == nil and markLineLo == nil then
        return
    end
    local segs = layer.confirmedSegs
    if #segs < 2 + period * 2 then
        return
    end
    layer.markHi = {}
    layer.markLo = {}
    for i = 1 + period, #segs - period do
        tryMarkSegmentPivot(layer, segs, i, period, markLineHi, markLineLo)
    end
end

local function scanDivergences(layer, period, pivotSpanMax, candidates)
    local segs = layer.confirmedSegs
    if #segs < 2 + period * 2 then
        divLogLayer(layer, "SCAN skip", "segments=", #segs, "need=", 2 + period * 2)
        return
    end

    pivotSpanMax = pivotSpanMax or DIV_PIVOT_SPAN_MAX
    if pivotSpanMax < 1 then
        pivotSpanMax = 1
    end
    if pivotSpanMax > 3 then
        pivotSpanMax = 3
    end

    divLogLayer(layer, "SCAN start", "segments=", #segs,
        "period=", period, "pivotSpanMax=", pivotSpanMax)

    local highPivots = {}
    local lowPivots = {}

    for i = 1 + period, #segs - period do
        if segPivotHigh(layer, segs, i, period) then
            highPivots[#highPivots + 1] = i
            logSegPivot(layer, "high", segs[i], i)
        end
        if segPivotLow(layer, segs, i, period) then
            lowPivots[#lowPivots + 1] = i
            logSegPivot(layer, "low", segs[i], i)
        end
    end

    divLogLayer(layer, "SCAN pivots", "high=", #highPivots, "low=", #lowPivots)

    for pivotSpan = 1, pivotSpanMax do
        local gap = pivotSpan
        divLogLayer(layer, "SCAN pairs", "pivotSpan=", pivotSpan)
        for k = gap + 1, #highPivots do
            checkHighDivergences(layer, candidates,
                segs[highPivots[k - gap]], segs[highPivots[k]], pivotSpan,
                highPivots[k - gap], highPivots[k])
        end
        for k = gap + 1, #lowPivots do
            checkLowDivergences(layer, candidates,
                segs[lowPivots[k - gap]], segs[lowPivots[k]], pivotSpan,
                lowPivots[k - gap], lowPivots[k])
        end
    end

    divLogLayer(layer, "SCAN done", "candidates=", #candidates)
end

local function flushAllDivLines(layer, period, pivotSpanMax, drawLines)
    if layer.divLines == nil then
        return
    end
    if drawLines == nil then
        drawLines = true
    end

    divLogLayer(layer, "FLUSH div lines", "period=", period,
        "pivotSpanMax=", pivotSpanMax, "draw=", drawLines and 1 or 0)

    if drawLines then
        clearDivLinesOnChart(layer)
    end

    local candidates = {}
    scanDivergences(layer, period, pivotSpanMax, candidates)

    table.sort(candidates, function(a, b)
        if a.idx2 == b.idx2 then
            return (a.idx1 or 0) > (b.idx1 or 0)
        end
        return (a.idx2 or 0) > (b.idx2 or 0)
    end)

    layer.divBuf = {}
    layer.divDrawn = layer.divDrawn or {}
    local drawn = 0
    for i = 1, #candidates do
        local entry = candidates[i]
        if shouldDrawDivKind(layer, entry.kind) then
            if drawn >= DIV_SLOTS then
                divLogLayer(layer, "FLUSH slot limit", "skipped kind=", entry.kind,
                    "idx2=", formatBarIdx(entry.idx2))
                break
            end
            drawn = drawn + 1
            layer.divBuf[drawn] = entry
            if drawLines then
                applyDivEntryToChart(entry, layer.divLines[drawn])
                layer.divDrawn[drawn] = {
                    idx1 = entry.idx1,
                    idx2 = entry.idx2,
                }
            end
            divLogLayer(layer, drawLines and "FLUSH draw slot" or "FLUSH log slot", drawn, "kind=", entry.kind,
                "idx1=", formatBarIdx(entry.idx1), "idx2=", formatBarIdx(entry.idx2),
                "rpm1=", fmtNum(entry.rpm1), "rpm2=", fmtNum(entry.rpm2))
        else
            divLogLayer(layer, "FLUSH skip draw", "kind=", entry.kind,
                "idx2=", formatBarIdx(entry.idx2), "(hidden/weak disabled)")
        end
    end
    layer.divSlot = drawn
    divLogLayer(layer, "FLUSH done", "drawn=", drawn, "of", #candidates, "candidates")
end

local function invalidateDivLayer(layer, index, rpmVal, hi, lo)
    local changed = false
    for i = 1, DIV_SLOTS do
        local d = layer.divBuf[i]
        if d then
            local broken = false
            if d.kind == "bear" or d.kind == "extended_bear" or d.kind == "weak_bear" then
                if hi ~= nil and d.price2 ~= nil and hi > d.price2 then
                    broken = true
                end
                if index >= d.idx2 and rpmVal ~= nil and d.rpm2 ~= nil and rpmVal > d.rpm2 then
                    broken = true
                end
            elseif d.kind == "hidden_bear" then
                if hi ~= nil and d.price1 ~= nil and hi > d.price1 then
                    broken = true
                end
                if index >= d.idx2 and rpmVal ~= nil and d.rpm2 ~= nil and rpmVal < d.rpm2 then
                    broken = true
                end
            elseif d.kind == "bull" or d.kind == "extended_bull" or d.kind == "weak_bull" then
                if lo ~= nil and d.price2 ~= nil and lo < d.price2 then
                    broken = true
                end
                if index >= d.idx2 and rpmVal ~= nil and d.rpm2 ~= nil and rpmVal < d.rpm2 then
                    broken = true
                end
            elseif d.kind == "hidden_bull" then
                if lo ~= nil and d.price1 ~= nil and lo < d.price1 then
                    broken = true
                end
                if index >= d.idx2 and rpmVal ~= nil and d.rpm2 ~= nil and rpmVal > d.rpm2 then
                    broken = true
                end
            end
            if broken then
                divLogLayer(layer, "INVALIDATE", "slot=", i, "kind=", d.kind,
                    "bar=", formatBarIdx(index), "rpm=", fmtNum(rpmVal))
                if layer.divDrawn and layer.divDrawn[i] and layer.divLines then
                    clearDivEntryFromChart(layer.divDrawn[i], layer.divLines[i])
                    layer.divDrawn[i] = nil
                end
                layer.divBuf[i] = nil
                changed = true
            end
        end
    end
    return changed
end

local function processExtLayer(layer, index, segId, rpmVal, opts)
    if opts == nil then
        return
    end
    if opts.divDraw ~= 1 and opts.rpmLabelDraw ~= 1 and not divLogEnabled then
        return
    end
    if rpmVal == nil then
        return
    end

    local hi = H(index)
    local lo = L(index)
    if hi == nil or lo == nil then
        return
    end

    local period = opts.segPeriod or DIV_SEG_PERIOD
    local segConfirmed = trackSegmentLayer(layer, index, segId, rpmVal, hi, lo)

    if segConfirmed and divLogEnabled then
        local n = #layer.confirmedSegs
        local seg = layer.confirmedSegs[n]
        if seg then
            divLogLayer(layer, "SEG closed", "segId=", seg.segId,
                "bars", formatBarIdx(seg.startIndex)..".."..formatBarIdx(seg.endIndex),
                "rpmMax=", fmtNum(seg.rpmMax), "@", formatBarIdx(seg.rpmMaxIdx),
                "rpmMin=", fmtNum(seg.rpmMin), "@", formatBarIdx(seg.rpmMinIdx),
                "priceMax=", fmtNum(seg.priceMax), "priceMin=", fmtNum(seg.priceMin))
        end
    end

    if opts.rpmLabelDraw == 1 and segConfirmed then
        onSegmentConfirmed(layer, period, opts.markLineHi, opts.markLineLo)
    end

    if opts.divDraw == 1 then
        invalidateDivLayer(layer, index, rpmVal, hi, lo)
    end
end

local function fillDivLine(layer, slot, index)
    local d = layer.divBuf[slot]
    if d == nil then
        return nil
    end
    if index >= d.idx1 and index <= d.idx2 and d.idx2 ~= d.idx1 then
        return d.rpm1 + (d.rpm2 - d.rpm1) * (index - d.idx1) / (d.idx2 - d.idx1)
    end
    return nil
end

local function Algo(Fsettings, ds)

    Fsettings               = (Fsettings or {})

    local small             = Fsettings["1_Small_TF"] or Fsettings.Small or "Mn5"
    local periodSmall       = Fsettings["1_Small_Period"] or Fsettings.PeriodSmall or 20
    local periodSmallSlow   = Fsettings["1_Small_PeriodSlow"] or Fsettings.PeriodSmallSlow or 40
    local smallDraw         = getSetting(Fsettings, "1_Small_Draw", "SmallDraw", 1)
    local smallHistDraw     = getSetting(Fsettings, "1_Small_HistDraw", "SmallHistDraw", 0)
    local smallDivDraw      = getSetting(Fsettings, "1_Small_DivDraw", "SmallDivDraw", 0)
    local smallLabelDraw    = getSetting(Fsettings, "1_Small_LabelDraw", "SmallLabelDraw", 0)
    local middle             = Fsettings["2_Middle_TF"] or Fsettings["2_Midle_TF"] or Fsettings.Middle or Fsettings.Midle or "Mn15"
    local periodMiddle       = Fsettings["2_Middle_Period"] or Fsettings["2_Midle_Period"] or Fsettings.PeriodMiddle or Fsettings.PeriodMidle or 20
    local periodMiddleSlow   = Fsettings["2_Middle_PeriodSlow"] or Fsettings["2_Midle_PeriodSlow"] or Fsettings.PeriodMiddleSlow or Fsettings.PeriodMidleSlow or 40
    local middleDraw         = getSetting(Fsettings, "2_Middle_Draw", "2_Midle_Draw", "MiddleDraw", "MidleDraw", 1)
    local middleHistDraw     = getSetting(Fsettings, "2_Middle_HistDraw", "2_Midle_HistDraw", "MiddleHistDraw", "MidleHistDraw", 0)
    local middleDivDraw      = getSetting(Fsettings, "2_Middle_DivDraw", "2_Midle_DivDraw", "MiddleDivDraw", "MidleDivDraw", 0)
    local middleLabelDraw    = getSetting(Fsettings, "2_Middle_LabelDraw", "2_Midle_LabelDraw", "MiddleLabelDraw", "MidleLabelDraw", 0)
    local up                = Fsettings["3_Up_TF"] or Fsettings.Up or "D1"
    local periodUp          = Fsettings["3_Up_Period"] or Fsettings.PeriodUp or 180
    local periodUpSlow      = Fsettings["3_Up_PeriodSlow"] or Fsettings.PeriodUpSlow or 240
    local upDraw            = getSetting(Fsettings, "3_Up_Draw", "UpDraw", 1)
    local upHistDraw        = getSetting(Fsettings, "3_Up_HistDraw", "UpHistDraw", 0)
    local upDivDraw         = getSetting(Fsettings, "3_Up_DivDraw", "UpDivDraw", 0)
    local upLabelDraw       = getSetting(Fsettings, "3_Up_LabelDraw", "UpLabelDraw", 0)
    local divSegPeriod      = Fsettings.Div_SegPeriod or DIV_SEG_PERIOD
    divSegsMax              = Fsettings.Div_SegsMax or DIV_SEGS_MAX
    local divPivotSpanMax   = Fsettings.Div_PivotSpanMax or DIV_PIVOT_SPAN_MAX
    local divDrawHidden     = getSetting(Fsettings, "Div_DrawHidden", "DivDrawHidden", 0)
    local divDrawWeak       = getSetting(Fsettings, "Div_DrawWeak", "DivDrawWeak", 0)
    if divSegPeriod < 1 then divSegPeriod = 1 end
    if divPivotSpanMax < 1 then divPivotSpanMax = 1 end
    if divPivotSpanMax > 3 then divPivotSpanMax = 3 end

    local function layerEnabled(draw, histDraw, divDraw, labelDraw)
        return draw == 1 or histDraw == 1 or divDraw == 1 or labelDraw == 1
    end
    local needSmall  = layerEnabled(smallDraw, smallHistDraw, smallDivDraw, smallLabelDraw)
    local needMiddle = layerEnabled(middleDraw, middleHistDraw, middleDivDraw, middleLabelDraw)
    local needUp     = layerEnabled(upDraw, upHistDraw, upDivDraw, upLabelDraw)

    local fEmaMiddle
    local fEmaMiddleSlow
    local fEmaSmall
    local fEmaSmallSlow
    local fEmaUp
    local fEmaUpSlow

    error_log               = {}
    local middlePrice        = { O=number; H=number; L=number; C=number; T={} }
    local smallPrice        = { O=number; H=number; L=number; C=number; T={} }
    local upPrice           = { O=number; H=number; L=number; C=number; T={} }

    local _rpmMiddle         = {}
    local _rpmSmall         = {}
    local _rpmUp            = {}
    local _histMiddle        = {}
    local _histSmall        = {}
    local _hist             = {}

    local zero_line
    local hUpUp
    local hUpDw
    local hSmallUp
    local hSmallDw
    local hMiddleUp
    local hMiddleDw
    local rpmMiddle
    local rpmSmall
    local rpmUp
    local emaRpmMiddle
    local emaRpmSmall
    local emaRpmUp

    local divSmallLayer = newSegLayer()
    local divMiddleLayer = newSegLayer()
    local divUpLayer    = newSegLayer()
    divSmallLayer.name = "Small("..small..")"
    divMiddleLayer.name = "Middle("..middle..")"
    divUpLayer.name    = "Up("..up..")"
    divSmallLayer.divLines = { LINE.divSmall1, LINE.divSmall2, LINE.divSmall3, LINE.divSmall4 }
    divMiddleLayer.divLines = { LINE.divMiddle1, LINE.divMiddle2, LINE.divMiddle3, LINE.divMiddle4 }
    divUpLayer.divLines    = { LINE.divUp1, LINE.divUp2, LINE.divUp3, LINE.divUp4 }
    divSmallLayer.divDrawHidden = divDrawHidden
    divSmallLayer.divDrawWeak   = divDrawWeak
    divMiddleLayer.divDrawHidden = divDrawHidden
    divMiddleLayer.divDrawWeak   = divDrawWeak
    divUpLayer.divDrawHidden    = divDrawHidden
    divUpLayer.divDrawWeak      = divDrawWeak
    divSmallLayer.rpmSeries  = _rpmSmall
    divMiddleLayer.rpmSeries = _rpmMiddle
    divUpLayer.rpmSeries     = _rpmUp

    local divSmall1
    local divSmall2
    local divSmall3
    local divSmall4
    local divMiddle1
    local divMiddle2
    local divMiddle3
    local divMiddle4
    local divUp1
    local divUp2
    local divUp3
    local divUp4

    local markSmallHi
    local markSmallLo
    local markMiddleHi
    local markMiddleLo
    local markUpHi
    local markUpLo

    local function calcHist(fEmaFast, fEmaSlow, index, histSeries, histDraw)
        if histDraw ~= 1 then
            return nil, nil
        end
        local hValue = (fEmaFast(index)[index] or 0) - (fEmaSlow(index)[index] or 0)
        histSeries[index] = hValue * 5
        if histSeries[index - 1] == nil then
            return nil, nil
        end
        if histSeries[index] > histSeries[index - 1] then
            return histSeries[index], nil
        end
        return nil, histSeries[index]
    end

    return function (index)

        if index == 1 then
            reopenCalcLog()
            initDivLog(Fsettings)
            if needSmall then
                clearArray(smallPrice)
                fEmaSmall = nil
                fEmaSmallSlow = nil
                resetSegLayer(divSmallLayer)
            end
            if needMiddle then
                clearArray(middlePrice)
                fEmaMiddle = nil
                fEmaMiddleSlow = nil
                resetSegLayer(divMiddleLayer)
            end
            if needUp then
                clearArray(upPrice)
                fEmaUp = nil
                fEmaUpSlow = nil
                resetSegLayer(divUpLayer)
            end
        end

        zero_line       = nil
        hUpUp           = nil
        hUpDw           = nil
        hSmallUp        = nil
        hSmallDw        = nil
        hMiddleUp        = nil
        hMiddleDw        = nil
        rpmMiddle        = nil
        rpmSmall        = nil
        rpmUp           = nil
        emaRpmMiddle     = nil
        emaRpmSmall     = nil
        emaRpmUp        = nil
        divSmall1       = nil
        divSmall2       = nil
        divSmall3       = nil
        divSmall4       = nil
        divMiddle1       = nil
        divMiddle2       = nil
        divMiddle3       = nil
        divMiddle4       = nil
        divUp1          = nil
        divUp2          = nil
        divUp3          = nil
        divUp4          = nil
        markSmallHi     = nil
        markSmallLo     = nil
        markMiddleHi     = nil
        markMiddleLo     = nil
        markUpHi        = nil
        markUpLo        = nil

        local status, res = pcall(function()

            if not maLib then
                myLog("not maLib = nil")
                return
            end

            if needSmall or needMiddle or needUp then
                myLog('tf:'..up..' bar '..#upPrice..'; tf:'..middle..' bar '..#middlePrice..'; tf:'..small..' bar '..#smallPrice);
            end

            local halfStart = halfHistoryStart()

            if needMiddle then
                if usesHalfHistory(middle) and index == halfStart then
                    clearArray(middlePrice)
                    fEmaMiddle = nil
                    fEmaMiddleSlow = nil
                    resetSegLayer(divMiddleLayer)
                end
                if aggLayerActive(index, middle) then
                    if (#middlePrice == 0) then
                        setPrice(middle, middlePrice, index, ds);
                        if (#middlePrice == 1) then
                            fEmaMiddle = maLib.new({method = 'EMA', period = periodMiddle, data_type = 'Any'}, _rpmMiddle);
                            fEmaMiddleSlow = maLib.new({method = 'EMA', period = periodMiddleSlow, data_type = 'Any'}, _rpmMiddle);
                            myLog('tf:'..middle..' EMA init');
                        end
                    else
                        setPrice(middle, middlePrice, index, ds);
                    end
                end
            end

            if needSmall then
                if usesHalfHistory(small) and index == halfStart then
                    clearArray(smallPrice)
                    fEmaSmall = nil
                    fEmaSmallSlow = nil
                    resetSegLayer(divSmallLayer)
                end
                if aggLayerActive(index, small) then
                    if (#smallPrice == 0) then
                        setPrice(small, smallPrice, index, ds);
                        if (#smallPrice == 1) then
                            fEmaSmall = maLib.new({method = 'EMA', period = periodSmall, data_type = 'Any'}, _rpmSmall);
                            fEmaSmallSlow = maLib.new({method = 'EMA', period = periodSmallSlow, data_type = 'Any'}, _rpmSmall);
                            myLog('tf:'..small..' EMA init');
                        end
                    else
                        setPrice(small, smallPrice, index, ds);
                    end
                end
            end

            if needUp then
                if usesHalfHistory(up) and index == halfStart then
                    clearArray(upPrice)
                    fEmaUp = nil
                    fEmaUpSlow = nil
                    resetSegLayer(divUpLayer)
                end
                if aggLayerActive(index, up) then
                    if (#upPrice == 0) then
                        setPrice(up, upPrice, index, ds);
                        if (#upPrice == 1) then
                            fEmaUp = maLib.new({method = 'EMA', period = periodUp, data_type = 'Any'}, _rpmUp);
                            fEmaUpSlow = maLib.new({method = 'EMA', period = periodUpSlow, data_type = 'Any'}, _rpmUp);
                            myLog('tf:'..up..' EMA init');
                        end
                    else
                        setPrice(up, upPrice, index, ds);
                    end
                end
            end

            if needMiddle and aggLayerActive(index, middle) and fEmaMiddle ~= nil and #middlePrice > 12 then
                _rpmMiddle[index] = RPMTFUpTransform(#middlePrice, middlePrice);
                if (middleDraw == 1) then
                    rpmMiddle = _rpmMiddle[index];
                    emaRpmMiddle = fEmaMiddle(index)[index];
                end
                hMiddleUp, hMiddleDw = calcHist(fEmaMiddle, fEmaMiddleSlow, index, _histMiddle, middleHistDraw)
                processExtLayer(divMiddleLayer, index, #middlePrice, _rpmMiddle[index], {
                    divDraw      = middleDivDraw,
                    rpmLabelDraw = middleLabelDraw,
                    segPeriod    = divSegPeriod,
                    pivotSpanMax = divPivotSpanMax,
                    markLineHi   = LINE.markMiddleHi,
                    markLineLo   = LINE.markMiddleLo,
                })
            end

            if needSmall and aggLayerActive(index, small) and fEmaSmall ~= nil and #smallPrice > 12 then
                _rpmSmall[index] = RPMTFUpTransform(#smallPrice, smallPrice);
                if (smallDraw == 1) then
                    rpmSmall = _rpmSmall[index];
                    emaRpmSmall = fEmaSmall(index)[index];
                end
                hSmallUp, hSmallDw = calcHist(fEmaSmall, fEmaSmallSlow, index, _histSmall, smallHistDraw)
                processExtLayer(divSmallLayer, index, #smallPrice, _rpmSmall[index], {
                    divDraw      = smallDivDraw,
                    rpmLabelDraw = smallLabelDraw,
                    segPeriod    = divSegPeriod,
                    pivotSpanMax = divPivotSpanMax,
                    markLineHi   = LINE.markSmallHi,
                    markLineLo   = LINE.markSmallLo,
                })
            end

            if needUp and aggLayerActive(index, up) and fEmaUp ~= nil and #upPrice > 12 then
                _rpmUp[index] = RPMTFUpTransform(#upPrice, upPrice);
                if (upDraw == 1) then
                    rpmUp = _rpmUp[index];
                    emaRpmUp = fEmaUp(index)[index];
                end
                hUpUp, hUpDw = calcHist(fEmaUp, fEmaUpSlow, index, _hist, upHistDraw);
                processExtLayer(divUpLayer, index, #upPrice, _rpmUp[index], {
                    divDraw      = upDivDraw,
                    rpmLabelDraw = upLabelDraw,
                    segPeriod    = divSegPeriod,
                    pivotSpanMax = divPivotSpanMax,
                    markLineHi   = LINE.markUpHi,
                    markLineLo   = LINE.markUpLo,
                })
            end

            if index == Size() then
                if divLogEnabled then
                    divLog("=== FLUSH chart bar", index, "totalSize=", Size(), "===")
                    if needSmall then
                        divLog("Small TF=", small, "div=", smallDivDraw, "label=", smallLabelDraw,
                            "segs=", #smallPrice, "rpmSeries=", divSmallLayer.rpmSeries and "yes" or "no")
                    end
                    if needMiddle then
                        divLog("Middle TF=", middle, "div=", middleDivDraw, "label=", middleLabelDraw,
                            "segs=", #middlePrice)
                    end
                    if needUp then
                        divLog("Up TF=", up, "div=", upDivDraw, "label=", upLabelDraw,
                            "segs=", #upPrice)
                    end
                end
                if needSmall and (smallLabelDraw == 1 or divLogEnabled) then
                    if divLogEnabled then divLogLayer(divSmallLayer, "FLUSH marks") end
                    if smallLabelDraw == 1 then
                        flushAllPivotMarks(divSmallLayer, divSegPeriod,
                            LINE.markSmallHi, LINE.markSmallLo)
                    end
                end
                if needMiddle and (middleLabelDraw == 1 or divLogEnabled) then
                    if divLogEnabled then divLogLayer(divMiddleLayer, "FLUSH marks") end
                    if middleLabelDraw == 1 then
                        flushAllPivotMarks(divMiddleLayer, divSegPeriod,
                            LINE.markMiddleHi, LINE.markMiddleLo)
                    end
                end
                if needUp and (upLabelDraw == 1 or divLogEnabled) then
                    if divLogEnabled then divLogLayer(divUpLayer, "FLUSH marks") end
                    if upLabelDraw == 1 then
                        flushAllPivotMarks(divUpLayer, divSegPeriod,
                            LINE.markUpHi, LINE.markUpLo)
                    end
                end
                if needSmall and (smallDivDraw == 1 or divLogEnabled) then
                    flushAllDivLines(divSmallLayer, divSegPeriod, divPivotSpanMax, smallDivDraw == 1)
                end
                if needMiddle and (middleDivDraw == 1 or divLogEnabled) then
                    flushAllDivLines(divMiddleLayer, divSegPeriod, divPivotSpanMax, middleDivDraw == 1)
                end
                if needUp and (upDivDraw == 1 or divLogEnabled) then
                    flushAllDivLines(divUpLayer, divSegPeriod, divPivotSpanMax, upDivDraw == 1)
                end
            end

            if needSmall then
                markSmallHi = smallLabelDraw == 1 and divSmallLayer.markHi[index] or nil
                markSmallLo = smallLabelDraw == 1 and divSmallLayer.markLo[index] or nil
                divSmall1 = fillDivLine(divSmallLayer, 1, index)
                divSmall2 = fillDivLine(divSmallLayer, 2, index)
                divSmall3 = fillDivLine(divSmallLayer, 3, index)
                divSmall4 = fillDivLine(divSmallLayer, 4, index)
            end
            if needMiddle then
                markMiddleHi = middleLabelDraw == 1 and divMiddleLayer.markHi[index] or nil
                markMiddleLo = middleLabelDraw == 1 and divMiddleLayer.markLo[index] or nil
                divMiddle1 = fillDivLine(divMiddleLayer, 1, index)
                divMiddle2 = fillDivLine(divMiddleLayer, 2, index)
                divMiddle3 = fillDivLine(divMiddleLayer, 3, index)
                divMiddle4 = fillDivLine(divMiddleLayer, 4, index)
            end
            if needUp then
                markUpHi = upLabelDraw == 1 and divUpLayer.markHi[index] or nil
                markUpLo = upLabelDraw == 1 and divUpLayer.markLo[index] or nil
                divUp1 = fillDivLine(divUpLayer, 1, index)
                divUp2 = fillDivLine(divUpLayer, 2, index)
                divUp3 = fillDivLine(divUpLayer, 3, index)
                divUp4 = fillDivLine(divUpLayer, 4, index)
            end

            zero_line  = 0

        end)
        if not status then
            if not error_log[tostring(res)] then
                error_log[tostring(res)] = true
                myLog(tostring(res))
                message(tostring(res))
            end
            return nil
        end
        return hUpUp, hUpDw, hSmallUp, hSmallDw, hMiddleUp, hMiddleDw,
               zero_line, rpmMiddle, rpmUp, emaRpmMiddle, emaRpmUp, rpmSmall, emaRpmSmall,
               divSmall1, divSmall2, divSmall3, divSmall4,
               divMiddle1, divMiddle2, divMiddle3, divMiddle4,
               divUp1, divUp2, divUp3, divUp4,
               markSmallHi, markSmallLo, markMiddleHi, markMiddleLo, markUpHi, markUpLo
    end
end

function _G.Init()
    closeCalcLog()
    closeDivLog()
    PlotLines = Algo(_G.Settings)
    return 31
end

function _G.OnChangeSettings()
    _G.Init()
end

function _G.OnStop()
    closeCalcLog()
    closeDivLog()
end

function _G.OnCalculate(index)
    return PlotLines(index)
end
