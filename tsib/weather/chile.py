"""Adaptador TMY de BD Ancestral al formato requerido por tsib."""
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


def bd_tmy_to_tsib(tmy_df: pd.DataFrame) -> pd.DataFrame:
    """
    Convierte TMY desde el formato de BD Ancestral al formato esperado por tsib.

    Parameters
    ----------
    tmy_df : pd.DataFrame
        DataFrame con 8760 filas en formato BD Ancestral.

    Returns
    -------
    pd.DataFrame
        DataFrame con columnas renombradas al formato tsib y DatetimeIndex horario.
    """
    cols_present = {k: v for k, v in _COL_MAP.items() if k in tmy_df.columns}
    result = tmy_df.rename(columns=cols_present)

    if not isinstance(result.index, pd.DatetimeIndex):
        if "timestamp" in tmy_df.columns:
            result.index = pd.to_datetime(tmy_df["timestamp"])
        else:
            result.index = pd.date_range("2024-01-01", periods=len(result), freq="h")

    return result
