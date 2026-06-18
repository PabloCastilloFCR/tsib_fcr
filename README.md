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

Archetypes are stored in [`tsib/data/episcope/CL_episcope.csv`](tsib/data/episcope/CL_episcope.csv). 27 archetypes covering the Chilean residential stock, organized by building type × normative period × materialidad.

### ID convention

```
CL.{BuildingType}.{Period}.{Material}
```

| Segment | Values | Meaning |
|---------|--------|---------|
| `CL` | fixed | Country code |
| `BuildingType` | `SFH`, `MFH`, `AB` | Single-family home, multi-family home, apartment block |
| `Period` | `preN`, `intN`, `DS50` | Normative period (see below) |
| `Material` | `mad`, `lad`, `hor` | Materialidad (see below) |

### Building types

| Code | Full name | Storeys | Ref. area (m²) |
|------|-----------|---------|----------------|
| `SFH` | Vivienda unifamiliar | 1–2 | 60–70 |
| `MFH` | Edificio bajo | 4 | 55–65 |
| `AB` | Edificio en altura | 12–14 | 52–62 |

### Normative periods

| Code | Years | Regulation | Typical envelope |
|------|-------|------------|-----------------|
| `preN` | 1900–1999 | No thermal requirements | U_Wall 2.3–3.4, U_Win 5.8 W/m²K |
| `intN` | 2000–2015 | Reglamentación Térmica RT 2007 | U_Wall ~1.9, U_Win 3.5 W/m²K |
| `DS50` | 2016–2030 | DS50 Eficiencia Energética | U_Wall 0.6, U_Win 2.8 W/m²K |

### Materialidad

| Code | Material | Thermal mass | Infiltration (1/h) |
|------|----------|--------------|--------------------|
| `mad` | Madera — wood frame | Low | 0.50–0.80 |
| `lad` | Ladrillo — brick masonry | Medium | 0.25–0.50 |
| `hor` | Hormigón — concrete | High | 0.18–0.30 |

> Pre-normativa concrete walls were thin and uninsulated (~15 cm), giving U_Wall ≈ 3.4 W/m²K — higher than brick or wood of the same era. For `intN` and `DS50`, added insulation dominates and all three materials converge to similar U_Wall values.

### Complete archetype table

| ID | Type | Period | Material | Storeys | A_C_Ref (m²) | U_Wall | U_Roof | U_Floor | U_Win | g_gl_n | n_Inf |
|----|------|--------|----------|---------|--------------|--------|--------|---------|-------|--------|-------|
| CL.SFH.preN.mad | SFH | preN | Madera | 1 | 60 | 2.7 | 2.5 | 1.4 | 5.8 | 0.87 | 0.80 |
| CL.SFH.preN.lad | SFH | preN | Ladrillo | 1 | 60 | 2.3 | 2.5 | 1.4 | 5.8 | 0.75 | 0.50 |
| CL.SFH.preN.hor | SFH | preN | Hormigón | 1 | 60 | 3.4 | 2.5 | 1.4 | 5.8 | 0.75 | 0.30 |
| CL.SFH.intN.mad | SFH | intN | Madera | 1 | 65 | 1.9 | 1.5 | 0.8 | 3.5 | 0.75 | 0.60 |
| CL.SFH.intN.lad | SFH | intN | Ladrillo | 1 | 65 | 1.9 | 1.5 | 0.8 | 3.5 | 0.75 | 0.50 |
| CL.SFH.intN.hor | SFH | intN | Hormigón | 1 | 65 | 1.9 | 1.5 | 0.8 | 3.5 | 0.75 | 0.30 |
| CL.SFH.DS50.mad | SFH | DS50 | Madera | 2 | 70 | 0.6 | 0.6 | 0.5 | 2.8 | 0.60 | 0.50 |
| CL.SFH.DS50.lad | SFH | DS50 | Ladrillo | 2 | 70 | 0.6 | 0.6 | 0.5 | 2.8 | 0.60 | 0.40 |
| CL.SFH.DS50.hor | SFH | DS50 | Hormigón | 2 | 70 | 0.6 | 0.6 | 0.5 | 2.8 | 0.60 | 0.25 |
| CL.MFH.preN.mad | MFH | preN | Madera | 4 | 55 | 2.7 | 2.5 | 1.4 | 5.8 | 0.87 | 0.70 |
| CL.MFH.preN.lad | MFH | preN | Ladrillo | 4 | 55 | 2.3 | 2.5 | 1.4 | 5.8 | 0.75 | 0.45 |
| CL.MFH.preN.hor | MFH | preN | Hormigón | 4 | 55 | 3.4 | 2.5 | 1.4 | 5.8 | 0.75 | 0.25 |
| CL.MFH.intN.mad | MFH | intN | Madera | 4 | 60 | 1.9 | 1.5 | 0.8 | 3.5 | 0.75 | 0.55 |
| CL.MFH.intN.lad | MFH | intN | Ladrillo | 4 | 60 | 1.9 | 1.5 | 0.8 | 3.5 | 0.75 | 0.45 |
| CL.MFH.intN.hor | MFH | intN | Hormigón | 4 | 60 | 1.9 | 1.5 | 0.8 | 3.5 | 0.75 | 0.25 |
| CL.MFH.DS50.mad | MFH | DS50 | Madera | 4 | 65 | 0.6 | 0.6 | 0.5 | 2.8 | 0.60 | 0.45 |
| CL.MFH.DS50.lad | MFH | DS50 | Ladrillo | 4 | 65 | 0.6 | 0.6 | 0.5 | 2.8 | 0.60 | 0.35 |
| CL.MFH.DS50.hor | MFH | DS50 | Hormigón | 4 | 65 | 0.6 | 0.6 | 0.5 | 2.8 | 0.60 | 0.22 |
| CL.AB.preN.mad  | AB  | preN | Madera | 12 | 52 | 2.7 | 2.5 | 1.4 | 5.8 | 0.87 | 0.60 |
| CL.AB.preN.lad  | AB  | preN | Ladrillo | 12 | 52 | 2.3 | 2.5 | 1.4 | 5.8 | 0.75 | 0.35 |
| CL.AB.preN.hor  | AB  | preN | Hormigón | 12 | 52 | 3.4 | 2.5 | 1.4 | 5.8 | 0.75 | 0.20 |
| CL.AB.intN.mad  | AB  | intN | Madera | 12 | 58 | 1.9 | 1.5 | 0.8 | 3.5 | 0.75 | 0.45 |
| CL.AB.intN.lad  | AB  | intN | Ladrillo | 12 | 58 | 1.9 | 1.5 | 0.8 | 3.5 | 0.75 | 0.35 |
| CL.AB.intN.hor  | AB  | intN | Hormigón | 12 | 58 | 1.9 | 1.5 | 0.8 | 3.5 | 0.75 | 0.18 |
| CL.AB.DS50.mad  | AB  | DS50 | Madera | 14 | 62 | 0.6 | 0.6 | 0.5 | 2.8 | 0.60 | 0.35 |
| CL.AB.DS50.lad  | AB  | DS50 | Ladrillo | 14 | 62 | 0.6 | 0.6 | 0.5 | 2.8 | 0.60 | 0.28 |
| CL.AB.DS50.hor  | AB  | DS50 | Hormigón | 14 | 62 | 0.6 | 0.6 | 0.5 | 2.8 | 0.60 | 0.18 |

All U-values in W/m²K. `g_gl_n` = solar transmittance of glazing. `n_Inf` = air infiltration rate (1/h).

### Geometry

Areas in the CSV are derived from the reference floor area:

```
A_Roof_1   = A_C_Ref / n_Storey
A_Floor_1  = A_C_Ref / n_Storey
A_Wall_1   = 4 × sqrt(A_C_Ref / n_Storey) × n_Storey × 2.4   [ceiling height 2.4 m]
A_Window_1 = A_Wall_1 × WWR
```

Window-to-wall ratios: SFH = 0.15, MFH = 0.17, AB = 0.20. Window area is split equally across the four cardinal orientations.

### Zone-specific U-values

The CSV stores zone-neutral default U-values. Override them per simulation call to apply zone- and period-specific values without needing separate CSV rows per zone:

```python
cfg = tsib.BuildingConfiguration({
    "ID":      "CL.SFH.preN.mad",
    "country": "CL",
    "a_ref":   60,
    "weatherData": tmy,
    "weatherID": "zona_g",
    # zone-specific overrides:
    "U_Wall_1":       2.7,
    "U_Roof_1":       2.5,
    "U_Floor_1":      1.4,
    "U_Window_1":     5.8,
    "n_Infiltration": 0.80,
    "g_gl_n":         0.87,
})
```

This allows 27 geometry archetypes × 7 thermal zones without needing 189 CSV rows.

### Chilean defaults applied when `country='CL'`

| Parameter | Value |
|-----------|-------|
| Heating setpoint | 18 °C |
| Cooling setpoint | 26 °C |
| Infiltration rate | 0.8 ACH |
| Heating system | Electric heater |

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

## Examples

| Script | Description |
|--------|-------------|
| [`examples/santiago_ab_calibration.py`](examples/santiago_ab_calibration.py) | Real-world calibration of a 219-unit concrete apartment block in downtown Santiago (2005) against monthly gas billing data. Covers ACS + heating demand separation, gas volume conversion, and monthly error breakdown. |

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
