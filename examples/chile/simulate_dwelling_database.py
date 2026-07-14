# -*- coding: utf-8 -*-
"""Batch simulation over a dwelling database — no hardcoded U-values.

Unlike validation_direct_5r1c.py (which fixes a single archetype + explicit
U_Wall_1/etc. as a reproducible engine fixture), this example shows the
pattern for simulating thousands of real dwellings: each row only supplies
buildingYear/buildingType/material/thermalZone/a_ref, and tsib resolves the
matching archetype + zone-specific U-values internally (CL_episcope.csv +
CL_zone_uvalues.csv). No "ID" kwarg, no U_Wall_1/U_Roof_1/etc. anywhere.

Run:
    python examples/chile/simulate_dwelling_database.py
"""
import numpy as np
import pandas as pd
import tsib

# Stand-in for a real dwelling database (e.g. one row per SII cadastral
# record, after MERLIN_RCP maps its material/zone codes onto tsib's
# "mad"/"lad"/"hor" and "A".."I" conventions). Same TMY reused for all rows
# below purely for brevity -- a real run would use one TMY per comuna/zone
# via tsib.bd_tmy_to_tsib.
DWELLINGS = pd.DataFrame(
    [
        {"dwelling_id": "D001", "buildingYear": 1985, "buildingType": "SFH", "material": "mad", "thermalZone": "G", "a_ref": 60.0},
        {"dwelling_id": "D002", "buildingYear": 2003, "buildingType": "SFH", "material": "hor", "thermalZone": "D", "a_ref": 65.0},
        {"dwelling_id": "D003", "buildingYear": 2012, "buildingType": "MFH", "material": "lad", "thermalZone": "D", "a_ref": 60.0},
        {"dwelling_id": "D004", "buildingYear": 2018, "buildingType": "AB",  "material": "hor", "thermalZone": "A", "a_ref": 58.0},
        {"dwelling_id": "D005", "buildingYear": 1972, "buildingType": "SFH", "material": "lad", "thermalZone": "F", "a_ref": 62.0},
    ]
)


def _fixed_synthetic_tmy(t_mean_c=8.0, n=8760):
    rng = pd.date_range("2010-01-01", periods=n, freq="h")
    t = np.arange(n)
    T = t_mean_c + 10.0 * np.sin(2 * np.pi * (t - 2000) / n)
    return pd.DataFrame(
        {
            "T":   T,
            "DHI": np.clip(200 * np.sin(np.pi * t / 24), 0, None),
            "DNI": np.clip(400 * np.sin(np.pi * t / 24), 0, None),
            "GHI": np.clip(500 * np.sin(np.pi * t / 24), 0, None),
        },
        index=rng,
    )


def simulate_one(row, tmy):
    n = len(tmy)

    cfg_obj = tsib.BuildingConfiguration(
        {
            "country":      "CL",
            "buildingYear": int(row["buildingYear"]),
            "buildingType": row["buildingType"],
            "material":     row["material"],
            "thermalZone":  row["thermalZone"],
            "a_ref":        float(row["a_ref"]),
            "weatherData":  tmy,
            "weatherID":    f"dwelling_{row['dwelling_id']}",
            "refurbishment": False,
        },
        ignore_profiles=True,
    )
    cfg = cfg_obj.getBdgCfg(includeSupply=True)

    zeros = pd.Series(np.zeros(n), index=tmy.index)
    cfg.update(
        {
            "Q_ig":         np.full(n, 0.3),
            "occ_nothome":  zeros,
            "occ_sleeping": zeros,
            "elecLoad":     zeros,
            "hotWaterLoad": zeros,
        }
    )

    model = tsib.Building5R1C(cfg)
    model.sim_demand_direct()  # constant comfort setpoints (cfg["comfortT_lb"/"ub"])

    heating_kwh = model.detailedResults["Heating Load"].sum()
    cooling_kwh = model.detailedResults["Cooling Load"].sum()
    return {
        "dwelling_id":  row["dwelling_id"],
        "U_Wall_1":     cfg["U_Wall_1"],   # resolved, not hardcoded -- varies per row below
        "U_Window":     cfg["U_Window"],
        "heating_kWh":  heating_kwh,
        "cooling_kWh":  cooling_kwh,
        "q_h_nd_kWh_m2": heating_kwh / row["a_ref"],
    }


def main():
    tmy = _fixed_synthetic_tmy()
    results = pd.DataFrame([simulate_one(row, tmy) for _, row in DWELLINGS.iterrows()])
    print(DWELLINGS.merge(results, on="dwelling_id").to_string(index=False))


if __name__ == "__main__":
    main()
