# -*- coding: utf-8 -*-
"""
Builds the runtime CL_episcope.csv: every archetype fully resolved (geometry +
zone/period/material-specific U-values) in a single row, reachable by one
"ID" lookup or by tsib.BuildingConfiguration's buildingType/buildingYear/
material/thermalZone filter path -- no separate zone-U-value table or
runtime period-binning logic needed.

Inputs:
  - CL_episcope_base.csv: the original 27 hand-authored geometry archetypes
    (3 building types x 3 periods x 3 materials). Geometry (areas, storeys,
    n_apartments, infiltration, g_gl_n) never varied by material in this
    seed -- only U-values did -- so it's read here purely for geometry,
    keyed by (buildingType, geometry period).
  - build_cl_zone_uvalues.build_zone_uvalues_table(): U-values for 6
    materials x 5 vintage periods x 9 zones.

Output: CL_episcope.csv, 3 building types x 5 periods x 6 materials x 9
zones = 810 rows, ID convention "CL.{BuildingType}.{Period}.{Material}.{Zone}"
(e.g. "CL.SFH.RT2.hor.D"), fully replacing the previous 27-row/4-segment-ID
table.

Not imported by the package at runtime -- run manually to regenerate:

    python tsib/data/episcope/build_cl_episcope.py
"""
import itertools
import os

import pandas as pd

import build_cl_zone_uvalues as zone_uvalues

HERE = os.path.dirname(os.path.abspath(__file__))
BASE_PATH = os.path.join(HERE, "CL_episcope_base.csv")
OUT_PATH = os.path.join(HERE, "CL_episcope.csv")

BUILDING_TYPES = ["SFH", "MFH", "AB"]

# fine period -> (Year1_Building, Year2_Building) written into each row, so
# the standard buildingYear-range filter in _get_typ_building resolves the
# right period without any custom binning code at runtime.
PERIOD_YEAR_BOUNDS = {label: (lo, hi) for label, lo, hi in zone_uvalues.PERIOD_BINS}

U_VALUE_COLUMNS = {
    "U_Wall_1": "U_Actual_Wall_1",
    "U_Roof_1": "U_Actual_Roof_1",
    "U_Floor_1": "U_Actual_Floor_1",
    "U_Window_1": "U_Window_1",
}


def load_geometry_lookup():
    """(buildingType, geometry period) -> geometry row (dict), material-independent."""
    base = pd.read_csv(BASE_PATH)
    lookup = {}
    for _, row in base.iterrows():
        _, building_type, geometry_period, _ = row["Code_BuildingVariant"].split(".")
        lookup.setdefault((building_type, geometry_period), row.to_dict())
    return lookup


def main():
    geometry_lookup = load_geometry_lookup()
    zone_uvalues_table = zone_uvalues.build_zone_uvalues_table().set_index(
        ["Code_Material", "Code_Period", "Code_Zone"]
    )

    rows = []
    for building_type, period, material, zone in itertools.product(
        BUILDING_TYPES, zone_uvalues.PERIODS, zone_uvalues.ALL_MATERIALS, zone_uvalues.ZONES
    ):
        geometry_period = zone_uvalues.PERIOD_FALLBACK_MAP[period]
        row = dict(geometry_lookup[(building_type, geometry_period)])

        new_id = f"CL.{building_type}.{period}.{material}.{zone}"
        row["Code_BuildingVariant"] = new_id
        row["Code_Building"] = new_id
        row["Code_Period"] = period
        row["Code_Material"] = material
        row["Code_Zone"] = zone

        year1, year2 = PERIOD_YEAR_BOUNDS[period]
        row["Year1_Building"] = year1
        row["Year2_Building"] = year2

        uvalue_row = zone_uvalues_table.loc[(material, period, zone)]
        for episcope_col, base_col in U_VALUE_COLUMNS.items():
            row[base_col] = uvalue_row[episcope_col]

        rows.append(row)

    out = pd.DataFrame(rows)

    # Code_Zone sits alongside the other Code_* columns for readability.
    cols = list(out.columns)
    cols.remove("Code_Zone")
    insert_at = cols.index("Code_Material") + 1
    cols.insert(insert_at, "Code_Zone")
    out = out[cols]

    out.to_csv(OUT_PATH, index=False)
    print(f"Wrote {len(out)} rows to {OUT_PATH}")


if __name__ == "__main__":
    main()
