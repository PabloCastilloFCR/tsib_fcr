"""Simulate heat load for a Santiago apartment tower with tsib.

The case represents a 23-storey, 229-unit mid-2000s apartment building in
downtown Santiago de Chile. Because the bundled tsib archetype/weather data are
European, the script uses Madrid, Spain PVGIS TMY weather as a Mediterranean
European proxy and uses tsib's German apartment-block fabric as a temporary
mid-2000s envelope proxy.
"""

from __future__ import annotations

import contextlib
import json
import sys
import urllib.request
import warnings
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[3]
TSIB_ROOT = ROOT / "external" / "tsib"
if str(TSIB_ROOT) not in sys.path:
    sys.path.insert(0, str(TSIB_ROOT))

import tsib  # noqa: E402
import tsib.thermal.model5R1C as tsib_model5r1c  # noqa: E402
import tsib.thermal.utils as tsib_thermal_utils  # noqa: E402


CASE = {
    "name": "approach1_engineering_sensitivity_proxy_madrid",
    "building_data_source": "engineering_sensitivity_case",
    "building_year": 2005,
    "storeys": 23,
    "units": 229,
    "apply_reported_u_values_in_model": False,
    "mean_unit_area_m2": 42.0,
    "persons_per_unit": 3,
    "calibrate_to_reported_ua": False,
    "comfort_t_lb_c": 20.0,
    "comfort_t_ub_c": 26.0,
    "dhw_l_per_person_day": 30.0,
    "dhw_supply_c": 45.0,
    "dhw_cold_c": 10.0,
    "internal_gains_kwh_m2_year": 15.552,
    "window_to_wall_ratio": 0.22,
    "thermal_loss_multiplier": 1.5,
    "thermal_loss_multiplier_note": (
        "Engineering sensitivity for lower-quality Chilean construction: "
        "multiplies envelope U-values and infiltration/ventilation losses."
    ),
    "boiler_efficiency_lhv": 0.88,
    "natural_gas_lhv_kwh_m3": 9.5,
    "proxy_location": "Madrid, Spain",
    "proxy_latitude": 40.4168,
    "proxy_longitude": -3.7038,
    "proxy_reason": (
        "Mediterranean/inland European climate proxy for Santiago: dry warm "
        "summers, cool winters, and an urban high-density context."
    ),
}


OUT_DIR = ROOT / "sectors" / "residential" / "results" / "santiago_tower_tsib"
WEATHER_JSON = OUT_DIR / "weather_pvgis_tmy_madrid.json"
WEATHER_CSV = OUT_DIR / "weather_pvgis_tmy_madrid.csv"
HOURLY_CSV = OUT_DIR / "santiago_tower_heat_load_hourly.csv"
MONTHLY_CSV = OUT_DIR / "santiago_tower_heat_load_monthly.csv"
SUMMARY_CSV = OUT_DIR / "santiago_tower_heat_load_summary.csv"
REPORT_MD = OUT_DIR / "santiago_tower_heat_load_report.md"
SOLVER_LOG = OUT_DIR / "highs_solve.log"
MONTHLY_PNG = OUT_DIR / "santiago_tower_monthly_thermal_load_and_gas.png"
COMPONENTS_HOURLY_CSV = OUT_DIR / "santiago_tower_tsib_components_hourly.csv"
COMPONENTS_MONTHLY_CSV = OUT_DIR / "santiago_tower_tsib_components_monthly.csv"
COMPONENTS_SUMMARY_CSV = OUT_DIR / "santiago_tower_tsib_components_summary.csv"
COMPONENTS_COMPARISON_CSV = OUT_DIR / "santiago_tower_tsib_vs_catedral_components.csv"
COMPONENTS_REPORT_MD = OUT_DIR / "santiago_tower_tsib_component_comparison_report.md"


def fetch_pvgis_tmy() -> dict:
    """Fetch and cache PVGIS TMY weather for the selected European proxy."""
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    if WEATHER_JSON.exists():
        return json.loads(WEATHER_JSON.read_text(encoding="utf-8"))

    url = (
        "https://re.jrc.ec.europa.eu/api/v5_2/tmy?"
        f"lat={CASE['proxy_latitude']}&lon={CASE['proxy_longitude']}"
        "&outputformat=json"
    )
    with urllib.request.urlopen(url, timeout=60) as response:
        payload = response.read().decode("utf-8")
    WEATHER_JSON.write_text(payload, encoding="utf-8")
    return json.loads(payload)


def pvgis_to_tsib_weather(payload: dict) -> pd.DataFrame:
    """Convert PVGIS TMY JSON to tsib weather columns: T, DHI, DNI."""
    hourly = pd.DataFrame(payload["outputs"]["tmy_hourly"])
    idx = pd.date_range("2010-01-01 00:00", periods=len(hourly), freq="h", tz="UTC")

    weather = pd.DataFrame(index=idx)
    weather["T"] = hourly["T2m"].astype(float).to_numpy()
    weather["DHI"] = hourly["Gd(h)"].astype(float).clip(lower=0).to_numpy()
    weather["DNI"] = hourly["Gb(n)"].astype(float).clip(lower=0).to_numpy()
    weather["GHI"] = hourly["G(h)"].astype(float).clip(lower=0).to_numpy()

    if len(weather) != 8760:
        raise ValueError(f"Expected 8760 hourly weather rows, got {len(weather)}")

    weather.to_csv(WEATHER_CSV)
    return weather


def normalized_daily_shape(index: pd.DatetimeIndex, weights_by_hour: dict[int, float]) -> pd.Series:
    """Return an hourly profile whose average value is one."""
    weights = pd.Series(index=index, data=[weights_by_hour.get(ts.hour, 1.0) for ts in index])
    return weights / weights.mean()


def build_profiles(index: pd.DatetimeIndex, area_m2: float, persons: int) -> dict[str, pd.Series]:
    """Create deterministic aggregate profiles needed by tsib's 5R1C model."""
    internal_shape = normalized_daily_shape(
        index,
        {
            0: 1.05,
            1: 0.95,
            2: 0.90,
            3: 0.85,
            4: 0.85,
            5: 0.95,
            6: 1.20,
            7: 1.35,
            8: 1.15,
            17: 1.20,
            18: 1.45,
            19: 1.65,
            20: 1.70,
            21: 1.55,
            22: 1.35,
            23: 1.20,
        },
    )
    annual_internal_kwh = area_m2 * CASE["internal_gains_kwh_m2_year"]
    q_ig = internal_shape * (annual_internal_kwh / len(index))

    sleeping = pd.Series(0.08, index=index)
    sleeping[(index.hour >= 23) | (index.hour <= 6)] = 0.85

    not_home = pd.Series(0.15, index=index)
    weekday = index.weekday < 5
    not_home[weekday & (index.hour >= 9) & (index.hour <= 17)] = 0.62
    not_home[~weekday & (index.hour >= 11) & (index.hour <= 17)] = 0.35

    dhw_shape = normalized_daily_shape(
        index,
        {
            0: 0.25,
            1: 0.15,
            2: 0.10,
            3: 0.10,
            4: 0.15,
            5: 0.45,
            6: 1.60,
            7: 2.40,
            8: 1.85,
            9: 0.95,
            10: 0.65,
            11: 0.70,
            12: 0.95,
            13: 0.85,
            14: 0.60,
            15: 0.55,
            16: 0.65,
            17: 0.90,
            18: 1.40,
            19: 1.95,
            20: 2.10,
            21: 1.55,
            22: 0.95,
            23: 0.45,
        },
    )
    if "reported_annual_dhw_kwh" in CASE:
        annual_dhw_kwh = CASE["reported_annual_dhw_kwh"]
    else:
        dhw_delta_t = CASE["dhw_supply_c"] - CASE["dhw_cold_c"]
        dhw_kwh_person_day = CASE["dhw_l_per_person_day"] * 4.186 * dhw_delta_t / 3600.0
        annual_dhw_kwh = persons * dhw_kwh_person_day * 365.0
    hot_water_load = dhw_shape * (annual_dhw_kwh / len(index))

    return {
        "Q_ig": q_ig,
        "occ_sleeping": sleeping,
        "occ_nothome": not_home,
        "elecLoad": pd.Series(0.0, index=index),
        "hotWaterLoad": hot_water_load,
    }


def adapt_to_tower_geometry(cfg: dict) -> dict:
    """Replace TABULA low-rise geometry with a compact 23-storey tower shape."""
    area = CASE.get("total_useful_surface_m2", CASE["units"] * CASE["mean_unit_area_m2"])
    storeys = CASE["storeys"]
    floor_plate = area / storeys
    side = floor_plate**0.5
    perimeter = 4.0 * side
    cfg["h_room"] = CASE.get("room_height_m", cfg["h_room"])
    gross_facade = perimeter * cfg["h_room"] * storeys
    window_area = CASE.get(
        "reported_window_area_m2", gross_facade * CASE["window_to_wall_ratio"]
    )
    opaque_wall_area = gross_facade - window_area
    if opaque_wall_area <= 0:
        raise ValueError("Reported window area is larger than the inferred facade area.")

    cfg["A_ref"] = area
    cfg["a_ref"] = area
    cfg["n_apartments"] = CASE["units"]
    cfg["n_Storey"] = storeys

    cfg["A_Roof_1"] = floor_plate
    cfg["A_Roof_2"] = 0.0
    cfg["A_Floor_1"] = floor_plate
    cfg["A_Floor_2"] = 0.0
    cfg["A_Wall_1"] = opaque_wall_area
    cfg["A_Wall_2"] = 0.0
    cfg["A_Wall_3"] = 0.0
    cfg["A_Door_1"] = 20.0

    for direction in ["North", "East", "South", "West"]:
        cfg[f"A_Window_{direction}"] = window_area / 4.0
    cfg["A_Window_Horizontal"] = 0.0
    cfg["A_Window"] = window_area

    if CASE.get("apply_reported_u_values_in_model", True):
        cfg["U_Window"] = CASE["reported_u_window_w_m2k"]
        cfg["U_Wall_1"] = CASE["reported_u_wall_w_m2k"]
        cfg["U_Wall_2"] = CASE["reported_u_wall_w_m2k"]
        cfg["U_Wall_3"] = CASE["reported_u_wall_w_m2k"]
        cfg["U_Floor_1"] = CASE["reported_u_floor_w_m2k"]
        cfg["U_Floor_2"] = CASE["reported_u_floor_w_m2k"]
        cfg["U_Roof_1"] = CASE["reported_u_roof_w_m2k"]
        cfg["U_Roof_2"] = CASE["reported_u_roof_w_m2k"]

    ua_mode = CASE.get("calibrate_to_reported_ua", False)
    if ua_mode:
        target = CASE["reported_ua_w_k"]
        current = calc_loss_coefficient_w_k(cfg)
        if current <= 0:
            raise ValueError("Cannot calibrate losses because current UA is non-positive.")
        cfg["reported_ua_calibration_multiplier"] = target / current
        if ua_mode == "in_model":
            cfg = calibrate_losses_to_reported_ua(cfg)

    return cfg


def calc_loss_coefficient_w_k(cfg: dict) -> float:
    """Calculate the modelled transmission plus air-exchange loss coefficient."""
    h_transmission = (
        cfg["A_Roof_1"] * cfg["U_Roof_1"] * cfg["b_Transmission_Roof_1"]
        + cfg["A_Roof_2"] * cfg["U_Roof_2"] * cfg["b_Transmission_Roof_2"]
        + cfg["A_Wall_1"] * cfg["U_Wall_1"] * cfg["b_Transmission_Wall_1"]
        + cfg["A_Wall_2"] * cfg["U_Wall_2"] * cfg["b_Transmission_Wall_2"]
        + cfg["A_Wall_3"] * cfg["U_Wall_3"] * cfg["b_Transmission_Wall_3"]
        + cfg["A_Window"] * cfg["U_Window"]
        + cfg["A_Door_1"] * cfg["U_Door_1"]
        + cfg["A_Floor_1"] * cfg["U_Floor_1"] * cfg["b_Transmission_Floor_1"]
        + cfg["A_Floor_2"] * cfg["U_Floor_2"] * cfg["b_Transmission_Floor_2"]
    )
    h_air = (
        cfg["A_ref"]
        * cfg["h_room"]
        * 1.2
        * 1006
        * (cfg["n_air_infiltration"] + cfg["n_air_use"])
        / 3600
    )
    return h_transmission + h_air


def calibrate_losses_to_reported_ua(cfg: dict) -> dict:
    """Scale losses so the modelled H coefficient matches the EDA-reported UA."""
    target = CASE["reported_ua_w_k"]
    current = calc_loss_coefficient_w_k(cfg)
    if current <= 0:
        raise ValueError("Cannot calibrate losses because current UA is non-positive.")
    scale = target / current
    cfg["reported_ua_calibration_multiplier"] = scale
    for key in list(cfg):
        if key.startswith("U_"):
            cfg[key] *= scale
    for key in ["n_air_infiltration", "n_air_use"]:
        cfg[key] *= scale
    return cfg


def apply_thermal_loss_multiplier(cfg: dict) -> dict:
    """Scale thermal losses for construction-quality sensitivity analysis."""
    multiplier = CASE["thermal_loss_multiplier"]
    if multiplier == 1.0:
        return cfg

    for key in list(cfg):
        if key.startswith("U_"):
            cfg[key] *= multiplier

    for key in ["n_air_infiltration", "n_air_use"]:
        cfg[key] *= multiplier

    return cfg


def _value(obj) -> float:
    """Return a float value from either a Pyomo object or a plain number."""
    return float(obj.value if hasattr(obj, "value") else obj)


def extract_component_flows(
    model: tsib.Building5R1C,
    profiles: dict[str, pd.Series],
    hourly: pd.DataFrame,
    heating_multiplier: float = 1.0,
) -> pd.DataFrame:
    """Extract annual-comparable 5R1C heat-balance terms from solved tsib model.

    Sign convention in exported columns:
    - losses are positive when heat leaves the building.
    - solar/internal gains are positive when heat enters the building.
    """
    m = model.M
    index = hourly.index
    full_time = list(m.fullTimeIndex)

    def sum_q_comp(component_set) -> np.ndarray:
        values = []
        for time_key in full_time:
            val = 0.0
            for comp, dec in component_set:
                val += _value(m.bQ_comp[comp, dec, time_key])
            values.append(val)
        return np.asarray(values, dtype=float)

    def profile(name: str) -> np.ndarray:
        return np.asarray([m.profiles[name][time_key] for time_key in full_time], dtype=float)

    def active_solar_profile() -> np.ndarray:
        values = []
        for time_key in full_time:
            val = 0.0
            for comp, dec in m.bX_solar:
                active = _value(m.exVars[comp, dec])
                val += m.profiles["bQ_sol_" + comp + dec][time_key] * active
            values.append(val)
        return np.asarray(values, dtype=float)

    t_e = profile("T_e")
    t_m = model.detailedResults["T_m"].to_numpy(dtype=float)
    door_loss = m.bH_door * (t_m - t_e)

    envelope_losses = (
        sum_q_comp(m.bX_opaque)
        + sum_q_comp(m.bX_windows)
        + np.asarray(door_loss, dtype=float)
    )
    air_renewal_losses = sum_q_comp(m.bX_vent)
    solar_gains = active_solar_profile()

    component_hourly = pd.DataFrame(index=index)
    component_hourly["q_ra_air_renewal_kwh"] = air_renewal_losses
    component_hourly["q_e_envelope_losses_kwh"] = envelope_losses
    component_hourly["q_acs_dhw_kwh"] = profiles["hotWaterLoad"].to_numpy(dtype=float)
    component_hourly["q_rad_solar_gains_kwh"] = solar_gains
    component_hourly["q_intg_internal_gains_kwh"] = profiles["Q_ig"].to_numpy(dtype=float)
    component_hourly["space_heating_kwh"] = (
        model.detailedResults["Heating Load"].to_numpy(dtype=float) * heating_multiplier
    )
    component_hourly["space_cooling_kwh"] = model.detailedResults["Cooling Load"].to_numpy(
        dtype=float
    )
    component_hourly["t_air_c"] = model.detailedResults["T_air"].to_numpy(dtype=float)
    component_hourly["t_m_c"] = t_m
    component_hourly["t_e_c"] = t_e
    return component_hourly


def compare_components_to_catedral(component_hourly: pd.DataFrame) -> pd.DataFrame:
    """Compare tsib annual component sums to Catedral 1330 previous-model outputs."""
    q_summary_path = (
        ROOT
        / "com_pub_hcarb_chile_2024"
        / "catedral_1330_dp_eda"
        / "tables"
        / "q_summary.csv"
    )
    q_summary = pd.read_csv(q_summary_path).set_index("variable")
    mapping = [
        ("q_ra", "q_ra_air_renewal_kwh", "air renewed heating"),
        ("q_e", "q_e_envelope_losses_kwh", "envelope losses"),
        ("q_acs", "q_acs_dhw_kwh", "DHW heating"),
        ("q_rad", "q_rad_solar_gains_kwh", "solar gains"),
    ]

    rows = []
    for catedral_var, tsib_col, label in mapping:
        catedral_kwh = float(q_summary.loc[catedral_var, "sum"])
        tsib_kwh = float(component_hourly[tsib_col].sum())
        rows.append(
            {
                "component": label,
                "catedral_variable": catedral_var,
                "tsib_column": tsib_col,
                "catedral_kwh": catedral_kwh,
                "tsib_kwh": tsib_kwh,
                "error_kwh": tsib_kwh - catedral_kwh,
                "abs_error_kwh": abs(tsib_kwh - catedral_kwh),
                "pct_error": ((tsib_kwh - catedral_kwh) / catedral_kwh * 100.0)
                if catedral_kwh
                else np.nan,
            }
        )
    return pd.DataFrame(rows)


def write_component_report(
    component_summary: pd.Series,
    component_comparison: pd.DataFrame,
) -> None:
    """Write a compact report for tsib component extraction and comparison."""
    lines = [
        "# tsib component extraction vs Catedral 1330 previous model",
        "",
        "## Active tsib case",
        "",
        "- Approach: first engineering sensitivity case.",
        f"- Units: {CASE['units']}.",
        f"- Mean unit area: {CASE['mean_unit_area_m2']:.1f} m2.",
        f"- Persons per unit: {CASE['persons_per_unit']}.",
        f"- Thermal-loss multiplier: {CASE['thermal_loss_multiplier']:.2f}x.",
        "",
        "## Extracted tsib Annual Components",
        "",
        "| component | tsib_kwh |",
        "|---|---:|",
    ]
    for key, value in component_summary.items():
        lines.append(f"| {key} | {value:.0f} |")

    lines.extend(
        [
            "",
            "## Comparison To Catedral EDA q Variables",
            "",
            "| component | Catedral variable | Catedral kWh | tsib kWh | error kWh | pct error |",
            "|---|---|---:|---:|---:|---:|",
        ]
    )
    for _, row in component_comparison.iterrows():
        lines.append(
            f"| {row['component']} | {row['catedral_variable']} | "
            f"{row['catedral_kwh']:.0f} | {row['tsib_kwh']:.0f} | "
            f"{row['error_kwh']:.0f} | {row['pct_error']:.1f}% |"
        )

    lines.extend(
        [
            "",
            "## Notes",
            "",
            "- `q_ra` is compared to tsib ventilation/air-renewal heat losses.",
            "- `q_e` is compared to tsib opaque envelope, windows, and door heat losses.",
            "- `q_acs` is compared to the external DHW profile added to tsib.",
            "- `q_rad` is compared to tsib net solar-gain profiles from the 5R1C model.",
            "- All hourly values are summed directly because the simulation timestep is one hour, so kW equals kWh per step.",
        ]
    )
    COMPONENTS_REPORT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_simulation(weather: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.Series, pd.DataFrame]:
    """Build the tsib configuration and run the 5R1C heat-load model."""
    area = CASE.get("total_useful_surface_m2", CASE["units"] * CASE["mean_unit_area_m2"])
    occupants = CASE.get("total_persons", CASE["units"] * CASE["persons_per_unit"])
    tsib_persons_per_unit = max(1, int(round(occupants / CASE["units"])))

    bdg_cfg = tsib.BuildingConfiguration(
        {
            "country": "DE",
            "buildingType": "MFH",
            "buildingYear": CASE["building_year"],
            "a_ref": float(area),
            "n_apartments": CASE["units"],
            "weatherData": weather,
            "weatherID": "PVGIS_TMY_MADRID_PROXY_FOR_SANTIAGO",
            "longitude": CASE["proxy_longitude"],
            "latitude": CASE["proxy_latitude"],
            "refurbishment": False,
            "refurbished": False,
            "nightReduction": True,
            "occControl": False,
            "capControl": True,
            "comfortT_lb": CASE["comfort_t_lb_c"],
            "comfortT_ub": CASE["comfort_t_ub_c"],
            "n_persons": tsib_persons_per_unit,
            "hotWaterElec": False,
            "existingHeatSupply": "Gas boiler",
            "replaceHeatSupply": False,
            "hasSolarThermal": False,
            "hasPhotovoltaic": False,
            "hasFirePlace": False,
            "roofTilt": 0.0,
            "roofOrientation": 180.0,
            "mean_load": True,
        },
        ignore_profiles=True,
    )

    cfg = bdg_cfg.getBdgCfg(includeSupply=True)
    cfg = adapt_to_tower_geometry(cfg)
    cfg = apply_thermal_loss_multiplier(cfg)
    profiles = build_profiles(weather.index, area, occupants)
    model_profiles = {key: value.copy() for key, value in profiles.items()}
    cfg.update(model_profiles)

    model = tsib.Building5R1C(cfg)
    original_manage_solver_opts = tsib_thermal_utils.manageSolverOpts
    original_highs_class = tsib_model5r1c.appsi.solvers.Highs

    class ScaledSimplexHighs(original_highs_class):
        """Keep tsib's HiGHS path, but avoid its hard-coded IPM/no-scale options."""

        def __setattr__(self, name, value):
            if name == "highs_options" and isinstance(value, dict):
                value = {"solver": "simplex"}
            super().__setattr__(name, value)

    tsib_thermal_utils.manageSolverOpts = (
        lambda solver, opts: {} if solver == "highs" else original_manage_solver_opts(solver, opts)
    )
    tsib_model5r1c.appsi.solvers.Highs = ScaledSimplexHighs
    try:
        with SOLVER_LOG.open("w", encoding="utf-8") as log:
            with contextlib.redirect_stdout(log), contextlib.redirect_stderr(log):
                with warnings.catch_warnings():
                    warnings.filterwarnings("ignore", category=FutureWarning)
                    model.sim5R1C(solver="highs", tee=False)
    finally:
        tsib_thermal_utils.manageSolverOpts = original_manage_solver_opts
        tsib_model5r1c.appsi.solvers.Highs = original_highs_class

    hourly = pd.DataFrame(index=weather.index)
    hourly["outdoor_temperature_c"] = weather["T"]
    heating_ua_multiplier = (
        cfg.get("reported_ua_calibration_multiplier", 1.0)
        if CASE.get("calibrate_to_reported_ua") == "postprocess"
        else 1.0
    )
    hourly["space_heating_kw"] = (
        model.detailedResults["Heating Load"].to_numpy() * heating_ua_multiplier
    )
    hourly["space_cooling_kw"] = model.detailedResults["Cooling Load"].to_numpy()
    hourly["dhw_kw"] = profiles["hotWaterLoad"].to_numpy()
    hourly["total_thermal_kw"] = hourly["space_heating_kw"] + hourly["dhw_kw"]
    hourly["internal_gains_kw"] = profiles["Q_ig"].to_numpy()
    hourly["t_air_c"] = model.detailedResults["T_air"].to_numpy()
    component_hourly = extract_component_flows(
        model,
        profiles,
        hourly,
        heating_multiplier=heating_ua_multiplier,
    )

    monthly = hourly.resample("ME").sum()
    monthly.index = monthly.index.strftime("%Y-%m")
    monthly = monthly[["space_heating_kw", "dhw_kw", "total_thermal_kw"]]
    monthly.columns = ["space_heating_kwh", "dhw_kwh", "total_thermal_kwh"]
    monthly["natural_gas_final_kwh_lhv"] = (
        monthly["total_thermal_kwh"] / CASE["boiler_efficiency_lhv"]
    )
    monthly["natural_gas_m3"] = (
        monthly["natural_gas_final_kwh_lhv"] / CASE["natural_gas_lhv_kwh_m3"]
    )

    peak_ts = hourly["total_thermal_kw"].idxmax()
    summary = pd.Series(
        {
            "proxy_location": CASE["proxy_location"],
            "total_units": CASE["units"],
            "storeys": CASE["storeys"],
            "heated_area_m2": area,
            "occupants_assumed": occupants,
            "mean_unit_area_m2": area / CASE["units"],
            "mean_persons_per_unit": occupants / CASE["units"],
            "thermal_loss_multiplier": CASE["thermal_loss_multiplier"],
            "reported_ua_w_k": CASE.get("reported_ua_w_k", np.nan),
            "reported_ua_calibration_multiplier": cfg.get(
                "reported_ua_calibration_multiplier", np.nan
            ),
            "annual_space_heating_mwh": hourly["space_heating_kw"].sum() / 1000.0,
            "annual_dhw_mwh": hourly["dhw_kw"].sum() / 1000.0,
            "annual_total_thermal_mwh": hourly["total_thermal_kw"].sum() / 1000.0,
            "annual_natural_gas_final_mwh_lhv": (
                monthly["natural_gas_final_kwh_lhv"].sum() / 1000.0
            ),
            "annual_natural_gas_m3": monthly["natural_gas_m3"].sum(),
            "space_heating_kwh_m2_year": hourly["space_heating_kw"].sum() / area,
            "total_thermal_kwh_m2_year": hourly["total_thermal_kw"].sum() / area,
            "peak_space_heating_kw": hourly["space_heating_kw"].max(),
            "peak_dhw_kw": hourly["dhw_kw"].max(),
            "peak_total_thermal_kw": hourly["total_thermal_kw"].max(),
            "peak_total_thermal_timestamp": peak_ts.isoformat(),
            "weather_min_temperature_c": hourly["outdoor_temperature_c"].min(),
            "weather_mean_temperature_c": hourly["outdoor_temperature_c"].mean(),
        }
    )
    return hourly, monthly, summary, component_hourly


def plot_monthly_load_and_gas(monthly: pd.DataFrame) -> None:
    """Create a monthly bar chart for useful load and natural gas consumption."""
    month_labels = pd.to_datetime(monthly.index).strftime("%b")
    x = np.arange(len(monthly))
    width = 0.68

    heating_mwh = monthly["space_heating_kwh"] / 1000.0
    dhw_mwh = monthly["dhw_kwh"] / 1000.0
    gas_m3 = monthly["natural_gas_m3"]

    fig, axes = plt.subplots(
        2,
        1,
        figsize=(11, 7.2),
        sharex=True,
        gridspec_kw={"height_ratios": [1.25, 1.0]},
    )

    axes[0].bar(x, heating_mwh, width=width, label="Space heating", color="#386cb0")
    axes[0].bar(x, dhw_mwh, width=width, bottom=heating_mwh, label="DHW", color="#fdb462")
    axes[0].set_ylabel("Useful thermal load (MWh/month)")
    axes[0].set_title("Monthly thermal load and natural gas consumption")
    axes[0].legend(loc="upper right", frameon=False)
    axes[0].grid(axis="y", alpha=0.25)

    axes[1].bar(x, gas_m3, width=width, color="#4daf4a")
    axes[1].set_ylabel("Natural gas (m3/month)")
    axes[1].set_xlabel("Month")
    axes[1].grid(axis="y", alpha=0.25)
    axes[1].text(
        0.01,
        0.95,
        (
            f"Boiler efficiency: {CASE['boiler_efficiency_lhv']:.0%} LHV; "
            f"natural gas LHV: {CASE['natural_gas_lhv_kwh_m3']:.1f} kWh/m3"
        ),
        transform=axes[1].transAxes,
        va="top",
        fontsize=9,
    )

    axes[1].set_xticks(x)
    axes[1].set_xticklabels(month_labels)
    for ax in axes:
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)

    fig.tight_layout()
    fig.savefig(MONTHLY_PNG, dpi=180)
    plt.close(fig)


def write_report(monthly: pd.DataFrame, summary: pd.Series) -> None:
    """Write a concise Markdown report beside the simulation outputs."""
    top_months = monthly.sort_values("space_heating_kwh", ascending=False).head(4)
    top_month_lines = [
        "| month | space_heating_kwh | dhw_kwh | total_thermal_kwh |",
        "|---|---:|---:|---:|",
    ]
    for month, row in top_months.iterrows():
        top_month_lines.append(
            f"| {month} | {row['space_heating_kwh']:.0f} | "
            f"{row['dhw_kwh']:.0f} | {row['total_thermal_kwh']:.0f} |"
        )
    case_lines = [
        "# Santiago Centro apartment tower heat-load simulation",
        "",
        "## Case definition",
        "",
        f"- Building data source: `{CASE['building_data_source']}`.",
        f"- Building: {CASE['storeys']}-storey apartment tower, {CASE['units']} units.",
        f"- Heated area: {summary['heated_area_m2']:.0f} m2 "
        f"({summary['mean_unit_area_m2']:.1f} m2 mean unit area).",
        f"- Construction period: mid-2000s, modelled as {CASE['building_year']}.",
        f"- Occupancy assumption: {summary['mean_persons_per_unit']:.2f} persons/unit "
        f"({summary['occupants_assumed']:.0f} people total).",
        f"- European proxy weather: {CASE['proxy_location']} PVGIS TMY.",
        f"- Proxy rationale: {CASE['proxy_reason']}",
        f"- Additional thermal-loss multiplier: {CASE['thermal_loss_multiplier']:.2f}x.",
    ]
    if "reported_window_area_m2" in CASE:
        case_lines.extend(
            [
                f"- Reported window area: {CASE['reported_window_area_m2']:.1f} m2.",
                f"- Reported U-values: window {CASE['reported_u_window_w_m2k']:.2f}, "
                f"wall {CASE['reported_u_wall_w_m2k']:.2f}, floor {CASE['reported_u_floor_w_m2k']:.2f}, "
                f"roof {CASE['reported_u_roof_w_m2k']:.2f} W/m2K.",
                f"- Reported U-values applied inside LP solve: {CASE['apply_reported_u_values_in_model']}.",
            ]
        )
    if CASE.get("calibrate_to_reported_ua"):
        case_lines.append(
            f"- Reported UA target: {summary['reported_ua_w_k']:.0f} W/K; "
            f"space-heating UA calibration multiplier: {summary['reported_ua_calibration_multiplier']:.2f}x "
            f"({CASE['calibrate_to_reported_ua']})."
        )

    lines = case_lines + [
        "",
        "## Main results",
        "",
        f"- Annual space-heating load: {summary['annual_space_heating_mwh']:.1f} MWh "
        f"({summary['space_heating_kwh_m2_year']:.1f} kWh/m2-year).",
        f"- Annual DHW useful load: {summary['annual_dhw_mwh']:.1f} MWh.",
        f"- Annual total useful thermal load: {summary['annual_total_thermal_mwh']:.1f} MWh "
        f"({summary['total_thermal_kwh_m2_year']:.1f} kWh/m2-year).",
        f"- Annual natural gas consumption: {summary['annual_natural_gas_final_mwh_lhv']:.1f} MWh LHV "
        f"({summary['annual_natural_gas_m3']:.0f} m3).",
        f"- Peak space-heating load: {summary['peak_space_heating_kw']:.1f} kW.",
        f"- Peak combined space-heating + DHW load: {summary['peak_total_thermal_kw']:.1f} kW "
        f"at {summary['peak_total_thermal_timestamp']}.",
        f"- Monthly graph: `{MONTHLY_PNG.name}`.",
        "",
        "## Highest space-heating months",
        "",
        "\n".join(top_month_lines),
        "",
        "## Important assumptions and limits",
        "",
        "- tsib's German/European apartment-block fabric is used as the starting template.",
        "- Geometry is overwritten to a compact 23-storey tower.",
        f"- {CASE['thermal_loss_multiplier_note']}",
        "- DHW is not optimized by tsib; it is added as a useful thermal load profile.",
        f"- Natural gas is estimated with a central boiler seasonal efficiency of {CASE['boiler_efficiency_lhv']:.0%} "
        f"LHV and natural gas LHV of {CASE['natural_gas_lhv_kwh_m3']:.1f} kWh/m3.",
        "- Distribution losses are not added separately.",
    ]
    REPORT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    payload = fetch_pvgis_tmy()
    weather = pvgis_to_tsib_weather(payload)
    hourly, monthly, summary, component_hourly = run_simulation(weather)

    component_energy_cols = [
        "q_ra_air_renewal_kwh",
        "q_e_envelope_losses_kwh",
        "q_acs_dhw_kwh",
        "q_rad_solar_gains_kwh",
        "q_intg_internal_gains_kwh",
        "space_heating_kwh",
        "space_cooling_kwh",
    ]
    component_monthly = component_hourly[component_energy_cols].resample("ME").sum()
    component_monthly.index = component_monthly.index.strftime("%Y-%m")
    component_summary = component_hourly[component_energy_cols].sum()
    component_comparison = compare_components_to_catedral(component_hourly)

    hourly.to_csv(HOURLY_CSV)
    monthly.to_csv(MONTHLY_CSV)
    summary.to_frame("value").to_csv(SUMMARY_CSV)
    component_hourly.to_csv(COMPONENTS_HOURLY_CSV)
    component_monthly.to_csv(COMPONENTS_MONTHLY_CSV)
    component_summary.to_frame("tsib_kwh").to_csv(COMPONENTS_SUMMARY_CSV)
    component_comparison.to_csv(COMPONENTS_COMPARISON_CSV, index=False)
    plot_monthly_load_and_gas(monthly)
    write_report(monthly, summary)
    write_component_report(component_summary, component_comparison)

    print("Simulation complete")
    print(f"Annual space heating: {summary['annual_space_heating_mwh']:.1f} MWh")
    print(f"Annual DHW: {summary['annual_dhw_mwh']:.1f} MWh")
    print(f"Annual total thermal: {summary['annual_total_thermal_mwh']:.1f} MWh")
    print(f"Annual natural gas: {summary['annual_natural_gas_m3']:.0f} m3")
    print(f"Peak combined load: {summary['peak_total_thermal_kw']:.1f} kW")
    print(f"Monthly graph: {MONTHLY_PNG}")
    print(f"Report: {REPORT_MD}")
    print(f"Component comparison: {COMPONENTS_COMPARISON_CSV}")
    print(f"Component report: {COMPONENTS_REPORT_MD}")


if __name__ == "__main__":
    main()
