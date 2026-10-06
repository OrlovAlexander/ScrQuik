# Исследование One2One 121

**Архив.** Рудимент, **не развивать.** Скрипты подбора параметров паттерна 121. Живой индикатор и анализатор от этих прогонов **не зависят**. Код `analyzer/one2one.py`, `config/One2One_121.ini`, `*One2One_121` оставлен.

Исключение: `extract_rpm_up_ini.py` ещё пишет `config/RPM_TF_Up_5.ini` из `finam.wnd` — это не 121.

Запуск из корня репозитория:

```text
python tools/one2one/extract_rpm_up_ini.py
python tools/one2one/move_stats.py --help
```

Кэши `cache_*.json` и `move_stats_*.json` в git не входят. JSON с результатами sweep (`sweep_*.json`) — зафиксированные прогоны.

## WatchNetUi

WPF-монитор пула `--watch-net` (не 121): [WatchNetUi/README.md](WatchNetUi/README.md).

