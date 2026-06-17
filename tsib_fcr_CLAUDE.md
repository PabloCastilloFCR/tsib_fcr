# tsib_fcr — Chile Adaptation

Fork of [FZJ-IEK3-VSA/tsib](https://github.com/FZJ-IEK3-VSA/tsib) for residential building thermal simulation in Chile.

**Consuming project:** MERLIN_RCP (residential energy demand model for Chile)  
**Entry point in MERLIN_RCP:** `sectors/residential/src/archetype_sim.py`  
**Interface contract:** MERLIN_RCP calls `BuildingConfiguration` and `Building5R1C` only — no other tsib internals.

---

## Scope of changes

Minimal surgical modifications to add Chile support. The core 5R1C model, EPISCOPE loading, and geometry scaling are **not changed**.

| Type | File | Description |
|---|---|---|
| Modify | `tsib/buildingconfig.py` | Add `'CL'` to `KWARG_TYPES["country"]`; add Chilean defaults; add U-value override kwargs |
| Create | `tsib/data/episcope/CL_episcope.csv` | 27 archetype configurations (prototype) |
| Create | `tsib/weather/chile.py` | TMY adapter for BD Ancestral column format |
| Modify | `setup.py` / `pyproject.toml` | Version bump, add Chile to description |

**Solver dependency (existing):** the 5R1C model requires a MILP solver. See §5 below.

---

## 1. `tsib/buildingconfig.py` — three targeted edits

### Edit 1.1 — Add `'CL'` to KWARG_TYPES

Find the `KWARG_TYPES` dict where `"country"` is defined. It will look like:

```python
KWARG_TYPES = {
    ...
    "country": ["DE", "AT", ...],   # list of allowed country codes
    ...
}
```

Add `'CL'` to that list:

```python
"country": ["DE", "AT", ..., "CL"],
```

---

### Edit 1.2 — Add Chilean defaults to KWARG_DEFAULTS

Find `KWARG_DEFAULTS` and add a conditional block, or extend the existing structure, so that when `country == 'CL'` the defaults reflect Chilean conditions instead of German ones:

```python
# After existing KWARG_DEFAULTS = {...}:
KWARG_DEFAULTS_CL = {
    "country": "CL",
    "buildingYear": 1990,
    "comfortT_lb": 18.0,     # °C — Chilean norm uses 18°C setpoint
    "comfortT_ub": 26.0,
    "n_persons": 3,           # average Chilean household size (Censo 2024)
    "existingHeatSupply": "Electric resistance",
    "hotWaterElec": False,
    "nightReduction": False,
    "occControl": False,
}
```

In `BuildingConfiguration.__init__` (or `_set_defaults`), apply these when `country == 'CL'`:

```python
if self.kwargs.get("country") == "CL":
    for k, v in KWARG_DEFAULTS_CL.items():
        if k not in self.kwargs:
            self.kwargs[k] = v
```

---

### Edit 1.3 — Add U-value override support in `_get_fabric`

In `_get_fabric` (the method that reads U-values from EPISCOPE and sets them in `self.cfg`), add an override block at the end. This allows MERLIN_RCP to inject zone- and period-specific U-values without needing one EPISCOPE row per zone.

Locate the end of `_get_fabric` where it finishes writing `self.cfg` with envelope values. Add:

```python
# Override U-values from kwargs if provided (used for Chile zone-specific injection)
_u_override_keys = [
    "U_Wall_1", "U_Roof_1", "U_Floor_1", "U_Window_1",
    "n_Infiltration", "g_gl_n",
]
for _key in _u_override_keys:
    if _key in self.kwargs:
        self.cfg[_key] = float(self.kwargs[_key])
```

This means `_get_fabric` still reads the EPISCOPE archetype normally (geometry, base U-values) but any U-value explicitly passed as a kwarg overwrites the CSV value before the config is returned.

**Why:** Chilean archetypes have 7 thermal zones × different normative periods. Rather than 189 EPISCOPE rows, MERLIN_RCP has 27 geometry rows in the CSV and injects the correct U-values per simulation call.

---

## 2. `tsib/data/episcope/CL_episcope.csv` — new file

### Column format

The CSV must match the column names tsib reads in `_get_typ_building`, `_get_form`, and `_get_fabric`. Based on the TABULA/EPISCOPE standard used by tsib:

```
Code_BuildingVariant, Country, Year1_Begin, Year1_End, BuildingType,
n_Storey, A_C_Ref, A_Roof_1, A_Wall_1, A_Floor_1, A_Window_1,
U_Roof_1, U_Wall_1, U_Floor_1, U_Window_1,
g_gl_n, n_Infiltration,
n_Persons_ref, q_H_nd
```

| Column | Description | Notes |
|---|---|---|
| `Code_BuildingVariant` | Archetype ID, e.g. `PT.SFH.preN.mad` | Must be unique |
| `Country` | `CL` | All rows |
| `Year1_Begin` / `Year1_End` | Construction year range | Used for indirect archetype selection |
| `BuildingType` | `SFH` / `MFH` / `AB` | Matches tsib building type names |
| `n_Storey` | Number of storeys | |
| `A_C_Ref` | Reference conditioned floor area (m²) | Median from SII cluster |
| `A_Roof_1` | Roof area (m²) | = `A_C_Ref / n_Storey` for flat roof |
| `A_Wall_1` | Gross external wall area (m²) | Estimated from perimeter × height |
| `A_Floor_1` | Ground floor area (m²) | = `A_C_Ref / n_Storey` |
| `A_Window_1` | Total window area (m²) | = `A_Wall_1 × window_wall_ratio` |
| `U_Roof_1` | Default U-value roof (W/m²K) | Zone-neutral default; overridden per simulation |
| `U_Wall_1` | Default U-value wall (W/m²K) | Zone-neutral default; overridden per simulation |
| `U_Floor_1` | Default U-value floor (W/m²K) | Zone-neutral default; overridden per simulation |
| `U_Window_1` | Default U-value window (W/m²K) | Zone-neutral default; overridden per simulation |
| `g_gl_n` | Solar transmittance of glazing | 0.60 high quality / 0.75 mid / 0.87 simple |
| `n_Infiltration` | Air infiltration rate (1/h) | By materialidad: madera=0.8, ladrillo=0.5, hormigon=0.3 |
| `n_Persons_ref` | Reference occupant count | 3 (Chilean household average) |
| `q_H_nd` | Reference specific heating demand (kWh/m²yr) | From literature; used for validation only |

### Geometry estimation formulas

For SFH (n_storey = 1 or 2):

```
A_Roof_1  = A_C_Ref / n_Storey
A_Floor_1 = A_C_Ref / n_Storey
A_Wall_1  = 4 * sqrt(A_C_Ref / n_Storey) * n_Storey * ceiling_height_m
A_Window_1 = A_Wall_1 * window_wall_ratio
```

Use `ceiling_height_m = 2.4` for Chilean residential stock.  
`window_wall_ratio` by type: SFH=0.15, MFH=0.17, AB=0.20.

### 27-row table (prototype)

```
Code_BuildingVariant, Country, Year1_Begin, Year1_End, BuildingType, n_Storey, A_C_Ref, A_Roof_1, A_Wall_1, A_Floor_1, A_Window_1, U_Roof_1, U_Wall_1, U_Floor_1, U_Window_1, g_gl_n, n_Infiltration, n_Persons_ref, q_H_nd
PT.SFH.preN.mad, CL, 1900, 1999, SFH, 1, 60, 60, 57.6, 60, 8.6, 2.5, 2.7, 1.4, 5.8, 0.87, 0.80, 3, 120
PT.SFH.preN.lad, CL, 1900, 1999, SFH, 1, 60, 60, 57.6, 60, 8.6, 2.5, 2.3, 1.4, 5.8, 0.75, 0.50, 3, 100
PT.SFH.preN.hor, CL, 1900, 1999, SFH, 1, 60, 60, 57.6, 60, 8.6, 2.5, 3.4, 1.4, 5.8, 0.75, 0.30, 3, 110
PT.SFH.intN.mad, CL, 2000, 2015, SFH, 1, 65, 65, 62.4, 65, 9.4, 1.5, 1.9, 0.8, 3.5, 0.75, 0.60, 3, 80
PT.SFH.intN.lad, CL, 2000, 2015, SFH, 1, 65, 65, 62.4, 65, 9.4, 1.5, 1.9, 0.8, 3.5, 0.75, 0.50, 3, 75
PT.SFH.intN.hor, CL, 2000, 2015, SFH, 1, 65, 65, 62.4, 65, 9.4, 1.5, 1.9, 0.8, 3.5, 0.75, 0.30, 3, 72
PT.SFH.DS50.mad, CL, 2016, 2030, SFH, 2, 70, 35, 67.2, 35, 10.1, 0.6, 0.6, 0.5, 2.8, 0.60, 0.50, 3, 40
PT.SFH.DS50.lad, CL, 2016, 2030, SFH, 2, 70, 35, 67.2, 35, 10.1, 0.6, 0.6, 0.5, 2.8, 0.60, 0.40, 3, 38
PT.SFH.DS50.hor, CL, 2016, 2030, SFH, 2, 70, 35, 67.2, 35, 10.1, 0.6, 0.6, 0.5, 2.8, 0.60, 0.25, 3, 36
PT.MFH.preN.mad, CL, 1900, 1999, MFH, 4, 55, 14, 52.8, 14, 9.0, 2.5, 2.7, 1.4, 5.8, 0.87, 0.70, 3, 130
PT.MFH.preN.lad, CL, 1900, 1999, MFH, 4, 55, 14, 52.8, 14, 9.0, 2.5, 2.3, 1.4, 5.8, 0.75, 0.45, 3, 105
PT.MFH.preN.hor, CL, 1900, 1999, MFH, 4, 55, 14, 52.8, 14, 9.0, 2.5, 3.4, 1.4, 5.8, 0.75, 0.25, 3, 115
PT.MFH.intN.mad, CL, 2000, 2015, MFH, 4, 60, 15, 57.6, 15, 9.8, 1.5, 1.9, 0.8, 3.5, 0.75, 0.55, 3, 85
PT.MFH.intN.lad, CL, 2000, 2015, MFH, 4, 60, 15, 57.6, 15, 9.8, 1.5, 1.9, 0.8, 3.5, 0.75, 0.45, 3, 78
PT.MFH.intN.hor, CL, 2000, 2015, MFH, 4, 60, 15, 57.6, 15, 9.8, 1.5, 1.9, 0.8, 3.5, 0.75, 0.25, 3, 74
PT.MFH.DS50.mad, CL, 2016, 2030, MFH, 4, 65, 16, 62.4, 16, 10.6, 0.6, 0.6, 0.5, 2.8, 0.60, 0.45, 3, 42
PT.MFH.DS50.lad, CL, 2016, 2030, MFH, 4, 65, 16, 62.4, 16, 10.6, 0.6, 0.6, 0.5, 2.8, 0.60, 0.35, 3, 40
PT.MFH.DS50.hor, CL, 2016, 2030, MFH, 4, 65, 16, 62.4, 16, 10.6, 0.6, 0.6, 0.5, 2.8, 0.60, 0.22, 3, 38
PT.AB.preN.mad,  CL, 1900, 1999, AB,  12, 52, 4,  49.9, 4,  8.5, 2.5, 2.7, 1.4, 5.8, 0.87, 0.60, 3, 125
PT.AB.preN.lad,  CL, 1900, 1999, AB,  12, 52, 4,  49.9, 4,  8.5, 2.5, 2.3, 1.4, 5.8, 0.75, 0.35, 3, 100
PT.AB.preN.hor,  CL, 1900, 1999, AB,  12, 52, 4,  49.9, 4,  8.5, 2.5, 3.4, 1.4, 5.8, 0.75, 0.20, 3, 112
PT.AB.intN.mad,  CL, 2000, 2015, AB,  12, 58, 5,  55.7, 5,  9.5, 1.5, 1.9, 0.8, 3.5, 0.75, 0.45, 3, 82
PT.AB.intN.lad,  CL, 2000, 2015, AB,  12, 58, 5,  55.7, 5,  9.5, 1.5, 1.9, 0.8, 3.5, 0.75, 0.35, 3, 76
PT.AB.intN.hor,  CL, 2000, 2015, AB,  12, 58, 5,  55.7, 5,  9.5, 1.5, 1.9, 0.8, 3.5, 0.75, 0.18, 3, 72
PT.AB.DS50.mad,  CL, 2016, 2030, AB,  14, 62, 4,  59.5, 4,  10.1, 0.6, 0.6, 0.5, 2.8, 0.60, 0.35, 3, 40
PT.AB.DS50.lad,  CL, 2016, 2030, AB,  14, 62, 4,  59.5, 4,  10.1, 0.6, 0.6, 0.5, 2.8, 0.60, 0.28, 3, 38
PT.AB.DS50.hor,  CL, 2016, 2030, AB,  14, 62, 4,  59.5, 4,  10.1, 0.6, 0.6, 0.5, 2.8, 0.60, 0.18, 3, 35
```

> **Nota:** Los valores de `A_C_Ref`, `A_Roof_1`, `A_Wall_1`, `A_Floor_1`, `A_Window_1` son estimaciones iniciales. Deben reemplazarse por las medianas calculadas desde `sii_residencial.parquet` (Task 0.1 de MERLIN_RCP) antes de usar en producción. Los valores de `q_H_nd` son de referencia para validación; no se usan en el cálculo.

---

## 3. `tsib/weather/chile.py` — nuevo módulo

El TMY de la BD Ancestral tiene columnas distintas a las que tsib espera (`DHI`, `T`, `DNI`). Este módulo hace la traducción.

```python
# tsib/weather/chile.py
"""Adaptador TMY de BD Ancestral al formato requerido por tsib."""
import pandas as pd


# Mapeo de columnas BD Ancestral → nombres tsib
_COL_MAP = {
    "tdry":           "T",         # temperatura seca exterior (°C)
    "dhi":            "DHI",       # irradiancia horizontal difusa (W/m²)
    "dni":            "DNI",       # irradiancia directa normal (W/m²)
    "ghi":            "GHI",       # irradiancia horizontal global (W/m²)
    "wspd":           "WS",        # velocidad del viento (m/s)
    "pres":           "p",         # presión (Pa)
    "e_norte":        "e_norte",   # irradiancia orientación norte (W/m²) — extra CL
    "e_este":         "e_este",
    "e_sur":          "e_sur",
    "e_oeste":        "e_oeste",
    "e_techo":        "e_techo",
    "h_conv":         "h_conv",    # coeficiente convectivo (W/m²K) — extra CL
    "t_mains":        "t_mains",   # temperatura agua de red (°C) — extra CL
    "air_density":    "air_density",
    "air_specific_heat": "air_specific_heat",
}


def bd_tmy_to_tsib(tmy_df: pd.DataFrame) -> pd.DataFrame:
    """
    Convierte TMY desde el formato de BD Ancestral al formato esperado por tsib.

    La BD Ancestral ya tiene pre-calculados: h_conv, e_norte/este/sur/oeste/techo,
    t_mains, air_density, air_specific_heat. No se recalcula nada.

    Parameters
    ----------
    tmy_df : pd.DataFrame
        DataFrame con 8760 filas, columnas en formato BD Ancestral.

    Returns
    -------
    pd.DataFrame
        DataFrame con columnas renombradas al formato tsib.
    """
    cols_present = {k: v for k, v in _COL_MAP.items() if k in tmy_df.columns}
    result = tmy_df.rename(columns=cols_present)

    # tsib espera un índice DatetimeIndex horario
    if not isinstance(result.index, pd.DatetimeIndex):
        if "timestamp" in tmy_df.columns:
            result.index = pd.to_datetime(tmy_df["timestamp"])
        else:
            result.index = pd.date_range("2024-01-01", periods=8760, freq="h")

    return result
```

Exponer en `tsib/__init__.py`:

```python
from tsib.weather.chile import bd_tmy_to_tsib
```

---

## 4. Solver — dependencia obligatoria

El modelo 5R1C en `tsib/thermal/model5R1C.py` usa **Pyomo** como problema de optimización LP/MILP. Requiere un solver instalado por separado.

### Opción recomendada: HiGHS (libre, rápido, sin licencia)

```bash
pip install highspy
```

HiGHS está soportado via `pyomo.contrib.appsi`. Verificar que tsib lo detecte:

```python
from pyomo.contrib import appsi
solver = appsi.solvers.Highs()
solver.available()  # debe retornar True
```

### Alternativa: CBC (libre)

```bash
# Linux/Mac
conda install -c conda-forge coincbc

# Windows: descargar binario desde https://github.com/coin-or/Cbc/releases
# y agregar al PATH
```

### Configurar en código

```python
import os
os.environ["SOLVER"] = "highs"   # o "cbc"
```

O pasar directamente al crear `Building5R1C`:

```python
bdg = tsib.Building(cfg, solver="highs")
```

> **IMPORTANTE para MERLIN_RCP:** las ~189 simulaciones del prototipo se ejecutan con Pyomo. Si HiGHS no está disponible, las simulaciones fallan silenciosamente o con error oscuro. Documentar el requisito del solver en el README del fork y en `requirements.txt`.

### Agregar a `setup.py` / `pyproject.toml`

```toml
[project.optional-dependencies]
solver_highs = ["highspy"]
solver_cbc   = []  # CBC se instala externamente
```

---

## 5. `setup.py` / `pyproject.toml` — actualizar metadatos

```toml
[project]
name = "tsib_fcr"
version = "0.2.0-cl"
description = "Time Series Initialization for Buildings — Chile fork (Fraunhofer Chile)"
```

O en `setup.py`:

```python
name="tsib_fcr",
version="0.2.0-cl",
```

---

## 6. Tests

### Test mínimo de integración Chile

Agregar `test/test_chile.py`:

```python
"""Smoke test: simulación completa con arquetipo CL y TMY sintético."""
import numpy as np
import pandas as pd
import tsib


def _make_synthetic_tmy(T_mean=10.0):
    """TMY sintético con 8760 filas en formato BD Ancestral → renombrado a tsib."""
    rng = pd.date_range("2024-01-01", periods=8760, freq="h")
    T = T_mean + 10 * np.sin(2 * np.pi * (np.arange(8760) - 2000) / 8760)
    return pd.DataFrame({
        "T":   T,
        "DHI": np.clip(200 * np.sin(np.pi * np.arange(8760) / 24), 0, None),
        "DNI": np.clip(400 * np.sin(np.pi * np.arange(8760) / 24), 0, None),
        "GHI": np.clip(500 * np.sin(np.pi * np.arange(8760) / 24), 0, None),
    }, index=rng)


def test_sfh_prenorma_madera_zona_g():
    """SFH pre-norma madera en zona G (fría): q_h_nd debe ser alto."""
    tmy = _make_synthetic_tmy(T_mean=5.0)   # zona G: T media ~5°C
    u_vals = {"U_Wall_1": 2.7, "U_Roof_1": 2.5, "U_Floor_1": 1.4, "U_Window_1": 5.8}

    cfg = tsib.BuildingConfiguration({
        "ID":          "PT.SFH.preN.mad",
        "country":     "CL",
        "a_ref":       60,
        "weatherData": tmy,
        "weatherID":   "test_zona_g",
        **u_vals,
    })
    bdg = tsib.Building(cfg)
    bdg.getHeatLoad()

    q_h_nd = bdg.timeseries["Heating Load"].sum() / 60   # kWh/m²/año
    assert q_h_nd > 50, f"q_h_nd={q_h_nd:.1f} demasiado bajo para zona G pre-norma"
    assert q_h_nd < 300, f"q_h_nd={q_h_nd:.1f} irrealmente alto"


def test_sfh_ds50_menor_que_prenorma():
    """DS50 debe tener menor demanda que pre-norma para misma zona."""
    tmy = _make_synthetic_tmy(T_mean=8.0)
    u_prenorma = {"U_Wall_1": 2.7, "U_Roof_1": 2.5, "U_Floor_1": 1.4, "U_Window_1": 5.8}
    u_ds50     = {"U_Wall_1": 0.6, "U_Roof_1": 0.6, "U_Floor_1": 0.5, "U_Window_1": 2.8}

    def sim(archetype_id, u_vals):
        cfg = tsib.BuildingConfiguration({
            "ID": archetype_id, "country": "CL", "a_ref": 60,
            "weatherData": tmy, "weatherID": "test_mono", **u_vals,
        })
        bdg = tsib.Building(cfg)
        bdg.getHeatLoad()
        return bdg.timeseries["Heating Load"].sum() / 60

    q_pre = sim("PT.SFH.preN.mad", u_prenorma)
    q_ds  = sim("PT.SFH.DS50.mad", u_ds50)
    assert q_pre > q_ds, f"pre-norma ({q_pre:.1f}) debe ser > DS50 ({q_ds:.1f})"


def test_country_cl_accepted():
    """BuildingConfiguration no debe lanzar error con country='CL'."""
    tmy = _make_synthetic_tmy()
    try:
        tsib.BuildingConfiguration({
            "ID": "PT.SFH.intN.lad", "country": "CL",
            "a_ref": 65, "weatherData": tmy, "weatherID": "test_country",
        })
    except ValueError as e:
        assert False, f"country='CL' rechazado: {e}"
```

Ejecutar:

```bash
pytest test/test_chile.py -v
```

---

## 7. Uso desde MERLIN_RCP

Flujo de llamada en `sectors/residential/src/archetype_sim.py`:

```python
import tsib
from tsib.weather.chile import bd_tmy_to_tsib

def simulate_archetype(
    archetype_id: str,
    a_ref: float,
    u_values: dict,
    tmy_bd: pd.DataFrame,
) -> dict:
    """
    u_values: {"U_Wall_1": float, "U_Roof_1": float, "U_Floor_1": float,
               "U_Window_1": float, "n_Infiltration": float, "g_gl_n": float}
    tmy_bd: DataFrame en formato BD Ancestral (columnas: tdry, dhi, dni, ...)
    """
    tmy = bd_tmy_to_tsib(tmy_bd)

    # A_C_Ref del arquetipo base (desde CL_episcope.csv)
    a_ref_base = _load_episcope_value(archetype_id, "A_C_Ref")

    cfg = tsib.BuildingConfiguration({
        "ID":          archetype_id,
        "country":     "CL",
        "a_ref":       a_ref_base,      # geometría base del arquetipo
        "weatherData": tmy,
        "weatherID":   f"{archetype_id}_{tmy.index[0].year}",
        **u_values,                     # sobrescribe U-values del CSV
    })

    bdg = tsib.Building(cfg)
    bdg.getHeatLoad()

    heating_h = bdg.timeseries["Heating Load"].values   # kWh/h, 8760 valores
    q_h_nd    = heating_h.sum() / a_ref_base             # kWh/m²/año

    scale = a_ref / a_ref_base
    return {
        "q_h_nd_kWh_m2":         q_h_nd,
        "Q_heating_h":           heating_h * scale,      # np.ndarray[8760]
        "Q_heating_annual_kWh":  heating_h.sum() * scale,
    }
```

---

## 8. Checklist de implementación

- [ ] **1.1** Agregar `'CL'` a `KWARG_TYPES["country"]` en `buildingconfig.py`
- [ ] **1.2** Agregar `KWARG_DEFAULTS_CL` y aplicarlo cuando `country == 'CL'`
- [ ] **1.3** Agregar bloque de override U-values al final de `_get_fabric`
- [ ] **2** Crear `tsib/data/episcope/CL_episcope.csv` con las 27 filas
- [ ] **3** Crear `tsib/weather/chile.py` con `bd_tmy_to_tsib`
- [ ] **3** Exponer `bd_tmy_to_tsib` en `tsib/__init__.py`
- [ ] **4** Verificar que HiGHS o CBC esté instalado y accesible por Pyomo
- [ ] **5** Crear `test/test_chile.py` y confirmar que los 3 tests pasan
- [ ] **6** Bump de versión en `setup.py` / `pyproject.toml` a `0.2.0-cl`
- [ ] **6** Actualizar `README.md` con sección "Chile support" y nota sobre solver
