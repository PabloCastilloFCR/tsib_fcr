# Catedral 1330 — natural gas validation report

**Building:** Catedral 1330, downtown Santiago, Chile
**Type:** Apartment Block (AB), hormigon (concrete), ~2005
**Archetype:** `CL.AB.intN.hor` — 2000-2015 normative period, horizontal (flat roof)
**GeoNode record:** `merlin_rcp.edificios.edificio_id = 2618695`
**Script:** `santiago_ab_calibration.py`

---

## Simulation pipeline

| Step | Source | Value |
|------|--------|-------|
| Building properties | `merlin_rcp.edificios` | 248 inmuebles, 9,844 m², avg 39.7 m²/unit |
| Census district | `boundaries.src0125__ine__censo2024__poly__distrital` | `1310102` — Santiago / Moneda |
| Typical Meteorological Year | `tmy.src0101__minenergia__tmy_hourly` | MinEnergía national dataset, 8760 h |
| Archetype | `tsib/data/episcope/CL_episcope.csv` | U_Wall 1.9, U_Roof 1.5, U_Floor 0.8, U_Win 3.5 W/m²K |
| ACS calibration | Summer billing baseline (Jan–Mar 2025) | 35.3 L/person/day (heating = 0 in summer) |
| Simulation engine | `tsib.Building5R1C.sim_demand_direct()` | ISO 13790 5R1C, forward-Euler, no LP solver |
| Scale-up | 219 residential units | (248 DB units includes commercial/parking) |

---

## TMY profile — district 1310102 (Santiago / Moneda)

| Month | Mean T (°C) | Mean GHI (W/m²) |
|-------|------------|-----------------|
| Jan | 21.9 | 358 |
| Feb | 22.1 | 321 |
| Mar | 19.1 | 256 |
| Apr | 16.6 | 187 |
| May | 11.1 | 107 |
| Jun | 10.6 | 91 |
| **Jul** | **9.8** | **88** |
| Aug | 12.0 | 126 |
| Sep | 13.6 | 193 |
| Oct | 17.2 | 257 |
| Nov | 18.9 | 326 |
| Dec | 20.7 | 366 |

---

## Annual summary

| Item | Value |
|------|-------|
| Archetype ref area (CSV) | 58 m² |
| Heating demand (simulated) | 49 kWh/m²/a (archetype unit) |
| Annual heating — whole building | 623 MWh/a |
| Annual ACS (calibrated) | 369 MWh/a |
| Gas — heating | 67,815 m³/a |
| Gas — ACS | 40,182 m³/a |
| **Gas — total simulated** | **107,997 m³/a** |
| **Gas — billed (Jul 2024 – Jun 2025)** | **106,292 m³** |
| **Annual error** | **+1.6%** |

---

## Monthly comparison

| Month | Billed (m³) | Sim-heating (m³) | Sim-ACS (m³) | Sim-total (m³) | Error (%) |
|-------|------------|-----------------|--------------|---------------|-----------|
| Jul-24 | 19,571 | 17,732 | 3,413 | 21,145 | +8.0 |
| Aug-24 | 19,161 | 11,456 | 3,413 | 14,868 | -22.4 |
| Sep-24 | 15,400 | 6,092 | 3,303 | 9,395 | -39.0 |
| Oct-24 | 4,260 | 1,362 | 3,413 | 4,775 | +12.1 |
| Nov-24 | 4,450 | 156 | 3,303 | 3,459 | -22.3 |
| Dec-24 | 3,790 | 0 | 3,413 | 3,413 | -10.0 |
| Jan-25 | 3,520 | 0 | 3,413 | 3,413 | -3.0 |
| Feb-25 | 3,120 | 0 | 3,082 | 3,082 | -1.2 |
| Mar-25 | 3,400 | 570 | 3,413 | 3,982 | +17.1 |
| Apr-25 | 4,570 | 2,031 | 3,303 | 5,333 | +16.7 |
| May-25 | 10,750 | 13,434 | 3,413 | 16,847 | +56.7 |
| Jun-25 | 14,300 | 14,982 | 3,303 | 18,285 | +27.9 |
| Jul-25 | 15,100 | 17,732 | 3,413 | 21,145 | +40.0 |

---

## Validation metrics

| Approach | Bill total (m³) | Sim total (m³) | Annual bias | MAE (m³/month) | MAPE (%) |
|----------|----------------|---------------|-------------|----------------|---------|
| tsib-fcr + real TMY (this work) | 106,292 | 107,997 | **+1.6%** | **2,413** | **21.3** |
| approach1 (prev. engineering, Madrid proxy) | 121,392 | 92,308 | -24.0% | 2,554 | 22.2 |
| approach2 (UA postcalibrated, Madrid proxy) | 121,392 | 278,908 | +129.8% | 12,896 | 106.4 |

---

## Key findings

**Annual total:** Model matches bills within 1.6% using a fully automated pipeline
(no manual calibration beyond the ACS summer-baseline adjustment).

**Monthly shape error (MAPE 21.3%):** The TMY represents a *typical* year, not
calendar 2024-2025. The real winter was shifted — August 2024 was the coldest billing
month (19,161 m³) while the typical year peaks in July. Cold snaps and inter-annual
variability are not captured by a TMY.

**ACS calibration:** Summer baseline (Jan–Mar 2025, when heating = 0) implies
35.3 L/person/day, lower than the commonly assumed 50 L/day. This reflects actual
measured consumption at this building rather than a design value.

**Underestimate in Sep 2024 (−39%):** September had unusually high gas consumption
suggesting a cold front not present in the typical year. This is a known limitation
of TMY-based simulations.

## Files

| File | Description |
|------|-------------|
| `santiago_ab_calibration.py` | Full pipeline script (DB → TMY → sim → comparison) |
| `natural_gas_consumption.csv` | Raw monthly gas bills Jul-2024 to Jul-2025 |
| `tmy_santiago_1310102.csv` | Real TMY extracted from GeoNode (cached) |
| `tsib_validation_monthly_comparison.csv` | Previous approach monthly data |
| `tsib_validation_report.md` | This report |
