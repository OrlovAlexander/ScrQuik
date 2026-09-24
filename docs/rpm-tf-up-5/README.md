# RPM_TF_Up_5 — дивергенции RPM

Документация по модулю дивергенций индикатора [`lua/RPM_TF_Up_5.lua`](../../lua/RPM_TF_Up_5.lua).

Сохранено из чата Cursor, август 2026. Актуальный файл в репозитории — v5; v4 и раньше в [`lua/archive/`](../../lua/archive/).

## Содержание

| Файл | Описание |
|------|----------|
| [01-chat-history.md](01-chat-history.md) | Хронология запросов и решений в чате |
| [02-terminology.md](02-terminology.md) | Классификация дивергенций (учебник + код) |
| [03-architecture.md](03-architecture.md) | Архитектура модуля дивергенций в v5 |
| [04-settings-and-usage.md](04-settings-and-usage.md) | Настройки, установка в QUIK, типичные проблемы |
| [05-changelog.md](05-changelog.md) | Изменения v4 → v5 |

## Файлы проекта

| Файл | Назначение |
|------|------------|
| `lua/archive/RPM_TF_Up_4.lua` | базовый индикатор без дивергенций (13 линий) |
| `lua/RPM_TF_Up_5.lua` | индикатор с модулем дивергенций |
| `lua/maLib.lua` | зависимость (агрегация TF, EMA) |
| `config/RPM_TF_Up_5.ini` | живые слои Small/Middle/Up по ТФ графика (для Python) |

## Установка в QUIK

```text
C:\QuikFinam\LuaIndicators\RPM_TF_Up_5.lua
C:\QuikFinam\LuaIndicators\maLib.lua
```

После обновления файла — снять индикатор с графика и навесить снова.
