# WatchNetUi

WPF-монитор живого `--watch-net` и **barsSaver** (шаблона WinUI 3 в SDK не было — Windows UI на WPF).

Каждый «воркер» — отдельный процесс `python -m analyzer --watch-net` (не поток: GIL / numpy). Лимит **8** воркеров — как `JOBS_CAP` в `analyzer/watch_pool.py`. При 16–20 параллельных `export_net` машина thrash'ится: CPU крутится, CSV почти не обновляются. Запрошенное число > 8 UI обрезает до 8.

## Запуск

```text
dotnet run --project tools/WatchNetUi/WatchNetUi/WatchNetUi.csproj -c Release
```

Перед стартом остановите `python -m analyzer --watch-net-pool` и другой WatchNetUi — два писателя на одни CSV.

## barsSaver

Верхняя полоса и колонки **Bars M1** / **Bars** смотрят `C:\QuikFinam\LuaScripts\barsSaver\data\`:

| статус | смысл |
|---|---|
| `ok` | M1 CSV новее ~90 с |
| `тихо` | 90–180 с без записи (возможна пауза рынка) |
| `stale M1` | M1 старше 180 с |
| `M1≪M10` | M10 новее M1 больше чем на **120 с** — тот же порог, что `STALE_M1_BEHIND_M10_SEC` в barsSaver |
| `нет M1` | файла нет |

Полоса также показывает, запущен ли QUIK (`info.exe`). Это **не** замена лога Lua (`RebuildDataFunctors` / stale DS) — только mtime CSV.

## Инструменты (barsSaver → marks → net)

| кнопка | поведение |
|---|---|
| **+ инструмент** | пишет 5 строк в `sec_list.txt`. Список Sec — из `sec_dump.csv` (Lua `SecDump.lua` / справочник QUIK); можно ввести вручную. CNY→`CRZ6`, Si→`SiZ6` |
| **− удалить выбр.** | убирает из `sec_list`, удаляет CSV bars/marks/net и `net_{SEC}_{CLASS}.npz`, останавливает сеть по тикеру |

Справочник: скопировать [`lua/SecDump.lua`](../../lua/SecDump.lua) в `C:\QuikFinam\LuaScripts\`, запустить (Сервисы → Lua-скрипты). Пишет `sec_dump.csv` (коды + имя, шаг, цена, оборот, объём, экспирация) и `sec_dump_classes.csv`. Раз в 5 мин. В «+ инструмент» — таблица, сортировка по клику на заголовок (по умолчанию — оборот ↓).

После +/− **перезапустите** Lua barsSaver в QUIK. Пока нет `*_M1_.csv`…`*_H4_.csv`, строка может не появиться в сетке (список из data\).

## Метки (`*AnalyzerMarks`)

| кнопка | поведение |
|---|---|
| **Метки: watch** | один процесс `python -m analyzer --watch` на все тикеры (dirty M1→D1, budget 21 с) |
| **Метки: стоп** | гасит свой и чужой bare `--watch` (не трогает `--watch-net`) |
| **Метки: разово выбр.** | подряд `--marks --sec` / `--class-code` по выделенным строкам |

Полоса **marks:** pid watch и сколько CSV свежее 3 мин. Колонки **Marks** / **Marks st** — возраст лучшего marks CSV.

## Кнопки сети

| кнопка | поведение |
|---|---|
| **Сеть: все** | N воркеров (≤8) делят **все** тикеры round-robin через `--watch-only` |
| **Сеть: выбранные** | если выбранных ≤ N — по процессу на тикер; если больше — пул только по выбранным |
| **Сеть: стоп …** | гасит шард целиком |

## Термины сети

| слово | смысл |
|---|---|
| **export** | один полный `export_net` (~1–2 мин). В логе: `compute SEC …`. В шарде за poll — **не больше одного** (fair) |
| **круг** | ≈ `тикеров в шарде × длительность export` |
| **возраст net** | `сейчас − mtime` net CSV, не «сколько в пуле» |

Дорогое в export — расчёт по окну M1, не запись CSV по ТФ. Подробнее: [docs/analyzer-net.md](../../docs/analyzer-net.md).
