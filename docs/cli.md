# Команды

Запуск из **корня репозитория**. Python 3.10+. Данные свечей — barsSaver (`C:\QuikFinam\LuaScripts\barsSaver\data\`). Для `--train-net` / `--net` / `--watch-net` нужен `numpy`.

Общий вид: `python -m analyzer [флаги]`. Справка: `python -m analyzer --help`.

## Общие флаги

| флаг | что |
|---|---|
| `--sec TICKER` | инструмент. Без него у `--marks` / `--watch` / `--odds` / `--watch-odds` / `--train-net` / `--net` / `--watch-net` / `--watch-waves` — все тикеры barsSaver |
| `--class-code CLASS` | класс. По умолчанию TQBR; имя на `CNY*` → SPBFUT. `--watch` без класса берёт и TQBR, и SPBFUT |
| `--json` | печать JSON вместо текста. Нельзя с `--watch`, `--watch-waves`, `--watch-odds`, `--watch-net` |
| `--poll N` | простой секунд между проверками barsSaver у watch-команд. По умолчанию **11**. Окно не закрывать. Пачка грязных тикеров до **21** с, очередь ТФ: M1 → M10 → M30 → H4 → D1 |

`--sec` обязателен для снимка, `--combo`, `--m30`, `--waves`, `--pack-ahead`.

## Снимок и разбор в консоли

Не пишут CSV оверлея.

| команда | что делает |
|---|---|
| `python -m analyzer --sec GAZP` | снимок одного инструмента: RPM, теги, сетап, ход цены на M1/M10/M30/H4 |
| `python -m analyzer --sec GAZP --json` | тот же снимок JSON |
| `python -m analyzer --sec GAZP --combo` | уникальные деревья состояний H4→M1 и ходы M1 ≥ 1% (это **не** парная связка). Подробнее: [python-analyzer.md](python-analyzer.md) |
| `python -m analyzer --sec GAZP --m30` | ходы M30 ≥ 3% с состоянием M1/M10 на концах |

## Метки сетапов (`*AnalyzerMarks`)

Пишет CSV в `C:\QuikFinam\LuaIndicators\analyzer_marks\`. Комбо buy/sell **не меняет**. Подробнее: [analyzer-marks.md](analyzer-marks.md).

| команда | что делает |
|---|---|
| `python -m analyzer --sec GAZP --marks` | разовая выгрузка меток одного инструмента, M1/M10/M30/H4/D1 |
| `python -m analyzer --marks` | разовая выгрузка всех инструментов barsSaver |
| `python -m analyzer --watch` | живой оверлей меток: пересчёт при росте CSV barsSaver. Окно не закрывать |
| `python -m analyzer --watch --sec CNY12.26` | то же, только этот тикер |

## Волны (`*AnalyzerZigZag`)

Отдельный анализатор, не сетапы buy/sell. Геометрия 1–5 — предположение по Кречетову, не копия стратегии. Подробнее: [analyzer-waves.md](analyzer-waves.md).

| команда | что делает |
|---|---|
| `python -m analyzer --sec CNY12.26 --waves` | разовая выгрузка зигзага/волн M1/M10/M30 |
| `python -m analyzer --watch-waves --sec CNY12.26` | живой CSV зигзага при росте barsSaver |
| `python -m analyzer --watch-waves` | то же по всем инструментам |

## Сеть (`*AnalyzerNet`)

Три головы ahead (10 / 30 / 240 M1), головы действия нет. Точка на M10/M30 — среднее трёх softmax и порог. Веса: `C:\QuikFinam\LuaIndicators\analyzer_net\net.npz` (в git нет). Как ставят круг: [analyzer-net.md](analyzer-net.md#точка-обучение-и-живой-график).

| команда | что делает |
|---|---|
| `python -m analyzer --train-net` | обучение MLP на всех инструментах barsSaver (фьючерсы SPBFUT ×4). С `--sec` — один тикер |
| `python -m analyzer --sec CNY12.26 --net` | разовая запись CSV сети M1/M10/M30/H4/D1 из уже обученных весов |
| `python -m analyzer --net` | то же по всем инструментам |
| `python -m analyzer --watch-net --sec CNY12.26` | живой оверлей сети, такт M1. Закрытые строки CSV не переписывает. Окно не закрывать |
| `python -m analyzer --watch-net` | то же по всем инструментам |

Порядок: сначала `--train-net`, потом `--net` / `--watch-net`. После смены лосса (снятие `Wa`) веса переучить.

## Поиск похожей пачки D1

Не сеть и не odds. Доли без базы и lift. Подробнее: [tag-packs.md](tag-packs.md).

| команда | что делает |
|---|---|
| `python -m analyzer --sec CNY12.26 --pack-ahead` | пачка формирующегося D1 как запрос; аналоги на D1, H4, M30; исход — закрытие следующего D1 справа (без цепочки) |

## Архив odds (`*AnalyzerOdds`)

**Не развивать.** Кадр ведущий→M1, не парные связки. Продолжение — `--net`. Подробнее: [analyzer-odds.md](analyzer-odds.md).

| команда | что делает |
|---|---|
| `python -m analyzer --sec CNY12.26 --odds` | разовая выгрузка старого оверлея odds |
| `python -m analyzer --watch-odds --sec CNY12.26` | живой архивный оверлей |
| `python -m analyzer --watch-odds` | то же по всем инструментам |

CLI печатает предупреждение, что продолжение — `--net`.

## Тесты

| команда | что делает |
|---|---|
| `python -m unittest discover -s tests -t . -v` | все тесты пакета. Часть читает живые CSV barsSaver (GAZP); без файлов эти кейсы пропускаются |

## Служебное (не анализатор)

Исследование 121. Живой индикатор и `analyzer/one2one.py` от этих прогонов **не зависят**. Подробнее: [tools/README.md](../tools/README.md).

| команда | что делает |
|---|---|
| `python tools/one2one/extract_rpm_up_ini.py` | читает `C:\QuikFinam\finam.wnd`, пишет `config/RPM_TF_Up_5.ini` (секция D1 = пачка Small=`D5`) |
| `python tools/one2one/move_stats.py --help` | подбор параметров 121; остальные `tools/one2one/sweep_*.py` — разовые прогоны исследования |
