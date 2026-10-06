# Документация

| документ | о чём |
|---|---|
| [cli.md](cli.md) | все команды `python -m analyzer` и служебные скрипты, с описанием каждой |
| [tf-from-m1.md](tf-from-m1.md) | старшие ТФ из M1; история сигналов динамически такт M1; CSV старших — сверка на закрытии; формирующийся слот моргает |
| [tag-packs.md](tag-packs.md) | тег, пачка, парные связки M1–M10 / M5–M10 / M10–M20, кадр сети связкаМ1М5М10М20, цепочка 5; поиск пачки D1 |
| [python-analyzer.md](python-analyzer.md) | Python-анализатор: модули, сетапы, тесты |
| [analyzer-marks.md](analyzer-marks.md) | метки на графике M1/M10/M30/H4/D1: barsSaver, `--watch`, `*AnalyzerMarks`, теги сетапов |
| [analyzer-waves.md](analyzer-waves.md) | **архив:** зигзаг `--waves` / `*AnalyzerZigZag`; рудимент, не развивать |
| [analyzer-odds.md](analyzer-odds.md) | `--odds` эволюционировал в сеть (`--net`); оверлей ведущий→M1 не развивать |
| [analyzer-net.md](analyzer-net.md) | нейронка связкаМ1М5М10М20 + доли трёх пар: четыре головы ahead 1/5/10/20; точка только M10; пул `--watch-net-pool` (макс. 8, fair); окно 6000 M1 и история D1 |
| [WatchNetUi](../tools/WatchNetUi/README.md) | WPF-монитор пула `--watch-net`: шарды, возраст CSV, export/круг |
| [barsSaver.md](barsSaver.md) | установка и отличия от апстрима nick-nh |
| [barsSaver upstream](https://github.com/nick-nh/qlua/tree/master/barsSaver) | исходный скрипт выгрузки свечей |
| [rpm-tf-up-5/](rpm-tf-up-5/) | дивергенции `*RPM_TF_Up_5` |
| [qpile/readme.txt](qpile/readme.txt) | примеры QPILE (брокер / трейдер) |
| [import/](import/) | служебные trans-файлы |

Раскладка индикаторов на графике — в корневом [README.md](../README.md) и в `.cursor/rules/chart-tf-analysis.mdc`.
