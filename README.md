# ScrQuik

Индикаторы QUIK (QLua) и офлайн-анализатор тех же линий по CSV `barsSaver`.
Python повторяет раскладку живых графиков: на каждом ТФ один RPM-current и один RPM-up; паттерн 121 только на M30.

## Состав репозитория

```
lua/                 индикаторы QLua (копировать в QUIK)
lua/archive/         старые версии RPM-up
config/              ini RPM-up и 121
analyzer/            Python-пакет (снимок, сетапы, метки)
tests/               unittest
tools/one2one/       исследование параметров 121
docs/                документация
```

## Требования

- QUIK с QLua
- Python 3.10+
- скрипт [barsSaver](https://github.com/nick-nh/qlua/tree/master/barsSaver) (nick-nh) в QUIK (`C:\QuikFinam\LuaScripts\barsSaver\`); наша установка и `sec_list`: [docs/barsSaver.md](docs/barsSaver.md)

Зависимостей pip у анализатора нет.

## Установка индикаторов

Скопировать в `C:\QuikFinam\LuaIndicators\`:

| файл | зачем |
|---|---|
| `lua/maLib.lua` | библиотека TF / EMA |
| `lua/RPM_TF_Current.lua` | RPM текущего ТФ |
| `lua/RPM_TF_Up_5.lua` | RPM старших ТФ + гистограмма + дивер |
| `lua/One2One_121.lua` | паттерн 121 |
| `lua/one2oneLib.lua` | библиотека 121 |
| `lua/AnalyzerMarks.lua` | точки сетапов на цене |

После замены lua снять индикатор с графика и навесить снова.

Настройки RPM-up в репозитории: [`config/RPM_TF_Up_5.ini`](config/RPM_TF_Up_5.ini) (секция по ТФ **графика**, не по инструменту). На живом графике QUIK хранит свои значения в `finam.wnd`.

## Раскладка на графике

На M1, M10, M30, H4:

- один `*RPM_TF_Current`
- один `*RPM_TF_Up_5`

`*One2One_121` — **только M30**. `*AnalyzerMarks` — только M1 и M10, на ценовой панели.

Слои RPM-up (Small / Middle / Up):

| график | Small | Middle | Up (hist на M1/M30/H4) |
|---|---|---|---|
| M1 | Mn5 | Mn10 | Mn20 |
| M10 | Mn20 (hist) | Mn30 | H2 |
| M30 | H1 | H2 | H4 |
| H4 | H12 | D1 | W1 |

## Анализатор

Считает те же RPM и сетапы `buy` / `sell` / `buy1` / `sell1` / `buy2` / `sell2` по CSV свечей и пишет метки для `*AnalyzerMarks`.

```text
python -m analyzer --sec GAZP
python -m analyzer --sec GAZP --combo
python -m analyzer --marks
python -m analyzer --watch
```

`--watch` не закрывать: простой **11 с**, пачка грязных тикеров до **21 с**, сначала M1, потом M10.

Подробности запуска, задержки и сетапы: [docs/analyzer-marks.md](docs/analyzer-marks.md).
Архитектура Python: [docs/analyzer.md](docs/analyzer.md).
barsSaver: [docs/barsSaver.md](docs/barsSaver.md).

## Тесты

```text
python -m unittest discover -s tests -t . -v
```

Часть тестов читает живые CSV `barsSaver` (GAZP). Если файлов нет, эти кейсы пропускаются.

## Документация

- [docs/README.md](docs/README.md) — оглавление
- [docs/barsSaver.md](docs/barsSaver.md) — установка barsSaver и отличия от апстрима
- [docs/rpm-tf-up-5/](docs/rpm-tf-up-5/) — дивергенции RPM-up v5
- [lua/README.md](lua/README.md) — что копировать в QUIK
