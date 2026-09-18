# Changelog — RPM_TF_Up_5 (дивергенции)

## v5 — модуль дивергенций (итоговое состояние)

### Добавлено

- Файл `RPM_TF_Up_5.lua` на базе v4
- 12 линий дивергенций (4×3 слоя), TYPE_DASH
- Segment-based pivot detector для ступенчатых RPM
- Настройки `1_Small_DivDraw`, `2_Midle_DivDraw`, `3_Up_DivDraw` (default 0)
- Виды `kind`:
  - `bear`, `bull` — классические (strength I)
  - `hidden_bear`, `hidden_bull` — скрытые
  - `extended_bear`, `extended_bull` — расширенные (strength II)
  - `weak_bear`, `weak_bull` — тип III (strength III)
- Поле `strength`: I / II / III
- `pivotSpan` 1/2/3 — расстояние между pivot'ами (не тип I/II/III)
- Инвалидация линий при пробое
- `getSetting()` — корректная работа с `0`

### Исправлено

- Nil-guards для H/L/RPM (ошибка line 651)
- v4 очищен от кода дивергенций

### Константы

```lua
DIV_SLOTS             = 4
DIV_PRICE_PERIOD      = 5
DIV_SEG_PERIOD        = 1
DIV_EXTENDED_PCT      = 0.003
DIV_WEAK_RPM_PCT      = 0.015
DIV_WEAK_PRICE_PCT    = 0.005
```

---

## v4 — без дивергенций

- 13 линий: гистограммы, zero, RPM×3, EMA×3
- `*_HistDraw = 0` по умолчанию
- База для сравнения и отката

---

## Возможные следующие шаги (не реализовано)

- [ ] Лог детекции дивергенций в файл
- [ ] Отдельные цвета/стили для strength I/II/III
- [ ] Больше 4 слотов буфера или настройка `DIV_SLOTS`
- [ ] Ослабление фрактала/сегмента для H4 + H6/H8/D1
- [ ] Настройки порогов через `_G.Settings` вместо констант
