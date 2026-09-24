
_G.load   = _G.loadfile or _G.load
local maLib = load(_G.getWorkingFolder().."\\Luaindicators\\maLib.lua")()

local logFile = nil
-- logFile = io.open(_G.getWorkingFolder().."\\LuaIndicators\\RPM_TF_Up_4.txt", "w")

local message               = _G['message']
local number                = _G['number']
local RGB                   = _G['RGB']
local TYPE_LINE             = _G['TYPE_LINE']
local TYPE_HISTOGRAM        = _G['TYPE_HISTOGRAM']
local isDark                = _G.isDarkTheme()
local line_color            = isDark and RGB(240, 240, 240) or RGB(0, 0, 0)
local os_time	            = os.time

-- палитра: histUp/histDw — общие для всех гистограмм; линии RPM по таймфреймам
local palette = isDark and {
    histUp   = RGB(130, 210, 100),
    histDw   = RGB(230, 150, 110),
    zero     = RGB(160, 165, 175),
    rpmSmall = RGB(180, 140, 255),
    emaSmall = RGB(150, 110, 230),
    rpmMidle = RGB(255, 130, 130),
    emaMidle = RGB(255, 110, 170),
    rpmUp    = RGB( 90, 170, 255),
    emaUp    = RGB( 60, 130, 220),
} or {
    histUp   = RGB(120, 200,  95),
    histDw   = RGB(240, 165, 125),
    zero     = RGB(140, 145, 155),
    rpmSmall = RGB(130,  80, 210),
    emaSmall = RGB(100,  55, 175),
    rpmMidle = RGB(255, 125, 125),
    emaMidle = RGB(255, 145, 185),
    rpmUp    = RGB( 80, 155, 255),
    emaUp    = RGB(105, 175, 245),
}

_G.Settings= {
    Name 		        = "*RPM_TF_Up_4",
    ["1_Small_TF"]          = "Mn5",
    ["1_Small_Period"]      = 20,
    ["1_Small_PeriodSlow"]  = 40,
    ["1_Small_Draw"]        = 1,
    ["1_Small_HistDraw"]    = 0,
    ["2_Midle_TF"]          = "Mn15",
    ["2_Midle_Period"]      = 20,
    ["2_Midle_PeriodSlow"]  = 40,
    ["2_Midle_Draw"]        = 1,
    ["2_Midle_HistDraw"]    = 0,
    ["3_Up_TF"]             = "Mn30",
    ["3_Up_Period"]         = 20,
    ["3_Up_PeriodSlow"]     = 40,
    ["3_Up_Draw"]           = 1,
    ["3_Up_HistDraw"]       = 0,
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
            Name  = 'MidleUP',
            Color = palette.histUp,
            Type  = TYPE_HISTOGRAM,
            Width = 2
        },
        {
            Name  = 'MidleDW',
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
            Name = "rpmMidle",
            Color = palette.rpmMidle,
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
            Name = "emaMidle",
            Color = palette.emaMidle,
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

local PlotLines     = function(index) return index end
local error_log     = {}

local floor 		        = math.floor
local ceil 			        = math.ceil

local Size  		= _G['Size']
local T  			= _G['T']
local C  			= _G['C']
local L  			= _G['L']
local O  			= _G['O']
local H  			= _G['H']

-- длительность часового ТФ в часах (H1=1, H2=2, ...)
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

-- начало периода часового ТФ (min == 0 и hour кратен N)
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

-- новый бар часового ТФ: смена календарного дня или другой слот периода
local function isNewHourlyBar(tf, upT, crT)
    if not HOUR_TF_SLOT[tf] then
        return false
    end
    if upT.year ~= crT.year or upT.month ~= crT.month or upT.day ~= crT.day then
        return true
    end
    return hourSlot(upT.hour, tf) ~= hourSlot(crT.hour, tf)
end

local function round(num, idp)
    if num then
        local mult = 10^(idp or 0)
        if num >= 0 then
            return floor(num * mult + 0.5) / mult
        else
            return ceil(num * mult - 0.5) / mult
        end
    else
        return num
    end
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
end --toYYYYMMDDHHMMSS

-- обнулить секунды; для часовых ТФ также минуты
local function cleanBarTime(dt, tf)
    if dt then
        dt.sec = 0
        if isHourTf(tf) then
            dt.min = 0
        end
    end
    return dt
end

-- инициализировать время на UpTF Первым баром
-- tf - таймфрейм верхний, такой как "H4"
-- tfds - датасет верхнего таймфрейма
-- index - индекс текущего бара на текущем таймфрейме
-- ds таймфрейм текущий
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

-- обновить Price у верхнего tfds
-- tf - таймфрейм верхний, такой как "H4"
-- tfds - датасет верхнего таймфрейма
-- index - индекс текущего бара на текущем таймфрейме
-- ds таймфрейм текущий
local function setPrice(tf, tfds, index, ds)
    local status, res = pcall(function()

        -- флаг - добавить новый бар в верхний tfds
        local addNewBarInTfds = false;
        -- флкг - новый месяц
        local newMonth = false;
        -- флкг - новый день
        local newDay = false;
        -- флаг - новый час
        local newHour = false;

        -- инициализировать UpTF Первым баром
        if (#tfds == 0) then
            myLog('setPrice; tf:'..tf..' попытка установить первый бар');
            setFirstTime(tf, tfds, index, ds);
            -- нашли подходящий индекс на текущем ТФ для установки
            -- первого бара на верхнем ТФ
            if (#tfds == 1) then
                myLog('setPrice; tf:'..tf..' первый бар установлен');
            end
            -- если время все еще не установлено, тогда 
            -- можно функцию дальше не выполнять
            if (#tfds == 0) then
                myLog('setPrice; tf:'..tf..' первый бар не установлен');
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
        -- текущее время (crTfSec) должно ВСЕГДА быть больше или РАВНО времени Up бара (upTfSec)
        if (crTfSec < upTfSec) then
            local newLen = #tfds + 1;
            tfds[newLen] = { O=O(index); H=H(index); L=L(index); C=C(index); T=crT }
            myLog('setPrice; tf:'..tf..' add new bar');
            return;
        end
        -- флаг - наступление нового часа дня
        if (upT.hour ~= crT.hour) then
            newHour = true;
        end
        -- флаг - наступления нового дня
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
        -- h1, h2, h3, h4, h6, h8, h12 — сравнение слотов периода
        if isNewHourlyBar(tf, upT, crT) then
            addNewBarInTfds = true;
        end
        if (tf == "Mn2" and (newHour == true or crT.min % 2 == 0)) then
            upTfSec = upTfSec + 1 * 60; -- в секундах
            if (upTfSec < crTfSec) then
                addNewBarInTfds = true;
            end
        end
        if (tf == "Mn3" and (newHour == true or crT.min % 3 == 0)) then
            upTfSec = upTfSec + 1 * 60; -- в секундах
            if (upTfSec < crTfSec) then
                addNewBarInTfds = true;
            end
        end
        if (tf == "Mn4" and (newHour == true or crT.min % 4 == 0)) then
            upTfSec = upTfSec + 1 * 60; -- в секундах
            if (upTfSec < crTfSec) then
                addNewBarInTfds = true;
            end
        end
        if (tf == "Mn5" and (newHour == true or crT.min % 5 == 0)) then
            upTfSec = upTfSec + 1 * 60; -- в секундах
            if (upTfSec < crTfSec) then
                addNewBarInTfds = true;
            end
        end
        if (tf == "Mn6" and (newHour == true or crT.min % 6 == 0)) then
            upTfSec = upTfSec + 1 * 60; -- в секундах
            if (upTfSec < crTfSec) then
                addNewBarInTfds = true;
            end
        end
        if (tf == "Mn10" and (newHour == true or crT.min % 10 == 0)) then
            upTfSec = upTfSec + 1 * 60; -- в секундах
            if (upTfSec < crTfSec) then
                addNewBarInTfds = true;
            end
        end
        if (tf == "Mn15" and (newHour == true or crT.min % 15 == 0)) then
            upTfSec = upTfSec + 1 * 60; -- в секундах
            if (upTfSec < crTfSec) then
                addNewBarInTfds = true;
            end
        end
        if (tf == "Mn20" and (newHour == true or crT.min % 20 == 0)) then
            upTfSec = upTfSec + 1 * 60; -- в секундах
            if (upTfSec < crTfSec) then
                addNewBarInTfds = true;
            end
        end
        if (tf == "Mn30" and (newHour == true or crT.min % 30 == 0)) then
            upTfSec = upTfSec + 1 * 60; -- в секундах
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

        myLog('setPrice; tf:'..tf..' обновлен текущий бар:'..#tfds..'; time:'..toYYYYMMDDHHMMSS(T(index)));

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

local function getSetting(settings, key, altKey, default)
    local v = settings[key]
    if v == nil and altKey ~= nil then
        v = settings[altKey]
    end
    if v == nil then
        return default
    end
    return v
end

local function Algo(Fsettings, ds)

    Fsettings               = (Fsettings or {})

    local small             = Fsettings["1_Small_TF"] or Fsettings.Small or "Mn5"
    local periodSmall       = Fsettings["1_Small_Period"] or Fsettings.PeriodSmall or 20
    local periodSmallSlow   = Fsettings["1_Small_PeriodSlow"] or Fsettings.PeriodSmallSlow or 40
    local smallDraw         = getSetting(Fsettings, "1_Small_Draw", "SmallDraw", 1)
    local smallHistDraw     = getSetting(Fsettings, "1_Small_HistDraw", "SmallHistDraw", 0)
    local midle             = Fsettings["2_Midle_TF"] or Fsettings.Midle or "H4"
    local periodMidle       = Fsettings["2_Midle_Period"] or Fsettings.PeriodMidle or 90
    local periodMidleSlow   = Fsettings["2_Midle_PeriodSlow"] or Fsettings.PeriodMidleSlow or 40
    local midleDraw         = getSetting(Fsettings, "2_Midle_Draw", "MidleDraw", 1)
    local midleHistDraw     = getSetting(Fsettings, "2_Midle_HistDraw", "MidleHistDraw", 0)
    local up                = Fsettings["3_Up_TF"] or Fsettings.Up or "D1"
    local periodUp          = Fsettings["3_Up_Period"] or Fsettings.PeriodUp or 180
    local periodUpSlow      = Fsettings["3_Up_PeriodSlow"] or Fsettings.PeriodUpSlow or 240
    local upDraw            = getSetting(Fsettings, "3_Up_Draw", "UpDraw", 1)
    local upHistDraw        = getSetting(Fsettings, "3_Up_HistDraw", "UpHistDraw", 0)

    local fEmaMidle
    local fEmaMidleSlow
    local fEmaSmall
    local fEmaSmallSlow
    local fEmaUp
    local fEmaUpSlow

    error_log               = {}
    local midlePrice        = { O=number; H=number; L=number; C=number; T={} }
    local smallPrice        = { O=number; H=number; L=number; C=number; T={} }
    local upPrice           = { O=number; H=number; L=number; C=number; T={} }

    local _rpmMidle         = {}
    local _rpmSmall         = {}
    local _rpmUp            = {}
    local _histMidle        = {}
    local _histSmall        = {}
    local _hist             = {}

    local zero_line
    local hUpUp
    local hUpDw
    local hSmallUp
    local hSmallDw
    local hMidleUp
    local hMidleDw
    local rpmMidle
    local rpmSmall
    local rpmUp
    local emaRpmMidle
    local emaRpmSmall
    local emaRpmUp

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

        zero_line       = nil
        hUpUp           = nil
        hUpDw           = nil
        hSmallUp        = nil
        hSmallDw        = nil
        hMidleUp        = nil
        hMidleDw        = nil
        rpmMidle        = nil
        rpmSmall        = nil
        rpmUp           = nil
        emaRpmMidle     = nil
        emaRpmSmall     = nil
        emaRpmUp        = nil

        local status, res = pcall(function()

            if not maLib then
                myLog("not maLib = nil")
                return
            end

            myLog('tf:'..up..' обрабатывается бар '..#upPrice..'; tf:'..midle..' обрабатывается бар '..#midlePrice..'; tf:'..small..' обрабатывается бар '..#smallPrice);

            if (#midlePrice == 0) then
                setPrice(midle, midlePrice, index, ds);
                if (#midlePrice == 1) then
                    fEmaMidle = maLib.new({method = 'EMA', period = periodMidle, data_type = 'Any'}, _rpmMidle);
                    fEmaMidleSlow = maLib.new({method = 'EMA', period = periodMidleSlow, data_type = 'Any'}, _rpmMidle);
                    myLog('tf:'..midle..' функция установлена');
                end
            else
                setPrice(midle, midlePrice, index, ds);
            end

            if (#smallPrice == 0) then
                setPrice(small, smallPrice, index, ds);
                if (#smallPrice == 1) then
                    fEmaSmall = maLib.new({method = 'EMA', period = periodSmall, data_type = 'Any'}, _rpmSmall);
                    fEmaSmallSlow = maLib.new({method = 'EMA', period = periodSmallSlow, data_type = 'Any'}, _rpmSmall);
                    myLog('tf:'..small..' функция установлена');
                end
            else
                setPrice(small, smallPrice, index, ds);
            end

            if (#upPrice == 0) then
                setPrice(up, upPrice, index, ds);
                if (#upPrice == 1) then
                    fEmaUp = maLib.new({method = 'EMA', period = periodUp, data_type = 'Any'}, _rpmUp);
                    fEmaUpSlow = maLib.new({method = 'EMA', period = periodUpSlow, data_type = 'Any'}, _rpmUp);
                    myLog('tf:'..up..' функция установлена');
                end
            else
                setPrice(up, upPrice, index, ds);
            end

            if (fEmaMidle ~= nil and #midlePrice > 12) then
                _rpmMidle[index] = RPMTFUpTransform(#midlePrice, midlePrice);
                if (midleDraw == 1) then
                    rpmMidle = _rpmMidle[index];
                    emaRpmMidle = fEmaMidle(index)[index];
                end
                hMidleUp, hMidleDw = calcHist(fEmaMidle, fEmaMidleSlow, index, _histMidle, midleHistDraw)
            end

            if (fEmaSmall ~= nil and #smallPrice > 12) then
                _rpmSmall[index] = RPMTFUpTransform(#smallPrice, smallPrice);
                if (smallDraw == 1) then
                    rpmSmall = _rpmSmall[index];
                    emaRpmSmall = fEmaSmall(index)[index];
                end
                hSmallUp, hSmallDw = calcHist(fEmaSmall, fEmaSmallSlow, index, _histSmall, smallHistDraw)
            end

            if (fEmaUp ~= nil and #upPrice > 12) then
                _rpmUp[index] = RPMTFUpTransform(#upPrice, upPrice);
                if (upDraw == 1) then
                    rpmUp = _rpmUp[index];
                    emaRpmUp = fEmaUp(index)[index];
                end
                hUpUp, hUpDw = calcHist(fEmaUp, fEmaUpSlow, index, _hist, upHistDraw);
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
        return hUpUp, hUpDw, hSmallUp, hSmallDw, hMidleUp, hMidleDw,
               zero_line, rpmMidle, rpmUp, emaRpmMidle, emaRpmUp, rpmSmall, emaRpmSmall
    end
end

function _G.Init()
    PlotLines = Algo(_G.Settings)
    return 13
end

function _G.OnChangeSettings()
    _G.Init()
end

function _G.OnCalculate(index)
    return PlotLines(index)
end
