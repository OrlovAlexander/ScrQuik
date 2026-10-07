-- Dump QUIK security directory for WatchNetUi «+ инструмент».
-- Services ? Lua-scripts. Copy to C:\QuikFinam\LuaScripts\SecDump.lua
-- Writes: C:\QuikFinam\LuaScripts\barsSaver\sec_dump.csv
--          C:\QuikFinam\LuaScripts\barsSaver\sec_dump_classes.csv
-- Columns: code, names, price_step, last, valtoday, voltoday, mat_date, mat_time
-- Base: TQBR, SPBFUT + crypto-like classes.

local BASE_CLASSES = { "TQBR", "SPBFUT" }
local CRYPTO_TRY = {
    "CRYPTO", "CRYPTOM", "CCRYPTO", "FCRYPT", "FINCRYPTO",
    "BINANCE", "BNCRYPT", "SPOT", "COIN",
}
local CRYPTO_PATTERNS = { "CRYPT", "BTC", "COIN", "USDT", "DIGI", "TOKEN" }
local OUT_PATH = "C:\\QuikFinam\\LuaScripts\\barsSaver\\sec_dump.csv"
local OUT_CLASSES = "C:\\QuikFinam\\LuaScripts\\barsSaver\\sec_dump_classes.csv"
local REFRESH_SEC = 300
local getClassSecurities = _G["getClassSecurities"]
local getSecurityInfo = _G["getSecurityInfo"]
local getParamEx = _G["getParamEx"]
local getClassesList = _G["getClassesList"]
local getClassInfo = _G["getClassInfo"]
local isConnected = _G["isConnected"]
local sleep = _G["sleep"]

local function csvEscape(s)
    if s == nil then
        return ""
    end
    s = tostring(s)
    if string.find(s, "[;\r\n\"]") then
        return '"' .. string.gsub(s, '"', '""') .. '"'
    end
    return s
end

local function classHasSecurities(cls)
    if type(getClassSecurities) ~= "function" then
        return false
    end
    local raw = getClassSecurities(cls)
    return type(raw) == "string" and raw ~= "" and raw ~= ","
end

local function addClass(list, seen, cls)
    if cls == nil or cls == "" then
        return
    end
    cls = string.gsub(cls, "^%s+", "")
    cls = string.gsub(cls, "%s+$", "")
    if cls == "" or seen[cls] then
        return
    end
    seen[cls] = true
    list[#list + 1] = cls
end

local function looksCrypto(cls)
    local u = string.upper(cls)
    for _, pat in ipairs(CRYPTO_PATTERNS) do
        if string.find(u, pat, 1, true) then
            return true
        end
    end
    return false
end

local function resolveClasses()
    local list, seen = {}, {}
    for _, cls in ipairs(BASE_CLASSES) do
        addClass(list, seen, cls)
    end
    for _, cls in ipairs(CRYPTO_TRY) do
        if classHasSecurities(cls) then
            addClass(list, seen, cls)
        end
    end
    if type(getClassesList) == "function" then
        local raw = getClassesList()
        if type(raw) == "string" then
            for cls in string.gmatch(raw, "([^,]+)") do
                if looksCrypto(cls) and classHasSecurities(cls) then
                    addClass(list, seen, cls)
                end
            end
        end
    end
    return list
end

local function paramEx(cls, sec, pname)
    if type(getParamEx) ~= "function" then
        return nil, ""
    end
    local ok, t = pcall(getParamEx, cls, sec, pname)
    if not ok or type(t) ~= "table" then
        return nil, ""
    end
    local v = tonumber(t.param_value)
    local img = tostring(t.param_image or "")
    if img == "nil" then
        img = ""
    end
    return v, img
end

local function fmtNum(v)
    if v == nil then
        return ""
    end
    -- avoid scientific for CSV; trim trailing zeros lightly
    local s = string.format("%.10f", v)
    s = string.gsub(s, "(%..-)0+$", "%1")
    s = string.gsub(s, "%.$", "")
    return s
end

local function yyyymmdd(n)
    if n == nil or n <= 0 then
        return ""
    end
    local y = math.floor(n / 10000)
    local m = math.floor((n % 10000) / 100)
    local d = math.floor(n % 100)
    if y < 1990 or y > 2100 or m < 1 or m > 12 or d < 1 or d > 31 then
        return ""
    end
    return string.format("%04d-%02d-%02d", y, m, d)
end

local function hhmmss(n)
    if n == nil or n < 0 then
        return ""
    end
    -- QUIK times: 184500 or 184500000
    if n > 1000000 then
        n = math.floor(n / 1000)
    end
    local h = math.floor(n / 10000)
    local m = math.floor((n % 10000) / 100)
    local s = math.floor(n % 100)
    if h > 23 or m > 59 or s > 59 then
        return ""
    end
    return string.format("%02d:%02d:%02d", h, m, s)
end

local function resolveMaturity(cls, sec, info)
    local matDate, matTime = "", ""
    local v, img

    v, img = paramEx(cls, sec, "MATDATE")
    if img ~= "" and string.find(img, "%d") then
        matDate = img
    elseif v and v > 0 then
        matDate = yyyymmdd(v)
    end
    if matDate == "" then
        v, img = paramEx(cls, sec, "EXPDATE")
        if img ~= "" and string.find(img, "%d") then
            matDate = img
        elseif v and v > 0 then
            matDate = yyyymmdd(v)
        end
    end
    if matDate == "" and type(info) == "table" then
        local md = tonumber(info.maturity_date) or tonumber(info.MaturityDate)
        if md and md > 0 then
            matDate = yyyymmdd(md)
        end
    end

    -- optional expiry / evening settle time (not always present)
    v, img = paramEx(cls, sec, "EXPIRETIME")
    if img ~= "" and string.find(img, ":") then
        matTime = img
    elseif v and v > 0 then
        matTime = hhmmss(v)
    end
    if matTime == "" then
        v, img = paramEx(cls, sec, "EVNSETTLETIME")
        if img ~= "" and string.find(img, ":") then
            matTime = img
        elseif v and v > 0 then
            matTime = hhmmss(v)
        end
    end

    return matDate, matTime
end

local function dumpClassesFile()
    if type(getClassesList) ~= "function" then
        return
    end
    local raw = getClassesList() or ""
    local lines = { "class_code;name;n_sec;used_in_dump" }
    local used = {}
    for _, cls in ipairs(resolveClasses()) do
        used[cls] = true
    end
    for cls in string.gmatch(raw, "([^,]+)") do
        cls = string.gsub(cls, "^%s+", "")
        cls = string.gsub(cls, "%s+$", "")
        if cls ~= "" then
            local name = ""
            if type(getClassInfo) == "function" then
                local ok, info = pcall(getClassInfo, cls)
                if ok and type(info) == "table" then
                    name = info.name or info.class_name or ""
                end
            end
            local n = 0
            if type(getClassSecurities) == "function" then
                local secs = getClassSecurities(cls) or ""
                for _ in string.gmatch(secs, "([^,]+)") do
                    n = n + 1
                end
            end
            lines[#lines + 1] = table.concat({
                csvEscape(cls),
                csvEscape(name),
                tostring(n),
                used[cls] and "1" or "0",
            }, ";")
        end
    end
    local fh = io.open(OUT_CLASSES, "w")
    if fh ~= nil then
        fh:write(table.concat(lines, "\n"))
        fh:write("\n")
        fh:close()
    end
end

local function dumpOnce()
    if type(getClassSecurities) ~= "function" then
        return 0
    end
    dumpClassesFile()
    local classes = resolveClasses()
    local lines = {
        "sec_code;class_code;name;short_name;price_step;last;valtoday;voltoday;mat_date;mat_time",
    }
    local n = 0
    for _, cls in ipairs(classes) do
        local raw = getClassSecurities(cls)
        if type(raw) == "string" and raw ~= "" then
            for sec in string.gmatch(raw, "([^,]+)") do
                sec = string.gsub(sec, "^%s+", "")
                sec = string.gsub(sec, "%s+$", "")
                if sec ~= "" then
                    local name, short, step = "", "", ""
                    local info
                    if type(getSecurityInfo) == "function" then
                        local ok, inf = pcall(getSecurityInfo, cls, sec)
                        if ok and type(inf) == "table" then
                            info = inf
                            name = info.name or info.sec_name or ""
                            short = info.short_name or info.code or ""
                            local ps = tonumber(info.min_price_step)
                            if ps and ps > 0 then
                                step = fmtNum(ps)
                            end
                        end
                    end
                    if step == "" then
                        local v = paramEx(cls, sec, "SEC_PRICE_STEP")
                        if v and v > 0 then
                            step = fmtNum(v)
                        end
                    end

                    local lastV = paramEx(cls, sec, "LAST")
                    local valV = paramEx(cls, sec, "VALTODAY")
                    local volV = paramEx(cls, sec, "VOLTODAY")
                    local matDate, matTime = resolveMaturity(cls, sec, info)

                    lines[#lines + 1] = table.concat({
                        csvEscape(sec),
                        csvEscape(cls),
                        csvEscape(name),
                        csvEscape(short),
                        csvEscape(step),
                        csvEscape(fmtNum(lastV)),
                        csvEscape(fmtNum(valV)),
                        csvEscape(fmtNum(volV)),
                        csvEscape(matDate),
                        csvEscape(matTime),
                    }, ";")
                    n = n + 1
                end
            end
        end
    end
    local fh = io.open(OUT_PATH, "w")
    if fh == nil then
        return 0
    end
    fh:write(table.concat(lines, "\n"))
    fh:write("\n")
    fh:close()
    return n
end

function OnInit()
end

function main()
    while true do
        if type(isConnected) ~= "function" or isConnected() == 1 then
            dumpOnce()
        end
        if REFRESH_SEC == nil or REFRESH_SEC <= 0 then
            break
        end
        if type(sleep) == "function" then
            sleep(REFRESH_SEC * 1000)
        else
            break
        end
    end
end

function OnStop()
end
