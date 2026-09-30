# Анализатор

Python считает те же линии, что Lua на графике QUIK, по CSV barsSaver. Сетапы — дискретная классификация RPM-тегов. Метки для оверлея описаны отдельно: [analyzer-marks.md](analyzer-marks.md). Свечи: [barsSaver.md](barsSaver.md).

## Раскладка

Как на живых графиках (правило `.cursor/rules/chart-tf-analysis.mdc`):

- каждый ТФ: RPM-current + RPM-up;
- 121 только на M30;
- параметры up — из `config/RPM_TF_Up_5.ini`, секция по ТФ **графика**, не из дефолтов Lua и не по `sec_code`.

## Модули

| файл | роль |
|---|---|
| `analyzer/bars.py` | CSV barsSaver, алиасы фьючерсов (`CNY12.26` / `CRZ6` -> `CR_SPBFUT_*.csv`) |
| `analyzer/ema.py` | EMA |
| `analyzer/rpm_current.py` | FIR 12 + EMA(90), расчёт со второй половины истории (`floor(n/2)+1`, как Lua) |
| `analyzer/rpm_up.py` | агрегация Small/Middle/Up, гистограмма, дивер; D2–D5/W2–W5 — unix-слоты Lua |
| `analyzer/settings.py` | `config/RPM_TF_Up_5.ini`, `config/One2One_121.ini` |
| `analyzer/one2one.py` | 121 на M30 |
| `analyzer/neighbors.py` | закрытый бар младшего ТФ на момент старшего |
| `analyzer/states.py` | теги vs0 / vs_ema / slope / ema_vs0 / ema_slope / ema_trend / hist |
| `analyzer/combo.py` | сетапы buy/sell/buy1/sell1/buy2/sell2, дерево состояний |
| `analyzer/price.py` | классификация хода цены |
| `analyzer/snapshot.py` | снимок одного инструмента на M1/M10/M30/H4 (D1 — только метки `--watch` / `--marks`) |
| `analyzer/marks.py` | CSV меток M1/M10/M30/H4/D1 и `--watch` |
| `analyzer/waves.py` | зигзаг high/low и волны 1–5 (предположение по Кречетову, не копия стратегии); CSV для `*AnalyzerZigZag` |
| `analyzer/__main__.py` | CLI |

Пороги тегов (доля медианы модуля ряда): `NEAR_ZERO=0.25`, `NEAR_EMA=0.15`, `NEAR_SLOPE=0.08`, `NEAR_HIST=0.15`. Тренд EMA — за 5 баров.

Гистограмма на графике берётся с того слоя, у которого в ini `HistDraw=1` (M1/M30/H4/D1 — Up, M10 — Small). Цвет столбика — **направление**, не знак: зелёный (`histUp`) — столбик выше предыдущего, оранжевый (`histDw`) — ниже или равен, даже если hist всё ещё > 0.

D2–D5 и W2–W5 режутся **как в Lua**: unix-день `floor(os.time({year,month,day,hour=12})/86400)`, для недель `floor((dayNumber-4)/7)`. Не `datetime.toordinal()`: сдвиг эпохи на 3 дня даёт другие OHLC и другой `hist_dir` (на D1 sell оказывался на оранжевом столбике). W1 по-прежнему новый бар в понедельник. Ini-секцию `[RPM_TF_Up_5.D1]` (D5/W2/W5) снимает `tools/one2one/extract_rpm_up_ini.py` из `finam.wnd` по Small=`D5`.

## CLI

Из корня репозитория:

```text
python -m analyzer --sec GAZP
python -m analyzer --sec GAZP --json
python -m analyzer --sec GAZP --combo
python -m analyzer --sec GAZP --m30
python -m analyzer --sec CNY12.26 --waves
python -m analyzer --watch-waves --sec CNY12.26
python -m analyzer --sec GAZP --marks
python -m analyzer --marks
python -m analyzer --watch
python -m analyzer --watch --sec CNY12.26
```

Без `--sec` для `--marks` / `--watch` обрабатываются все инструменты из папки data. Класс по умолчанию TQBR; имя на `CNY*` -> SPBFUT. `--watch` без `--class-code` берёт и TQBR, и SPBFUT.

`--combo` — уникальные связки H4->M1 и ходы M1 >= 1%. `--m30` — ходы M30 >= 3% с состоянием M1/M10 на концах.

`--waves` — отдельный анализатор, не сетапы buy/sell. Зигзаг по high/low закрытых баров, ноги между пивотами, левая и правая волна 1–5. Геометрия (канал, маятник, 4→5 не длиннее 2→3, цель линия 1–4, стоп за 5) — **предположение** по разборам Кречетова, не точная копия стратегии. Окна M1×120 / M10×90 / M30×90, история M1 1600 / M10 800 / M30 800. Пороги зигзага: M1 0.15%, M10 0.2%, M30 0.25% (эвристика репозитория). Пишет CSV для оверлея `*AnalyzerZigZag` (см. [analyzer-waves.md](analyzer-waves.md)). `--watch-waves` обновляет этот CSV при росте barsSaver.

## Сетапы

Порядок в `setup_signal`: buy, sell, buy1, sell1, buy2, sell2, иначе `none`.

- **buy / sell** — классический стек small+middle+current+hist.
- **buy1 / sell1** — кросс как M10 25.08.2026 17:20; middle ещё с той стороны, наклон `flat` или против тренда (не только `falling`/`rising`).
- **buy2 / sell2** — как Si M1 22.09.2026 18:55 (middle относительно своей EMA: buy2 ниже EMA, sell2 выше).

Полные теги (одна таблица на все шесть сетапов) и счётчик появлений — в [analyzer-marks.md](analyzer-marks.md).

## Свечи

CSV пишет [barsSaver](barsSaver.md). Файлы:

`C:\QuikFinam\LuaScripts\barsSaver\data\{SEC}_{CLASS}_{TF}_.csv`

Для меток читаются последние ~6000 M1, ~2000 M10/M30/H4 и ~800 D1. Формирующаяся свеча в CSV не попадает: строка пишется, когда у бара новое время.

## Тесты

```text
python -m unittest discover -s tests -t . -v
```

Формулы RPM, секции ini (в том числе D1 = D5/W2/W5), unix-слоты D5/W5, сетапы, очередь `--watch` (M1 → M10 → M30 → H4 → D1) проверяются без QUIK. Снимок GAZP — только если CSV barsSaver на месте.
