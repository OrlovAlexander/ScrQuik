--[[
	One2One (121) harmonic pattern library for QUIK
	nick-h@yandex.ru / ScrQuik
]]

local M = {}

M.FIB_AB_MIN = 0.25
M.FIB_AB_MAX = 2.00
M.FIB_CD_MIN = 0.10
M.FIB_CD_MAX = 0.74
M.PRZ_RATIOS = {0.500, 0.618, 0.786}
M.TP1_RATIO = 0.236
M.TP3_RATIO = -0.272

function M.round(num, idp)
	if idp and num then
		local mult = 10 ^ (idp or 0)
		if num >= 0 then
			return math.floor(num * mult + 0.5) / mult
		end
		return math.ceil(num * mult - 0.5) / mult
	end
	return num
end

local function ratioInRange(value, minV, maxV, tol)
	return value >= (minV - tol) and value <= (maxV + tol)
end

function M.getDirection(pX, pA, pB, pC, pD)
	-- ZigZag alternates H/L. Bull = L-H-L-H-L (D is low): C > B, D < C.
	-- Bear = H-L-H-L-H (D is high): C < B, D > C.
	local bullish = (pA > pX and pB < pA and pC > pB and pD < pC)
	local bearish = (pA < pX and pB > pA and pC < pB and pD > pC)
	if bullish then
		return "bull"
	end
	if bearish then
		return "bear"
	end
	return nil
end

function M.getEmergingDirection(pX, pA, pB, pC)
	-- Forming 121 without D. Bull L-H-L-H, bear H-L-H-L.
	local bullish = (pA > pX and pB < pA and pC > pB)
	local bearish = (pA < pX and pB > pA and pC < pB)
	if bullish then
		return "bull"
	end
	if bearish then
		return "bear"
	end
	return nil
end

function M.diagnoseOne2One(pX, pA, pB, pC, pD, opts)
	opts = opts or {}
	local ratioTolPct = opts.ratioTolerance or 5
	local symTolPct = opts.symmetryTolerance or 15
	local tol = ratioTolPct / 100
	local symTol = symTolPct / 100
	local d = {
		XA = math.abs(pA - pX),
		AB = math.abs(pB - pA),
		BC = math.abs(pC - pB),
		XC = math.abs(pC - pX),
		CD = math.abs(pD - pC),
		abMin = M.FIB_AB_MIN - tol,
		abMax = M.FIB_AB_MAX + tol,
		cdMin = M.FIB_CD_MIN - tol,
		cdMax = M.FIB_CD_MAX + tol,
		symTolPct = symTolPct,
		direction = M.getDirection(pX, pA, pB, pC, pD),
	}
	if d.XA <= 0 or d.XC <= 0 or d.AB <= 0 or d.CD <= 0 then
		d.ok = false
		d.reason = "zero leg"
		return d
	end
	d.abRatio = d.AB / d.XA
	d.cdRatio = d.CD / d.XC
	d.symmetry = math.abs(d.AB - d.CD) / d.AB
	d.abOk = ratioInRange(d.abRatio, M.FIB_AB_MIN, M.FIB_AB_MAX, tol)
	d.cdOk = ratioInRange(d.cdRatio, M.FIB_CD_MIN, M.FIB_CD_MAX, tol)
	d.symOk = d.symmetry <= symTol
	d.dirOk = d.direction ~= nil
	if not d.abOk then
		d.ok = false
		d.reason = string.format(
			"AB/XA=%.3f outside [%.3f..%.3f] tol=%.0f%%",
			d.abRatio, d.abMin, d.abMax, ratioTolPct
		)
	elseif not d.cdOk then
		d.ok = false
		d.reason = string.format(
			"CD/XC=%.3f outside [%.3f..%.3f] tol=%.0f%%",
			d.cdRatio, d.cdMin, d.cdMax, ratioTolPct
		)
	elseif not d.symOk then
		d.ok = false
		d.reason = string.format("symmetry=%.1f%% > %.0f%%", d.symmetry * 100, symTolPct)
	elseif not d.dirOk then
		d.ok = false
		d.reason = "invalid zigzag structure"
	else
		d.ok = true
		d.reason = nil
	end
	return d
end

function M.explainOne2One(pX, pA, pB, pC, pD, opts)
	local d = M.diagnoseOne2One(pX, pA, pB, pC, pD, opts)
	if not d.ok then
		return false, nil, d.reason
	end
	return true, {
		direction = d.direction,
		abRatio = d.abRatio,
		cdRatio = d.cdRatio,
		symmetry = d.symmetry,
		XA = d.XA,
		AB = d.AB,
		BC = d.BC,
		XC = d.XC,
		CD = d.CD,
	}, nil
end

function M.checkOne2One(pX, pA, pB, pC, pD, opts)
	local ok, info = M.explainOne2One(pX, pA, pB, pC, pD, opts)
	return ok, info
end

function M.diagnoseEmerging(pX, pA, pB, pC, opts)
	opts = opts or {}
	local ratioTolPct = opts.ratioTolerance or 5
	local tol = ratioTolPct / 100
	local d = {
		XA = math.abs(pA - pX),
		AB = math.abs(pB - pA),
		BC = math.abs(pC - pB),
		XC = math.abs(pC - pX),
		abMin = M.FIB_AB_MIN - tol,
		abMax = M.FIB_AB_MAX + tol,
		direction = M.getEmergingDirection(pX, pA, pB, pC),
	}
	if d.XA <= 0 or d.AB <= 0 then
		d.ok = false
		d.reason = "zero leg"
		return d
	end
	d.abRatio = d.AB / d.XA
	d.abOk = ratioInRange(d.abRatio, M.FIB_AB_MIN, M.FIB_AB_MAX, tol)
	d.dirOk = d.direction ~= nil
	if not d.abOk then
		d.ok = false
		d.reason = string.format(
			"AB/XA=%.3f outside [%.3f..%.3f] tol=%.0f%%",
			d.abRatio, d.abMin, d.abMax, ratioTolPct
		)
	elseif not d.dirOk then
		d.ok = false
		d.reason = "invalid emerging structure"
	else
		d.ok = true
		d.reason = nil
		d.prz = M.calcPrzLevels(pX, pC, M.PRZ_RATIOS)
	end
	return d
end

function M.explainOne2OneEmerging(pX, pA, pB, pC, opts)
	local d = M.diagnoseEmerging(pX, pA, pB, pC, opts)
	if not d.ok then
		return false, nil, d.reason
	end
	return true, {
		direction = d.direction,
		abRatio = d.abRatio,
		prz = d.prz,
	}, nil
end

function M.checkOne2OneEmerging(pX, pA, pB, pC, opts)
	local ok, info = M.explainOne2OneEmerging(pX, pA, pB, pC, opts)
	return ok, info
end

function M.calcPrzLevels(pX, pC, ratios)
	local levels = {}
	for i = 1, #ratios do
		local ratio = ratios[i]
		levels[ratio] = pC + (pX - pC) * ratio
	end
	return levels
end

-- After D is printed, PRZ is the unfilled zone toward X.
-- Bull D is a low: PRZ is support, so only levels at/below D.
-- Bear D is a high: PRZ is resistance, so only levels at/above D.
-- Levels between C and D were already traded through and would sit
-- on the wrong side of price after the bounce.
function M.isPrzOnEntrySide(direction, pD, level)
	if direction == nil or pD == nil or level == nil then
		return true
	end
	if direction == "bull" then
		return level <= pD
	end
	if direction == "bear" then
		return level >= pD
	end
	return true
end

function M.filterCompletedPrz(prz, direction, pD)
	if prz == nil then
		return prz
	end
	local out = {}
	for ratio, level in pairs(prz) do
		if M.isPrzOnEntrySide(direction, pD, level) then
			out[ratio] = level
		end
	end
	return out
end

function M.calcStopLevel(pX, pC, scale)
	return M.round(pX, scale)
end

function M.calcTpLevels(pX, pC, pD)
	local xc = pX - pC
	local tp1
	if pD ~= nil then
		tp1 = pD + (pC - pD) * M.TP1_RATIO
	else
		tp1 = pC + xc * M.TP1_RATIO
	end
	return {
		tp1 = tp1,
		tp2 = pC,
		tp3 = pC + xc * M.TP3_RATIO,
	}
end

function M.formatPatternLabel(info, emerging)
	if info == nil then
		return ""
	end
	local dirText = info.direction == "bull" and "Bull" or "Bear"
	if emerging then
		return string.format(
			"%s (forming) AB=%.1f%%",
			dirText,
			(info.abRatio or 0) * 100
		)
	end
	return string.format(
		"%s AB=%.1f%% CD=%.1f%% sym=%.1f%%",
		dirText,
		(info.abRatio or 0) * 100,
		(info.cdRatio or 0) * 100,
		(info.symmetry or 0) * 100
	)
end

function M.createZZEngine(priceStep)
	local unpackFn = rawget(table, "unpack") or unpack
	local step = tonumber(priceStep) or 1

	local CC, CH, CL = {}, {}, {}
	local HighMapBuffer, LowMapBuffer = {}, {}
	local Peak = {}
	local ZZLevels = {}
	local lastindex = -1
	local lastlow, lasthigh = 0, 0

	local searchBoth, searchPeak, searchLawn = 0, 1, -1

	local function registerPeak(index, val, peakCount)
		peakCount = peakCount + 1
		Peak[index] = val
		local size = #ZZLevels + 1
		if peakCount <= 0 and #ZZLevels > 0 then
			ZZLevels[#ZZLevels + peakCount]["val"] = val
			ZZLevels[#ZZLevels + peakCount]["index"] = index
		else
			ZZLevels[size] = { val = val, index = index }
		end
		return peakCount
	end

	local function replaceLastPeak(index, val, peakCount)
		Peak[index] = val
		local size = #ZZLevels
		if peakCount <= 0 and #ZZLevels > 0 then
			ZZLevels[#ZZLevels + peakCount]["val"] = val
			ZZLevels[#ZZLevels + peakCount]["index"] = index
		elseif size > 0 then
			ZZLevels[size]["val"] = val
			ZZLevels[size]["index"] = index
		end
	end

	local function getPeak(index)
		local counter = 0
		for i = index, 1, -1 do
			if Peak[i] ~= nil then
				counter = counter + 1
				if counter == 3 then
					return i
				end
			end
		end
		return -1
	end

	return function(index, depth, deviation, backstep, setZZValue)
		if index == 1 then
			CC, CH, CL = {}, {}, {}
			HighMapBuffer, LowMapBuffer = {}, {}
			Peak = {}
			ZZLevels = {}
			lastindex = -1
			lastlow, lasthigh = 0, 0
			CC[index], CH[index], CL[index] = 0, 0, 0
			HighMapBuffer[index], LowMapBuffer[index] = 0, 0
			if setZZValue then
				setZZValue(index, nil)
			end
			return ZZLevels, false
		end

		CC[index] = CC[index - 1]
		CH[index] = CH[index - 1]
		CL[index] = CL[index - 1]

		if index < depth or not CandleExist(index) then
			HighMapBuffer[index] = HighMapBuffer[index - 1]
			LowMapBuffer[index] = LowMapBuffer[index - 1]
			Peak[index] = nil
			return ZZLevels, false
		end

		CC[index] = C(index)
		CH[index] = H(index)
		CL[index] = L(index)

		if index < Size() then
			HighMapBuffer[index] = HighMapBuffer[index - 1]
			LowMapBuffer[index] = LowMapBuffer[index - 1]
			Peak[index] = nil
			return ZZLevels, false
		end

		local sizeOfZZ = #ZZLevels
		local searchMode = searchBoth

		if index == lastindex and ZZLevels[sizeOfZZ] ~= nil then
			local lastZZ = ZZLevels[sizeOfZZ]["val"]
			local lastZZ_i = ZZLevels[sizeOfZZ]["index"]
			if LowMapBuffer[lastZZ_i] ~= 0 then
				searchMode = searchPeak
			elseif HighMapBuffer[lastZZ_i] ~= 0 then
				searchMode = searchLawn
			end
			if searchMode == searchPeak and L(index) < lastZZ then
				Peak[lastZZ_i] = nil
				LowMapBuffer[lastZZ_i] = 0
				LowMapBuffer[index] = L(index)
				if setZZValue then
					setZZValue(lastZZ_i, nil)
				end
				replaceLastPeak(index, L(index), 0)
			elseif searchMode == searchLawn and H(index) > lastZZ then
				Peak[lastZZ_i] = nil
				HighMapBuffer[lastZZ_i] = 0
				HighMapBuffer[index] = H(index)
				if setZZValue then
					setZZValue(lastZZ_i, nil)
				end
				replaceLastPeak(index, H(index), 0)
			end
		else
			if ZZLevels[sizeOfZZ] ~= nil and setZZValue then
				setZZValue(ZZLevels[sizeOfZZ]["index"], nil)
			end
			lastindex = index
			HighMapBuffer[index], LowMapBuffer[index] = 0, 0
			Peak[index] = nil

			local start = depth
			local last_peak, last_peak_i = 0, 0
			local peak_i = getPeak(index)
			if peak_i == -1 then
				last_peak_i, last_peak = 0, 0
			else
				last_peak_i, last_peak = peak_i, Peak[peak_i]
				start = peak_i
			end

			searchMode = searchBoth
			if LowMapBuffer[start] ~= 0 then
				searchMode = searchPeak
			elseif HighMapBuffer[start] ~= 0 then
				searchMode = searchLawn
			end

			for i = start, index do
				Peak[i] = nil
				LowMapBuffer[i] = 0
				HighMapBuffer[i] = 0
			end

			lastlow, lasthigh = -1, -1

			for i = start, index - 1 do
				local range = i - depth + 1
				local val = math.min(unpackFn(CL, range, i))
				if val ~= lastlow then
					lastlow = val
					if (CL[i] - val) > (step * deviation) then
						val = nil
					else
						for k = i - 1, i - backstep + 1, -1 do
							if HighMapBuffer[k] ~= 0 then
								break
							end
							if LowMapBuffer[k] ~= 0 and LowMapBuffer[k] > val then
								LowMapBuffer[k] = 0
							end
						end
					end
				else
					val = nil
				end
				LowMapBuffer[i] = (CL[i] == val) and val or 0

				val = math.max(unpackFn(CH, range, i))
				if val ~= lasthigh then
					lasthigh = val
					if (val - CH[i]) > (step * deviation) then
						val = nil
					else
						for k = i - 1, i - backstep + 1, -1 do
							if LowMapBuffer[k] ~= 0 then
								break
							end
							if HighMapBuffer[k] ~= 0 and HighMapBuffer[k] < val then
								HighMapBuffer[k] = 0
							end
						end
					end
				else
					val = nil
				end
				HighMapBuffer[i] = (CH[i] == val) and val or 0
			end

			local peak_count = (start ~= depth) and -3 or 0
			searchMode = (start ~= depth) and searchBoth or searchMode

			for i = start, index - 1 do
				sizeOfZZ = #ZZLevels
				if searchMode == searchBoth then
					if HighMapBuffer[i] ~= 0 then
						last_peak_i = i
						last_peak = CH[i]
						searchMode = searchLawn
						LowMapBuffer[i] = 0
						peak_count = registerPeak(i, last_peak, peak_count)
					elseif LowMapBuffer[i] ~= 0 then
						last_peak_i = i
						last_peak = CL[i]
						searchMode = searchPeak
						peak_count = registerPeak(i, last_peak, peak_count)
					end
				elseif searchMode == searchPeak then
					if LowMapBuffer[i] ~= 0 and LowMapBuffer[i] < last_peak then
						if setZZValue then
							setZZValue(last_peak_i, nil)
						end
						Peak[last_peak_i] = nil
						last_peak = LowMapBuffer[i]
						last_peak_i = i
						replaceLastPeak(i, last_peak, peak_count)
						HighMapBuffer[i] = 0
					end
					if HighMapBuffer[i] ~= 0 and LowMapBuffer[i] == 0 then
						last_peak = HighMapBuffer[i]
						last_peak_i = i
						searchMode = searchLawn
						peak_count = registerPeak(i, last_peak, peak_count)
					end
				elseif searchMode == searchLawn then
					if HighMapBuffer[i] ~= 0 and HighMapBuffer[i] > last_peak then
						if setZZValue then
							setZZValue(last_peak_i, nil)
						end
						Peak[last_peak_i] = nil
						last_peak = HighMapBuffer[i]
						last_peak_i = i
						replaceLastPeak(i, last_peak, peak_count)
						LowMapBuffer[i] = 0
					end
					if LowMapBuffer[i] ~= 0 and HighMapBuffer[i] == 0 then
						last_peak = LowMapBuffer[i]
						last_peak_i = i
						searchMode = searchPeak
						peak_count = registerPeak(i, last_peak, peak_count)
					end
				end
			end
		end

		sizeOfZZ = #ZZLevels
		if setZZValue then
			for n = 0, 4 do
				local pt = ZZLevels[sizeOfZZ - n]
				if pt ~= nil then
					setZZValue(pt["index"], pt["val"])
				end
			end
		end

		return ZZLevels, true
	end
end

function M.scanPatterns(zzLevels, opts)
	opts = opts or {}
	local found = {}
	local count = #zzLevels
	if count < 5 then
		return found
	end

	local maxHistory = opts.historyDepth or 1
	for endIdx = count, 5, -1 do
		local pX = zzLevels[endIdx - 4]["val"]
		local pA = zzLevels[endIdx - 3]["val"]
		local pB = zzLevels[endIdx - 2]["val"]
		local pC = zzLevels[endIdx - 1]["val"]
		local pD = zzLevels[endIdx]["val"]
		local ok, info = M.checkOne2One(pX, pA, pB, pC, pD, opts)
		if ok then
			table.insert(found, {
				info = info,
				endIdx = endIdx,
				peaksBack = count - endIdx,
				points = {
					X = zzLevels[endIdx - 4],
					A = zzLevels[endIdx - 3],
					B = zzLevels[endIdx - 2],
					C = zzLevels[endIdx - 1],
					D = zzLevels[endIdx],
				},
				values = { pX = pX, pA = pA, pB = pB, pC = pC, pD = pD },
			})
			if #found >= maxHistory then
				break
			end
		end
	end
	return found
end

return M
