"""Reusable hourly-profile utilities shared by the 5R1C engine and consumers
like MERLIN_RCP: normalizing scalar/array/Series inputs to aligned hourly
arrays, building daily-shape profiles, and computing domestic hot water (DHW)
thermal demand from a water-mains temperature series.
"""
import numpy as np
import pandas as pd


def as_hourly_series(value, index, name="value"):
    """Normalize a scalar, list, ``np.ndarray`` or ``pd.Series`` to a 1-D
    ``np.ndarray`` of floats aligned to ``len(index)``.

    Parameters
    ----------
    value: scalar, list, np.ndarray or pd.Series
    index: array-like or pd.Index
        Target time index; only its length is used for alignment.
    name: str, optional
        Used in error messages to identify which profile failed validation.

    Returns
    -------
    np.ndarray of shape (len(index),)
    """
    n = len(index)

    if np.isscalar(value):
        arr = np.full(n, float(value), dtype=float)
    else:
        arr = np.asarray(
            value.values if isinstance(value, (pd.Series, pd.DataFrame)) else value,
            dtype=float,
        ).reshape(-1)
        if arr.shape[0] != n:
            raise ValueError(
                f'"{name}" has length {arr.shape[0]}, expected {n} '
                "to match the simulation time index."
            )

    if not np.all(np.isfinite(arr)):
        raise ValueError(
            f'"{name}" contains non-finite values (NaN/inf). '
            "Provide a fully-defined hourly profile."
        )

    return arr


def _as_hourly_array_allow_nan(value, n, name="value"):
    """Like :func:`as_hourly_series` but permits NaN values to pass through,
    for inputs (e.g. ``t_mains``) whose null-handling policy is decided by
    the caller rather than rejected outright.
    """
    if np.isscalar(value):
        return np.full(n, float(value), dtype=float)

    arr = np.asarray(
        value.values if isinstance(value, (pd.Series, pd.DataFrame)) else value,
        dtype=float,
    ).reshape(-1)
    if arr.shape[0] != n:
        raise ValueError(
            f'"{name}" has length {arr.shape[0]}, expected {n} '
            "to match the simulation time index."
        )
    return arr


def normalize_profile_to_annual_energy(profile, annual_kwh):
    """Scale a relative hourly profile so that its sum equals ``annual_kwh``.

    Preserves the index if ``profile`` is a ``pd.Series``.
    """
    is_series = isinstance(profile, pd.Series)
    arr = np.asarray(profile.values if is_series else profile, dtype=float)

    total = arr.sum()
    if total <= 0:
        raise ValueError("'profile' must have a strictly positive sum to be normalized.")

    scaled = arr / total * float(annual_kwh)

    if is_series:
        return pd.Series(scaled, index=profile.index)
    return scaled


def normalize_daily_shape(index, daily_shape_weekday, daily_shape_weekend, holidays=None):
    """Build an hourly ``pd.Series`` over ``index`` by tiling a 24-value
    weekday or weekend/holiday daily shape according to each timestamp's
    calendar day.

    Parameters
    ----------
    index: pd.DatetimeIndex
    daily_shape_weekday: array-like of length 24
    daily_shape_weekend: array-like of length 24
    holidays: iterable of date-like, optional
        Dates (parseable by ``pd.to_datetime``) treated as weekend-shaped
        days even if they fall on a weekday.
    """
    weekday_shape = np.asarray(daily_shape_weekday, dtype=float)
    weekend_shape = np.asarray(daily_shape_weekend, dtype=float)
    if weekday_shape.shape[0] != 24 or weekend_shape.shape[0] != 24:
        raise ValueError(
            "'daily_shape_weekday' and 'daily_shape_weekend' must each have 24 values."
        )

    index = pd.DatetimeIndex(index)
    holiday_dates = set(pd.to_datetime(list(holidays)).date) if holidays is not None else set()

    is_weekend_shaped = (index.weekday >= 5) | np.isin(index.date, list(holiday_dates))

    values = np.where(is_weekend_shaped, weekend_shape[index.hour], weekday_shape[index.hour])

    return pd.Series(values, index=index)


_OCC_SLEEPING_WEEKDAY = np.array(
    [0.95, 0.98, 0.98, 0.98, 0.95, 0.80, 0.35, 0.05, 0.00, 0.00, 0.00, 0.00,
     0.00, 0.00, 0.00, 0.00, 0.00, 0.00, 0.00, 0.00, 0.00, 0.05, 0.35, 0.75]
)
_OCC_NOTHOME_WEEKDAY = np.array(
    [0.00, 0.00, 0.00, 0.00, 0.00, 0.00, 0.10, 0.35, 0.65, 0.75, 0.78, 0.75,
     0.65, 0.70, 0.75, 0.72, 0.60, 0.35, 0.15, 0.08, 0.04, 0.02, 0.00, 0.00]
)
_OCC_SLEEPING_WEEKEND = np.array(
    [0.95, 0.98, 0.98, 0.98, 0.95, 0.85, 0.60, 0.30, 0.10, 0.02, 0.00, 0.00,
     0.00, 0.00, 0.00, 0.00, 0.00, 0.00, 0.00, 0.00, 0.02, 0.08, 0.35, 0.75]
)
_OCC_NOTHOME_WEEKEND = np.array(
    [0.00, 0.00, 0.00, 0.00, 0.00, 0.00, 0.02, 0.05, 0.10, 0.18, 0.25, 0.30,
     0.32, 0.35, 0.35, 0.32, 0.28, 0.20, 0.12, 0.08, 0.05, 0.02, 0.00, 0.00]
)
_ELECTRICITY_WEEKDAY = np.array(
    [0.45, 0.40, 0.38, 0.36, 0.36, 0.45, 0.75, 0.95, 0.70, 0.55, 0.50, 0.52,
     0.58, 0.55, 0.52, 0.55, 0.70, 1.05, 1.35, 1.55, 1.45, 1.10, 0.80, 0.60]
)
_ELECTRICITY_WEEKEND = np.array(
    [0.55, 0.50, 0.45, 0.42, 0.42, 0.48, 0.65, 0.85, 1.00, 0.95, 0.85, 0.78,
     0.78, 0.75, 0.72, 0.75, 0.90, 1.10, 1.30, 1.45, 1.35, 1.05, 0.85, 0.68]
)
_DHW_WEEKDAY = np.array(
    [0.01, 0.00, 0.00, 0.00, 0.01, 0.04, 0.10, 0.13, 0.08, 0.04, 0.03, 0.04,
     0.05, 0.04, 0.03, 0.03, 0.04, 0.07, 0.10, 0.12, 0.10, 0.08, 0.04, 0.02]
)
_DHW_WEEKEND = np.array(
    [0.01, 0.00, 0.00, 0.00, 0.01, 0.02, 0.05, 0.08, 0.11, 0.10, 0.08, 0.06,
     0.05, 0.04, 0.04, 0.04, 0.05, 0.07, 0.10, 0.12, 0.10, 0.08, 0.04, 0.02]
)


def _integer_occupancy_counts(active, sleeping, nothome, persons):
    """Convert state fractions to integer persons using the largest remainder."""
    raw = np.column_stack([active, sleeping, nothome]) * persons
    counts = np.floor(raw).astype(int)
    missing = persons - counts.sum(axis=1)
    fractions = raw - counts
    for row, remainder in enumerate(missing):
        if remainder:
            selected = np.argsort(-fractions[row])[:remainder]
            counts[row, selected] += 1
    return counts


def build_default_occupancy_profiles(
    index,
    persons,
    n_apartments=1,
    annual_electricity_kwh_per_apartment=2500.0,
    dhw_liters_per_person_day=40.0,
    dhw_target_temp_c=55.0,
    t_mains=None,
    holidays=None,
):
    """Build the documented MERLIN_RCP deterministic residential profiles.

    Weekday/weekend occupancy, electricity and DHW shapes come from
    ``feature-request/perfiles_horarios_tsib_fcr.md``.  Values are transparent
    defaults for integration and sensitivity analysis, not calibrated Chilean
    measurements. ``persons`` is per apartment; power and DHW series are
    aggregated over ``n_apartments``.
    """
    index = pd.DatetimeIndex(index)
    persons = int(persons)
    n_apartments = int(n_apartments)
    if persons < 1 or n_apartments < 1:
        raise ValueError("'persons' and 'n_apartments' must both be at least 1.")

    sleeping = normalize_daily_shape(
        index, _OCC_SLEEPING_WEEKDAY, _OCC_SLEEPING_WEEKEND, holidays=holidays
    )
    nothome = normalize_daily_shape(
        index, _OCC_NOTHOME_WEEKDAY, _OCC_NOTHOME_WEEKEND, holidays=holidays
    )
    active = 1.0 - sleeping - nothome

    electricity_shape = normalize_daily_shape(
        index, _ELECTRICITY_WEEKDAY, _ELECTRICITY_WEEKEND, holidays=holidays
    )
    electricity_weights = electricity_shape * (0.35 + 0.85 * active)
    target_kwh = annual_electricity_kwh_per_apartment * n_apartments * len(index) / 8760.0
    elec_load = electricity_weights / electricity_weights.sum() * target_kwh

    counts = _integer_occupancy_counts(
        active.to_numpy(), sleeping.to_numpy(), nothome.to_numpy(), persons
    )
    active_persons = counts[:, 0] * n_apartments
    sleeping_persons = counts[:, 1] * n_apartments
    present_persons = active_persons + sleeping_persons
    q_ig = active_persons * 0.10 + sleeping_persons * 0.07 + 0.15 * elec_load.to_numpy()

    if t_mains is None:
        t_mains = np.full(len(index), 10.0)
    dhw_shape = normalize_daily_shape(index, _DHW_WEEKDAY, _DHW_WEEKEND, holidays=holidays)
    dhw = calculate_dhw_load(
        index=index,
        persons=present_persons,
        liters_per_person_day=dhw_liters_per_person_day,
        target_temp_c=dhw_target_temp_c,
        t_mains=t_mains,
        profile=dhw_shape,
    )

    return {
        "Q_ig": q_ig,
        "occ_nothome": nothome,
        "occ_sleeping": sleeping,
        "elecLoad": elec_load,
        "hotWaterLoad": dhw["DHW Load"],
    }


def calculate_dhw_load(
    index,
    persons,
    liters_per_person_day,
    target_temp_c,
    t_mains,
    profile=None,
    holidays=None,
    t_mains_nan_policy="raise",
):
    """Compute domestic hot water (DHW) *useful thermal* demand.

    ``Q_DHW_h = liters_h * deltaT_h * 0.001163`` with
    ``liters_h = persons_h * liters_per_person_day * profile_h`` and
    ``deltaT_h = max(target_temp_c - t_mains_h, 0)``.

    Parameters
    ----------
    index: pd.DatetimeIndex
        Hourly time index for the result.
    persons: scalar or hourly array/Series
        Occupants per dwelling. Accepts a per-hour profile (e.g. active +
        sleeping occupant counts) for callers that want to zero DHW demand
        in unoccupied hours themselves.
    liters_per_person_day: float
        Daily hot water volume per person [L/person/day].
    target_temp_c: float
        DHW delivery target temperature [degC].
    t_mains: scalar or hourly array/Series
        Water mains (cold feed) temperature [degC].
    profile: hourly array/Series, optional
        Fraction of the daily DHW volume assigned to each hour, already
        aligned to ``index`` (e.g. built with :func:`normalize_daily_shape`).
        Defaults to a flat profile (``1/24`` every hour) when ``None``.
    holidays: unused, kept for API symmetry with :func:`normalize_daily_shape`
        when callers pass the same kwargs to both functions.
    t_mains_nan_policy: {"raise", "interpolate"}, optional (default "raise")
        How to handle missing values in ``t_mains``. ``"raise"`` fails loudly;
        ``"interpolate"`` linearly interpolates and fills remaining edge gaps.
        ``"fallback_from_tdry"`` is intentionally not supported here — that
        estimation belongs to the TMY adapter (:func:`tsib.bd_tmy_to_tsib`),
        which has access to the dry-bulb temperature series.

    Returns
    -------
    pd.DataFrame indexed by ``index`` with columns
    ``"DHW Load"`` [kWh/h], ``"DHW Liters"`` [L/h], ``"DHW DeltaT"`` [degC],
    ``"T_mains"`` [degC].
    """
    n = len(index)

    persons_h = as_hourly_series(persons, index, name="persons")
    t_mains_h = _as_hourly_array_allow_nan(t_mains, n, name="t_mains")

    if np.any(pd.isna(t_mains_h)):
        if t_mains_nan_policy == "raise":
            raise ValueError(
                "'t_mains' contains missing values. Pass t_mains_nan_policy="
                "'interpolate' to fill them, or provide a complete series."
            )
        elif t_mains_nan_policy == "interpolate":
            t_mains_h = (
                pd.Series(t_mains_h, index=index)
                .interpolate(limit_direction="both")
                .values
            )
        else:
            raise ValueError(
                f"Unknown t_mains_nan_policy {t_mains_nan_policy!r}. "
                "Use 'raise' or 'interpolate'."
            )

    if profile is None:
        profile_h = np.full(n, 1.0 / 24.0, dtype=float)
    else:
        profile_h = as_hourly_series(profile, index, name="profile")

    liters_h = persons_h * float(liters_per_person_day) * profile_h
    deltaT_h = np.maximum(float(target_temp_c) - t_mains_h, 0.0)
    q_dhw_h = liters_h * deltaT_h * 0.001163

    return pd.DataFrame(
        {
            "DHW Load": q_dhw_h,
            "DHW Liters": liters_h,
            "DHW DeltaT": deltaT_h,
            "T_mains": t_mains_h,
        },
        index=index,
    )


def convert_thermal_to_final(load, efficiency=None, cop=None):
    """Convert a useful thermal load to final energy using a system
    efficiency or COP. Kept deliberately separate from the thermal engine —
    it is a system/technology conversion, not a demand calculation.

    Exactly one of ``efficiency`` or ``cop`` must be given.
    """
    if (efficiency is None) == (cop is None):
        raise ValueError("Provide exactly one of 'efficiency' or 'cop'.")

    factor = cop if cop is not None else efficiency
    if factor <= 0:
        raise ValueError("'efficiency'/'cop' must be strictly positive.")

    return load / factor
