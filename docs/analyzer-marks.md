# Метки анализатора на графике QUIK

Анализатор считает сетапы `buy` / `sell` / `buy1` / `sell1` / `buy2` / `sell2` по CSV свечей.
Индикатор `*AnalyzerMarks` только рисует эти сетапы точками на цене.
Сами RPM на графике по-прежнему считает Lua (current / up / 121).

Исходник оверлея: [`lua/AnalyzerMarks.lua`](../lua/AnalyzerMarks.lua).

## Что должно быть запущено

Нужны **три** процесса. Без любого из них картинка не живая.

| # | Что | Зачем |
|---|---|---|
| 1 | QUIK + скрипт **[barsSaver](https://github.com/nick-nh/qlua/tree/master/barsSaver)** | пишет свечи |
| 2 | `python -m analyzer --watch` из корня репозитория | считает сетапы и пишет метки |
| 3 | индикатор **\*AnalyzerMarks** на ценовой панели M1 или M10 | рисует точки |

M30 и H4 анализатор для меток **не считает**. На этих ТФ индикатор ничего не рисует.

## Запуск

### 1. Свечи

В QUIK запустите Lua-скрипт [barsSaver](https://github.com/nick-nh/qlua/tree/master/barsSaver) (`C:\QuikFinam\LuaScripts\barsSaver\`). Описание автора: [nick-nh.github.io](https://nick-nh.github.io/2021-11-24/barsSaver-post). Наша установка, `sec_list` и параметры: [barsSaver.md](barsSaver.md).
Список инструментов: `sec_list.txt`. Для каждого тикера нужны интервалы 1, 10, 30, 240.

Файлы свечей:

`C:\QuikFinam\LuaScripts\barsSaver\data\{SEC}_{CLASS}_{ТФ}_.csv`

Примеры: `GAZP_TQBR_M10_.csv`, `CR_SPBFUT_M1_.csv`.

barsSaver дописывает строку, когда у бара **новое время** (закрылась предыдущая свеча). Тики текущей свечи в файл не попадают.

После правки `sec_list.txt` скрипт нужно **перезапустить**. Если M1 одного тикера перестал расти, а M10 того же тикера пишется — перезапустить barsSaver (обрыв datasource после disconnect QUIK).

### 2. Анализатор

Из корня репозитория:

```text
python -m analyzer --watch
```

Окно не закрывать. Каждые **11 секунд** в консоли строка `poll#… n=… dirty=… M1=… M10=…`. Если `dirty=0` — свечи не выросли, пересчёта нет, это не зависание. Ctrl+C останавливает.

Сначала считаются все грязные **M1**, потом **M10**. Грязная пачка занимает до **21 с**; если не влезли — строка `defer … next poll`. Для меток считаются последние ~6 тыс. баров M1 и ~2 тыс. M10, не вся история CSV. После короткого цикла пауза — остаток до 11 с, а не ещё 11 с сверху.

Другие варианты:

```text
python -m analyzer --watch --sec GAZP
python -m analyzer --marks
python -m analyzer --sec GAZP --marks
python -m analyzer --sec CNY12.26 --watch
```

`--marks` без `--watch` — разовая выгрузка и выход.
`--sec` не указан — все инструменты из папки data (TQBR и SPBFUT).
Класс по умолчанию TQBR; для имени на `CNY*` — SPBFUT.

Код: пакет `analyzer/`.

### 3. Индикатор на графике

Скопировать `lua/AnalyzerMarks.lua` в:

`C:\QuikFinam\LuaIndicators\AnalyzerMarks.lua`

На графике **M1** или **M10**:

1. Добавить индикатор `*AnalyzerMarks`.
2. Поставить его **на ценовую панель** (не в отдельное окно).
3. После обновления lua — снять и навесить заново или пересчитать.

Настройки:

- `OnsetOnly = 1` — точка только на первом баре серии (так и нужно).
- `ReloadSec = 15` — как часто смотреть, изменился ли CSV. Полная перерисовка только если файл реально обновился.
- `MarksDir` пустой — папка `LuaIndicators\analyzer_marks`.

## Куда пишутся метки

`C:\QuikFinam\LuaIndicators\analyzer_marks\{SEC}_{CLASS}_{ТФ}.csv`

Только M1 и M10. Пример: `GAZP_TQBR_M10.csv`.

Индикатор берёт `sec_code` и ТФ из окна графика и открывает соответствующий файл.

## Что видно на графике

| точка | сетап | где |
|---|---|---|
| зелёная | buy | под low |
| красная | sell | над high |
| голубая | buy1 | под low |
| оранжевая | sell1 | над high |
| жёлто-зелёная | buy2 | под low |
| сиреневая | sell2 | над high |

**buy** — small и middle: `vs0=below_0` `vs_ema=below_ema` `ema_vs0=below_0` `ema_trend=falling`; current: `vs0=below_0` `vs_ema=below_ema` `ema_vs0=below_0`; hist: `below_0` `hist_growing`.
**sell** — зеркало: small/middle выше 0 и выше EMA, EMA выше 0 и `rising`; current выше 0 и выше EMA; hist `above_0` `hist_growing`.
**buy1** — current: `below_0` `below_ema` `slope=rising_below_ema`; small: `above_0` `below_ema` `falling_below_ema` `ema_vs0=above_0` `ema_slope=falling`; middle: `above_0` `above_ema` `falling_above_ema` `ema_vs0=above_0` `ema_slope=falling`; hist: `above_0` `hist_shrinking`.
**sell1** — зеркало buy1.
**buy2** — current: `below_0` `below_ema` `ema_vs0=above_0` `ema_trend=falling`; small: `above_0` `above_ema` `ema_vs0=above_0` `ema_trend=rising` `slope=rising_above_ema`; middle: `above_0` `vs_ema=below_ema` `ema_vs0=above_0` `ema_trend=falling`; hist: `above_0` `hist_shrinking`.
**sell2** — зеркало buy2: middle `below_0` и `vs_ema=above_ema`.

`ema_trend` — наклон EMA за 5 баров, не шаг к предыдущему бару (`ema_slope`).

## Задержка

Новый бар в barsSaver → до 11 с простоя до следующего poll Python → очередь тикеров (до 21 с на пачку) → до 15 с до точек на графике.
Плюс формирующаяся свеча в CSV ещё не попала: на M1 это около минуты.
Если barsSaver не дописал M1, метки на этом ТФ стоят на последнем сохранённом баре, даже если график QUIK уже ушёл вперёд.

## Как добавить инструмент

1. В `C:\QuikFinam\LuaScripts\barsSaver\sec_list.txt` добавить **четыре** строки: interval 1, 10, 30, 240.
2. `sec_code` и `class_code` взять **как в QUIK** (CreateDataSource). Длинные имена фьючерсов часто не работают.
3. Перезапустить barsSaver, дождаться файлов в `data\`.
4. `--watch` подхватит новый тикер сам, когда появятся M1 и M10.

Пример акций:

```text
{ sec_code = "SBER", class_code = "TQBR", interval = 1 },
```

Фьючерс CNY декабрь 2026 в QUIK — это **CRZ6** / SPBFUT, файлы `CR_SPBFUT_*.csv`.
Имя `CNY12.26` в barsSaver даёт `unknown sec code`. На графике CNY12.26 индикатор всё равно читает файл `CR`.

## Если точек нет

- Запущен ли barsSaver, есть ли свежий CSV в `data\` **на тот же ТФ**, что график.
- Запущен ли `python -m analyzer --watch`, пишет ли он строки в консоль (`poll=11s budget=21s`).
- Есть ли файл меток в `analyzer_marks` на тот же тикер и ТФ, что график, и не обрывается ли он раньше последней свечи.
- Индикатор навешен на **цену** M1/M10, lua скопирован из `lua/AnalyzerMarks.lua` в `LuaIndicators`.
- Для фьючерса в `sec_list` короткий код (`CRZ6`, не `CNY12.26`).
