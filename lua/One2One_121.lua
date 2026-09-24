--[[
	One2One (121) harmonic pattern indicator for QUIK
	Based on ZigZag from smartZZ (nick-nh/qlua)

	Install (??? ????? ? ???? ?????):
	  One2One_121.lua      -> QuikFinam\LuaIndicators\
	  one2oneLib.lua       -> QuikFinam\LuaIndicators\

	??? (Log_Enable=1):
	  QuikFinam\LuaIndicators\logs\One2One_121.log
]]

_G.load = _G.loadfile or _G.load
local libPath = _G.getWorkingFolder() .. "\\LuaIndicators\\one2oneLib.lua"
local libFn = load(libPath)
if libFn == nil then
	message("One2One_121: ?? ?????? " .. libPath)
end
local o2o = libFn and libFn() or {}

local SetValue       = _G.SetValue
local RGB            = _G.RGB
local TYPE_LINE      = _G.TYPE_LINE
local TYPE_DASH      = _G.TYPE_DASH or TYPE_LINE
local TYPE_POINT     = _G.TYPE_POINT
local AddLabel       = _G.AddLabel
local DelAllLabels   = _G.DelAllLabels
local DelLabel       = _G.DelLabel
local SetLabelParams = _G.SetLabelParams
local CandleExist    = _G.CandleExist
local Size           = _G.Size
local message        = _G.message

local LOG_FILE_NAME  = "One2One_121.log"
local logEnabled     = false
local logVerbose     = false
local logFile        = nil
local logOpened      = false
local logPath        = ""

local LINE_ZZ        = 1
local LINE_PATTERN   = 2
local LINE_PRZ50     = 3
local LINE_PRZ618    = 4
local LINE_PRZ786    = 5
local LINE_STOP      = 6
local LINE_TP1       = 7
local LINE_TP2       = 8
local LINE_TP3       = 9

local min_price_step = 1
local scale          = 0
local zzEngine       = nil
local lineIndex      = {}
local lastAlertKey   = ""
local lastDrawLogKey = ""
local AddedLabels    = {}
local zzLabelIds     = {}
local zzLabelCount   = 0
local extraLabelIds  = {}
local extraLabelCount = 0
local chartIdWarned  = false

Settings = {
	Name = "*One2One_121",
	Depth = 12,
	Deviation = 5,
	Backstep = 3,
	showZZ = 1,
	showZZLabel = 1,
	ratioTolerance = 0,
	symmetryTolerance = 999,
	showEmerging = 1,
	showHistory = 0,
	historyDepth = 3,
	showLabel = 1,
	showPrz = 1,
	showStop = 1,
	showTp = 1,
	przExtendBars = 5,
	enableAlert = 0,
	Log_Enable = 1,
	Log_Verbose = 1,
	LabelShift = 8,
	ChartId = "",
	labelFontHeight = 11,
	line = {
		{
			Name = "ZIGZAG",
			Color = RGB(128, 128, 128),
			Type = TYPE_LINE,
			Width = 1,
		},
		{
			Name = "One2One",
			Color = RGB(0, 128, 255),
			Type = TYPE_LINE,
			Width = 2,
		},
		{
			Name = "PRZ 50%",
			Color = RGB(0, 200, 100),
			Type = TYPE_DASH,
			Width = 1,
		},
		{
			Name = "PRZ 61.8%",
			Color = RGB(0, 160, 80),
			Type = TYPE_DASH,
			Width = 1,
		},
		{
			Name = "PRZ 78.6%",
			Color = RGB(255, 140, 0),
			Type = TYPE_DASH,
			Width = 1,
		},
		{
			Name = "Stop X",
			Color = RGB(255, 64, 64),
			Type = TYPE_DASH,
			Width = 1,
		},
		{
			Name = "TP1 23.6% D-C",
			Color = RGB(70, 170, 255),
			Type = TYPE_DASH,
			Width = 1,
		},
		{
			Name = "TP2 C",
			Color = RGB(230, 200, 40),
			Type = TYPE_DASH,
			Width = 1,
		},
		{
			Name = "TP3 127.2%",
			Color = RGB(180, 90, 220),
			Type = TYPE_DASH,
			Width = 1,
		},
	},
}

local function log_tostring(...)
	local n = select("#", ...)
	if n == 1 then
		return tostring(select(1, ...))
	end
	local parts = {}
	for i = 1, n do
		parts[#parts + 1] = tostring(select(i, ...))
	end
	return table.concat(parts, " ")
end

local function fmtNum(v)
	if v == nil then
		return "nil"
	end
	return string.format("%.6f", v)
end

local function toYYYYMMDDHHMMSS(datetime)
	if type(datetime) ~= "table" then
		return ""
	end
	local function pad2(v)
		v = tostring(v)
		if #v == 1 then
			return "0" .. v
		end
		return v
	end
	return string.format(
		"%04d.%02d.%02d %02d:%02d:%02d",
		datetime.year or 0,
		datetime.month or 0,
		datetime.day or 0,
		datetime.hour or 0,
		datetime.min or 0,
		datetime.sec or 0
	)
end

local function formatBarIdx(barIndex)
	if barIndex == nil then
		return "?"
	end
	if CandleExist(barIndex) then
		return tostring(barIndex) .. "(" .. toYYYYMMDDHHMMSS(T(barIndex)) .. ")"
	end
	return tostring(barIndex)
end

local function o2oLog(...)
	if not logEnabled or logFile == nil then
		return
	end
	logFile:write(os.date("%Y-%m-%d %H:%M:%S") .. " " .. log_tostring(...) .. "\n")
	logFile:flush()
end

local function initLog(settings)
	logEnabled = true
	logVerbose = true
	if not logEnabled then
		return
	end
	if logFile ~= nil then
		logFile:close()
		logFile = nil
		logOpened = false
	end
	local logsDirPath = _G.getWorkingFolder() .. "\\LuaIndicators\\logs"
	local probe = io.open(logsDirPath .. "\\._dir", "a")
	if probe ~= nil then
		probe:close()
	else
		os.execute('mkdir "' .. logsDirPath .. '" >nul 2>&1')
	end
	logPath = logsDirPath .. "\\" .. LOG_FILE_NAME
	logFile = io.open(logPath, "w")
	if logFile == nil then
		return
	end
	logOpened = true
	o2oLog("=== One2One_121 log session ===")
	o2oLog("log file:", logPath)
	o2oLog(
		"Depth=", settings.Depth,
		"Deviation=", settings.Deviation,
		"Backstep=", settings.Backstep,
		"ratioTolerance=", settings.ratioTolerance,
		"symmetryTolerance=", settings.symmetryTolerance,
		"showZZ=", settings.showZZ,
		"showZZLabel=", settings.showZZLabel,
		"showEmerging=", settings.showEmerging,
		"showHistory=", settings.showHistory,
		"Log_Verbose=", settings.Log_Verbose or 0
	)
end

local function closeLog()
	if logFile ~= nil then
		o2oLog("=== log closed ===")
		logFile:close()
		logFile = nil
		logOpened = false
	end
end

local function logZZLevels(zzLevels, tag)
	o2oLog(tag, "zz peaks=", #zzLevels)
	if not logVerbose then
		return
	end
	local fromIdx = math.max(1, #zzLevels - 14)
	for i = fromIdx, #zzLevels do
		local pt = zzLevels[i]
		o2oLog("  peak", i, "bar=", formatBarIdx(pt.index), "val=", fmtNum(pt.val))
	end
end

local function logDiagnosis(tag, d)
	o2oLog(
		tag,
		"XA=", fmtNum(d.XA), "AB=", fmtNum(d.AB), "BC=", fmtNum(d.BC),
		"XC=", fmtNum(d.XC), "CD=", fmtNum(d.CD),
		"AB/XA=", d.abRatio and string.format("%.3f", d.abRatio) or "nil",
		"win=[", d.abMin and string.format("%.3f..%.3f", d.abMin, d.abMax) or "?", "]",
		"CD/XC=", d.cdRatio and string.format("%.3f", d.cdRatio) or "nil",
		"win=[", d.cdMin and string.format("%.3f..%.3f", d.cdMin, d.cdMax) or "?", "]",
		"sym=", d.symmetry and string.format("%.1f%%", d.symmetry * 100) or "nil",
		"lim=", d.symTolPct and string.format("%.0f%%", d.symTolPct) or "?",
		"dir=", d.direction or "nil",
		d.ok and "OK" or ("FAIL " .. (d.reason or ""))
	)
end

local function logXabcd(prefix, pts)
	o2oLog(
		prefix,
		"X=", formatBarIdx(pts.X.index), fmtNum(pts.X.val),
		"A=", formatBarIdx(pts.A.index), fmtNum(pts.A.val),
		"B=", formatBarIdx(pts.B.index), fmtNum(pts.B.val),
		"C=", formatBarIdx(pts.C.index), fmtNum(pts.C.val),
		"D=", formatBarIdx(pts.D.index), fmtNum(pts.D.val)
	)
end

local function logPatternScan(zzLevels, opts)
	local count = #zzLevels
	if count < 5 then
		o2oLog("SCAN skip: need >=5 peaks, have", count)
		return
	end
	if not logVerbose then
		return
	end

	local scanFrom = count
	local scanTo = math.max(5, count - 9)
	local nOk, nFail = 0, 0
	for endIdx = scanFrom, scanTo, -1 do
		local pX = zzLevels[endIdx - 4]["val"]
		local pA = zzLevels[endIdx - 3]["val"]
		local pB = zzLevels[endIdx - 2]["val"]
		local pC = zzLevels[endIdx - 1]["val"]
		local pD = zzLevels[endIdx]["val"]
		local d = o2o.diagnoseOne2One(pX, pA, pB, pC, pD, opts)
		local dBar = formatBarIdx(zzLevels[endIdx]["index"])
		if d.ok then
			nOk = nOk + 1
			o2oLog("MATCH D=", dBar, d.direction,
				"AB=", string.format("%.1f%%", d.abRatio * 100),
				"CD=", string.format("%.1f%%", d.cdRatio * 100),
				"sym=", string.format("%.1f%%", d.symmetry * 100),
				"peaksBack=", count - endIdx)
			logDiagnosis("  calc", d)
		else
			nFail = nFail + 1
			o2oLog("REJECT D=", dBar, d.reason,
				"X=", fmtNum(pX), "A=", fmtNum(pA), "B=", fmtNum(pB),
				"C=", fmtNum(pC), "D=", fmtNum(pD))
			logDiagnosis("  calc", d)
		end
	end
	o2oLog("SCAN last10: ok=", nOk, "fail=", nFail, "zzPeaks=", count)
end

local function logEmergingScan(zzLevels, settings)
	local count = #zzLevels
	if count < 4 then
		return
	end
	local pX = zzLevels[count - 3]["val"]
	local pA = zzLevels[count - 2]["val"]
	local pB = zzLevels[count - 1]["val"]
	local pC = zzLevels[count]["val"]
	local d = o2o.diagnoseEmerging(pX, pA, pB, pC, settings)
	if d.ok then
		o2oLog(
			"EMERGING C=", formatBarIdx(zzLevels[count]["index"]),
			d.direction,
			"AB=", string.format("%.1f%%", d.abRatio * 100)
		)
		o2oLog(
			"  pts X=", formatBarIdx(zzLevels[count - 3]["index"]), fmtNum(pX),
			"A=", formatBarIdx(zzLevels[count - 2]["index"]), fmtNum(pA),
			"B=", formatBarIdx(zzLevels[count - 1]["index"]), fmtNum(pB),
			"C=", formatBarIdx(zzLevels[count]["index"]), fmtNum(pC)
		)
		o2oLog("  calc XA=", fmtNum(d.XA), "AB=", fmtNum(d.AB),
			"AB/XA=", string.format("%.3f", d.abRatio),
			"win=[", string.format("%.3f..%.3f", d.abMin, d.abMax), "]")
		if d.prz then
			o2oLog("  PRZ50=", fmtNum(d.prz[0.5]),
				"PRZ618=", fmtNum(d.prz[0.618]),
				"PRZ786=", fmtNum(d.prz[0.786]))
		end
	elseif logVerbose then
		o2oLog("EMERGING reject:", d.reason,
			"X=", fmtNum(pX), "A=", fmtNum(pA), "B=", fmtNum(pB), "C=", fmtNum(pC))
	end
end

local function logDrawOutcome(index, zzLevels, patterns, settings, opts)
	if #patterns > 0 then
		local pattern = patterns[1]
		local info = pattern.info
		local pts = pattern.points
		local vals = pattern.values
		local key = string.format(
			"hit|%s|%s|%.3f|%.3f",
			tostring(info.direction),
			tostring(pts.D.index),
			info.abRatio or 0,
			info.cdRatio or 0
		)
		if key == lastDrawLogKey then
			return
		end
		lastDrawLogKey = key
		local d = o2o.diagnoseOne2One(vals.pX, vals.pA, vals.pB, vals.pC, vals.pD, opts)
		local prz = o2o.calcPrzLevels(vals.pX, vals.pC, o2o.PRZ_RATIOS)
		local przDraw = o2o.filterCompletedPrz and o2o.filterCompletedPrz(prz, info.direction, vals.pD) or prz
		local stopLvl = o2o.calcStopLevel(vals.pX, vals.pC, scale)
		local tp = o2o.calcTpLevels and o2o.calcTpLevels(vals.pX, vals.pC, vals.pD) or {}
		o2oLog(
			"DRAW-HIT calcBar=", formatBarIdx(index),
			"zzPeaks=", #zzLevels,
			"endIdx=", pattern.endIdx or "?",
			"peaksBack=", pattern.peaksBack or "?",
			info.direction,
			"AB=", string.format("%.1f%%", (info.abRatio or 0) * 100),
			"CD=", string.format("%.1f%%", (info.cdRatio or 0) * 100),
			"sym=", string.format("%.1f%%", (info.symmetry or 0) * 100)
		)
		logXabcd("  pts", pts)
		logDiagnosis("  calc", d)
		o2oLog(
			"  PRZ50=", fmtNum(prz[0.5]), przDraw[0.5] and "on" or "hide",
			"PRZ618=", fmtNum(prz[0.618]), przDraw[0.618] and "on" or "hide",
			"PRZ786=", fmtNum(prz[0.786]), przDraw[0.786] and "on" or "hide",
			"stop=", fmtNum(stopLvl),
			"TP1=", fmtNum(tp.tp1),
			"TP2=", fmtNum(tp.tp2),
			"TP3=", fmtNum(tp.tp3)
		)
		if (pattern.peaksBack or 0) >= 10 then
			o2oLog("  note: match is outside last 10 SCAN windows")
		end
		return
	end

	if settings.showEmerging == 1 then
		local count = #zzLevels
		if count >= 4 then
			local d = o2o.diagnoseEmerging(
				zzLevels[count - 3]["val"],
				zzLevels[count - 2]["val"],
				zzLevels[count - 1]["val"],
				zzLevels[count]["val"],
				settings
			)
			local key = d.ok
				and ("em|" .. tostring(zzLevels[count]["index"]) .. "|" .. string.format("%.3f", d.abRatio or 0))
				or ("em-no|" .. tostring(zzLevels[count]["index"]) .. "|" .. tostring(d.reason))
			if key == lastDrawLogKey then
				return
			end
			lastDrawLogKey = key
		end
		logEmergingScan(zzLevels, settings)
		return
	end

	local key = "none|" .. tostring(index)
	if key == lastDrawLogKey then
		return
	end
	lastDrawLogKey = key
	o2oLog("DRAW nothing: no pattern, emerging off")
end

local function clearLine(lineNum, index)
	if lineIndex[lineNum] ~= nil and lineIndex[lineNum]["index"] ~= nil then
		SetValue(lineIndex[lineNum]["index"], lineNum, nil)
	end
	SetValue(index - 1, lineNum, nil)
	lineIndex[lineNum] = { index = index - 1, val = nil }
end

local function setLineAt(lineNum, barIndex, value)
	SetValue(barIndex, lineNum, value)
	lineIndex[lineNum] = { index = barIndex, val = value }
end

local function drawSegment(lineNum, fromBar, toBar, fromVal, toVal)
	if fromVal == nil or toVal == nil then
		return
	end
	local lo = math.min(fromBar, toBar)
	local hi = math.max(fromBar, toBar)
	if lo == hi then
		setLineAt(lineNum, lo, fromVal)
		return
	end
	local span = hi - lo
	for b = lo, hi do
		if CandleExist(b) then
			local t = (b - lo) / span
			SetValue(b, lineNum, fromVal + (toVal - fromVal) * t)
		end
	end
	lineIndex[lineNum] = { index = hi, val = toVal }
end

local function drawZZLine(zzLevels, lineNum)
	if #zzLevels < 2 then
		return
	end
	for i = 2, #zzLevels do
		local p1 = zzLevels[i - 1]
		local p2 = zzLevels[i]
		drawSegment(lineNum, p1.index, p2.index, p1.val, p2.val)
	end
end

local function drawHorizontalRange(lineNum, fromBar, toBar, value)
	if value == nil then
		return
	end
	local lo = math.min(fromBar, toBar)
	local hi = math.max(fromBar, toBar)
	for b = lo, hi do
		if CandleExist(b) then
			SetValue(b, lineNum, value)
		end
	end
	lineIndex[lineNum] = { index = hi, val = value }
end

local function clearHorizontalRange(lineNum, fromBar, toBar)
	if fromBar == nil or toBar == nil then
		return
	end
	local lo = math.min(fromBar, toBar)
	local hi = math.max(fromBar, toBar)
	for b = lo, hi do
		if CandleExist(b) then
			SetValue(b, lineNum, nil)
		end
	end
	lineIndex[lineNum] = { index = hi, val = nil }
end

local function przEndBar(anchorBar, index, settings)
	local extend = tonumber(settings.przExtendBars) or 5
	local toBar = (anchorBar or index) + extend
	if toBar > index then
		toBar = index
	end
	if toBar < 1 then
		toBar = 1
	end
	return toBar
end

local function drawTpLines(fromBar, toBar, pX, pC, pD, index, settings)
	if settings.showTp ~= 1 or o2o.calcTpLevels == nil then
		return
	end
	local tp = o2o.calcTpLevels(pX, pC, pD)
	clearHorizontalRange(LINE_TP1, fromBar, index)
	clearHorizontalRange(LINE_TP2, fromBar, index)
	clearHorizontalRange(LINE_TP3, fromBar, index)
	drawHorizontalRange(LINE_TP1, fromBar, toBar, o2o.round(tp.tp1, scale))
	drawHorizontalRange(LINE_TP2, fromBar, toBar, o2o.round(tp.tp2, scale))
	drawHorizontalRange(LINE_TP3, fromBar, toBar, o2o.round(tp.tp3, scale))
end

local function getCandleProp(index)
	if CandleExist(index) then
		local dt = T(index)
		return (((dt.year + dt.month / 100) * 100) + dt.day / 100) * 100,
			((dt.hour + dt.min / 100) * 100) * 100
	end
	return nil, nil
end

local function resetChartLabels()
	if Settings.ChartId ~= "" then
		DelAllLabels(Settings.ChartId)
	end
	AddedLabels = {}
	zzLabelIds = {}
	zzLabelCount = 0
	extraLabelIds = {}
	extraLabelCount = 0
end

local function isLastBar(index)
	return Size ~= nil and index >= Size()
end

local function peakIsHigh(zzLevels, i)
	if #zzLevels < 2 then
		return true
	end
	if i <= 1 then
		return zzLevels[1]["val"] > zzLevels[2]["val"]
	end
	return zzLevels[i]["val"] > zzLevels[i - 1]["val"]
end

local function upsertLabel(chartId, store, slot, barIndex, yValue, text, colorRgb, hint)
	if chartId == "" or barIndex == nil or text == nil or text == "" then
		return
	end
	local dateVal, timeVal = getCandleProp(barIndex)
	if dateVal == nil then
		return
	end
	local label = {
		TEXT = text,
		IMAGE_PATH = "",
		ALIGNMENT = "LEFT",
		YVALUE = yValue,
		DATE = dateVal,
		TIME = timeVal,
		R = colorRgb[1],
		G = colorRgb[2],
		B = colorRgb[3],
		TRANSPARENCY = 0,
		TRANSPARENT_BACKGROUND = 1,
		FONT_FACE_NAME = "Arial",
		FONT_HEIGHT = Settings.labelFontHeight or 11,
		HINT = hint or text,
	}
	local id = store[slot]
	if id ~= nil and id ~= -1 then
		SetLabelParams(chartId, id, label)
	else
		id = AddLabel(chartId, label)
		if id ~= nil and id ~= -1 then
			store[slot] = id
			table.insert(AddedLabels, id)
		end
	end
end

local function trimLabels(chartId, store, usedCount, prevCount)
	if prevCount == nil then
		prevCount = 0
	end
	for i = usedCount + 1, prevCount do
		if store[i] ~= nil then
			if chartId ~= "" and DelLabel ~= nil then
				DelLabel(chartId, store[i])
			end
			store[i] = nil
		end
	end
	return usedCount
end

local function roleColor(roleDir, emerging)
	if emerging then
		return { 200, 160, 0 }
	end
	if roleDir == "bull" then
		return { 0, 180, 80 }
	end
	if roleDir == "bear" then
		return { 220, 80, 80 }
	end
	return { 0, 128, 255 }
end

local function refreshChartLabels(index, zzLevels, patterns, emergingInfo, settings)
	local chartId = settings.ChartId or ""
	if chartId == "" then
		if not chartIdWarned and (settings.showZZLabel == 1 or settings.showLabel == 1) then
			chartIdWarned = true
			message("One2One_121: set ChartId to the chart identifier")
		end
		return
	end
	if not isLastBar(index) then
		return
	end

	local roles = {}
	local roleDir = nil
	local emerging = emergingInfo ~= nil
	if patterns ~= nil and #patterns > 0 then
		local pts = patterns[1].points
		roles[pts.X.index] = "X"
		roles[pts.A.index] = "A"
		roles[pts.B.index] = "B"
		roles[pts.C.index] = "C"
		roles[pts.D.index] = "D"
		roleDir = patterns[1].info.direction
	elseif emerging and #zzLevels >= 4 then
		roles[zzLevels[#zzLevels - 3]["index"]] = "X"
		roles[zzLevels[#zzLevels - 2]["index"]] = "A"
		roles[zzLevels[#zzLevels - 1]["index"]] = "B"
		roles[zzLevels[#zzLevels]["index"]] = "C"
		roleDir = emergingInfo.direction
	end

	if settings.showZZLabel == 1 then
		local used = 0
		for i = 1, #zzLevels do
			local pt = zzLevels[i]
			local isHigh = peakIsHigh(zzLevels, i)
			local role = roles[pt["index"]]
			local text = role or ((isHigh and "H" or "L") .. tostring(i))
			local color = role ~= nil and roleColor(roleDir, emerging) or { 140, 140, 140 }
			local yOff = min_price_step * 4
			local yValue = pt["val"] + (isHigh and yOff or -yOff)
			used = used + 1
			upsertLabel(
				chartId,
				zzLabelIds,
				used,
				pt["index"],
				yValue,
				text,
				color,
				text .. " " .. tostring(pt["val"])
			)
		end
		zzLabelCount = trimLabels(chartId, zzLabelIds, used, zzLabelCount)
	else
		zzLabelCount = trimLabels(chartId, zzLabelIds, 0, zzLabelCount)
	end

	local extraUsed = 0
	if settings.showLabel == 1 then
		if patterns ~= nil and #patterns > 0 then
			for i = 1, #patterns do
				local pattern = patterns[i]
				local pts = pattern.points
				local vals = pattern.values
				local info = pattern.info
				local labelBar = math.max(1, pts.D.index - (settings.LabelShift or 0))
				local labelY = vals.pD
				if info.direction == "bull" then
					labelY = labelY - min_price_step * 2
				else
					labelY = labelY + min_price_step * 2
				end
				extraUsed = extraUsed + 1
				upsertLabel(
					chartId,
					extraLabelIds,
					extraUsed,
					labelBar,
					labelY,
					o2o.formatPatternLabel(info, false),
					roleColor(info.direction, false)
				)
			end
		elseif emerging then
			local count = #zzLevels
			local labelBar = math.max(1, zzLevels[count]["index"] - (settings.LabelShift or 0))
			extraUsed = extraUsed + 1
			upsertLabel(
				chartId,
				extraLabelIds,
				extraUsed,
				labelBar,
				emergingInfo.prz[0.618],
				o2o.formatPatternLabel(emergingInfo, true),
				roleColor(emergingInfo.direction, true)
			)
		end
	end
	extraLabelCount = trimLabels(chartId, extraLabelIds, extraUsed, extraLabelCount)
end

local function drawPattern(pattern, index, settings, drawLines)
	local pts = pattern.points
	local vals = pattern.values
	local info = pattern.info

	if drawLines then
		clearLine(LINE_PATTERN, index)
		drawSegment(LINE_PATTERN, pts.X.index, pts.A.index, vals.pX, vals.pA)
		drawSegment(LINE_PATTERN, pts.A.index, pts.B.index, vals.pA, vals.pB)
		drawSegment(LINE_PATTERN, pts.B.index, pts.C.index, vals.pB, vals.pC)
		drawSegment(LINE_PATTERN, pts.C.index, pts.D.index, vals.pC, vals.pD)

		if settings.showPrz == 1 then
			local prz = o2o.calcPrzLevels(vals.pX, vals.pC, o2o.PRZ_RATIOS)
			if o2o.filterCompletedPrz then
				prz = o2o.filterCompletedPrz(prz, info.direction, vals.pD)
			end
			local fromBar = pts.C.index
			local toBar = przEndBar(pts.D.index, index, settings)
			clearHorizontalRange(LINE_PRZ50, fromBar, index)
			clearHorizontalRange(LINE_PRZ618, fromBar, index)
			clearHorizontalRange(LINE_PRZ786, fromBar, index)
			if prz[0.5] ~= nil then
				drawHorizontalRange(LINE_PRZ50, fromBar, toBar, o2o.round(prz[0.5], scale))
			end
			if prz[0.618] ~= nil then
				drawHorizontalRange(LINE_PRZ618, fromBar, toBar, o2o.round(prz[0.618], scale))
			end
			if prz[0.786] ~= nil then
				drawHorizontalRange(LINE_PRZ786, fromBar, toBar, o2o.round(prz[0.786], scale))
			end
		end

		if settings.showStop == 1 then
			local fromBar = pts.C.index
			local toBar = przEndBar(pts.D.index, index, settings)
			clearHorizontalRange(LINE_STOP, fromBar, index)
			local stopLvl = o2o.calcStopLevel(vals.pX, vals.pC, scale)
			drawHorizontalRange(LINE_STOP, fromBar, toBar, stopLvl)
		end

		local fromBar = pts.C.index
		local toBar = przEndBar(pts.D.index, index, settings)
		drawTpLines(fromBar, toBar, vals.pX, vals.pC, vals.pD, index, settings)
	end

	return string.format(
		"%s_%d_%s",
		info.direction,
		pts.D.index,
		o2o.formatPatternLabel(info, false)
	)
end

local function drawEmerging(zzLevels, index, settings)
	if settings.showEmerging ~= 1 then
		return
	end
	local count = #zzLevels
	if count < 4 then
		return
	end

	local pX = zzLevels[count - 3]["val"]
	local pA = zzLevels[count - 2]["val"]
	local pB = zzLevels[count - 1]["val"]
	local pC = zzLevels[count]["val"]
	local ok, info = o2o.checkOne2OneEmerging(pX, pA, pB, pC, settings)
	if not ok then
		return nil
	end

	clearLine(LINE_PATTERN, index)
	drawSegment(LINE_PATTERN, zzLevels[count - 3]["index"], zzLevels[count - 2]["index"], pX, pA)
	drawSegment(LINE_PATTERN, zzLevels[count - 2]["index"], zzLevels[count - 1]["index"], pA, pB)
	drawSegment(LINE_PATTERN, zzLevels[count - 1]["index"], zzLevels[count]["index"], pB, pC)

	if settings.showPrz == 1 then
		local fromBar = zzLevels[count]["index"]
		clearHorizontalRange(LINE_PRZ50, fromBar, index)
		clearHorizontalRange(LINE_PRZ618, fromBar, index)
		clearHorizontalRange(LINE_PRZ786, fromBar, index)
		drawHorizontalRange(LINE_PRZ50, fromBar, index, o2o.round(info.prz[0.5], scale))
		drawHorizontalRange(LINE_PRZ618, fromBar, index, o2o.round(info.prz[0.618], scale))
		drawHorizontalRange(LINE_PRZ786, fromBar, index, o2o.round(info.prz[0.786], scale))
	end

	local fromBar = zzLevels[count]["index"]
	local pD = nil
	if CandleExist(index) and _G.C then
		pD = _G.C(index)
	end
	drawTpLines(fromBar, index, pX, pC, pD, index, settings)

	return info
end

function Init()
	for i = 1, #Settings.line do
		lineIndex[i] = { index = 1, val = nil }
	end
	zzEngine = o2o.createZZEngine(min_price_step)
	return #Settings.line
end

function OnDestroy()
	closeLog()
	resetChartLabels()
end

function OnCalculate(index)
	if index == 1 then
		local ds = getDataSourceInfo()
		min_price_step = tonumber(getParamEx(ds.class_code, ds.sec_code, "SEC_PRICE_STEP").param_value) or 1
		scale = getSecurityInfo(ds.class_code, ds.sec_code).scale
		zzEngine = o2o.createZZEngine(min_price_step)
		initLog(Settings)
		if logEnabled then
			o2oLog(
				"INSTR", ds.class_code, ds.sec_code,
				"interval=", ds.interval,
				"price_step=", min_price_step,
				"scale=", scale,
				"bars=", Size()
			)
		end
		resetChartLabels()
		lastAlertKey = ""
		lastDrawLogKey = ""
	end

	local zzLevels, ready = zzEngine(
		index,
		Settings.Depth,
		Settings.Deviation,
		Settings.Backstep,
		nil
	)

	if not ready or #zzLevels < 4 then
		return nil
	end

	for i = LINE_PATTERN, LINE_TP3 do
		clearLine(i, index)
	end

	if Settings.showZZ == 1 then
		clearLine(LINE_ZZ, index)
		drawZZLine(zzLevels, LINE_ZZ)
	end

	local opts = {
		ratioTolerance = Settings.ratioTolerance,
		symmetryTolerance = Settings.symmetryTolerance,
		historyDepth = Settings.showHistory == 1 and Settings.historyDepth or 1,
	}

	if logEnabled then
		logZZLevels(zzLevels, "CALC bar=" .. formatBarIdx(index))
		logPatternScan(zzLevels, opts)
	end

	local patterns = o2o.scanPatterns(zzLevels, opts)
	local alertKey = ""
	local emergingInfo = nil

	if logEnabled then
		logDrawOutcome(index, zzLevels, patterns, Settings, opts)
	end

	if #patterns > 0 then
		for i = 1, #patterns do
			local key = drawPattern(patterns[i], index, Settings, i == 1)
			if i == 1 then
				alertKey = key
			end
		end
	elseif Settings.showEmerging == 1 then
		emergingInfo = drawEmerging(zzLevels, index, Settings)
	end

	if Settings.enableAlert == 1 and alertKey ~= "" and alertKey ~= lastAlertKey then
		message("One2One: " .. o2o.formatPatternLabel(patterns[#patterns].info, false))
		lastAlertKey = alertKey
	end

	refreshChartLabels(index, zzLevels, patterns, emergingInfo, Settings)

	return nil
end
