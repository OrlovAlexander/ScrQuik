# Индикаторы QLua

Рабочие файлы копировать в `C:\QuikFinam\LuaIndicators\`. После замены — снять индикатор с графика и навесить снова. `maLib.lua` нужен RPM-current и RPM-up.

## На график инструмента

| файл | имя на графике | где |
|---|---|---|
| `RPM_TF_Current.lua` | `*RPM_TF_Current` | M1, M10, M30, H4, D1 |
| `RPM_TF_Up_5.lua` | `*RPM_TF_Up_5` | M1, M10, M30, H4, D1 |
| `AnalyzerMarks.lua` | `*AnalyzerMarks` | M1, M10, M30, H4, D1, панель цены (на D1 сверка CSV по дате) |
| `AnalyzerNet.lua` | `*AnalyzerNet` | отдельное окно на M1/M10/M30/H4/D1; три пунктира среднего; не тянуть mix правее последней строки CSV; точки только M10 на 33 (голова 10 M1 + вето); на D1/H4/M30/M1 кругов нет — только пунктир; CNY/CR/CRZ6 → `CR_SPBFUT_*.csv` |

Ini в репозитории (`config/`) читает Python-анализатор. QUIK на графике берёт параметры из окна настроек / `finam.wnd`.

## Архив (рудименты, не развивать)

| файл | имя на графике | заметка |
|---|---|---|
| `One2One_121.lua` + `one2oneLib.lua` | `*One2One_121` | гармоника 121 на M30; код оставлен, оверлей не развивать |
| `AnalyzerZigZag.lua` | `*AnalyzerZigZag` | зигзаг `--waves`; код оставлен, оверлей не развивать |
| `AnalyzerOdds.lua` | `*AnalyzerOdds` | эволюционировал в `*AnalyzerNet` |

## Скрипты (не индикаторы)

| файл | назначение |
|---|---|
| `SecDump.lua` | дамп TQBR/SPBFUT/крипто + LAST/VALTODAY/шаг/экспирация → `barsSaver\sec_dump.csv` (+ `sec_dump_classes.csv`). Копировать в `LuaScripts\`, Сервисы → Lua-скрипты |

## Прочее

| файл | назначение |
|---|---|
| `bigPeriodLines.lua` | линии старших периодов |
| `ChartTradePanel.lua` / `ChartTradePanelButtons.lua` | панель сделок на графике |
| `EIS.lua` | EIS |
| `NumberOfTrades.lua` / `NumberOfTradesEvery60Sec.lua` | число сделок |

Старые RPM-up (v1–v4 и копия v5) лежат в [`archive/`](archive/).
