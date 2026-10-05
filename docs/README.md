# Документация

| документ | о чём |
|---|---|
| [tf-from-m1.md](tf-from-m1.md) | старшие ТФ из M1; история сигналов динамически такт M1; CSV старших — сверка на закрытии; формирующийся слот моргает |
| [tag-packs.md](tag-packs.md) | тег, пачка, парные связки D1–H4 / H4–M30 / M30–M10, цепочка, цепочка связок; поиск пачки D1 |
| [python-analyzer.md](python-analyzer.md) | Python-анализатор: модули, CLI, тесты |
| [analyzer-marks.md](analyzer-marks.md) | метки на графике M1/M10/M30/H4/D1: barsSaver, `--watch`, `*AnalyzerMarks`, теги сетапов |
| [analyzer-waves.md](analyzer-waves.md) | зигзаг на графике (`--watch-waves`, `*AnalyzerZigZag`); разметка 1–5 — предположение по Кречетову, не копия стратегии |
| [analyzer-odds.md](analyzer-odds.md) | `--odds` эволюционировал в сеть (`--net`); оверлей ведущий→M1 не развивать |
| [analyzer-net.md](analyzer-net.md) | нейронка: три головы ahead; точка M10/M30 = среднее трёх softmax и порог; `Wa` нет |
| [barsSaver.md](barsSaver.md) | установка и отличия от апстрима nick-nh |
| [barsSaver upstream](https://github.com/nick-nh/qlua/tree/master/barsSaver) | исходный скрипт выгрузки свечей |
| [rpm-tf-up-5/](rpm-tf-up-5/) | дивергенции `*RPM_TF_Up_5` |
| [qpile/readme.txt](qpile/readme.txt) | примеры QPILE (брокер / трейдер) |
| [import/](import/) | служебные trans-файлы |

Раскладка индикаторов на графике — в корневом [README.md](../README.md) и в `.cursor/rules/chart-tf-analysis.mdc`.
