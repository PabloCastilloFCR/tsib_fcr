import numpy as np, pandas as pd, tsib, warnings
from pyomo.contrib import appsi
warnings.filterwarnings('ignore')

rng = pd.date_range('2010-01-01', periods=8760, freq='h')
t = np.arange(8760)
T = 5 + 10*np.sin(2*np.pi*(t-2000)/8760)
tmy = pd.DataFrame({
    'T': T,
    'DHI': np.clip(200*np.sin(np.pi*t/24), 0, None),
    'DNI': np.clip(400*np.sin(np.pi*t/24), 0, None),
    'GHI': np.clip(500*np.sin(np.pi*t/24), 0, None),
}, index=rng)

cfg_obj = tsib.BuildingConfiguration({
    'ID': 'CL.SFH.preN.mad', 'country': 'CL', 'a_ref': 60.0,
    'weatherData': tmy, 'weatherID': 'pntee', 'refurbishment': False,
    'U_Wall_1': 2.7, 'U_Window_1': 5.8,
})
cfg = cfg_obj.getBdgCfg(includeSupply=True)
cfg['Q_ig'] = np.full(8760, 0.3)
for k in ['occ_nothome','occ_sleeping','elecLoad','hotWaterLoad']:
    cfg[k] = pd.Series(np.zeros(8760), index=rng)

m = tsib.Building5R1C(cfg)
m.sim_demand(solver='highs', tee=True)
