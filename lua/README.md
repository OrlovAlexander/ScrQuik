# Индикаторы QLua

Рабочие файлы копировать в `C:\QuikFinam\LuaIndicators\`. После замены — снять индикатор с графика и навесить снова. `maLib.lua` нужен RPM-current и RPM-up.

## На график инструмента

| файл | имя на графике | где |
|---|---|---|
| `RPM_TF_Current.lua` | `*RPM_TF_Current` | M1, M10, M30, H4, D1 |
| `RPM_TF_Up_5.lua` | `*RPM_TF_Up_5` | M1, M10, M30, H4, D1 |
| `One2One_121.lua` + `one2oneLib.lua` | `*One2One_121` | только M30 |
| `AnalyzerMarks.lua` | `*AnalyzerMarks` | M1, M10, M30, H4, D1, панель цены (на D1 сверка CSV по дате) |
| `AnalyzerZigZag.lua` | `*AnalyzerZigZag` | M1, M10, M30, панель цены |
| `AnalyzerOdds.lua` | `*AnalyzerOdds` | архив; эволюционировал в `*AnalyzerNet` |
| `AnalyzerNet.lua` | `*AnalyzerNet` | флет режима; три пунктира среднего; точки M10/M30 на 33; без impulse/pullback/uncertain/100 |

Ini в репозитории (`config/`) читает Python-анализатор. QUIK на графике берёт параметры из окна настроек / `finam.wnd`.

## Прочее

| файл | назначение |
|---|---|
| `bigPeriodLines.lua` | линии старших периодов |
| `ChartTradePanel.lua` / `ChartTradePanelButtons.lua` | панель сделок на графике |
| `EIS.lua` | EIS |
| `NumberOfTrades.lua` / `NumberOfTradesEvery60Sec.lua` | число сделок |

Старые RPM-up (v1–v4 и копия v5) лежат в [`archive/`](archive/).
