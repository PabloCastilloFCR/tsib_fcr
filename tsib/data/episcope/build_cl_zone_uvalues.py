# -*- coding: utf-8 -*-
"""
Builds CL_zone_uvalues.csv: a (Code_Material, Code_Period, Code_Zone) -> U-value
diagnostic table for 6 materials, aggregated from the CEV (Calificacion
Energetica de Viviendas) rating dataset in tabla_maestra_transmitancias_cev.parquet
plus two literature sources for materials CEV can't support.

This file is a build-time diagnostic only -- tsib.buildingconfig does not read
it at runtime. build_cl_episcope.py imports build_zone_uvalues_table() from
here and merges its rows into the actual runtime archetype table,
CL_episcope.csv. Not imported by the package itself; run manually to
regenerate when the source data or bins below change:

    python tsib/data/episcope/build_cl_zone_uvalues.py

PERIOD_BINS uses 5 vintage bands derived from a dedicated regression-tree
analysis of the CEV dataset (~55 fits, per zone/per material/pooled),
matching Chile's thermal-code milestones: pre-code, RT Etapa 1 (2000, roof
requirement only), RT Etapa 2 (2007, walls/floors/windows added), the
voluntary CEV era (2015, a data-driven break), and 2021+ (small/edge sample,
treat cautiously). This is a *finer and independent* binning from
CL_episcope_base.csv's 3 geometry periods (preN/intN/DS50) -- see
PERIOD_FALLBACK_MAP below for how the two relate (used only by
build_cl_episcope.py, to pick which geometry row to copy per period).

Caveats from that analysis (see also n_samples in the output CSV):
- u_norma (regulatory-minimum U-value) is not a clean function of
  año_construccion -- 3-4 distinct values coexist for a given year/zone, so
  it could not be used to derive these cutoffs directly; bins came from
  residualized regression trees on u_real instead.
- U_real is dominated by zona_termica (35% of wall-U variance) and
  materialidad (7%), not year (a 5-bin split alone explains ~1%); year only
  adds meaningfully *on top of* zone+material (+23 R2 points for roofs,
  +6-9 for walls/windows).
- u_real_pisos (floors) is only ~9% populated -- too sparse to bin per
  zone x material, so floor cells fall back to the pooled-across-materials
  value (see below) far more often than walls/roofs/windows.
- zona_termica "D" dominates the sample (77k of 120k wall records); other
  zones are comparatively data-poor.

Materials: 4 are CEV-derived (mad/lad/hor/prefab, via MATERIAL_MAP). 2 are
not -- met (Metal/Acero) and adobe -- see LITERATURE_WALL_U below for why.
"""
import itertools
import os

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
PARQUET_PATH = os.path.join(HERE, "tabla_maestra_transmitancias_cev.parquet")
OUT_PATH = os.path.join(HERE, "CL_zone_uvalues.csv")

# materialidad (free text) -> Code_Material. Categories not listed here
# (Desconocido/Otro, Aislantes puros, Metal / Acero, Vidrio / Ventanas) are
# dropped from the CEV aggregation:
# - Desconocido/Otro: unusable by definition.
# - Aislantes puros (Techumbres/Pisos): describes roof/floor insulation
#   composition, not a wall-structure material comparable to the others.
# - Vidrio / Ventanas: window rows, not a wall material.
# - Metal / Acero: kept OUT of CEV aggregation on purpose -- see
#   LITERATURE_WALL_U below, this session's research found the raw CEV
#   aggregate (~1.5 W/m2K, n=494) likely mixes in uninsulated industrial/shed
#   steel, not real insulated Metalcon residential walls.
MATERIAL_MAP = {
    "Madera/Tabiquería": "mad",
    "Hormigón": "hor",
    "Albañilería": "lad",
    "Panel SIP / Prefabricados": "prefab",
}

# Materials with no usable CEV signal for the wall U-value, sourced from
# literature instead (uniform across all periods/zones -- no engineering
# source exists to vary these by zone/period):
# - met (Metal/Acero, SII codes A+G): MINVU "Listado Oficial de Soluciones
#   Constructivas para Acondicionamiento Termico" (DITEC, Ed. 11, Mar 2014),
#   ~30 certified light-steel-frame ("Metalcon"-style) residential wall
#   assemblies (galvanized steel studs + mineral wool/EPS + board cladding),
#   U in [0.46, 0.99] W/m2K, clustering 0.7-0.85. 0.75 used as a round
#   representative value.
#   https://www.minvu.gob.cl/wp-content/uploads/2020/05/Listado-T%C3%A9rmico-11.pdf
# - adobe (SII code F): not a CEV materialidad category at all. NCh853 Annex
#   A / Table A1 (same document family) lists adobe's generic thermal
#   conductivity lambda = 0.900 W/(m*K), density 1,100-1,800 kg/m3. U-value
#   derived assuming a representative 50cm wall and NCh853's standard
#   combined surface resistance Rsi+Rse = 0.17 m2K/W for opaque walls:
#   U = 1 / (0.17 + 0.50/0.900) = 1.38 W/m2K.
LITERATURE_WALL_U = {
    "met": 0.75,
    "adobe": 1.38,
}

ALL_MATERIALS = sorted(set(MATERIAL_MAP.values()) | set(LITERATURE_WALL_U.keys()))

# (label, min_year_inclusive, max_year_inclusive) -- 5 vintage bands, see
# module docstring for rationale/provenance.
PERIOD_BINS = [
    ("preRT", 1, 1999),
    ("RT1", 2000, 2006),
    ("RT2", 2007, 2014),
    ("CEV", 2015, 2020),
    ("post2021", 2021, 9999),
]

# Each of the 5 PERIOD_BINS above maps onto one of CL_episcope_base.csv's 3
# geometry periods (preN 1900-1999 / intN 2000-2015 / DS50 2016-2030). Used
# only by build_cl_episcope.py to pick which geometry row (areas, storeys,
# n_apartments) to copy per period -- geometry doesn't vary by zone and isn't
# informed by CEV data for the finer periods. CEV (2015-2020) straddles the
# intN/DS50 boundary at 2016; mapped to DS50 since most of that band
# (2016-2020) falls there.
PERIOD_FALLBACK_MAP = {
    "preRT": "preN",
    "RT1": "intN",
    "RT2": "intN",
    "CEV": "DS50",
    "post2021": "DS50",
}

# source column -> archetype U-value field
# u_real_otros holds window transmittance (scale matches U_Window_1 in
# CL_episcope_base.csv, e.g. ~5.8 for single glazing), not a generic "other".
COLUMN_MAP = {
    "u_real_muros": "U_Wall_1",
    "u_real_techos": "U_Roof_1",
    "u_real_pisos": "U_Floor_1",
    "u_real_otros": "U_Window_1",
}

MIN_SAMPLES = 5

PERIODS = [label for label, _, _ in PERIOD_BINS]
ZONES = list("ABCDEFGHI")


def year_to_period(year):
    for label, lo, hi in PERIOD_BINS:
        if lo <= year <= hi:
            return label
    return None


def _load_cev():
    df = pd.read_parquet(PARQUET_PATH)

    # the "ano_construccion" column name is corrupted (non-UTF-8 bytes) in
    # the source parquet itself -- access it positionally instead of by name.
    year_col = df.columns[3]

    df["Code_Material"] = df["materialidad"].map(MATERIAL_MAP)
    df = df[df["Code_Material"].notna()]

    df = df[df["zona_termica"] != "0"]
    df = df.rename(columns={"zona_termica": "Code_Zone"})

    df = df[df[year_col].notna() & (df[year_col] > 0)]
    df["Code_Period"] = df[year_col].map(year_to_period)
    df = df[df["Code_Period"].notna()]

    return df


def build_zone_uvalues_table():
    """Returns the (Code_Material, Code_Period, Code_Zone) -> U-value DataFrame.

    Fallback hierarchy for any (material, period, zone) cell that is missing
    or under-sampled (n_samples < MIN_SAMPLES) in the CEV data, for the 4
    CEV-derived materials:
      1. that material's own (period, zone) median, if n_samples >= MIN_SAMPLES
      2. pooled-across-all-CEV-materials median for the same (period, zone)
      3. pooled-across-all-CEV-materials median for the same period (any zone)
    This also replaces met/adobe's roof/floor/window values (no
    material-specific data exists for either), while their wall U-value
    always comes from LITERATURE_WALL_U regardless of sample size.
    """
    df = _load_cev()

    def median_by(group_cols):
        agg = {}
        for src_col, out_col in COLUMN_MAP.items():
            g = df.groupby(group_cols)[src_col]
            agg[out_col] = g.median()
            agg[out_col + "__n"] = g.count()
        return pd.DataFrame(agg)

    by_material_period_zone = median_by(["Code_Material", "Code_Period", "Code_Zone"])
    by_period_zone = median_by(["Code_Period", "Code_Zone"])
    by_period = median_by(["Code_Period"])

    rows = []
    for material, period, zone in itertools.product(ALL_MATERIALS, PERIODS, ZONES):
        row = {"Code_Material": material, "Code_Period": period, "Code_Zone": zone}
        n_samples_min = None
        for out_col in COLUMN_MAP.values():
            n = 0
            value = None
            if material in MATERIAL_MAP.values() and (material, period, zone) in by_material_period_zone.index:
                cell = by_material_period_zone.loc[(material, period, zone)]
                n = int(cell[out_col + "__n"])
                if n >= MIN_SAMPLES:
                    value = cell[out_col]
            if value is None and (period, zone) in by_period_zone.index:
                cell = by_period_zone.loc[(period, zone)]
                if int(cell[out_col + "__n"]) > 0:
                    value = cell[out_col]
            if value is None:
                value = by_period.loc[period, out_col]

            if out_col == "U_Wall_1" and material in LITERATURE_WALL_U:
                value = LITERATURE_WALL_U[material]

            row[out_col] = value
            if n_samples_min is None or n < n_samples_min:
                n_samples_min = n
        row["n_samples"] = n_samples_min
        rows.append(row)

    out = pd.DataFrame(rows).sort_values(["Code_Material", "Code_Period", "Code_Zone"])
    return out[
        [
            "Code_Material",
            "Code_Period",
            "Code_Zone",
            "U_Wall_1",
            "U_Roof_1",
            "U_Floor_1",
            "U_Window_1",
            "n_samples",
        ]
    ].reset_index(drop=True)


def main():
    out = build_zone_uvalues_table()
    out.to_csv(OUT_PATH, index=False)
    print(f"Wrote {len(out)} rows to {OUT_PATH}")
    print(f"Cells using fallback/pooled/literature values (n_samples < {MIN_SAMPLES}): {(out['n_samples'] < MIN_SAMPLES).sum()}")


if __name__ == "__main__":
    main()
