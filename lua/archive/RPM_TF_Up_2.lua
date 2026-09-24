
_G.load   = _G.loadfile or _G.load
local maLib = load(_G.getWorkingFolder().."\\Luaindicators\\maLib.lua")()

local logFile = nil
-- logFile = io.open(_G.getWorkingFolder().."\\LuaIndicators\\RPM_TF_Up_2.txt", "w")

local message               = _G['message']
local number                = _G['number']
local RGB                   = _G['RGB']
local TYPE_LINE             = _G['TYPE_LINE']
local TYPE_HISTOGRAM        = _G['TYPE_HISTOGRAM']
local isDark                = _G.isDarkTheme()
local line_color            = isDark and RGB(240, 240, 240) or RGB(0, 0, 0)
local os_time	            = os.time

_G.Settings= {
    Name 		        = "*RPM_TF_Up_2",
    Midle               = "Mn15",
    PeriodMidle         = 20,
    Up                  = "Mn30",
    PeriodUp            = 20,
    PeriodUpSlow        = 40,
    line = {
        {
            Name  = 'UP',
            Color = RGB(186, 248, 118),
            Type  = TYPE_HISTOGRAM,
            Width = 2
        },
        {
            Name  = 'DW',
            Color = RGB(255, 209, 164),
            Type  = TYPE_HISTOGRAM,
            Width = 2
        },
        {
            Name = "zero_line",
            Color = RGB(51, 207, 255),
            Type  = TYPE_LINE,
            Width = 2
        },
        {
            Name = "rpmMidle",
            Color = RGB(255, 128, 128),
            Type  = TYPE_LINE,
            Width = 2
        },
        {
            Name = "rpmUp",
            Color = RGB(0, 191, 0),
            Type  = TYPE_LINE,
            Width = 2
        },
        {
            Name = "emaMidle",
            Color = RGB(255, 0, 255),
            Type  = TYPE_LINE,
            Width = 2
        },
        {
            Name = "emaUp",
            Color = RGB(0, 128, 128),
            Type  = TYPE_LINE,
            Width = 2
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

-- занулить минуты, секунды и т.д.
local function cleanMinSecMs(dt)
    if dt then
        -- myLog('dt: '..toYYYYMMDDHHMMSS(dt));
        -- dt.min = 0;
        dt.sec = 0;
        -- myLog('dt new value: '..toYYYYMMDDHHMMSS(dt));
    end
    return dt;
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
        if (tf == "H1") then
            setFirstBar = true;
        end
        if (tf == "H2" and crT.hour % 2 == 0) then
            setFirstBar = true;
        end
        if (tf == "H3" and crT.hour % 3 == 0) then
            setFirstBar = true;
        end
        if (tf == "H4" and crT.hour % 4 == 0) then
            setFirstBar = true;
        end
        if (tf == "H6" and crT.hour % 6 == 0) then
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
            tfds[1] = { O=O(index); H=H(index); L=L(index); C=C(index); T=cleanMinSecMs(crT) }
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
        local tt = T(index);
        myLog('setPrice; tf:'..tf..' upT:'..toYYYYMMDDHHMMSS(upT)..' crT:'..toYYYYMMDDHHMMSS(crT));
        cleanMinSecMs(upT);
        cleanMinSecMs(crT);
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
        -- h1
        if (tf == "H1") then
            upTfSec = upTfSec + 1 * 60 - 1; -- в секундах
            if (upTfSec < crTfSec) then
                addNewBarInTfds = true;
            end
        end
        if (tf == "H2" and (newDay == true or tt.hour % 2 == 0)) then
            upTfSec = upTfSec + 1 * 60; -- в секундах
            if (upTfSec < crTfSec) then
                addNewBarInTfds = true;
            end
        end
        if (tf == "H3" and (newDay == true or tt.hour % 3 == 0)) then
            upTfSec = upTfSec + 1 * 60; -- в секундах
            if (upTfSec < crTfSec) then
                addNewBarInTfds = true;
            end
        end
        if (tf == "H4" and (newDay == true or tt.hour % 4 == 0)) then
            -- отсекание минутных баров
            upTfSec = upTfSec + 1 * 60; -- в секундах
            if (upTfSec < crTfSec) then
                addNewBarInTfds = true;
            end
        end
        if (tf == "H6" and (newDay == true or tt.hour % 6 == 0)) then
            upTfSec = upTfSec + 1 * 60; -- в секундах
            if (upTfSec < crTfSec) then
                addNewBarInTfds = true;
            end
        end
        if (tf == "Mn2" and (newHour == true or tt.min % 2 == 0)) then
            upTfSec = upTfSec + 1 * 60; -- в секундах
            if (upTfSec < crTfSec) then
                addNewBarInTfds = true;
            end
        end
        if (tf == "Mn3" and (newHour == true or tt.min % 3 == 0)) then
            upTfSec = upTfSec + 1 * 60; -- в секундах
            if (upTfSec < crTfSec) then
                addNewBarInTfds = true;
            end
        end
        if (tf == "Mn4" and (newHour == true or tt.min % 4 == 0)) then
            upTfSec = upTfSec + 1 * 60; -- в секундах
            if (upTfSec < crTfSec) then
                addNewBarInTfds = true;
            end
        end
        if (tf == "Mn5" and (newHour == true or tt.min % 5 == 0)) then
            upTfSec = upTfSec + 1 * 60; -- в секундах
            if (upTfSec < crTfSec) then
                addNewBarInTfds = true;
            end
        end
        if (tf == "Mn6" and (newHour == true or tt.min % 6 == 0)) then
            upTfSec = upTfSec + 1 * 60; -- в секундах
            if (upTfSec < crTfSec) then
                addNewBarInTfds = true;
            end
        end
        if (tf == "Mn10" and (newHour == true or tt.min % 10 == 0)) then
            upTfSec = upTfSec + 1 * 60; -- в секундах
            if (upTfSec < crTfSec) then
                addNewBarInTfds = true;
            end
        end
        if (tf == "Mn15" and (newHour == true or tt.min % 15 == 0)) then
            upTfSec = upTfSec + 1 * 60; -- в секундах
            if (upTfSec < crTfSec) then
                addNewBarInTfds = true;
            end
        end
        if (tf == "Mn20" and (newHour == true or tt.min % 20 == 0)) then
            upTfSec = upTfSec + 1 * 60; -- в секундах
            if (upTfSec < crTfSec) then
                addNewBarInTfds = true;
            end
        end
        if (tf == "Mn30" and (newHour == true or tt.min % 30 == 0)) then
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

local function Algo(Fsettings, ds)

    Fsettings               = (Fsettings or {})

    local midle             = Fsettings.Midle or "H4"
    local periodMidle       = Fsettings.PeriodMidle or 90
    local up                = Fsettings.Up or "D1"
    local periodUp          = Fsettings.PeriodUp or 180
    local periodUpSlow      = Fsettings.PeriodUpSlow or 240

    local fEmaMidle
    local fEmaUp
    local fEmaUpSlow

    error_log               = {}
    local midlePrice        = { O=number; H=number; L=number; C=number; T={} }
    local upPrice           = { O=number; H=number; L=number; C=number; T={} }

    local _rpmMidle         = {}
    local _rpmUp            = {}
    local _hist             = {}

    local zero_line
    local hUp
    local hDw
    local rpmMidle
    local rpmUp
    local emaRpmMidle
    local emaRpmUp

    return function (index)

        zero_line       = nil
        hUp             = nil
        hDw             = nil
        rpmMidle        = nil
        rpmUp           = nil
        emaRpmMidle     = nil
        emaRpmUp        = nil

        local status, res = pcall(function()

            if not maLib then
                myLog("not maLib = nil")
                return
            end

            myLog('tf:'..up..' обрабатывается бар '..#upPrice..'; tf:'..midle..' обрабатывается бар '..#midlePrice);

            if (#midlePrice == 0) then
                setPrice(midle, midlePrice, index, ds);
                if (#midlePrice == 1) then
                    fEmaMidle = maLib.new({method = 'EMA', period = periodMidle, data_type = 'Any'}, _rpmMidle);
                    myLog('tf:'..midle..' функция установлена');
                end
            else
                setPrice(midle, midlePrice, index, ds);
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
                rpmMidle = _rpmMidle[index];
                emaRpmMidle = fEmaMidle(index)[index];
            end

            if (fEmaUp ~= nil and #upPrice > 12) then
                _rpmUp[index] = RPMTFUpTransform(#upPrice, upPrice);
                rpmUp = _rpmUp[index];
                emaRpmUp = fEmaUp(index)[index];

                local hValue = (fEmaUp(index)[index] or 0) - (fEmaUpSlow(index)[index] or 0);
                _hist[index] = hValue * 5;
                if (_hist[index - 1] ~= nil) then
                    hUp = _hist[index] >  _hist[index - 1] and _hist[index] or nil;
                    hDw = _hist[index] <= _hist[index - 1] and _hist[index] or nil;
                end
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
        return hUp, hDw, zero_line, rpmMidle, rpmUp, emaRpmMidle, emaRpmUp
    end
end

function _G.Init()
    PlotLines = Algo(_G.Settings)
    return 7
end

function _G.OnChangeSettings()
    _G.Init()
end

function _G.OnCalculate(index)
    return PlotLines(index)
end
