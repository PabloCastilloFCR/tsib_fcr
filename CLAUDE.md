# tsib_fcr — CLAUDE.md

Fork of [FZJ-IEK3-VSA/tsib](https://github.com/FZJ-IEK3-VSA/tsib) adapting the 5R1C residential building thermal model for Chile.
**Full implementation spec is in [`tsib_fcr_CLAUDE.md`](tsib_fcr_CLAUDE.md)** — read it before implementing anything.

---

## Dev commands

```bash
# Install in editable mode (from repo root)
pip install -e .

# Run all tests
pytest test/ -v

# Run Chile-specific tests only
pytest test/test_chile.py -v

# Verify solver is available
python -c "from pyomo.contrib import appsi; s = appsi.solvers.Highs(); print(s.available())"
```

---

## Current implementation status

| # | Task | File | Status |
|---|------|------|--------|
| 1.1 | Add `'CL'` to `KWARG_TYPES["country"]` | `tsib/buildingconfig.py:30` | ✅ |
| 1.2 | Add `KWARG_DEFAULTS_CL` + apply when `country=='CL'` | `tsib/buildingconfig.py` | ✅ |
| 1.3 | U-value override block at end of `_get_fabric` | `tsib/buildingconfig.py` | ✅ |
| 2 | Create `CL_episcope.csv` with 27 archetypes (later expanded, see task 12) | `tsib/data/episcope/CL_episcope.csv` | ✅ |
| 3a | Create `tsib/weather/chile.py` with `bd_tmy_to_tsib` | `tsib/weather/chile.py` | ✅ |
| 3b | Export `bd_tmy_to_tsib` from package | `tsib/__init__.py` | ✅ |
| 4 | Verify HiGHS solver works | env | ✅ |
| 5 | Create `test/test_chile.py` (3 smoke tests) | `test/test_chile.py` | ✅ |
| 6 | Bump version to `0.2.0-cl`, update package name | `setup.py` | ✅ |
| 7 | Hourly setpoints + HVAC availability mask in `sim_demand_direct` | `tsib/thermal/model5R1C.py` | ✅ |
| 8 | Normalize `Q_ig` (scalar/array/Series) via `as_hourly_series` | `tsib/thermal/model5R1C.py`, `tsib/profiles.py` | ✅ |
| 9 | `calculate_dhw_load` + profile utilities | `tsib/profiles.py` | ✅ |
| 10 | `t_mains` alias recognition + null-handling in `bd_tmy_to_tsib` | `tsib/weather/chile.py` | ✅ |
| 11 | Validation examples (`sim_demand_direct`, DHW) | `examples/chile/` | ✅ |
| 12 | `material`/`thermalZone` kwargs; merged `CL_episcope.csv` (810 rows, 6 materials incl. `met`/`adobe` from MINVU/NCh853 literature, 5-segment ID) replaces MERLIN-injected U-values | `tsib/buildingconfig.py`, `tsib/data/episcope/` | ✅ |

Tasks 7–11 implement the high-priority items from
[`feature-request/README_request.md`](feature-request/README_request.md) (a request
from the MERLIN_RCP integrator to move setpoint/DHW logic it was duplicating into
this fork). See the README sections "`sim_demand_direct()`", "Domestic hot water",
and "Water mains temperature" for usage. Item 8 of that request
(`getHouseholdProfiles()`) was deliberately **not** restored — see
"Occupancy profiles — currently unavailable in this fork" in README.md for why and
how to reactivate it.

---

## Architecture

```
tsib/
  buildingconfig.py     ← KWARG_TYPES, KWARG_DEFAULTS, BuildingConfiguration
  buildingmodel.py      ← Building class (calls buildingconfig + 5R1C)
  profiles.py           ← as_hourly_series, calculate_dhw_load, normalize_daily_shape,
                           normalize_profile_to_annual_energy, convert_thermal_to_final
  thermal/model5R1C.py  ← Pyomo LP/MILP optimization (requires solver) + sim_demand_direct
  data/episcope/
    episcope.csv        ← TABULA/EPISCOPE EU archetypes (read-only)
    CL_episcope.csv     ← Chile archetypes, fully resolved (810 rows: 3 types x 5 periods x 6 materials x 9 zones)
    CL_episcope_base.csv ← hand-authored 27-row geometry seed (input to build_cl_episcope.py, not read at runtime)
    CL_zone_uvalues.csv ← diagnostic-only U-value table (270 rows), built by build_cl_zone_uvalues.py, NOT read at runtime
    tabla_maestra_transmitancias_cev.parquet ← source CEV rating data (229k rows)
    build_cl_zone_uvalues.py ← CEV aggregation script (6 materials, pooled fallback + met/adobe literature constants), not imported at runtime
    build_cl_episcope.py     ← merges CL_episcope_base.csv + build_cl_zone_uvalues output -> CL_episcope.csv, not imported at runtime
  weather/
    testreferenceyear.py ← German TRY adapter
    chile.py            ← BD Ancestral TMY adapter (to be created)
```

### How archetype lookup works
`BuildingConfiguration.__init__` → validates kwargs against `KWARG_TYPES` → calls `_get_typ_building`, which either (a) reads the CSV row directly by `ID` (e.g. `"CL.SFH.RT2.hor.D"`), or (b) filters/sorts `iwu_bdgs` by `country`/`buildingYear`/`buildingType`/`material`/`thermalZone`/`surrounding`/`a_ref` and takes the best-fitting row. Every `CL_episcope.csv` row is now fully resolved (geometry + zone/period/material-specific U-values already baked in by `build_cl_episcope.py`), so `_get_fabric`'s existing `get_fabric()` call — which just reads `U_Actual_Wall_1` etc. off the resolved row — is already zone/period/material-correct with **no custom lookup logic needed at runtime**. `_get_fabric` then applies any explicit `U_Wall_1`/etc. kwargs (task 1.3), which always win over the row's own values.

Because each row's `Year1_Building`/`Year2_Building` reflect the fine 5-band vintage periods directly, the standard `buildingYear`-range filter (part of the generic country/buildingYear/buildingType/material/thermalZone/surrounding/a_ref filter chain, not CL-specific) resolves the correct period on its own — there is no separate zone-U-value table or period-binning function at runtime (there used to be; it was removed once the merge made it redundant — see task 12 and `tsib/data/episcope/build_cl_episcope.py`).

The U-value override (task 1.3) must run **after** `_get_fabric`'s own values, so it overwrites them — this is what keeps `test/test_chile.py` and `examples/chile/validation_direct_5r1c.py` (which pass explicit `U_*` kwargs) working.

---

## Interface contract (do not break)

MERLIN_RCP (consuming project) calls only:
- `tsib.BuildingConfiguration(kwargs_dict)` — for Chile, `kwargs_dict` includes `country="CL"`,
  `buildingYear`, `buildingType`, `material` (`"mad"`/`"lad"`/`"hor"`/`"met"`/`"prefab"`/`"adobe"`),
  and `thermalZone` (`"A"`–`"I"`, Chile's `zona_termica`). tsib resolves the archetype and its
  zone-specific U-values internally (see [Zone-specific U-values](README.md#zone-specific-u-values))
  — MERLIN_RCP does **not** compute or inject `U_Wall_1`/etc. itself; those kwargs remain available
  only as a manual override.
- `tsib.Building(cfg)` + `.getHeatLoad()` — OR, for the direct/no-solver path used by
  `test/test_chile.py` and MERLIN's real simulation script:
  `tsib.BuildingConfiguration(kwargs_dict, ignore_profiles=True).getBdgCfg(...)` →
  inject `Q_ig`/`elecLoad`/`occ_nothome`/`occ_sleeping`/`hotWaterLoad` into the cfg
  dict → `tsib.Building5R1C(cfg)` + `.sim_demand_direct(heating_setpoint=..., cooling_setpoint=..., heating_available=..., cooling_available=...)`
- `tsib.bd_tmy_to_tsib(df, t_mains_nan_policy=..., require_t_mains=...)`
- `tsib.calculate_dhw_load(...)`, `tsib.as_hourly_series(...)`, `tsib.normalize_daily_shape(...)`, `tsib.normalize_profile_to_annual_energy(...)`, `tsib.convert_thermal_to_final(...)`

No other tsib internals are used by MERLIN_RCP. Do **not** rely on
`tsib.getHouseholdProfiles()` — it was removed (see status table above).

---

## Key constraints

- **Solver required:** `model5R1C.py` uses Pyomo. HiGHS (`pip install highspy`) is the recommended solver. Without it simulations fail.
- **`_get_fabric` is the injection point:** U-value overrides (`U_Wall_1`, `U_Roof_1`, `U_Floor_1`, `U_Window_1`, `n_Infiltration`, `g_gl_n`) are passed as kwargs and must override CSV values at the end of `_get_fabric` (line 602).
- **KWARG validation runs first:** Any new kwarg passed to `BuildingConfiguration` must be registered in `KWARG_TYPES` or it will be silently dropped / raise a KeyError. The U-value override kwargs (`U_Wall_1` etc.) need to be added to `KWARG_TYPES` as `float`.
- **Chile archetypes are fully resolved, one row per (buildingType, period, material, zone):** `CL_episcope.csv` (810 rows) bakes zone/period/material-specific U-values directly into each row — there is no separate zone-U-value table at runtime (there used to be `CL_zone_uvalues.csv` + a custom period-binning function; both were retired once the merge made them redundant). Resolved internally via `material`+`buildingYear`+`buildingType`+`thermalZone` kwargs — MERLIN_RCP no longer computes/injects U-values (see Interface contract above). Regenerate via `tsib/data/episcope/build_cl_episcope.py`; never hand-edit `CL_episcope.csv` directly (edit `CL_episcope_base.csv` for geometry, or `build_cl_zone_uvalues.py` for U-value sourcing, then rerun both build scripts).
- **`existingHeatSupply` valid values:** must be one of the strings in `KWARG_TYPES["existingHeatSupply"]`. The Chilean default `"Electric resistance"` specified in the spec does **not** appear in that list — use `"Electric heater"` instead.

---

## CL_episcope.csv — implementation notes

The spec listed ~19 columns, but `get_shape` and `get_fabric` in `buildingconfig.py` access ~50. The actual CSV includes all required columns:

- **Secondary components** (`A_Wall_2/3`, `A_Roof_2`, `A_Floor_2`, `A_Window_2`) set to `0` — handles single-component Chilean envelope
- **Orientation split** — total `A_Window_1` distributed equally across N/E/S/W (25% each); `A_Window_Horizontal = 0`
- **`U_Actual_*`** — maps to `U_*` from spec; `get_fabric` writes these to `cfg["U_Wall_1"]` etc.
- **`b_Transmission_Wall_1 = 1.0`**, `b_Transmission_Floor_1 = 0.45` (ground contact), roofs `= 1.0`
- **Override key mapping** (implemented in `_get_fabric`): kwarg `U_Window_1` → `cfg["U_Window"]`, `g_gl_n` → `cfg["g_gl_n_Window"]`, `n_Infiltration` → `cfg["n_air_infiltration"]`
- **`Code_BuildingSizeClass`**: must be present — derived from second segment of `Code_BuildingVariant` (`SFH`/`MFH`/`AB`). Used to filter archetypes by `buildingType`; missing it causes fallback to European archetypes.
- **`Code_Period`** (`preRT`/`RT1`/`RT2`/`CEV`/`post2021`), **`Code_Material`** (`mad`/`lad`/`hor`/`met`/`prefab`/`adobe`), and **`Code_Zone`** (`A`–`I`): derived from the 3rd/4th/5th segments of `Code_BuildingVariant` by `build_cl_episcope.py`. All three are filter criteria in `_get_typ_building` (`period` via the generic `buildingYear` range filter against `Year1_Building`/`Year2_Building`, `material`/`thermalZone` via dedicated `"material fits"`/`"thermalZone fits"` sort criteria).
- **`Code_RoofType`**: `"SD"` (sloped, 45°) for SFH/MFH; `"FR"` (flat, 0°) for AB
- **Geometry never varies by material or zone** — only by `(buildingType, period)`. `build_cl_episcope.py` copies geometry columns from `CL_episcope_base.csv` (the original 27-row hand-authored set) regardless of which of the 6 materials/9 zones a row represents; only the `U_Actual_*`/`U_Window_1` columns actually change per material/zone.

See [README.md — Chilean archetypes](README.md#chilean-archetypes) for the full archetype classification and table.  
See the actual file at [`tsib/data/episcope/CL_episcope.csv`](tsib/data/episcope/CL_episcope.csv) for all columns (regenerate via `python tsib/data/episcope/build_cl_episcope.py`, never hand-edit).
