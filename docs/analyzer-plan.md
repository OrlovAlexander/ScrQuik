# План: анализатор одного инструмента (все ТФ + индикаторы)

Анализатор считает те же линии, что на живых графиках QUIK, по одному инструменту на M1 / M10 / M30 / H4.

Раскладка индикаторов — в `.cursor/rules/chart-tf-analysis.mdc`.

## Уже есть

- Свечи M1 / M10 / M30 / H4: `C:\QuikFinam\LuaScripts\barsSaver\data\{SEC}_{CLASS}_{TF}_.csv` (QUIK дописывает, пока скрипт запущен).
- Правило: на каждом ТФ один `*RPM_TF_Current` и один `*RPM_TF_Up_5`; **One2One_121 только на M30**.
- Живые настройки RPM-up: `RPM_TF_Up_5.ini`, секция по ТФ **графика** (`[RPM_TF_Up_5.M1]` … `[RPM_TF_Up_5.H4]`), общие для всех инструментов.
- Lua: `RPM_TF_Current.lua`, `RPM_TF_Up_5.lua`, `One2One_121.lua`.
- Python-replay 121: `One2One_121/tools/move_stats.py` (сейчас свечи с MOEX ISS, не из barsSaver).

## 1. Снимок инструмента

- Вход: `sec_code` + `class_code`.
- Четыре ряда OHLC с общей шкалой времени из CSV barsSaver.
- Старшие слои RPM-up **не** выгружать отдельно: агрегировать из младшего ряда
  - M1 ? Mn5 / Mn10 / Mn20
  - M10 ? Mn20 / Mn30 / H2
  - M30 ? H1 / H2 / H4
  - H4 ? H12 / D1 / W1

## 2. Расчёт индикаторов вне QUIK (узкое место)

Сейчас линии есть только в Lua на графике. Нужен Python-порт.

- **RPM-current** — FIR 12 баров + EMA. В wnd везде `Period=90`; отдельный ini не обязателен.
- **RPM-up** — секция `RPM_TF_Up_5.ini` по ТФ графика: агрегация слоёв, `RPMTFUpTransform`, две EMA, гистограмма, дивергенции. Не брать дефолты из `RPM_TF_Up_5.lua`.
- **121** — переключить `move_stats.py` на **локальный M30 CSV** того же инструмента. Живые параметры 121 из `finam.wnd` ещё не снимали (в Lua: Depth=12, Deviation=5, AB 0.25–2.00, CD 0.10–0.74).

## 3. Сшивка ТФ

На один момент времени:

- current и up по M1, M10, M30, H4;
- паттерн 121 с M30 (X–A–B–C–D, stop, TP).

Без общей шкалы это четыре отдельных индикатора, не анализатор.

## 4. Правило сигнала

Ещё не зафиксировано: дивер up на M30 + 121, подтверждение current, фильтр старшим ТФ и т.д. Без этого можно только выгрузить ряды, не «анализ».

## 5. Сверка с графиком QUIK

Один тикер, одна дата: значения RPM и точки 121 в Python vs терминал. Иначе порт разъедется с `halfHistory` и границами Mn/H.

## Порядок работ

1. ~~Загрузчик CSV barsSaver ? объект «инструмент ? 4 ТФ».~~ (`analyzer/bars.py`)
2. ~~Порт RPM-current.~~ (`analyzer/rpm_current.py`)
3. ~~Порт RPM-up (агрегация + дивер) + чтение ini.~~ (`analyzer/rpm_up.py`, `analyzer/settings.py`)
4. ~~121 на M30 из barsSaver (не ISS).~~ (`analyzer/one2one.py`, `One2One_121.ini` из wnd: Depth=12, Deviation=5, Backstep=3)
5. ~~Сшивка по времени.~~ (`analyzer/snapshot.py`, `python -m analyzer --sec TICKER`; раскладка проверяется: current+up на каждом ТФ, 121 только на M30)
Проверка без QUIK: `python -m unittest analyzer.test_analyzer -v` (формула RPM-current, секции ini, раскладка на GAZP CSV).
7. Правило сигнала (отдельное решение).
