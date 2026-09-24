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
| `analyzer/rpm_up.py` | агрегация Small/Middle/Up, гистограмма, дивер |
| `analyzer/settings.py` | `config/RPM_TF_Up_5.ini`, `config/One2One_121.ini` |
| `analyzer/one2one.py` | 121 на M30 |
| `analyzer/neighbors.py` | закрытый бар младшего ТФ на момент старшего |
| `analyzer/states.py` | теги vs0 / vs_ema / slope / ema_vs0 / ema_slope / ema_trend / hist |
| `analyzer/combo.py` | сетапы buy/sell/buy1/sell1/buy2/sell2, дерево состояний |
| `analyzer/price.py` | классификация хода цены |
| `analyzer/snapshot.py` | снимок одного инструмента на M1/M10/M30/H4 |
| `analyzer/marks.py` | CSV меток и `--watch` |
| `analyzer/__main__.py` | CLI |

Пороги тегов (доля медианы модуля ряда): `NEAR_ZERO=0.25`, `NEAR_EMA=0.15`, `NEAR_SLOPE=0.08`, `NEAR_HIST=0.15`. Тренд EMA — за 5 баров.

Гистограмма на графике берётся с того слоя, у которого в ini `HistDraw=1` (M1/M30/H4 — Up, M10 — Small).

## CLI

Из корня репозитория:

```text
python -m analyzer --sec GAZP
python -m analyzer --sec GAZP --json
python -m analyzer --sec GAZP --combo
python -m analyzer --sec GAZP --m30
python -m analyzer --sec GAZP --marks
python -m analyzer --marks
python -m analyzer --watch
python -m analyzer --watch --sec CNY12.26
```

Без `--sec` для `--marks` / `--watch` обрабатываются все инструменты из папки data. Класс по умолчанию TQBR; имя на `CNY*` -> SPBFUT. `--watch` без `--class-code` берёт и TQBR, и SPBFUT.

`--combo` — уникальные связки H4->M1 и ходы M1 >= 1%. `--m30` — ходы M30 >= 3% с состоянием M1/M10 на концах.

## Сетапы

Порядок в `setup_signal`: buy, sell, buy1, sell1, buy2, sell2, иначе `none`.

- **buy / sell** — классический стек small+middle+current+hist.
- **buy1 / sell1** — кросс как M10 25.08.2026 17:20; middle ещё с той стороны, наклон `flat` или против тренда (не только `falling`/`rising`).
- **buy2 / sell2** — как Si M1 22.09.2026 18:55 (middle относительно своей EMA: buy2 ниже EMA, sell2 выше).

Полные теги и счётчик появлений по истории — в [analyzer-marks.md](analyzer-marks.md).

## Свечи

CSV пишет [barsSaver](barsSaver.md). Файлы:

`C:\QuikFinam\LuaScripts\barsSaver\data\{SEC}_{CLASS}_{TF}_.csv`

Для меток читаются последние ~6000 M1 и ~2000 M10. Формирующаяся свеча в CSV не попадает: строка пишется, когда у бара новое время.

## Тесты

```text
python -m unittest discover -s tests -t . -v
```

Формулы RPM, секции ini, сетапы, очередь `--watch` (M1 раньше M10) проверяются без QUIK. Снимок GAZP — только если CSV barsSaver на месте.
