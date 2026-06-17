# Plan: Replace LP Optimization with Direct Time-Stepping Simulation

## Goal

Eliminate Pyomo/HiGHS dependency for demand calculation. The 5R1C model with
fixed envelope (no refurbishment) does not need an LP — it reduces to a simple
ODE + algebraic system solvable analytically at each timestep.

## Background

`sim_demand` (current) builds and solves an LP via Pyomo + HiGHS. HiGHS fails
with `TerminationCondition.unknown` for 8760-hour runs due to excessively small
row bounds (RHS range [5e-05, 3e+01]) triggering dual simplex scaling failure.

The original `sim5R1C` was designed to simultaneously optimize insulation options
(refurbishment). For fixed U-values, that optimization machinery is unnecessary.

---

## The Math

The 5R1C energy balance with single fixed conductance per component:

### Per-timestep profiles (precomputed, no temperatures involved)

```
Q_m[t]  = 0.5 × (A_m/A_tot) × Q_ig[t]  +  (A_f/A_tot) × Q_sol_all[t]
Q_st[t] = (1 - H_win/(h_ms × A_tot)) × 0.5 × Q_ig[t]
          - (H_win/(h_ms × A_tot)) × Q_sol_all[t]
          + Q_sol_all[t]  -  Q_m[t]
```

### Node equations at each timestep

**Mass node (ODE):**
```
C_m × (T_m[t+1] - T_m[t]) / dt
    = Q_m[t] - H_ms×(T_m-T_s) - (H_em+H_door)×(T_m-T_e)
```

**Surface node (algebraic):**
```
H_ms×(T_s - T_m) + H_is×(T_s - T_air) + H_win×(T_m - T_e) = Q_st
```
Note: window heat flow uses T_m (mass temp), matching original heatFlowActive constraint.

**Air node (algebraic):**
```
H_vent×(T_m - T_e) + H_is×(T_air - T_s) = Q_st + Q_H - Q_C
```
Note: ventilation heat flow uses T_m (mass temp), matching original model.

### Analytical solution per timestep

Given T_m[t] (known from previous step), T_e[t], Q_m[t], Q_st[t]:

**Step 1 — free-float** (set Q_H = Q_C = 0, add both algebraic equations):
```
H_ms × T_s = 2×Q_st + (H_ms - H_win)×T_m + H_win×T_e - H_vent×(T_m - T_e)
T_s_free = [...] / H_ms

T_air_free = T_s_free + (Q_st - H_vent×(T_m - T_e)) / H_is
```

**Step 2 — decide conditioning:**

- If `T_air_free < T_lb` (heating needed):
  ```
  T_air = T_lb
  T_s = (Q_st + (H_ms-H_win)×T_m + H_win×T_e + H_is×T_lb) / (H_ms + H_is)
  Q_H = max(0,  H_vent×(T_m-T_e) + H_is×(T_lb - T_s) - Q_st)
  Q_C = 0
  ```

- If `T_air_free > T_ub` (cooling needed):
  ```
  T_air = T_ub
  T_s = (Q_st + (H_ms-H_win)×T_m + H_win×T_e + H_is×T_ub) / (H_ms + H_is)
  Q_C = max(0, -(H_vent×(T_m-T_e) + H_is×(T_ub - T_s) - Q_st))
  Q_H = 0
  ```

- Otherwise: `T_air = T_air_free`, `T_s = T_s_free`, `Q_H = Q_C = 0`

**Step 3 — update mass temperature:**
```
T_m[t+1] = T_m[t] + (Q_m - H_ms×(T_m-T_s) - (H_em+H_door)×(T_m-T_e)) × dt / C_m
```

### Periodic boundary condition

Run the annual loop up to 5 times. Start with `T_m[0] = T_lb`. After each pass,
use the final `T_m[8760]` as the new `T_m[0]`. Stop when
`|T_m[end] - T_m[0]| < 0.01 K`.

---

## Files to Change

| File | Change |
|------|--------|
| `tsib/thermal/model5R1C.py` | Add `sim_demand_direct()` method |
| `test/test_chile.py` | Call `sim_demand_direct()` instead of `sim_demand()` |
| `debug_sim_demand.py` | Delete (temporary debug file) |
| `debug_ds50.py` | Delete (temporary debug file) |

### Files NOT changed
- `tsib/buildingconfig.py` — no changes
- `tsib/weather/chile.py` — no changes
- `tsib/__init__.py` — no changes
- `sim5R1C` — remains for refurbishment optimization users

---

## Comparison

| | `sim_demand` (LP) | `sim_demand_direct` (new) |
|--|--|--|
| Solver | HiGHS required | none |
| Pyomo | required (LP build) | still used for param extraction |
| Instability | fails at 8760h | not possible — no LP |
| Speed | ~3–5 s | ~0.01 s |
| Result | LP optimum (Q_H min cost) | identical physics |

---

## Task List

- [ ] **T1** Verify Q_m and Q_st formulas against original gainMassNode/gainSurNode
      using a 2-timestep debug run (print both LP variable values and formula values)
- [ ] **T2** Implement `sim_demand_direct()` in `tsib/thermal/model5R1C.py`
      - Extract params via `_initOpti` + `_addOpti` (reuse existing machinery)
      - Precompute Q_m[t] and Q_st[t] arrays
      - Forward-Euler time loop with analytical T_s / T_air / Q_H / Q_C
      - Periodic BC iteration (max 5 passes, tolerance 0.01 K)
      - Write results to `self.detailedResults` (same keys as `sim5R1C`)
- [ ] **T3** Update `test/test_chile.py` — replace `sim_demand` → `sim_demand_direct`
- [ ] **T4** Run `pytest test/test_chile.py -v` and confirm all 3 tests pass
- [ ] **T5** Sanity-check results: preN.mad heating load ≫ DS50.mad (expected ~3–5×)
- [ ] **T6** Delete `debug_sim_demand.py` and `debug_ds50.py`
- [ ] **T7** (CLAUDE.md task 5) Mark test/test_chile.py as ✅ in implementation table
- [ ] **T8** (CLAUDE.md task 6) Bump version to `0.2.0-cl` in `setup.py`
