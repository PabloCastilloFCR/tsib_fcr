# -*- coding: utf-8 -*-
"""Reproducible validation case for tsib.calculate_dhw_load.

Fixes persons, daily volume, target temperature, an hourly DHW draw-off
shape and a synthetic hourly t_mains series, so the printed annual result is
stable across runs. Mirrors the ACS formula MERLIN_RCP relies on, so it can
be diffed against this fork's own output going forward.

Run:
    python examples/chile/validation_dhw.py
"""
import numpy as np
import pandas as pd
import tsib

PERSONS_PER_UNIT       = 3
LITERS_PER_PERSON_DAY  = 40.0
TARGET_TEMP_C          = 55.0

# Simple two-peak daily draw-off shape (morning shower + evening peak),
# normalized below to sum to exactly 1 per day (calculate_dhw_load's
# "daily volume == persons * liters_per_person_day" guarantee only holds for
# a profile that truly sums to 1 — hand-authored weights rarely do exactly).
_DAILY_SHAPE_RAW = np.array(
    [
        0.01, 0.00, 0.00, 0.00, 0.01, 0.04, 0.10, 0.13,
        0.08, 0.04, 0.03, 0.04, 0.05, 0.04, 0.03, 0.03,
        0.04, 0.07, 0.10, 0.12, 0.10, 0.08, 0.04, 0.02,
    ]
)
_DAILY_SHAPE = _DAILY_SHAPE_RAW / _DAILY_SHAPE_RAW.sum()


def _fixed_hourly_index(n=8760):
    return pd.date_range("2024-01-01", periods=n, freq="h")


def main():
    index = _fixed_hourly_index()
    n = len(index)

    # Synthetic water-mains temperature: seasonal sinusoid, colder in winter
    # (Jun-Aug in the Southern Hemisphere), no randomness.
    day_of_year = index.dayofyear.values
    t_mains = pd.Series(
        12.0 - 4.0 * np.cos(2 * np.pi * (day_of_year - 15) / 365.0), index=index
    )

    profile = tsib.normalize_daily_shape(
        index, daily_shape_weekday=_DAILY_SHAPE, daily_shape_weekend=_DAILY_SHAPE
    )

    result = tsib.calculate_dhw_load(
        index=index,
        persons=PERSONS_PER_UNIT,
        liters_per_person_day=LITERS_PER_PERSON_DAY,
        target_temp_c=TARGET_TEMP_C,
        t_mains=t_mains,
        profile=profile,
    )

    annual_kwh = result["DHW Load"].sum()
    annual_liters = result["DHW Liters"].sum()
    expected_liters = PERSONS_PER_UNIT * LITERS_PER_PERSON_DAY * (n / 24.0)

    print(f"Persons per unit:        {PERSONS_PER_UNIT}")
    print(f"Target temperature:      {TARGET_TEMP_C} degC")
    print(f"t_mains range:           {t_mains.min():.1f} - {t_mains.max():.1f} degC")
    print(f"Annual DHW volume:       {annual_liters:10.0f} L  (expected {expected_liters:.0f} L)")
    print(f"Annual DHW useful load:  {annual_kwh:10.1f} kWh")


if __name__ == "__main__":
    main()
