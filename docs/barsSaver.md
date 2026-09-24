# barsSaver в этом проекте

Скрипт не входит в репозиторий. Исходник: [nick-nh/qlua/barsSaver](https://github.com/nick-nh/qlua/tree/master/barsSaver), описание автора: [nick-nh.github.io](https://nick-nh.github.io/2021-11-24/barsSaver-post). Код `barsSaver.lua` **не патчили**: отличие от апстрима — установка, список инструментов и режим работы.

Живая копия:

```text
C:\QuikFinam\LuaScripts\barsSaver\
  barsSaver.lua
  barsSaver_params.ini
  sec_list.txt
  log.lua
  maLib.lua
  data\
  logs\
```

Это **Lua-скрипт** (Сервисы → Lua-скрипты), не индикатор. `log.lua` и `maLib.lua` обязательны даже без EMA/MACD в списке.

## Что изменено относительно апстрима

### `sec_list.txt`

В апстриме примеры `SRZ1` / `RIZ1` с алгоритмами EMA/MACD. У нас только OHLC, без `algo`.

У каждого инструмента **четыре** интервала: `1`, `10`, `30`, `240` (M1 / M10 / M30 / H4). Другие ТФ анализатор не читает.

Список собран из открытых графиков (`finam.wnd`): акции TQBR и фьючерсы SPBFUT. Коды — как в `CreateDataSource`, не как заголовок графика.

| график | `sec_code` | `class_code` | файлы |
|---|---|---|---|
| акции | `SBER`, `GAZP`, … | `TQBR` | `{SEC}_TQBR_{TF}_.csv` |
| CNY12.26 | **`CRZ6`**, не `CNY12.26` | `SPBFUT` | `CR_SPBFUT_{TF}_.csv` (короткий корень фьючерса) |
| Si | **`SiZ6`**, не `Si` | `SPBFUT` | `Si_SPBFUT_{TF}_.csv` |

Имя `CNY12.26` в `sec_list` даёт `unknown sec code`. В строках CSV при этом остаётся полный код (`CRZ6`). Анализатор режет алиасы в `analyzer/bars.py`.

После правки `sec_list.txt` скрипт **перезапустить**.

### Режим записи

В `barsSaver.lua` / `barsSaver_params.ini` для живых меток:

| параметр | значение | зачем |
|---|---|---|
| `ONLY_HISTORY` | `0` | дописывать новые бары, пока скрипт запущен. `1` — снять историю и остановиться, `--watch` замирает |
| `str_startNewDayTime` / `str_startTradeTime` | `06:00:00` | вечерняя сессия фьючерсов |
| `str_endOfDay` | `23:50:00` | не резать день в 19:00 |
| `SERVER_DATA_CYCLE_TIME` | `-1` | не ждать «время сервера» (иначе простой после reconnect) |
| `MAX_LOCAL_TO_SERVER_TIME_DIFF` | `-1` | не стопорить из-за часов |

Строка в CSV появляется, когда у бара **новое время** (закрылась предыдущая свеча). Тики текущей свечи в файл не попадают.

Имя файла фьючерса без точки в коде обрезается (`CRZ6` → `CR`) — так устроен апстрим, не наша правка.

## Сбой после disconnect

После `OnDisconnected` datasource M1 одного тикера может перестать расти, а M10 того же тикера — писаться дальше. Тогда метки M1 стоят на последнем сохранённом баре, хотя график QUIK уже ушёл вперёд. Лечится **перезапуском barsSaver**.

## Как добавить инструмент

Четыре строки в `sec_list.txt`:

```text
{ sec_code = "SBER", class_code = "TQBR", interval = 1 },
{ sec_code = "SBER", class_code = "TQBR", interval = 10 },
{ sec_code = "SBER", class_code = "TQBR", interval = 30 },
{ sec_code = "SBER", class_code = "TQBR", interval = 240 },
```

Перезапустить скрипт, дождаться файлов в `data\`. `--watch` подхватит тикер, когда появятся M1 и M10.
