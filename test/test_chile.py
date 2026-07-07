"""Smoke tests: simulación completa con archetypes CL y TMY sintético.

Bypasses tsorb (pd.datetime incompatible con pandas >= 2.0) usando el mismo
patrón que simulate_santiago_tower_tsib.py: Building5R1C directamente con
perfiles deterministas inyectados en cfg antes de sim5R1C().
"""
import numpy as np
import pandas as pd
import pytest
import tsib


def _make_synthetic_tmy(T_mean=10.0):
    rng = pd.date_range("2010-01-01", periods=8760, freq="h")
    t = np.arange(8760)
    T = T_mean + 10 * np.sin(2 * np.pi * (t - 2000) / 8760)
    return pd.DataFrame({
        "T":   T,
        "DHI": np.clip(200 * np.sin(np.pi * t / 24), 0, None),
        "DNI": np.clip(400 * np.sin(np.pi * t / 24), 0, None),
        "GHI": np.clip(500 * np.sin(np.pi * t / 24), 0, None),
    }, index=rng)


def _dummy_profiles(index, q_ig_kw=0.3):
    """Perfiles deterministas para evitar tsorb (pd.datetime roto en pandas >= 2.0).

    Q_ig debe ser un numpy array 1D (indexado por posición 0..8759 en la
    conversión profiles→dict de model5R1C línea 1294-1299).
    occ_* y elecLoad son pandas Series con DatetimeIndex; model5R1C aplica .values.
    """
    n = len(index)
    zeros = pd.Series(np.zeros(n), index=index)
    return {
        "Q_ig":         np.full(n, q_ig_kw),
        "occ_nothome":  zeros,
        "occ_sleeping": zeros,
        "elecLoad":     zeros,
        "hotWaterLoad": zeros,
    }


def _build_cfg(archetype_id, tmy, a_ref, u_vals=None, weather_id="test", q_ig_kw=0.3):
    """Arma un cfg listo para Building5R1C, sin pasar por Building."""
    u_vals = u_vals or {}
    bdg_cfg = tsib.BuildingConfiguration(
        {
            "ID":            archetype_id,
            "country":       "CL",
            "a_ref":         a_ref,
            "weatherData":   tmy,
            "weatherID":     weather_id,
            "refurbishment": False,
            **u_vals,
        },
        ignore_profiles=True,
    )
    cfg = bdg_cfg.getBdgCfg(includeSupply=True)
    cfg.update(_dummy_profiles(tmy.index, q_ig_kw=q_ig_kw))
    return cfg


def _run_heat_load(archetype_id, tmy, a_ref, u_vals=None, weather_id="test"):
    """Corre el modelo 5R1C directamente via Building5R1C, sin pasar por Building."""
    cfg = _build_cfg(archetype_id, tmy, a_ref, u_vals, weather_id)
    model = tsib.Building5R1C(cfg)
    model.sim_demand_direct()
    return model.detailedResults["Heating Load"].sum() / a_ref


def test_country_cl_accepted():
    """BuildingConfiguration no debe lanzar error con country='CL'."""
    tmy = _make_synthetic_tmy()
    tsib.BuildingConfiguration({
        "ID":          "CL.SFH.intN.lad",
        "country":     "CL",
        "a_ref":       65.0,
        "weatherData": tmy,
        "weatherID":   "test_country",
    })


def test_sfh_prenorma_madera_zona_g():
    """SFH pre-norma madera en zona G (fría): demanda específica debe ser alta."""
    tmy = _make_synthetic_tmy(T_mean=5.0)
    u_vals = {
        "U_Wall_1": 2.7, "U_Roof_1": 2.5,
        "U_Floor_1": 1.4, "U_Window_1": 5.8,
    }
    q_h_nd = _run_heat_load("CL.SFH.preN.mad", tmy, 60.0, u_vals)
    assert q_h_nd > 50,   f"q_h_nd={q_h_nd:.1f} kWh/m²/a demasiado bajo para zona G pre-norma"
    assert q_h_nd < 1500, f"q_h_nd={q_h_nd:.1f} kWh/m²/a irrealmente alto"


def test_sfh_ds50_menor_que_prenorma():
    """DS50 debe tener menor demanda de calefacción que pre-norma en la misma zona."""
    tmy = _make_synthetic_tmy(T_mean=6.0)
    u_prenorma = {"U_Wall_1": 2.7, "U_Roof_1": 2.5, "U_Floor_1": 1.4, "U_Window_1": 5.8}
    u_ds50     = {"U_Wall_1": 0.6, "U_Roof_1": 0.6, "U_Floor_1": 0.5, "U_Window_1": 2.8}
    q_pre = _run_heat_load("CL.SFH.preN.mad", tmy, 60.0, u_prenorma, weather_id="test_pre")
    q_ds  = _run_heat_load("CL.SFH.DS50.mad", tmy, 60.0, u_ds50,     weather_id="test_ds50")
    assert q_pre > q_ds, f"pre-norma ({q_pre:.1f}) debe ser > DS50 ({q_ds:.1f}) kWh/m²/a"


# ── sim_demand_direct: setpoints horarios y máscara de disponibilidad ──

_U_VALS_PRENORMA = {"U_Wall_1": 2.7, "U_Roof_1": 2.5, "U_Floor_1": 1.4, "U_Window_1": 5.8}


def test_sim_demand_direct_hourly_setpoints_match_constant_default():
    """Setpoints horarios constantes (arrays) deben dar el mismo resultado
    que no pasar ningún argumento (comportamiento por default)."""
    tmy = _make_synthetic_tmy(T_mean=6.0)
    n = len(tmy)

    cfg_a = _build_cfg("CL.SFH.preN.mad", tmy, 60.0, _U_VALS_PRENORMA, weather_id="test_default")
    model_a = tsib.Building5R1C(cfg_a)
    model_a.sim_demand_direct()

    cfg_b = _build_cfg("CL.SFH.preN.mad", tmy, 60.0, _U_VALS_PRENORMA, weather_id="test_explicit")
    model_b = tsib.Building5R1C(cfg_b)
    model_b.sim_demand_direct(
        heating_setpoint=np.full(n, cfg_b["comfortT_lb"]),
        cooling_setpoint=np.full(n, cfg_b["comfortT_ub"]),
    )

    np.testing.assert_allclose(
        model_a.detailedResults["Heating Load"].values,
        model_b.detailedResults["Heating Load"].values,
    )
    np.testing.assert_allclose(
        model_a.detailedResults["T_air"].values,
        model_b.detailedResults["T_air"].values,
    )
    assert "Heating Setpoint" in model_a.detailedResults.columns
    assert "Cooling Setpoint" in model_a.detailedResults.columns


def test_sim_demand_direct_heating_available_mask_forces_free_float():
    """heating_available=False debe apagar la calefacción (Heating Load = 0)
    y dejar T_air en free-float, sin usar setpoints infinitos."""
    tmy = _make_synthetic_tmy(T_mean=-5.0)  # frío: calefacción se activaría todas las horas
    n = len(tmy)
    cfg = _build_cfg("CL.SFH.preN.mad", tmy, 60.0, _U_VALS_PRENORMA, weather_id="test_avail")

    heating_available = np.ones(n, dtype=bool)
    heating_available[:24] = False

    model = tsib.Building5R1C(cfg)
    model.sim_demand_direct(heating_available=heating_available)

    assert (model.detailedResults["Heating Load"].values[:24] == 0.0).all()
    assert (model.detailedResults["T_air"].values[:24] < cfg["comfortT_lb"]).any()


def test_sim_demand_direct_rejects_non_finite_setpoints():
    tmy = _make_synthetic_tmy()
    cfg = _build_cfg("CL.SFH.intN.lad", tmy, 65.0, weather_id="test_nonfinite")
    model = tsib.Building5R1C(cfg)
    bad_setpoint = np.full(len(tmy), np.nan)
    with pytest.raises(ValueError):
        model.sim_demand_direct(heating_setpoint=bad_setpoint)


def test_sim_demand_direct_rejects_inverted_setpoints():
    tmy = _make_synthetic_tmy()
    cfg = _build_cfg("CL.SFH.intN.lad", tmy, 65.0, weather_id="test_inverted")
    model = tsib.Building5R1C(cfg)
    n = len(tmy)
    with pytest.raises(ValueError):
        model.sim_demand_direct(
            heating_setpoint=np.full(n, 25.0),
            cooling_setpoint=np.full(n, 20.0),
        )


# ── Q_ig: escalar / array / Series deben dar el mismo resultado ──

def test_q_ig_accepts_scalar_array_and_series():
    tmy = _make_synthetic_tmy(T_mean=8.0)
    n = len(tmy)
    totals = {}
    for label, q_ig in [
        ("scalar", 0.3),
        ("array", np.full(n, 0.3)),
        ("series", pd.Series(np.full(n, 0.3), index=tmy.index)),
    ]:
        cfg = _build_cfg("CL.SFH.intN.lad", tmy, 65.0, weather_id=f"test_qig_{label}")
        cfg["Q_ig"] = q_ig
        model = tsib.Building5R1C(cfg)
        model.sim_demand_direct()
        totals[label] = model.detailedResults["Heating Load"].sum()

    assert totals["scalar"] == pytest.approx(totals["array"])
    assert totals["scalar"] == pytest.approx(totals["series"])


def test_q_ig_rejects_wrong_length():
    tmy = _make_synthetic_tmy()
    cfg = _build_cfg("CL.SFH.intN.lad", tmy, 65.0, weather_id="test_qig_badlen")
    cfg["Q_ig"] = np.full(10, 0.3)  # wrong length
    model = tsib.Building5R1C(cfg)
    with pytest.raises(ValueError):
        model.sim_demand_direct()


# ── bd_tmy_to_tsib: alias y fallback de t_mains ──

def _make_bd_ancestral_df(t_mains_col=None, t_mains_value=15.0, n=8760):
    rng = pd.date_range("2024-01-01", periods=n, freq="h")
    data = {
        "tdry": 10.0 + 5.0 * np.sin(2 * np.pi * np.arange(n) / 8760),
        "dhi":  np.zeros(n),
        "dni":  np.zeros(n),
        "ghi":  np.zeros(n),
    }
    if t_mains_col is not None:
        data[t_mains_col] = np.full(n, t_mains_value)
    return pd.DataFrame(data, index=rng)


@pytest.mark.parametrize(
    "alias", ["t_mains", "tmains", "t_water_mains", "t_red", "temperatura_red", "t_agua_red"]
)
def test_bd_tmy_to_tsib_preserves_t_mains_aliases(alias):
    df = _make_bd_ancestral_df(t_mains_col=alias, t_mains_value=15.0)
    result = tsib.bd_tmy_to_tsib(df)
    assert "t_mains" in result.columns
    np.testing.assert_allclose(result["t_mains"].values, 15.0)
    assert result.attrs["t_mains_source"] == "observed"


def test_bd_tmy_to_tsib_missing_t_mains_warns_and_estimates():
    df = _make_bd_ancestral_df(t_mains_col=None)
    with pytest.warns(UserWarning):
        result = tsib.bd_tmy_to_tsib(df)
    assert "t_mains" in result.columns
    assert result.attrs["t_mains_source"] == "estimated_from_tdry"
    assert result["t_mains"].notna().all()


def test_bd_tmy_to_tsib_interpolates_partial_t_mains_nulls():
    df = _make_bd_ancestral_df(t_mains_col="t_mains", t_mains_value=15.0)
    df.loc[df.index[100], "t_mains"] = np.nan
    result = tsib.bd_tmy_to_tsib(df, t_mains_nan_policy="interpolate")
    assert result["t_mains"].notna().all()
    assert result.attrs["t_mains_source"] == "observed_interpolated"


# ── calculate_dhw_load ──

def test_calculate_dhw_load_daily_volume_matches_persons_liters():
    rng = pd.date_range("2024-01-01", periods=24, freq="h")
    result = tsib.calculate_dhw_load(
        index=rng,
        persons=3,
        liters_per_person_day=40,
        target_temp_c=55,
        t_mains=10.0,
    )
    assert result["DHW Liters"].sum() == pytest.approx(3 * 40)


def test_calculate_dhw_load_varies_with_hourly_t_mains():
    rng = pd.date_range("2024-01-01", periods=24, freq="h")
    t_mains = pd.Series(np.linspace(5.0, 20.0, 24), index=rng)
    result = tsib.calculate_dhw_load(
        index=rng, persons=3, liters_per_person_day=40, target_temp_c=55, t_mains=t_mains,
    )
    assert result["DHW Load"].nunique() > 1


def test_calculate_dhw_load_nan_policy_raise_and_interpolate():
    rng = pd.date_range("2024-01-01", periods=24, freq="h")
    t_mains = pd.Series(np.full(24, 10.0), index=rng)
    t_mains.iloc[5] = np.nan

    with pytest.raises(ValueError):
        tsib.calculate_dhw_load(
            index=rng, persons=3, liters_per_person_day=40, target_temp_c=55, t_mains=t_mains,
        )

    result = tsib.calculate_dhw_load(
        index=rng, persons=3, liters_per_person_day=40, target_temp_c=55, t_mains=t_mains,
        t_mains_nan_policy="interpolate",
    )
    assert result["T_mains"].notna().all()
