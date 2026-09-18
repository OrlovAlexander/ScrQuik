
_G.load   = _G.loadfile or _G.load
local maLib = load(_G.getWorkingFolder().."\\Luaindicators\\maLib.lua")()

local logFile = nil
local LOG_PATH = nil

local message       = _G['message']
local RGB           = _G['RGB']
local TYPE_LINE     = _G['TYPE_LINE']
local isDark        = _G.isDarkTheme()
local os_time	    = os.time


_G.Settings= {
    Name 		        = "*RPM_TF_Current",
    Period              = 90,
    line = {
        {
            Name = "rpm",
            Color = RGB(39, 242, 7),
            Type  = TYPE_LINE,
            Width = 2
        },
        {
            Name = "ema",
            Color = RGB(240, 50, 50),
            Type  = TYPE_LINE,
            Width = 2
        },
        {
            Name = "zero_line",
            Color = RGB(51, 207, 255),
            Type  = TYPE_LINE,
            Width = 2
        }
    }
}


local PlotLines     = function(index) return index end
local error_log     = {}


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

local function closeLog()
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

local function logsDir()
    local dir = _G.getWorkingFolder().."\\LuaIndicators\\logs"
    os.execute('mkdir "'..dir..'" >nul 2>&1')
    return dir
end

local function reopenLog()
    closeLog()
    local tf = chartTfTag()
    LOG_PATH = logsDir().."\\RPM_TF_Current."..tf..".txt"
    logFile = io.open(LOG_PATH, "w")
    if logFile == nil then
        return
    end
    local classCode, secCode, interval, nBars = instrumentHeader()
    myLog("=== RPM_TF_Current log session ===")
    myLog("INSTR", classCode, secCode, "tf=", tf, "interval=", interval, "bars=", nBars)
end


local function Algo(Fsettings, ds)

    Fsettings               = (Fsettings or {})

    local period            = Fsettings.Period or 90

    error_log               = {}

    local fRpm
    local rpm
    local emaRpm
    local zero_line

    return function (index)

        rpm        = nil
        emaRpm     = nil
        zero_line  = nil

        local status, res = pcall(function()

            if not maLib then
                myLog("not maLib")
                return
            end

            if fRpm == nil or index == 1 then
                reopenLog()
                myLog("fRpm == nil or index == 1")
                fRpm = maLib.new({method = 'RPMTFC', period = period}, ds)
                return
            end

            myLog("pcall before fRpm", index)
            local _rpm, _emaRPM = fRpm(index)
            myLog("pcall after fRpm", index, _rpm[index], _emaRPM[index])

            if not _rpm or not _emaRPM then
                myLog("not _rpm or not _emaRPM")
                return
            end

            rpm        = _rpm[index]
            emaRpm     = _emaRPM[index]
            zero_line  = 0

            if not maLib.CheckIndex(index, ds) then
                myLog("not maLib.CheckIndex(index, ds)")
				return
			end

        end)
        if not status then
            if not error_log[tostring(res)] then
                error_log[tostring(res)] = true
                myLog(tostring(res))
                message(tostring(res))
            end
            myLog("not status")
            return nil
        end
        return rpm, emaRpm, zero_line
    end
end

function _G.Init()
    PlotLines = Algo(_G.Settings)
    return 3
end

function _G.OnChangeSettings()
    _G.Init()
end

function _G.OnStop()
    closeLog()
end

function _G.OnCalculate(index)
    return PlotLines(index)
end