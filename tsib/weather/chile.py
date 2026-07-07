"""Adaptador TMY de BD Ancestral al formato requerido por tsib."""
import warnings

import numpy as np
import pandas as pd


_COL_MAP = {
    "tdry":              "T",
    "dhi":               "DHI",
    "dni":               "DNI",
    "ghi":               "GHI",
    "wspd":              "WS",
    "pres":              "p",
    "e_norte":           "e_norte",
    "e_este":            "e_este",
    "e_sur":             "e_sur",
    "e_oeste":           "e_oeste",
    "e_techo":           "e_techo",
    "h_conv":            "h_conv",
    "t_mains":           "t_mains",
    "air_density":       "air_density",
    "air_specific_heat": "air_specific_heat",
}

# Recognized input column names for the water-mains (cold feed) temperature,
# in priority order. The first one present in the input is used.
_T_MAINS_ALIASES = [
    "t_mains", "tmains", "tmain", "t_water_mains", "t_mains_c",
    "temp_mains", "temp_water_mains", "t_red", "temp_red",
    "temperatura_red", "t_agua_red", "temp_agua_red",
]

_T_MAINS_FALLBACK_WINDOW_HOURS = 24 * 30  # 30-day rolling mean, per spec


def bd_tmy_to_tsib(
    tmy_df: pd.DataFrame,
    t_mains_nan_policy: str = "interpolate",
    require_t_mains: bool = False,
) -> pd.DataFrame:
    """
    Convierte TMY desde el formato de BD Ancestral al formato esperado por tsib.

    Parameters
    ----------
    tmy_df : pd.DataFrame
        DataFrame con 8760 filas en formato BD Ancestral.
    t_mains_nan_policy : {"raise", "interpolate", "fallback_from_tdry"}, optional
        Qué hacer con nulos parciales quando la columna de temperatura de red
        SÍ está presente. "raise" levanta ValueError; "interpolate" (default)
        interpola linealmente y rellena bordes; "fallback_from_tdry" solo
        rellena los nulos con una media móvil de 30 días de la temperatura
        seca exterior (`T`).
    require_t_mains : bool, optional (default False)
        Si es True y ninguna columna de temperatura de red está presente,
        levanta ValueError en vez de advertir y estimar `t_mains` desde `T`.

    Returns
    -------
    pd.DataFrame
        DataFrame con columnas renombradas al formato tsib, DatetimeIndex
        horario, columna `t_mains` estandarizada (si hay datos disponibles o
        estimables) y `attrs["t_mains_source"]` documentando su procedencia.
    """
    cols_present = {k: v for k, v in _COL_MAP.items() if k in tmy_df.columns}
    result = tmy_df.rename(columns=cols_present)

    if not isinstance(result.index, pd.DatetimeIndex):
        if "timestamp" in tmy_df.columns:
            result.index = pd.to_datetime(tmy_df["timestamp"])
        else:
            result.index = pd.date_range("2024-01-01", periods=len(result), freq="h")

    t_mains_col = next((c for c in _T_MAINS_ALIASES if c in tmy_df.columns), None)

    if t_mains_col is not None:
        t_mains = pd.to_numeric(
            pd.Series(tmy_df[t_mains_col].values, index=result.index), errors="coerce"
        )
        source = "observed"

        if t_mains.isna().any():
            if t_mains_nan_policy == "raise":
                raise ValueError(
                    f'Column "{t_mains_col}" has missing values. Pass '
                    't_mains_nan_policy="interpolate" or "fallback_from_tdry" '
                    "to fill them, or provide a complete series."
                )
            elif t_mains_nan_policy == "interpolate":
                t_mains = t_mains.interpolate(limit_direction="both")
                source = "observed_interpolated"
            elif t_mains_nan_policy == "fallback_from_tdry":
                if "T" not in result.columns:
                    raise ValueError(
                        "Cannot apply t_mains_nan_policy='fallback_from_tdry': "
                        "no dry-bulb temperature column ('T'/'tdry') available."
                    )
                fallback = result["T"].rolling(
                    _T_MAINS_FALLBACK_WINDOW_HOURS, center=True, min_periods=1
                ).mean()
                t_mains = t_mains.fillna(fallback)
                source = "observed_partial_fallback_from_tdry"
            else:
                raise ValueError(
                    f"Unknown t_mains_nan_policy {t_mains_nan_policy!r}. "
                    "Use 'raise', 'interpolate' or 'fallback_from_tdry'."
                )
    else:
        if require_t_mains:
            raise ValueError(
                "No water-mains temperature column found in the input "
                f"(recognized names: {_T_MAINS_ALIASES}) and require_t_mains=True."
            )
        if "T" not in result.columns:
            warnings.warn(
                "No water-mains temperature column found and no dry-bulb "
                "temperature ('T'/'tdry') available to estimate a fallback; "
                "'t_mains' will not be set. DHW calculations will need an "
                "explicit t_mains input."
            )
            return result

        warnings.warn(
            "No water-mains temperature column found in TMY input "
            f"(recognized names: {_T_MAINS_ALIASES}). Estimating t_mains as a "
            "30-day rolling mean of the dry-bulb temperature. This is an "
            "ESTIMATE, not observed or modeled water-mains data — do not "
            "present it as calibrated ACS/DHW input without validation."
        )
        t_mains = result["T"].rolling(
            _T_MAINS_FALLBACK_WINDOW_HOURS, center=True, min_periods=1
        ).mean()
        source = "estimated_from_tdry"

    result["t_mains"] = t_mains.values
    result.attrs["t_mains_source"] = source

    return result
