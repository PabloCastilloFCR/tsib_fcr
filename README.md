# tsib-fcr — Time Series Initialization for Buildings (Chile Fork)

**Version 0.2.0-cl** · Fork of [FZJ-IEK3-VSA/tsib](https://github.com/FZJ-IEK3-VSA/tsib) adapted for Chilean residential buildings by [Fraunhofer Chile Research](https://www.fraunhofer.cl).

This fork adapts the ISO 13790 5R1C residential building thermal model to the Chilean context: Chilean building archetypes (pre-normativa and DS50), a BD Ancestral weather adapter, and a solver-free direct simulation path for thermal demand calculation.

---

## What's different from upstream tsib

| Feature | Upstream tsib | tsib-fcr |
|---------|--------------|----------|
| Archetype catalogue | Germany (TABULA/EPISCOPE) | + Chile (27 archetypes, `CL_episcope.csv`) |
| Weather adapter | DWD Testreferenzjahre (Germany) | + BD Ancestral TMY (`bd_tmy_to_tsib`) |
| Demand calculation | LP solver required (HiGHS/CBC) | `sim_demand_direct()` — no solver needed |
| Country kwarg | `'DE'` only | + `'CL'` with Chilean defaults |

---

## Installation

Clone and install in editable mode:

```bash
git clone https://github.com/your-org/tsib_fcr.git
cd tsib_fcr
pip install -e .
```

No solver installation required for demand-only simulations. The original `sim5R1C` optimization path still requires a solver (HiGHS recommended):

```bash
pip install highspy
```

---

## Quick start

### 1. Compute heating demand for a Chilean building

```python
import numpy as np
import pandas as pd
import tsib

# Weather data — hourly TMY with DatetimeIndex
rng = pd.date_range("2024-01-01", periods=8760, freq="h")
tmy = pd.DataFrame({
    "T":   ...,   # dry-bulb temperature [°C]
    "DHI": ...,   # diffuse horizontal irradiance [W/m²]
    "DNI": ...,   # direct normal irradiance [W/m²]
    "GHI": ...,   # global horizontal irradiance [W/m²]
}, index=rng)

# Configure building — Chilean archetype, DS50 standard, wood-frame
cfg_obj = tsib.BuildingConfiguration({
    "ID":          "CL.SFH.DS50.mad",   # archetype ID from CL_episcope.csv
    "country":     "CL",
    "a_ref":       70.0,                # conditioned floor area [m²]
    "weatherData": tmy,
    "weatherID":   "my_location",
    # optional: override U-values from archetype CSV
    "U_Wall_1":    0.6,                 # [W/(m²·K)]
    "U_Roof_1":    0.6,
    "U_Floor_1":   0.5,
    "U_Window_1":  2.8,
    "refurbishment": False,
})
cfg = cfg_obj.getBdgCfg(includeSupply=True)

# Inject occupancy / internal-gain profiles
cfg["Q_ig"]         = np.full(8760, 0.3)   # internal gains [kW]
cfg["occ_nothome"]  = pd.Series(np.zeros(8760), index=rng)
cfg["occ_sleeping"] = pd.Series(np.zeros(8760), index=rng)
cfg["elecLoad"]     = pd.Series(np.zeros(8760), index=rng)
cfg["hotWaterLoad"] = pd.Series(np.zeros(8760), index=rng)

# Run direct 5R1C simulation (no solver required)
model = tsib.Building5R1C(cfg)
model.sim_demand_direct()

# Annual heating demand [kWh/m²/a]
q_h_nd = model.detailedResults["Heating Load"].sum() / 70.0
print(f"Heating demand: {q_h_nd:.1f} kWh/m²/a")
```

### 2. Convert BD Ancestral TMY to tsib format

```python
import pandas as pd
import tsib

# bd_df: DataFrame from BD Ancestral with columns tdry, dhi, dni, ghi, ...
tsib_tmy = tsib.bd_tmy_to_tsib(bd_df)
# → returns DataFrame with columns T, DHI, DNI, GHI, ... and DatetimeIndex
```

### 3. Use tsorb for occupancy profiles (optional)

tsorb is the original occupancy stochastic model built into tsib. It requires pandas < 2.0 due to a `pd.datetime` deprecation. If you are on pandas ≥ 2.0, inject profiles manually as shown above.

---

## Chilean archetypes

Archetypes are stored in [`tsib/data/episcope/CL_episcope.csv`](tsib/data/episcope/CL_episcope.csv). Each row defines the geometry and envelope properties of one Chilean building type.

### ID convention

```
CL.<type>.<standard>.<construction>
```

| Segment | Values | Meaning |
|---------|--------|---------|
| `CL` | — | Chile |
| `<type>` | `SFH`, `MFH`, `AB` | Single-family, multi-family, apartment block |
| `<standard>` | `preN`, `intN`, `DS50` | Pre-normativa, intermediate normativa, DS50 |
| `<construction>` | `mad`, `lad`, `mam`, `hor` | Wood light, wood heavy, masonry, concrete |

**Examples:**

| ID | Description |
|----|-------------|
| `CL.SFH.preN.mad` | Single-family, pre-normativa, light wood frame |
| `CL.SFH.DS50.lad` | Single-family, DS50, heavy wood frame |
| `CL.MFH.intN.mam` | Multi-family, intermediate, masonry |
| `CL.AB.DS50.hor`  | Apartment block, DS50, reinforced concrete |

27 archetypes in total: 3 types × 3 standards × 3 constructions = 27 (AB only has `hor`).

### Chilean defaults applied when `country='CL'`

| Parameter | Value | Notes |
|-----------|-------|-------|
| Heating setpoint | 18 °C | |
| Cooling setpoint | 26 °C | |
| Infiltration rate | 0.8 ACH | typical unretrofitted Chilean housing |
| Heating system | Electric heater | |

U-values from the archetype CSV can be overridden per simulation call using `U_Wall_1`, `U_Roof_1`, `U_Floor_1`, `U_Window_1` kwargs.

---

## `sim_demand_direct()` — solver-free demand calculation

`Building5R1C.sim_demand_direct()` computes annual heating and cooling demand by solving the ISO 13790 5R1C energy balance analytically at each hourly timestep, without building or solving an LP.

**Algorithm:**
1. Extracts 5R1C parameters (conductances, thermal mass, profiles) via existing tsib machinery.
2. Precomputes per-timestep gain vectors `Q_m` (mass node) and `Q_st` (surface/star node) from irradiance and internal gain profiles.
3. Runs a forward-Euler time loop: at each step, analytically solves for free-float air temperature; if below heating setpoint, computes required `Q_H`; if above cooling setpoint, computes required `Q_C`.
4. Iterates up to 5 times for the annual periodic boundary condition (start and end mass temperature converge to < 0.01 K).

**Results written to `model.detailedResults`:**

| Key | Unit | Description |
|-----|------|-------------|
| `"Heating Load"` | kW | hourly heating power |
| `"Cooling Load"` | kW | hourly cooling power |
| `"Electricity Load"` | kW | hourly electricity demand |
| `"T_air"` | °C | indoor air temperature |
| `"T_s"` | °C | surface/star node temperature |
| `"T_m"` | °C | thermal mass temperature |

`sim_demand()` is an alias for `sim_demand_direct()` kept for backwards compatibility.

The original `sim5R1C()` method remains available for full refurbishment optimization (requires a Pyomo-compatible LP solver).

---

## Package structure

```
tsib/
  buildingconfig.py          — BuildingConfiguration: kwarg validation, archetype lookup
  buildingmodel.py           — Building class (high-level wrapper)
  thermal/
    model5R1C.py             — Building5R1C: 5R1C model + sim_demand_direct + sim5R1C
  data/episcope/
    episcope.csv             — TABULA/EPISCOPE EU archetypes (upstream, read-only)
    CL_episcope.csv          — Chilean archetypes (27 rows)
  weather/
    testreferenceyear.py     — German DWD TRY adapter
    chile.py                 — BD Ancestral TMY adapter (bd_tmy_to_tsib)
```

---

## Running tests

```bash
# All tests
pytest test/ -v

# Chile-specific smoke tests only
pytest test/test_chile.py -v
```

The Chile tests verify:
1. `country='CL'` is accepted without error
2. Pre-normativa SFH in cold zone (Zona G) returns heating demand > 50 kWh/m²/a
3. DS50 SFH has lower heating demand than pre-normativa SFH in the same climate

---

## License

MIT License

Copyright (C) 2016–2022 Leander Kotzur (FZJ IEK-3), Timo Kannengießer, Kevin Knosala, Peter Stenzel, Peter Markewitz, Martin Robinius, Detlef Stolten (FZJ IEK-3)

Chile fork additions Copyright (C) 2024–2026 Fraunhofer Chile Research

See [LICENSE](LICENSE) for the full text.

---

## Original tsib citation

If you use the 5R1C thermal model in published work, please cite:

> Kotzur et al. (2018). *Impact of different time series aggregation methods on optimal energy system design.* Renewable Energy. [http://juser.fz-juelich.de/record/858675](http://juser.fz-juelich.de/record/858675)
