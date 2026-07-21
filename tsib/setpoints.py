"""Monthly Chilean thermal-zone setpoint profiles."""
from pathlib import Path

import pandas as pd


_SETPOINTS_PATH = Path(__file__).parent / "data" / "chile" / "thermal_setpoints_by_zone_month.csv"
_SUPPORTED_RUNTIME_ZONES = set("ABCDEFGHI")


def get_chile_monthly_setpoints(index, thermal_zone):
    """Return hourly heating and cooling setpoints for a Chilean thermal zone.

    The source table is monthly and uses the calendar month of every timestamp
    in ``index``.  The archetype catalogue currently supports zones A--I;
    although the source table preserves zone J, it cannot be requested until
    the catalogue and kwarg validation support that zone as well.

    Returns a DataFrame indexed like ``index`` with ``"Heating Setpoint"`` and
    ``"Cooling Setpoint"`` columns in degrees Celsius.
    """
    index = pd.DatetimeIndex(index)
    zone = str(thermal_zone).upper()
    if zone not in _SUPPORTED_RUNTIME_ZONES:
        raise ValueError(
            f"thermal_zone must be one of {sorted(_SUPPORTED_RUNTIME_ZONES)}; "
            f"got {thermal_zone!r}. Zone J is retained in the source table but "
            "is not yet supported by the archetype catalogue."
        )

    table = pd.read_csv(_SETPOINTS_PATH)
    zone_table = table.loc[table["zone"] == zone].set_index("month")
    if set(zone_table.index) != set(range(1, 13)):
        raise ValueError(f"Setpoint table is incomplete for thermal zone {zone!r}.")

    values = zone_table.reindex(index.month)
    return pd.DataFrame(
        {
            "Heating Setpoint": values["heating_setpoint_c"].to_numpy(),
            "Cooling Setpoint": values["cooling_setpoint_c"].to_numpy(),
        },
        index=index,
    )
