# Архитектура модуля дивергенций

Файл: `RPM_TF_Up_5.lua`, блок начиная с комментария `-- --- дивергенции RPM ---`.

---

## Общая схема

```
Свеча графика (index)
    |
    +-- updatePriceFractal()     — фракталы H/L на TF графика
    +-- trackSegmentLayer()      — сегмент по segId (= #aggregatedBars слоя)
    |       segId меняется → confirm сегмент → confirmedSegs[]
    +-- invalidateDivLayer()     — сброс линий при пробое
    +-- scanDivergences()        — pivot'ы по сегментам → check*Divergences()

Отрисовка: fillDivLine() → divSmall1..4, divMidle1..4, divUp1..4
```

---

## Сегмент (segment)

RPM на графике **ступенчатый**: одно значение RPM на несколько свечей.

- `segId` = номер бара в агрегированном массиве слоя (`#smallPrice`, `#midlePrice`, `#upPrice`).
- Пока `segId` не меняется — накапливаются:
  - `rpmMax`, `rpmMin`, индексы на графике
  - `priceMax`, `priceMin` внутри сегмента
- При смене `segId` — предыдущий сегмент **подтверждается** в `confirmedSegs`.

---

## Pivot по сегментам

**Pivot high:** локальный максимум `rpmMax` среди соседних сегментов (`DIV_SEG_PERIOD`) **и** фрактал цены на `priceMaxIdx` внутри сегмента.

**Pivot low:** аналогично для `rpmMin` / `priceMinIdx` / `fractalL`.

---

## Структура записи дивергенции (`divBuf`)

```lua
{
    kind      = "bear",       -- см. terminology.md
    strength  = "I",          -- I | II | III | nil
    pivotSpan = 1,            -- 1 | 2 | 3
    segId1, segId2,
    idx1, idx2,               -- индексы на TF графика
    rpm1, rpm2,
    price1, price2,
}
```

Кольцевой буфер: `DIV_SLOTS = 4` на слой. Дубликаты (тот же kind + pivotSpan + segId1/2) не добавляются.

---

## Функции

| Функция | Назначение |
|---------|------------|
| `newDivLayer()` | состояние слоя |
| `updatePriceFractal()` | фракталы цены |
| `trackSegmentLayer()` | трекинг сегментов |
| `segPivotHigh` / `segPivotLow` | pivot RPM + фрактал цены |
| `checkHighDivergences` / `checkLowDivergences` | детекция kind |
| `scanDivergences` | обход pivotSpan 1..3 |
| `invalidateDivLayer` | инвалидация по пробою цены/RPM |
| `processDivLayer` | вызов на каждом баре слоя |
| `fillDivLine` | интерполяция линии между idx1 и idx2 |

---

## Линии в Init()

| Линии | Слой | Стиль |
|-------|------|-------|
| `divSmall1` … `divSmall4` | Small | TYPE_DASH, W=1, цвет rpmSmall |
| `divMidle1` … `divMidle4` | Midle | TYPE_DASH, W=1, цвет rpmMidle |
| `divUp1` … `divUp4` | Up | TYPE_DASH, W=1, цвет rpmUp |

Всего **25 линий** (гистограммы + zero + 3×RPM + 3×EMA + 12 div).

---

## Отличие v4 и v5

| | RPM_TF_Up_4 | RPM_TF_Up_5 |
|---|-------------|-------------|
| Линий | 13 | 25 |
| Дивергенции | нет | да |
| `*_DivDraw` | нет | да (default 0) |
