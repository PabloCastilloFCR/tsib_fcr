import numpy as np, pandas as pd, tsib, warnings
from pyomo.contrib import appsi
warnings.filterwarnings('ignore')

full_rng = pd.date_range('2010-01-01', periods=8760, freq='h')
t = np.arange(8760)
T_arr = 6 + 10 * np.sin(2 * np.pi * (t - 2000) / 8760)

original_solve = appsi.solvers.Highs.solve

def make_cfg(n, wid):
    rng = full_rng[:n]
    tmy = pd.DataFrame({
        'T':   T_arr[:n],
        'DHI': np.clip(200 * np.sin(np.pi * t[:n] / 24), 0, None),
        'DNI': np.clip(400 * np.sin(np.pi * t[:n] / 24), 0, None),
        'GHI': np.clip(500 * np.sin(np.pi * t[:n] / 24), 0, None),
    }, index=rng)
    cfg_obj = tsib.BuildingConfiguration({
        'ID': 'CL.SFH.DS50.mad', 'country': 'CL', 'a_ref': 60.0,
        'weatherData': tmy, 'weatherID': wid,
        'refurbishment': False, 'U_Wall_1': 0.6, 'U_Window_1': 2.8,
    })
    cfg = cfg_obj.getBdgCfg(includeSupply=True)
    cfg['Q_ig'] = np.full(n, 0.3)
    for k in ['occ_nothome', 'occ_sleeping', 'elecLoad', 'hotWaterLoad']:
        cfg[k] = pd.Series(np.zeros(n), index=rng)
    return cfg

for n in [24, 168, 720, 1440, 4380, 8760]:
    captured = {}

    def patched_solve(self, m, **kw):
        self.config.load_solution = False
        r = original_solve(self, m, **kw)
        captured['tc'] = str(r.termination_condition)
        return r

    appsi.solvers.Highs.solve = patched_solve
    cfg = make_cfg(n, 'ds' + str(n))
    model = tsib.Building5R1C(cfg)
    try:
        model.sim5R1C(solver='highs', tee=False)
        print('n=%5d: %s OK' % (n, captured.get('tc', '?')))
    except Exception as e:
        print('n=%5d: %s FAIL - %s' % (n, captured.get('tc', '?'), type(e).__name__))
    appsi.solvers.Highs.solve = original_solve
