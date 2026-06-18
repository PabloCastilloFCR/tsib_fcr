# -*- coding: utf-8 -*-
"""
Calibration of tsib-fcr against real gas billing data — Catedral 1330.

Process flow
------------
1. Connect to GeoNode (internal PostGIS database)
2. Load building properties from  merlin_rcp.edificios  by edificio_id
3. Count residential units from  merlin_rcp.resultados_inmuebles
4. Derive archetype ID from building properties
   (type from clasificacion; period + material from DB columns when available)
5. Read A_C_Ref for that archetype from  tsib/data/episcope/CL_episcope.csv
6. Identify census district by spatial intersection → TMY district_id
7. Extract TMY from  tmy.src0101__minenergia__tmy_hourly
8. Load monthly gas bills from CSV
9. Detect summer baseline dynamically (SH summer = Dec–Mar, min gas = ACS only)
10. Run  sim_demand_direct()  and compare vs bills

Only truly fixed inputs:
  EDIFICIO_ID     — the building to simulate
  BOILER_EFF      — boiler thermal efficiency (physical constant for this system)
  GAS_LHV_KWH     — lower heating value of Chilean natural gas (physical constant)
  PERSONS_UNIT    — occupancy per unit (national average; override when census data
                    is available in DB)
"""

import sys
import os
import numpy as np
import pandas as pd
import tsib
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL

sys.stdout.reconfigure(encoding="utf-8")

HERE      = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))

# ── fixed physical / policy constants ─────────────────────────────────────────
EDIFICIO_ID  = 2618695   # ← only required input: which building to simulate
BOILER_EFF   = 0.85      # atmospheric gas boiler, 2005-era
GAS_LHV_KWH  = 10.8      # kWh/Nm3, Chilean natural gas LHV
PERSONS_UNIT = 2.5       # national average; replace with census value when available

# ── 1. GeoNode connection ──────────────────────────────────────────────────────
DB_URL = URL.create(
    drivername="postgresql+psycopg2",
    host="192.168.2.195", port=5432,
    username="guest1", password="guest1_2026_merlin",
    database="geonode_local_data",
)
engine = create_engine(DB_URL, pool_pre_ping=True)

# ── 2. Building properties from merlin_rcp.edificios ─────────────────────────
# NOTE: columns  periodo_normativo  and  material_predominante  are not yet in
# the table. When added, they will be read here automatically; until then the
# script falls back to the defaults below.
with engine.connect() as conn:
    building = conn.execute(text("""
        SELECT edificio_id, longitud, latitud, codigo_comuna,
               n_inmuebles, area_total_construida, area_promedio_inmueble,
               max_numero_pisos_sii, promedio_numero_pisos_sii,
               clasificacion, materialidad, zona_termica, anio_construccion
        FROM merlin_rcp.edificios
        WHERE edificio_id = :eid;
    """), {"eid": EDIFICIO_ID}).mappings().fetchone()

lon              = float(building["longitud"])
lat              = float(building["latitud"])
codigo_comuna    = int(building["codigo_comuna"])
area_avg         = float(building["area_promedio_inmueble"])
area_total       = float(building["area_total_construida"])
clasificacion    = str(building["clasificacion"])
max_pisos        = float(building["max_numero_pisos_sii"] or 1)
materialidad_raw = building["materialidad"]       # e.g. "hormigon", "madera", "ladrillo"
zona_termica     = building["zona_termica"]        # e.g. "D"
anio_const       = building["anio_construccion"]   # e.g. 2005

print("=" * 60)
print("STEP 2  Building from merlin_rcp.edificios")
print("=" * 60)
print(f"  edificio_id      : {building['edificio_id']}")
print(f"  coordinates      : ({lat:.5f}, {lon:.5f})")
print(f"  codigo_comuna    : {codigo_comuna}")
print(f"  clasificacion    : {clasificacion}")
print(f"  max_pisos_sii    : {max_pisos}")
print(f"  area_promedio    : {area_avg:.1f} m2/unit")
print(f"  area_total       : {area_total:.0f} m2")
print(f"  materialidad     : {materialidad_raw}")
print(f"  zona_termica     : {zona_termica}")
print(f"  anio_construccion: {anio_const}")

# ── 3. Residential unit count from resultados_inmuebles ───────────────────────
with engine.connect() as conn:
    n_units_residential = conn.execute(text("""
        SELECT COUNT(*)
        FROM merlin_rcp.resultados_inmuebles
        WHERE edificio_id = :eid
          AND tipo_inmueble = 'depto';
    """), {"eid": EDIFICIO_ID}).scalar()

# Fallback: if no depto rows yet (q_anual still NULL), use n_inmuebles from DB
N_UNITS = int(n_units_residential) if n_units_residential else int(building["n_inmuebles"])
n_persons = N_UNITS * PERSONS_UNIT

print("\n" + "=" * 60)
print("STEP 3  Residential unit count from resultados_inmuebles")
print("=" * 60)
print(f"  tipo_inmueble='depto' rows : {n_units_residential}")
print(f"  N_UNITS used               : {N_UNITS}")

# ── 4. Derive archetype ID from DB fields ────────────────────────────────────
# Building type: 'edificio' → AB; 'casa' → SFH
btype = "AB" if clasificacion == "edificio" else "SFH"

# Normative period from anio_construccion
def _period(year):
    if year is None: return "intN"
    if year < 2000:  return "preN"
    if year < 2016:  return "intN"
    return "DS50"

period = _period(anio_const)

# Material code from materialidad text
_MAT_MAP = {
    "hormigon": "hor", "hormigón": "hor",
    "madera":   "mad",
    "ladrillo": "lad",
    "albanileria": "lad", "albañilería": "lad",
}
material = _MAT_MAP.get((materialidad_raw or "").lower().strip(), "hor")

archetype_id = f"CL.{btype}.{period}.{material}"

print("\n" + "=" * 60)
print("STEP 4  Archetype derivation from DB fields")
print("=" * 60)
print(f"  btype        : {btype}  (clasificacion='{clasificacion}')")
print(f"  period       : {period}  (anio_construccion={anio_const})")
print(f"  material     : {material}  (materialidad='{materialidad_raw}')")
print(f"  zona_termica : {zona_termica}")
print(f"  archetype_id : {archetype_id}")

# ── 5. Read A_C_Ref from CL_episcope.csv ─────────────────────────────────────
episcope_path = os.path.join(REPO_ROOT, "tsib", "data", "episcope", "CL_episcope.csv")
episcope      = pd.read_csv(episcope_path)
arch_row      = episcope[episcope["Code_BuildingVariant"] == archetype_id]

if arch_row.empty:
    raise ValueError(f"Archetype '{archetype_id}' not found in CL_episcope.csv. "
                     f"Available: {episcope['Code_BuildingVariant'].tolist()}")

A_C_REF    = float(arch_row["A_C_Ref"].iloc[0])
U_WALL     = float(arch_row["U_Actual_Wall_1"].iloc[0])
U_ROOF     = float(arch_row["U_Actual_Roof_1"].iloc[0])
U_FLOOR    = float(arch_row["U_Actual_Floor_1"].iloc[0])
U_WINDOW   = float(arch_row["U_Window_1"].iloc[0])
N_INF      = float(arch_row["n_air_infiltration"].iloc[0])

print("\n" + "=" * 60)
print("STEP 5  Archetype parameters from CL_episcope.csv")
print("=" * 60)
print(f"  A_C_Ref    : {A_C_REF:.0f} m2")
print(f"  U_Wall     : {U_WALL} W/m2K")
print(f"  U_Roof     : {U_ROOF} W/m2K")
print(f"  U_Floor    : {U_FLOOR} W/m2K")
print(f"  U_Window   : {U_WINDOW} W/m2K")
print(f"  n_inf      : {N_INF} 1/h")

# ── 6. Census district → TMY district_id ─────────────────────────────────────
with engine.connect() as conn:
    district = conn.execute(text("""
        SELECT cut, region, provincia, comuna, distrito, id_distrito
        FROM boundaries.src0125__ine__censo2024__poly__distrital
        WHERE ST_Contains(shape, ST_SetSRID(ST_MakePoint(:lon, :lat), 4674))
        LIMIT 1;
    """), {"lat": lat, "lon": lon}).mappings().fetchone()

district_id = int(district["id_distrito"])

print("\n" + "=" * 60)
print("STEP 6  Census district by spatial intersection")
print("=" * 60)
print(f"  district_id : {district_id}")
print(f"  distrito    : {district['distrito']}")
print(f"  comuna      : {district['comuna']}")
print(f"  region      : {district['region']}")

# ── 7. Extract TMY ────────────────────────────────────────────────────────────
with engine.connect() as conn:
    tmy_raw = pd.read_sql(text("""
        SELECT month, day, hour,
               tdry AS t, ghi, dni, dhi
        FROM tmy.src0101__minenergia__tmy_hourly
        WHERE district_id = :did
        ORDER BY month, day, hour;
    """), conn, params={"did": district_id})

tmy_raw = tmy_raw.rename(columns={"t": "T", "ghi": "GHI", "dni": "DNI", "dhi": "DHI"})
tmy_raw["timestamp"] = pd.to_datetime({
    "year": 2023, "month": tmy_raw["month"],
    "day": tmy_raw["day"], "hour": tmy_raw["hour"],
})
tmy_tsib = tmy_raw.set_index("timestamp")[["T", "GHI", "DNI", "DHI"]]
rng      = tmy_tsib.index

print("\n" + "=" * 60)
print("STEP 7  TMY from tmy.src0101__minenergia__tmy_hourly")
print("=" * 60)
print(f"  district_id : {district_id}  ({len(tmy_tsib)} rows)")
monthly_t = tmy_tsib.groupby(tmy_tsib.index.month)["T"].mean().round(1)
print(f"  T range     : {monthly_t.min()} degC (month {monthly_t.idxmin()}) "
      f"to {monthly_t.max()} degC (month {monthly_t.idxmax()})")

# ── 8. Load billing data ──────────────────────────────────────────────────────
DATA_CSV = os.path.join(HERE, "natural_gas_consumption.csv")
bills_raw = pd.read_csv(DATA_CSV, skipinitialspace=True)
bills_raw.columns = [c.strip().replace("ñ", "n").replace("á", "a")
                     for c in bills_raw.columns]
_ES = {"enero":1,"febrero":2,"marzo":3,"abril":4,"mayo":5,"junio":6,
       "julio":7,"agosto":8,"septiembre":9,"octubre":10,"noviembre":11,"diciembre":12}
bills_raw["month_num"] = bills_raw["mes"].str.strip().map(_ES)
bills_raw["date"]      = pd.to_datetime(
    bills_raw["ano"].astype(str) + "-" + bills_raw["month_num"].astype(str).str.zfill(2)
)
bills_raw = bills_raw.sort_values("date").reset_index(drop=True)
BILLING   = pd.Series(bills_raw["consumo_gas_m3"].values,
                      index=bills_raw["date"], name="gas_m3")

# 12-month window: last 12 complete months in billing data
end_month   = BILLING.index[-1] - pd.DateOffset(months=1)   # exclude last (may be partial)
start_month = end_month - pd.DateOffset(months=11)
bill_12m    = BILLING[start_month:end_month].sum()

print("\n" + "=" * 60)
print("STEP 8  Billing data from CSV")
print("=" * 60)
for d, v in BILLING.items():
    print(f"  {d.strftime('%b %Y'):>8}: {v:>7,.0f} m3")
print(f"  12-month window : {start_month.strftime('%b %Y')} – {end_month.strftime('%b %Y')}")
print(f"  12-month total  : {bill_12m:,.0f} m3")

# ── 9. Calibrate ACS from summer billing baseline ─────────────────────────────
# SH summer = Dec–Mar (months 12, 1, 2, 3); space-heating ≈ 0 in those months.
# Take the mean of whichever summer months appear in the billing data.
summer_months = BILLING[BILLING.index.month.isin([12, 1, 2, 3])]
acs_m3_month  = float(summer_months.mean())
acs_kwh_day   = acs_m3_month / 30.4 * GAS_LHV_KWH * BOILER_EFF

days_per_month  = np.array([31,28,31,30,31,30,31,31,30,31,30,31], dtype=float)
acs_gas_monthly = (acs_kwh_day * days_per_month) / BOILER_EFF / GAS_LHV_KWH

l_per_person_day = (acs_kwh_day * 3_600_000) / (n_persons * 4186 * 45)

print("\n" + "=" * 60)
print("STEP 9  ACS calibration (SH summer baseline Dec–Mar)")
print("=" * 60)
print(f"  Summer months used : {sorted(summer_months.index.month.unique().tolist())}")
print(f"  Baseline           : {acs_m3_month:.0f} m3/month avg")
print(f"  ACS thermal        : {acs_kwh_day:.0f} kWh/day  ({acs_kwh_day/24:.1f} kW avg)")
print(f"  Calibrated DHW     : {l_per_person_day:.1f} L/person/day")

# ── 10. Simulate and compare ──────────────────────────────────────────────────
print("\n" + "=" * 60)
print("STEP 10  Simulation and comparison")
print("=" * 60)

cfg_obj = tsib.BuildingConfiguration(
    {
        "ID":            archetype_id,
        "country":       "CL",
        "a_ref":         float(area_avg),
        "weatherData":   tmy_tsib,
        "weatherID":     f"district_{district_id}",
        "refurbishment": False,
    },
    ignore_profiles=True,
)
cfg = cfg_obj.getBdgCfg(includeSupply=True)

Q_ig = round(PERSONS_UNIT * 0.08 + area_avg * 0.004, 3)  # metabolic + appliances [kW]
zeros = pd.Series(np.zeros(len(rng)), index=rng)
cfg["Q_ig"]         = np.full(len(rng), Q_ig)
cfg["occ_nothome"]  = zeros
cfg["occ_sleeping"] = zeros
cfg["elecLoad"]     = zeros
cfg["hotWaterLoad"] = zeros

model = tsib.Building5R1C(cfg)
model.sim_demand_direct()
Q_heat_unit = model.detailedResults["Heating Load"]

# Scale to full building
Q_heat_bldg      = pd.Series(Q_heat_unit * N_UNITS, index=rng)
heat_monthly_kwh = Q_heat_bldg.resample("ME").sum()
heat_kwh_annual  = float(Q_heat_unit.sum() * N_UNITS)
acs_kwh_annual   = acs_kwh_day * 365
gas_heat_annual  = heat_kwh_annual / BOILER_EFF / GAS_LHV_KWH
gas_acs_annual   = acs_kwh_annual  / BOILER_EFF / GAS_LHV_KWH
gas_total        = gas_heat_annual + gas_acs_annual
err_12m          = (gas_total - bill_12m) / bill_12m * 100

print(f"\n  Archetype          : {archetype_id}  (A_C_Ref={A_C_REF:.0f} m2)")
print(f"  Internal gains     : {Q_ig:.3f} kW/unit")
print(f"  N_UNITS            : {N_UNITS}")
print(f"  Heating (sim)      : {heat_kwh_annual/1000:.0f} MWh/a  "
      f"({Q_heat_unit.sum()/A_C_REF:.0f} kWh/m2/a)")
print(f"  ACS (calibrated)   : {acs_kwh_annual/1000:.0f} MWh/a")
print(f"  Gas heating        : {gas_heat_annual:,.0f} m3/a")
print(f"  Gas ACS            : {gas_acs_annual:,.0f} m3/a")
print(f"  Gas total sim      : {gas_total:,.0f} m3/a")
print(f"  Gas billed 12m     : {bill_12m:,.0f} m3")
print(f"  Annual error       : {err_12m:+.1f}%")

sim_heat_by_m = {m: heat_monthly_kwh[heat_monthly_kwh.index.month == m].mean()
                 for m in range(1, 13)}
sim_acs_by_m  = {m: acs_gas_monthly[m-1] for m in range(1, 13)}

print(f"\n  {'Month':<9} {'Billed':>8} {'Sim-heat':>9} {'Sim-ACS':>8} "
      f"{'Sim-tot':>8} {'Error%':>7}")
errors_abs = []
for _, row in bills_raw.iterrows():
    m      = int(row["month_num"])
    lbl    = row["date"].strftime("%b-%y")
    billed = float(row["consumo_gas_m3"])
    sim_h  = sim_heat_by_m[m] / BOILER_EFF / GAS_LHV_KWH
    sim_a  = sim_acs_by_m[m]
    sim_t  = sim_h + sim_a
    err    = (sim_t - billed) / billed * 100
    errors_abs.append(abs(sim_t - billed))
    print(f"  {lbl:<9} {billed:>8,.0f} {sim_h:>9,.0f} {sim_a:>8,.0f} "
          f"{sim_t:>8,.0f} {err:>+7.1f}%")

mae  = float(np.mean(errors_abs))
mape = float(np.mean([e / float(r["consumo_gas_m3"]) * 100
                      for e, (_, r) in zip(errors_abs, bills_raw.iterrows())]))

print(f"\n  MAE  : {mae:,.0f} m3/month")
print(f"  MAPE : {mape:.1f}%")
print(f"  Annual bias: {err_12m:+.1f}%")
