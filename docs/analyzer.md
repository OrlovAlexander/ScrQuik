# 

Python    ,  Lua   QUIK,  CSV `barsSaver`.     RPM-.     : [analyzer-marks.md](analyzer-marks.md).

## 

    ( `.cursor/rules/chart-tf-analysis.mdc`):

-  : RPM-current + RPM-up;
- 121   M30;
-  up   `config/RPM_TF_Up_5.ini`,    ****,    Lua    `sec_code`.

## 

|  |  |
|---|---|
| `analyzer/bars.py` | CSV barsSaver,   (`CNY12.26` / `CRZ6` -> `CR_SPBFUT_*.csv`) |
| `analyzer/ema.py` | EMA |
| `analyzer/rpm_current.py` | FIR 12 + EMA(90),      (`floor(n/2)+1`,  Lua) |
| `analyzer/rpm_up.py` |  Small/Middle/Up, ,  |
| `analyzer/settings.py` | `config/RPM_TF_Up_5.ini`, `config/One2One_121.ini` |
| `analyzer/one2one.py` | 121  M30 |
| `analyzer/neighbors.py` |        |
| `analyzer/states.py` |  vs0 / vs_ema / slope / ema_vs0 / ema_slope / ema_trend / hist |
| `analyzer/combo.py` |  buy/sell/buy1/sell1/buy2/sell2,   |
| `analyzer/price.py` |    |
| `analyzer/snapshot.py` |     M1/M10/M30/H4 |
| `analyzer/marks.py` | CSV   `--watch` |
| `analyzer/__main__.py` | CLI |

  (  ||): `NEAR_ZERO=0.25`, `NEAR_EMA=0.15`, `NEAR_SLOPE=0.08`, `NEAR_HIST=0.15`.  EMA   5 .

      ,    ini `HistDraw=1` (M1/M30/H4  Up, M10  Small).

## CLI

  :

```text
python -m analyzer --sec GAZP
python -m analyzer --sec GAZP --json
python -m analyzer --sec GAZP --combo
python -m analyzer --sec GAZP --m30
python -m analyzer --sec GAZP --marks
python -m analyzer --marks
python -m analyzer --watch
python -m analyzer --watch --sec CNY12.26
```

 `--sec`  `--marks` / `--watch`      data.    TQBR;   `CNY*` -> SPBFUT. `--watch`  `--class-code`   TQBR,  SPBFUT.

`--combo`    H4->M1   M1 >= 1%. `--m30`   M30 >= 3%   M1/M10  .

## 

  `setup_signal`: buy, sell, buy1, sell1, buy2, sell2,  `none`.

- **buy / sell**    small+middle+current+hist.
- **buy1 / sell1**    M10 25.08.2026 17:20.
- **buy2 / sell2**   Si M1 22.09.2026 18:55 (middle   EMA: buy2  EMA, sell2 ).

    [analyzer-marks.md](analyzer-marks.md).

## 

CSV: ρμ. [barsSaver.md](barsSaver.md). Τΰιλϋ:

`C:\QuikFinam\LuaScripts\barsSaver\data\{SEC}_{CLASS}_{TF}_.csv`

    ~6000 M1  ~2000 M10.    CSV  :  ,     .

## 

```text
python -m unittest discover -s tests -t . -v
```

 RPM,  ini, ,  `--watch` (M1  M10)   QUIK.  GAZP    CSV barsSaver  .
