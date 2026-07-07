# -*- coding: utf-8 -*-
"""Reproducible validation case for the direct 5R1C path (sim_demand_direct).

Fixes every input explicitly — archetype, synthetic TMY, internal gains,
hourly setpoints and an HVAC availability mask — so the printed annual result
is stable across runs and can be diffed against a recorded baseline. This is
a validation fixture for the thermal engine itself, separate from any
occupancy/scenario assumptions (those belong to the consuming project, e.g.
MERLIN_RCP).

Run:
    python examples/chile/validation_direct_5r1c.py
"""
import numpy as np
import pandas as pd
import tsib

ARCHETYPE_ID = "CL.SFH.preN.mad"          # single-family, pre-code, wood frame
A_REF        = 60.0                        # conditioned floor area [m2]
U_VALS = {
    "U_Wall_1":   2.7,
    "U_Roof_1":   2.5,
    "U_Floor_1":  1.4,
    "U_Window_1": 5.8,
}
Q_IG_KW = 0.3                               # constant internal gains [kW]


def _fixed_synthetic_tmy(t_mean_c=6.0, n=8760):
    """Deterministic sinusoidal TMY — no randomness, always identical."""
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


def main():
    tmy = _fixed_synthetic_tmy()
    n = len(tmy)

    cfg_obj = tsib.BuildingConfiguration(
        {
            "ID":            ARCHETYPE_ID,
            "country":       "CL",
            "a_ref":         A_REF,
            "weatherData":   tmy,
            "weatherID":     "validation_direct_5r1c",
            "refurbishment": False,
            **U_VALS,
        },
        ignore_profiles=True,
    )
    cfg = cfg_obj.getBdgCfg(includeSupply=True)

    zeros = pd.Series(np.zeros(n), index=tmy.index)
    cfg.update(
        {
            "Q_ig":         np.full(n, Q_IG_KW),
            "occ_nothome":  zeros,
            "occ_sleeping": zeros,
            "elecLoad":     zeros,
            "hotWaterLoad": zeros,
        }
    )

    # Explicit hourly setpoints: comfort during the day, night setback, and
    # heating switched off overnight (hours 0-5) via the availability mask —
    # demonstrates the "off" pattern without ever using infinite setpoints.
    hour_of_day = np.array([ts.hour for ts in tmy.index])
    heating_setpoint = np.where(hour_of_day < 6, 16.0, 20.0)
    cooling_setpoint = np.full(n, 26.0)
    heating_available = hour_of_day >= 6

    model = tsib.Building5R1C(cfg)
    model.sim_demand_direct(
        heating_setpoint=heating_setpoint,
        cooling_setpoint=cooling_setpoint,
        heating_available=heating_available,
    )

    heating_kwh = model.detailedResults["Heating Load"].sum()
    cooling_kwh = model.detailedResults["Cooling Load"].sum()
    q_h_nd = heating_kwh / A_REF

    print(f"Archetype:            {ARCHETYPE_ID}")
    print(f"Annual heating demand: {heating_kwh:10.1f} kWh  ({q_h_nd:.1f} kWh/m2/a)")
    print(f"Annual cooling demand: {cooling_kwh:10.1f} kWh")
    print(f"Hours with heating off (night, 00-05h): {int((~heating_available).sum())}")


if __name__ == "__main__":
    main()
