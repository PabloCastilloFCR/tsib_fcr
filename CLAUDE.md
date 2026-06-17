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
| 2 | Create `CL_episcope.csv` with 27 archetypes | `tsib/data/episcope/CL_episcope.csv` | ✅ |
| 3a | Create `tsib/weather/chile.py` with `bd_tmy_to_tsib` | `tsib/weather/chile.py` | ❌ |
| 3b | Export `bd_tmy_to_tsib` from package | `tsib/__init__.py` | ❌ |
| 4 | Verify HiGHS solver works | env | ❌ |
| 5 | Create `test/test_chile.py` (3 smoke tests) | `test/test_chile.py` | ❌ |
| 6 | Bump version to `0.2.0-cl`, update package name | `setup.py` | ❌ |

---

## Architecture

```
tsib/
  buildingconfig.py     ← KWARG_TYPES, KWARG_DEFAULTS, BuildingConfiguration
  buildingmodel.py      ← Building class (calls buildingconfig + 5R1C)
  thermal/model5R1C.py  ← Pyomo LP/MILP optimization (requires solver)
  data/episcope/
    episcope.csv        ← TABULA/EPISCOPE EU archetypes (read-only)
    CL_episcope.csv     ← Chile archetypes to be created (27 rows)
  weather/
    testreferenceyear.py ← German TRY adapter
    chile.py            ← BD Ancestral TMY adapter (to be created)
```

### How archetype lookup works
`BuildingConfiguration.__init__` → validates kwargs against `KWARG_TYPES` → calls `_get_typ_building` which reads the correct CSV row by `ID` → `_get_fabric` writes U-values into `self.cfg`.

The U-value override (task 1.3) must run **after** `_get_fabric` has written the EPISCOPE values, so it overwrites them.

---

## Interface contract (do not break)

MERLIN_RCP (consuming project) calls only:
- `tsib.BuildingConfiguration(kwargs_dict)` 
- `tsib.Building(cfg)` + `.getHeatLoad()`
- `tsib.bd_tmy_to_tsib(df)` (to be added)

No other tsib internals are used by MERLIN_RCP.

---

## Key constraints

- **Solver required:** `model5R1C.py` uses Pyomo. HiGHS (`pip install highspy`) is the recommended solver. Without it simulations fail.
- **`_get_fabric` is the injection point:** U-value overrides (`U_Wall_1`, `U_Roof_1`, `U_Floor_1`, `U_Window_1`, `n_Infiltration`, `g_gl_n`) are passed as kwargs and must override CSV values at the end of `_get_fabric` (line 602).
- **KWARG validation runs first:** Any new kwarg passed to `BuildingConfiguration` must be registered in `KWARG_TYPES` or it will be silently dropped / raise a KeyError. The U-value override kwargs (`U_Wall_1` etc.) need to be added to `KWARG_TYPES` as `float`.
- **Chile archetypes use 27 geometry rows × zone-specific U-values:** Do not create one CSV row per zone×period combination. MERLIN_RCP injects U-values per call.
- **`existingHeatSupply` valid values:** must be one of the strings in `KWARG_TYPES["existingHeatSupply"]`. The Chilean default `"Electric resistance"` specified in the spec does **not** appear in that list — use `"Electric heater"` instead.

---

## CL_episcope.csv — implementation notes

The spec listed ~19 columns, but `get_shape` and `get_fabric` in `buildingconfig.py` access ~50. The actual CSV includes all required columns:

- **Secondary components** (`A_Wall_2/3`, `A_Roof_2`, `A_Floor_2`, `A_Window_2`) set to `0` — handles single-component Chilean envelope
- **Orientation split** — total `A_Window_1` distributed equally across N/E/S/W (25% each); `A_Window_Horizontal = 0`
- **`U_Actual_*`** — maps to `U_*` from spec; `get_fabric` writes these to `cfg["U_Wall_1"]` etc.
- **`b_Transmission_Wall_1 = 1.0`**, `b_Transmission_Floor_1 = 0.45` (ground contact), roofs `= 1.0`
- **Override key mapping** (implemented in `_get_fabric`): kwarg `U_Window_1` → `cfg["U_Window"]`, `g_gl_n` → `cfg["g_gl_n_Window"]`, `n_Infiltration` → `cfg["n_air_infiltration"]`
- **`Code_RoofType`**: `"SD"` (sloped, 45°) for SFH/MFH; `"FR"` (flat, 0°) for AB

See [`ARCHETYPES_CL.md`](ARCHETYPES_CL.md) for the full archetype classification and table.  
See the actual file at [`tsib/data/episcope/CL_episcope.csv`](tsib/data/episcope/CL_episcope.csv) for all 50 columns.
