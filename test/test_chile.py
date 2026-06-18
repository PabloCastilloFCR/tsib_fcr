"""Smoke tests: simulación completa con archetypes CL y TMY sintético.

Bypasses tsorb (pd.datetime incompatible con pandas >= 2.0) usando el mismo
patrón que simulate_santiago_tower_tsib.py: Building5R1C directamente con
perfiles deterministas inyectados en cfg antes de sim5R1C().
"""
import numpy as np
import pandas as pd
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


def _run_heat_load(archetype_id, tmy, a_ref, u_vals=None, weather_id="test"):
    """Corre el modelo 5R1C directamente via Building5R1C, sin pasar por Building."""
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
    cfg.update(_dummy_profiles(tmy.index))
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
