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

### 3. Compute setpoints, availability masks and DHW for MERLIN-style scenarios

```python
import numpy as np

n = len(tmy)
hour = np.array([ts.hour for ts in tmy.index])

# Night setback + heating switched off overnight — no infinite setpoints needed.
heating_setpoint  = np.where(hour < 6, 16.0, 20.0)
cooling_setpoint  = np.full(n, 26.0)
heating_available = hour >= 6

model = tsib.Building5R1C(cfg)
model.sim_demand_direct(
    heating_setpoint=heating_setpoint,
    cooling_setpoint=cooling_setpoint,
    heating_available=heating_available,
)

# Domestic hot water (ACS), independent of the space-heating system:
dhw = tsib.calculate_dhw_load(
    index=tmy.index,
    persons=3,
    liters_per_person_day=40,
    target_temp_c=55,
    t_mains=tmy["t_mains"],   # from bd_tmy_to_tsib, see §2
)
```

See the "`sim_demand_direct()`" and "Domestic hot water" sections below for details.

### 4. Occupancy profiles — currently unavailable in this fork

`tsib.getHouseholdProfiles()` (upstream tsib's stochastic occupancy/electricity/DHW
generator, built on the `tsorb` package) was **removed from this fork** in commit
`ef5f172` ("Remove VisualizeOccupancy script and related household profile
functionalities"). `Building._get_occupancy_profile()` still calls it, but the
function no longer exists anywhere in `tsib` — that code path is dead and will
raise `AttributeError` if reached. There is no version-gated fallback; it is
simply gone.

**Use the pattern above instead**: inject `Q_ig`, `elecLoad`, `occ_nothome`,
`occ_sleeping`, `hotWaterLoad` into `cfg` yourself (deterministically or from
your own occupancy model) and call `Building5R1C` / `sim_demand_direct()`
directly, exactly as `test/test_chile.py` and the examples in this README do.
Occupancy/behavioral assumptions are intentionally out of scope for this
fork — see [`feature-request/README_request.md`](feature-request/README_request.md)
for the rationale.

<details>
<summary>Reactivating <code>getHouseholdProfiles()</code> (not done — notes for a future PR)</summary>

**Root cause of the removal:** the installed `tsorb` package *is* present and
does define `getHouseholdProfiles`'s dependencies (`ElectricalLoadProfile`,
`DataExchangeCsv`), but `tsorb/ElectricalLoadProfile.py` calls
`pd.datetime(year, 1, 1)` (an alias removed from pandas ≥ 1.0). Under this
project's pinned pandas 2.2.3 that raises
`AttributeError: module 'pandas' has no attribute 'datetime'` the moment a
profile is generated — which is why the previous maintainer deleted the
calling code instead of leaving it silently broken.

Reactivation path, without forking `tsorb`:

1. Restore `tsib/household/profiles.py` and `tsib/household/__init__.py` from
   git history: `git show ef5f172~1:tsib/household/profiles.py`.
2. Re-add `from .household.profiles import simSingleHousehold, simHouseholdsParallel, getHouseholdProfiles`
   to `tsib/__init__.py`.
3. Re-add `tsorb` to `requirements.txt`.
4. Apply a pandas-compatibility shim *before* `tsorb.ElectricalLoadProfile` is
   imported (e.g. at the top of `tsib/household/__init__.py`), instead of
   patching the installed package:
   ```python
   import datetime
   import pandas as pd
   if not hasattr(pd, "datetime"):
       pd.datetime = datetime.datetime
   ```
5. Re-verify `Building._get_occupancy_profile()` end-to-end — the config keys
   it depends on (`state_seed`, `varyoccupancy`, `mean_load`, `n_apartments`,
   `tsorb_device_load`, `hasFirePlace`) are all still validated in
   `buildingconfig.py`, so no config-side changes should be needed.
6. Add a regression test that exercises `Building.getHeatLoad()` through the
   stochastic path (not just the direct-path dummy-profile pattern used
   today), so it cannot silently break again.

</details>

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
2. Resolves hourly heating/cooling setpoints and availability masks (see below).
3. Precomputes per-timestep gain vectors `Q_m` (mass node) and `Q_st` (surface/star node) from irradiance and internal gain profiles. `Q_ig` is normalized via `tsib.as_hourly_series` and accepts a scalar, list, `np.ndarray` or `pd.Series`.
4. Runs a forward-Euler time loop: at each step, analytically solves for free-float air temperature; if below the hour's heating setpoint *and* heating is available, computes required `Q_H`; if above the hour's cooling setpoint *and* cooling is available, computes required `Q_C`; otherwise the air is left in free-float.
5. Iterates up to 5 times for the annual periodic boundary condition (start and end mass temperature converge to < 0.01 K).

**Signature:**

```python
model.sim_demand_direct(
    heating_setpoint=None,   # scalar / list / np.ndarray / pd.Series, °C
    cooling_setpoint=None,   # scalar / list / np.ndarray / pd.Series, °C
    heating_available=None,  # array-like of bool, hourly HVAC-on mask
    cooling_available=None,  # array-like of bool, hourly HVAC-on mask
)
```

- `heating_setpoint`/`cooling_setpoint` default to `None`, which reproduces
  the historical behavior exactly: constant setpoints from
  `cfg["comfortT_lb"]`/`cfg["comfortT_ub"]`. Any other input is normalized to
  an hourly array aligned to the weather index; `cooling_setpoint` must be
  strictly greater than `heating_setpoint` in every hour, and both must be
  finite (`ValueError` otherwise).
- `heating_available`/`cooling_available` represent "HVAC switched off" for a
  given hour **without ever using infinite or extreme finite setpoints**
  (e.g. -20 °C / 60 °C): when unavailable, the indoor air is simply left to
  free-float and the corresponding load is 0. Default: available every hour.

**Results written to `model.detailedResults`:**

| Key | Unit | Description |
|-----|------|-------------|
| `"Heating Load"` | kW | hourly heating power |
| `"Cooling Load"` | kW | hourly cooling power |
| `"Electricity Load"` | kW | hourly electricity demand |
| `"T_air"` | °C | indoor air temperature |
| `"T_s"` | °C | surface/star node temperature |
| `"T_m"` | °C | thermal mass temperature |
| `"Heating Setpoint"` | °C | heating setpoint actually used, per hour |
| `"Cooling Setpoint"` | °C | cooling setpoint actually used, per hour |

`sim_demand()` is an alias for `sim_demand_direct()` kept for backwards compatibility (called with no arguments, same as before).

The original `sim5R1C()` method remains available for full refurbishment optimization (requires a Pyomo-compatible LP solver); the setpoint/availability arguments above are only supported by the direct path.

---

## Domestic hot water (`calculate_dhw_load`)

Computes DHW *useful thermal* demand (not final energy) from a water-mains
temperature series, independent of any heating/DHW equipment:

```python
dhw = tsib.calculate_dhw_load(
    index=tmy.index,
    persons=3,                    # scalar or hourly array/Series
    liters_per_person_day=40,
    target_temp_c=55,
    t_mains=tmy["t_mains"],       # scalar or hourly array/Series, °C
    profile=None,                 # None → flat 1/24 per hour; or an hourly
                                   # draw-off shape from normalize_daily_shape()
    t_mains_nan_policy="raise",   # "raise" | "interpolate"
)
# columns: "DHW Load" [kWh/h], "DHW Liters", "DHW DeltaT", "T_mains"
```

`Q_DHW_h = liters_h * deltaT_h * 0.001163` with `liters_h = persons_h *
liters_per_person_day * profile_h` and `deltaT_h = max(target_temp_c -
t_mains_h, 0)`. If the daily `profile` sums to 1, the annual volume equals
`persons * liters_per_person_day * n_days`.

Related utilities in `tsib.profiles` (also exported at package level):

- `as_hourly_series(value, index, name)` — normalizes scalar/list/ndarray/Series to an hourly array, rejecting non-finite values and length mismatches.
- `normalize_daily_shape(index, daily_shape_weekday, daily_shape_weekend, holidays=None)` — tiles two 24-value daily shapes over a full year.
- `normalize_profile_to_annual_energy(profile, annual_kwh)` — scales a relative profile to a target annual sum.
- `convert_thermal_to_final(load, efficiency=None, cop=None)` — thin system-conversion helper (useful thermal → final energy), deliberately kept out of the thermal engine.

---

## Water mains temperature (`t_mains`) in `bd_tmy_to_tsib`

`bd_tmy_to_tsib` recognizes several input column name variants for the water
mains (cold feed) temperature and standardizes them to a `t_mains` column:

```
t_mains, tmains, tmain, t_water_mains, t_mains_c, temp_mains,
temp_water_mains, t_red, temp_red, temperatura_red, t_agua_red, temp_agua_red
```

```python
tsib_tmy = tsib.bd_tmy_to_tsib(bd_df, t_mains_nan_policy="interpolate")
tsib_tmy.attrs["t_mains_source"]
# one of: "observed", "observed_interpolated",
#         "observed_partial_fallback_from_tdry", "estimated_from_tdry"
```

- If a recognized column is present with partial nulls, `t_mains_nan_policy`
  controls how they're filled: `"raise"`, `"interpolate"` (default, linear +
  edge fill) or `"fallback_from_tdry"` (fills only the nulls with a 30-day
  rolling mean of dry-bulb temperature).
- If no recognized column is present, `bd_tmy_to_tsib` **does not silently
  invent data without saying so**: it emits a `UserWarning` and estimates
  `t_mains` as a 30-day rolling mean of dry-bulb temperature, marking
  `attrs["t_mains_source"] = "estimated_from_tdry"`. Pass
  `require_t_mains=True` to raise instead. Old TMYs without a mains-temperature
  column keep working unchanged (no exception by default).

---

## Units and conventions

| Variable | Unit | Notes |
|---|---:|---|
| `Q_ig` | kW | Hourly sensible internal gain. Accepts scalar/array/Series via `as_hourly_series`. |
| `elecLoad` | kW | Reported electricity load; not necessarily internal heat. |
| `hotWaterLoad` | kW | Legacy DHW cfg key, ignored by the thermal engine — use `calculate_dhw_load` instead. |
| `DHW Load` | kWh/h | DHW useful thermal demand, from `calculate_dhw_load`. |
| `Heating Load` / `Cooling Load` | kW | Useful thermal demand, from `sim_demand_direct`. |
| `Heating Setpoint` / `Cooling Setpoint` | °C | Setpoint actually applied per hour. |
| `t_mains` | °C | Water mains (cold feed) temperature. |
| `T_air` / `T_s` / `T_m` | °C | Air / surface(star) / thermal-mass node temperatures. |

---

## Package structure

```
tsib/
  buildingconfig.py          — BuildingConfiguration: kwarg validation, archetype lookup
  buildingmodel.py           — Building class (high-level wrapper)
  profiles.py                — as_hourly_series, calculate_dhw_load, normalize_daily_shape,
                                normalize_profile_to_annual_energy, convert_thermal_to_final
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
| [`examples/santiago_AB/santiago_ab_calibration.py`](examples/santiago_AB/santiago_ab_calibration.py) | Real-world calibration of a 219-unit concrete apartment block in downtown Santiago (2005) against monthly gas billing data. Covers ACS + heating demand separation, gas volume conversion, and monthly error breakdown. |
| [`examples/chile/validation_direct_5r1c.py`](examples/chile/validation_direct_5r1c.py) | Reproducible, deterministic validation case for `sim_demand_direct()` with hourly setpoints and an HVAC availability mask (fixed archetype, synthetic TMY, no randomness). |
| [`examples/chile/validation_dhw.py`](examples/chile/validation_dhw.py) | Reproducible, deterministic validation case for `calculate_dhw_load()` with a synthetic hourly `t_mains` series and a normalized daily draw-off shape. |

---

## Running tests

```bash
# All tests
pytest test/ -v

# Chile-specific smoke tests only
pytest test/test_chile.py -v
```

`test/test_chile.py` covers:
1. `country='CL'` is accepted without error.
2. Pre-normativa SFH in cold zone (Zona G) returns heating demand > 50 kWh/m²/a.
3. DS50 SFH has lower heating demand than pre-normativa SFH in the same climate.
4. `sim_demand_direct()` hourly setpoints match the constant-scalar default, and it is a backwards-compatible no-arg call.
5. `heating_available=False` forces `Heating Load = 0` and lets `T_air` free-float, without infinite setpoints.
6. Non-finite or inverted (`cooling <= heating`) setpoints raise `ValueError`.
7. `Q_ig` gives identical results as a scalar, `np.ndarray`, or `pd.Series`, and rejects mismatched lengths.
8. `bd_tmy_to_tsib` preserves `t_mains` across all recognized column aliases, warns and estimates when absent, and interpolates partial nulls.
9. `calculate_dhw_load` reproduces `persons * liters_per_person_day` daily volume, varies with hourly `t_mains`, and honors the `t_mains_nan_policy`.

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
