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
