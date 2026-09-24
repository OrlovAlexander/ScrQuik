# Исследование One2One 121

Скрипты подбора параметров паттерна 121. Живой индикатор и анализатор **не** зависят от этих прогонов: на графике Lua, в Python — `analyzer/one2one.py` и `config/One2One_121.ini`.

Запуск из корня репозитория:

```text
python tools/one2one/move_stats.py --help
python tools/one2one/extract_rpm_up_ini.py
```

`extract_rpm_up_ini.py` читает `C:\QuikFinam\finam.wnd` и пишет `config/RPM_TF_Up_5.ini`.

Кэши `cache_*.json` и `move_stats_*.json` в git не входят. JSON с результатами sweep (`sweep_*.json`) — зафиксированные прогоны.
