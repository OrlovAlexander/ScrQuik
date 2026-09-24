--[[
  ChartTradePanel — торговля с графика QUIK (Lua-скрипт)

  Только панель: цены покупки/продажи и кнопки. Линии на графике не рисуются.

  Настройка:
    1. На графике: свойства -> «Идентификатор» (например CHART1).
    2. Скопируйте ChartTradePanel.lua в LuaScripts, укажите CONFIG ниже.
    3. Запустите: Сервисы -> Lua-скрипты -> ChartTradePanel.

  Цены:
    - «ОБНОВИТЬ» считает min/max по свечам графика и заполняет ячейки
      (покупка = min - 5% диапазона, продажа = max + 5% диапазона).
    - Ячейки «Покупка» / «Продажа» можно править вручную.
    - КУПИТЬ / ПРОДАТЬ берут цену из соответствующей ячейки.
]]

CONFIG = {
    ClassCode      = "TQBR",
    SecCode        = "MSNG",
    Account        = "L01+00000F00",
    ClientCode     = "166252RI5FH",
    ChartTag       = "CHARTMSNG",
    MarginPct      = 5,
    VisibleBars    = 0,
    DefaultLots    = 1,
    PriceMode      = 3,
    ConfirmOrder   = 1,
    QuantityField  = "Лоты",
    PriceStep      = 0,
}

PANEL = {
    Width          = 320,
    Height         = 320,
    PollIntervalMs = 500,
}

local message                 = _G.message
local RGB                     = _G.RGB
local sendTransaction         = _G.sendTransaction
local getParamEx              = _G.getParamEx
local getSecurityInfo         = _G.getSecurityInfo
local getWorkingFolder        = _G.getWorkingFolder
local getNumCandles           = _G.getNumCandles
local getCandlesByIndex       = _G.getCandlesByIndex
local AllocTable              = _G.AllocTable
local CreateWindow            = _G.CreateWindow
local DestroyTable            = _G.DestroyTable
local IsWindowClosed          = _G.IsWindowClosed
local AddColumn               = _G.AddColumn
local InsertRow               = _G.InsertRow
local SetCell                 = _G.SetCell
local GetCell                 = _G.GetCell
local SetColor                = _G.SetColor
local SetWindowCaption        = _G.SetWindowCaption
local SetWindowPos            = _G.SetWindowPos
local SetTableNotificationCallback = _G.SetTableNotificationCallback
local QTABLE_LBUTTONDOWN      = _G.QTABLE_LBUTTONDOWN
local QTABLE_CACHED_STRING_TYPE = _G.QTABLE_CACHED_STRING_TYPE
local QTABLE_DOUBLE_TYPE      = _G.QTABLE_DOUBLE_TYPE

local COL_LABEL = 1
local COL_VALUE = 2

local ROW_INSTR    = 1
local ROW_LOTSIZE  = 2
local ROW_LOTS     = 3
local ROW_BUY      = 4
local ROW_SELL     = 5
local ROW_UPDATE   = 6
local ROW_BUYBTN   = 7
local ROW_SELLBTN  = 8
local ROW_STATUS   = 9

local t_id         = nil
local trans_id     = 0
local class_code   = ""
local sec_code     = ""
local chart_tag    = ""
local price_step   = 0.01
local lot_size     = 0
local buy_price    = 0
local sell_price   = 0

local cfg = {}

local function copy_config()
    cfg = {
        Account       = CONFIG.Account or "",
        ClientCode    = CONFIG.ClientCode or "",
        DefaultLots   = CONFIG.DefaultLots or 1,
        PriceMode     = CONFIG.PriceMode or 3,
        ConfirmOrder  = CONFIG.ConfirmOrder or 0,
        QuantityField = CONFIG.QuantityField or "Лоты",
        PriceStep     = CONFIG.PriceStep or 0,
        MarginPct     = CONFIG.MarginPct or 5,
        VisibleBars   = CONFIG.VisibleBars or 0,
    }
end

local function state_file_path()
    return (getWorkingFolder() or "") .. "\\LuaScripts\\ChartTradePanel.state"
end

local function save_state()
    if class_code == "" or sec_code == "" then
        return
    end
    pcall(function()
        local f = io.open(state_file_path(), "w")
        if not f then
            return
        end
        f:write(string.format("%s|%s|%.10g|%.10g|%s|%s|%s|%s|%s|%s|%s|%s",
            class_code,
            sec_code,
            buy_price or 0,
            sell_price or 0,
            cfg.Account or "",
            cfg.ClientCode or "",
            tostring(cfg.DefaultLots or 1),
            tostring(cfg.PriceMode or 3),
            tostring(cfg.ConfirmOrder or 0),
            cfg.QuantityField or "Лоты",
            tostring(cfg.PriceStep or 0),
            chart_tag or ""))
        f:close()
    end)
end

local function set_status(text)
    if t_id and not IsWindowClosed(t_id) then
        SetCell(t_id, ROW_STATUS, COL_VALUE, text, 0)
    end
end

local function round_price(price)
    if not price or price_step <= 0 then
        return price
    end
    return math.floor(price / price_step + 0.5) * price_step
end

local function format_price(price)
    if not price then
        return "-"
    end
    return tostring(round_price(price))
end

local function load_instrument_info()
    price_step = cfg.PriceStep or 0
    lot_size = 0

    if class_code == "" or sec_code == "" then
        if price_step <= 0 then
            price_step = 0.01
        end
        return
    end

    local info = getSecurityInfo(class_code, sec_code)
    if info then
        if price_step <= 0 and tonumber(info.min_price_step) then
            price_step = tonumber(info.min_price_step)
        end
        lot_size = tonumber(info.lot_size) or tonumber(info.LotSize) or 0
    end

    if price_step <= 0 then
        price_step = 0.01
    end
end

local function format_lot_size_text()
    if lot_size and lot_size > 0 then
        return tostring(lot_size) .. " шт."
    end
    return "—"
end

local function format_lots_summary(lots)
    lots = lots or get_lots()
    if lot_size and lot_size > 0 then
        return string.format("%s лот = %s шт.", lots, lots * lot_size)
    end
    return tostring(lots) .. " лот"
end

local function update_lot_size_cell()
    if not t_id or IsWindowClosed(t_id) then
        return
    end
    SetCell(t_id, ROW_LOTSIZE, COL_LABEL, "Размер лота", 0)
    SetCell(t_id, ROW_LOTSIZE, COL_VALUE, format_lot_size_text(), 0)
end

local function resolve_instrument()
    class_code = CONFIG.ClassCode or ""
    sec_code = CONFIG.SecCode or ""
    chart_tag = CONFIG.ChartTag or ""

    if class_code ~= "" and sec_code ~= "" then
        return true
    end

    if chart_tag == "" or not getCandlesByIndex then
        return false
    end

    local candles, n, legend = getCandlesByIndex(chart_tag, 0, 0, 1)
    if legend and legend ~= "" then
        local cc, sc = legend:match("([^/]+)/([^/]+)")
        if cc and sc then
            class_code = cc:match("^%s*(.-)%s*$")
            sec_code = sc:match("^%s*(.-)%s*$")
            return class_code ~= "" and sec_code ~= ""
        end
    end

    return class_code ~= "" and sec_code ~= ""
end

local function update_instrument_cell()
    if not t_id or IsWindowClosed(t_id) then
        return
    end
    local text = "укажите ClassCode/SecCode"
    if class_code ~= "" and sec_code ~= "" then
        text = class_code .. " / " .. sec_code
    end
    SetCell(t_id, ROW_INSTR, COL_VALUE, text, 0)
    if sec_code ~= "" then
        SetWindowCaption(t_id, "Торговля: " .. sec_code)
    else
        SetWindowCaption(t_id, "ChartTradePanel")
    end
end

local function set_panel_prices(update_buy, update_sell)
    if not t_id or IsWindowClosed(t_id) then
        return
    end
    if update_buy ~= false then
        if buy_price > 0 then
            SetCell(t_id, ROW_BUY, COL_VALUE, format_price(buy_price), buy_price)
        else
            SetCell(t_id, ROW_BUY, COL_VALUE, "не задана", 0)
        end
    end
    if update_sell ~= false then
        if sell_price > 0 then
            SetCell(t_id, ROW_SELL, COL_VALUE, format_price(sell_price), sell_price)
        else
            SetCell(t_id, ROW_SELL, COL_VALUE, "не задана", 0)
        end
    end
end

local function read_panel_price(row)
    if not t_id or IsWindowClosed(t_id) then
        return row == ROW_BUY and buy_price or sell_price
    end
    local cell = GetCell(t_id, row, COL_VALUE)
    if cell then
        local p = tonumber(cell.image) or tonumber(cell.value)
        if p and p > 0 then
            return round_price(p)
        end
    end
    return row == ROW_BUY and buy_price or sell_price
end

local function candle_high(candle)
    return tonumber(candle.high) or tonumber(candle.H) or tonumber(candle.h)
end

local function candle_low(candle)
    return tonumber(candle.low) or tonumber(candle.L) or tonumber(candle.l)
end

local function fetch_visible_candles()
    if chart_tag == "" or not getNumCandles or not getCandlesByIndex then
        return nil, "Не задан ChartTag (идентификатор графика)"
    end

    local total = getNumCandles(chart_tag)
    if not total or total <= 0 then
        return nil, "График не найден или нет свечей. Проверьте ChartTag и откройте график."
    end

    local count = cfg.VisibleBars
    if not count or count <= 0 or count > total then
        count = total
    end

    local first = total - count
    if first < 0 then
        first = 0
    end

    local candles, n = getCandlesByIndex(chart_tag, 0, first, count)
    if not candles or not n or n <= 0 then
        return nil, "Не удалось получить свечи графика"
    end
    return candles, nil, n
end

local function calc_prices_from_visible_bars()
    local candles, err, n = fetch_visible_candles()
    if not candles then
        return false, err
    end

    local min_low = nil
    local max_high = nil

    for i = 1, n do
        local c = candles[i]
        if c then
            local hi = candle_high(c)
            local lo = candle_low(c)
            if hi and (not max_high or hi > max_high) then
                max_high = hi
            end
            if lo and (not min_low or lo < min_low) then
                min_low = lo
            end
        end
    end

    if not min_low or not max_high then
        return false, "Не удалось определить min/max по свечам"
    end

    local range = max_high - min_low
    if range <= 0 then
        range = math.max(max_high * 0.001, price_step)
    end

    local margin = (cfg.MarginPct or 5) / 100
    buy_price = round_price(min_low - range * margin)
    sell_price = round_price(max_high + range * margin)

    if buy_price <= 0 then
        buy_price = round_price(min_low * (1 - margin))
    end
    if sell_price <= 0 then
        sell_price = round_price(max_high * (1 + margin))
    end

    set_panel_prices(true, true)
    save_state()
    return true, string.format("Баров: %s | min=%s max=%s", n, format_price(min_low), format_price(max_high))
end

local function get_last_price()
    if class_code == "" or sec_code == "" then
        return nil
    end
    local p = getParamEx(class_code, sec_code, "LAST")
    if p and p.result == "1" and tonumber(p.param_value) then
        return tonumber(p.param_value)
    end
    return nil
end

local function get_lots()
    if not t_id or IsWindowClosed(t_id) then
        return cfg.DefaultLots or 1
    end
    local cell = GetCell(t_id, ROW_LOTS, COL_VALUE)
    if cell then
        local lots = tonumber(cell.image) or tonumber(cell.value)
        if lots and lots > 0 then
            return math.floor(lots)
        end
    end
    return cfg.DefaultLots or 1
end

local function resolve_order_price(operation)
    local row = (operation == "B") and ROW_BUY or ROW_SELL
    local p = read_panel_price(row)
    if not p or p <= 0 then
        return nil, nil, (operation == "B") and "Укажите цену покупки" or "Укажите цену продажи"
    end

    if operation == "B" then
        buy_price = p
    else
        sell_price = p
    end
    save_state()

    local mode = cfg.PriceMode or 3
    if mode == 0 then
        return "0", "Рыночная", nil
    end
    if mode == 1 then
        local last = get_last_price()
        if not last then
            return nil, nil, "Не удалось получить LAST"
        end
        return tostring(last), "Лимитированная", nil
    end
    return tostring(p), "Лимитированная", nil
end

local function next_trans_id()
    trans_id = trans_id + 1
    return tostring(trans_id)
end

local function build_transaction(operation)
    local lots = get_lots()
    local price_str, order_type, err = resolve_order_price(operation)
    if not price_str then
        return nil, err
    end
    local side = (operation == "B") and "Купля" or "Продажа"
    return {
        TRANS_ID    = next_trans_id(),
        ACTION      = "Ввод заявки",
        CLASSCODE   = class_code,
        ["Торговый счет"] = cfg.Account,
        ["Примечание"]    = cfg.ClientCode,
        ["Инструмент"]    = sec_code,
        ["К/П"]           = side,
        ["Цена"]          = price_str,
        [cfg.QuantityField or "Лоты"] = tostring(lots),
        ["Тип"]           = order_type,
    }, nil
end

local function send_order(operation)
    if not _G.isConnected or _G.isConnected() ~= 1 then
        message("Нет подключения к серверу QUIK", 3)
        set_status("Нет подключения")
        return
    end
    if cfg.Account == nil or cfg.Account == "" then
        message("Укажите Account в CONFIG", 3)
        set_status("Не задан счёт")
        return
    end
    if class_code == "" or sec_code == "" then
        message("Укажите ClassCode и SecCode в CONFIG", 3)
        set_status("Нет инструмента")
        return
    end

    local lots = get_lots()
    local tr, err = build_transaction(operation)
    if not tr then
        message(err, 3)
        set_status(err)
        return
    end

    local side_text = (operation == "B") and "ПОКУПКА" or "ПРОДАЖА"
    if cfg.ConfirmOrder == 1 then
        message(string.format("%s %s\n%s\n%s\nЦена: %s",
            side_text, sec_code, format_lots_summary(lots), tr["Тип"], tr["Цена"]), 2)
    end

    local result = sendTransaction(tr)
    if result and result ~= "" then
        message("Ошибка QUIK: " .. result, 3)
        set_status("Ошибка: " .. result)
    else
        message(string.format("Заявка %s: %s %s, %s @ %s",
            tr.TRANS_ID, side_text, sec_code, lots, tr["Цена"]), 1)
        set_status("Отправлено " .. tr.TRANS_ID)
    end
end

local function refresh_prices()
    local ok, info = calc_prices_from_visible_bars()
    if not ok then
        message(info, 3)
        set_status(info)
        return
    end
    set_status(string.format("BUY %s | SELL %s", format_price(buy_price), format_price(sell_price)))
    message("Цены обновлены:\nПокупка: " .. format_price(buy_price) ..
        "\nПродажа: " .. format_price(sell_price) .. "\n" .. info, 1)
end

function OnTableEvent(table_id, msg, par1, par2)
    if table_id ~= t_id or msg ~= QTABLE_LBUTTONDOWN then
        return
    end
    if par1 == ROW_BUYBTN then
        send_order("B")
    elseif par1 == ROW_SELLBTN then
        send_order("S")
    elseif par1 == ROW_UPDATE then
        refresh_prices()
    end
end

local function create_panel()
    if t_id and not IsWindowClosed(t_id) then
        DestroyTable(t_id)
    end

    t_id = AllocTable()
    if not t_id then
        message("Не удалось создать панель (AllocTable)", 3)
        return false
    end

    AddColumn(t_id, COL_LABEL, "Параметр", true, QTABLE_CACHED_STRING_TYPE, 12)
    AddColumn(t_id, COL_VALUE, "Значение", true, QTABLE_DOUBLE_TYPE, 22)
    CreateWindow(t_id)

    for row = 1, ROW_STATUS do
        InsertRow(t_id, row)
    end

    SetCell(t_id, ROW_INSTR, COL_LABEL, "Инструмент", 0)
    SetCell(t_id, ROW_LOTSIZE, COL_LABEL, "Размер лота", 0)
    SetCell(t_id, ROW_LOTSIZE, COL_VALUE, format_lot_size_text(), 0)
    SetCell(t_id, ROW_LOTS, COL_LABEL, "Лоты", 0)
    SetCell(t_id, ROW_LOTS, COL_VALUE, tostring(cfg.DefaultLots or 1), cfg.DefaultLots or 1)
    SetCell(t_id, ROW_BUY, COL_LABEL, "Покупка", 0)
    SetCell(t_id, ROW_SELL, COL_LABEL, "Продажа", 0)
    SetCell(t_id, ROW_UPDATE, COL_LABEL, "", 0)
    SetCell(t_id, ROW_UPDATE, COL_VALUE, "  ОБНОВИТЬ  ", 0)
    SetColor(t_id, ROW_UPDATE, COL_VALUE,
        RGB(70, 70, 140), RGB(255, 255, 255),
        RGB(50, 50, 110), RGB(255, 255, 255))

    SetCell(t_id, ROW_BUYBTN, COL_LABEL, "", 0)
    SetCell(t_id, ROW_BUYBTN, COL_VALUE, "  КУПИТЬ  ", 0)
    SetColor(t_id, ROW_BUYBTN, COL_VALUE,
        RGB(0, 140, 0), RGB(255, 255, 255),
        RGB(0, 100, 0), RGB(255, 255, 255))

    SetCell(t_id, ROW_SELLBTN, COL_LABEL, "", 0)
    SetCell(t_id, ROW_SELLBTN, COL_VALUE, "  ПРОДАТЬ  ", 0)
    SetColor(t_id, ROW_SELLBTN, COL_VALUE,
        RGB(180, 0, 0), RGB(255, 255, 255),
        RGB(140, 0, 0), RGB(255, 255, 255))

    SetCell(t_id, ROW_STATUS, COL_LABEL, "Статус", 0)
    SetCell(t_id, ROW_STATUS, COL_VALUE, "Готов", 0)

    update_instrument_cell()
    update_lot_size_cell()
    set_panel_prices(true, true)
    SetWindowPos(t_id, 100, 100, PANEL.Width or 320, PANEL.Height or 300)
    SetTableNotificationCallback(t_id, OnTableEvent)
    return true
end

function OnTransReply(trans_reply)
    if not trans_reply then
        return
    end
    set_status(string.format("Ответ %s: %s [%s]",
        tostring(trans_reply.trans_id),
        tostring(trans_reply.status),
        tostring(trans_reply.result_msg or "")))
end

function main()
    copy_config()
    trans_id = os.time()

    if not resolve_instrument() then
        message("ChartTradePanel: укажите ClassCode/SecCode в CONFIG", 3)
    end

    load_instrument_info()

    if not create_panel() then
        return
    end

    refresh_prices()

    while t_id and not IsWindowClosed(t_id) do
        sleep(PANEL.PollIntervalMs or 500)
    end

    if t_id then
        DestroyTable(t_id)
        t_id = nil
    end
    message("ChartTradePanel: панель закрыта", 1)
end
