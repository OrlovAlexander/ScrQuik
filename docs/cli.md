# Команды

Запуск из **корня репозитория**. Python 3.10+. Данные свечей — barsSaver (`C:\QuikFinam\LuaScripts\barsSaver\data\`). Для `--train-net` / `--net` / `--watch-net` / `--watch-net-pool` нужен `numpy`.

Общий вид: `python -m analyzer [флаги]`. Справка: `python -m analyzer --help`.

## Общие флаги

| флаг | что |
|---|---|
| `--sec TICKER` | инструмент. Без него у `--marks` / `--watch` / `--odds` / `--watch-odds` / `--train-net` / `--net` / `--watch-net` / `--watch-net-pool` — все тикеры barsSaver (у архивного `--watch-waves` — тоже) |
| `--class-code CLASS` | класс. По умолчанию TQBR; имя на `CNY*` → SPBFUT. `--watch` без класса берёт и TQBR, и SPBFUT |
| `--json` | печать JSON вместо текста. Нельзя с `--watch`, `--watch-waves`, `--watch-odds`, `--watch-net`, `--watch-net-pool` |
| `--poll N` | простой секунд между проверками barsSaver у watch-команд. По умолчанию **11**. Окно не закрывать. Пачка грязных тикеров до **21** с, очередь ТФ: M1 → M10 → M30 → H4 → D1 |
| `--jobs N` | число процессов у `--watch-net-pool` и лимит в WatchNetUi. Без флага — по числу ядер, **не больше 8**. Явный `N>8` тоже **обрезается до 8** (иначе thrash: CPU есть, CSV почти не двигаются). `0` — по процессу на каждый инструмент (тяжёлый RAM, numpy; лимит 8 не применяется) |

`--sec` обязателен для снимка, `--combo`, `--m30`, `--pack-ahead` (и архивного `--waves`).

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

## Архив: волны (`*AnalyzerZigZag`)

**Архив.** Рудимент, **не развивать.** Подробнее: [analyzer-waves.md](analyzer-waves.md).

| команда | что делает |
|---|---|
| `python -m analyzer --sec CNY12.26 --waves` | разовая выгрузка зигзага/волн M1/M10/M30 |
| `python -m analyzer --watch-waves --sec CNY12.26` | живой CSV зигзага при росте barsSaver |
| `python -m analyzer --watch-waves` | то же по всем инструментам |

## Сеть (`*AnalyzerNet`)

Четыре головы ahead (1 / 5 / 10 / 20 M1) на одном векторе **связкаМ1М5М10М20** плюс доли трёх парных связок (цепочка 5), головы действия нет. Точка только на M10 — голова 10 M1, плюс согласие со средним и вето импульса. Пунктир — среднее четырёх. Веса: `C:\QuikFinam\LuaIndicators\analyzer_net\net.npz` или `net_{SEC}_{CLASS}.npz` (в git нет). Как ставят круг: [analyzer-net.md](analyzer-net.md#точка-обучение-и-живой-график).

| команда | что делает |
|---|---|
| `python -m analyzer --train-net` | обучение MLP на всех инструментах barsSaver (фьючерсы SPBFUT ×4). Пишет общий `net.npz` |
| `python -m analyzer --train-net --sec CNY12.26` | обучение с нуля только этого тикера в `net_CNY12.26_SPBFUT.npz`, общий `net.npz` не трогает |
| `python -m analyzer --sec CNY12.26 --net` | разовая запись CSV сети M1/M10/M30/H4/D1 из уже обученных весов (per-sec, иначе общий) |
| `python -m analyzer --net` | то же по всем инструментам |
| `python -m analyzer --watch-net --sec CNY12.26` | живой оверлей сети, такт M1. Закрытые пунктиры не переписывает. Веса не трогает. Окно не закрывать |
| `python -m analyzer --watch-net` | то же по всем инструментам **в одном процессе** (очередь грязных тикеров) |
| `python -m analyzer --watch-net-pool` | живой оверлей всех инструментов, несколько процессов `--watch-net` (по числу ядер, **макс. 8**; явный `--jobs 20` тоже обрежется до 8). В шарде очередь **fair**: сначала давно не обновлённые; за poll — **1** `export_net` (~60–90 с, до ~2 мин под нагрузкой). Не 52 процесса: numpy/OpenBLAS съедают RAM; >8 → thrash, CSV «стоят». Окно не закрывать. Ctrl+C гасит воркеров |
| `python -m analyzer --watch-net-pool --jobs 4` | явно 4 процесса, тикеры по round-robin |
| `python -m analyzer --watch-net-pool --jobs 0` | по процессу на каждый тикер; на 52 инструментах обычно MemoryError (лимит 8 на `jobs>0` не действует только у `0`) |
| `tools\watch-net-pool.cmd` | то же, что `--watch-net-pool` (аргументы после `.cmd` пробрасываются) |
| `dotnet run --project tools/WatchNetUi/WatchNetUi/WatchNetUi.csproj -c Release` | WPF-монитор пула: **Старт всех** = до 8 шардов `--watch-only` на все тикеры; возраст/ETA/«считает сейчас». Не запускать вместе с `--watch-net-pool`. См. [tools/WatchNetUi/README.md](../tools/WatchNetUi/README.md) |

Порядок: сначала `--train-net` (общий или `--sec`), потом `--net` / `--watch-net`. После смены связки или входа веса переучить: старый `net.npz` с другой связкой не загрузится. `--watch-net-pool` веса не трогает, только запускает живые `--watch-net`.

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

`extract_rpm_up_ini.py` ещё нужен для ini RPM-up. Остальное в `tools/one2one/` — **архив 121**, рудимент, не развивать. Подробнее: [tools/README.md](../tools/README.md).

| команда | что делает |
|---|---|
| `python tools/one2one/extract_rpm_up_ini.py` | читает `C:\QuikFinam\finam.wnd`, пишет `config/RPM_TF_Up_5.ini` (секция D1 = пачка Small=`D5`) |
| `python tools/one2one/move_stats.py --help` | архив: подбор параметров 121; `sweep_*.py` не развивать |
