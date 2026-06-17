# Chilean Building Archetypes — CL_episcope.csv

27 archetypes covering the Chilean residential stock, organized by **building type × normative period × materialidad**.  
Source file: `tsib/data/episcope/CL_episcope.csv`

---

## Naming convention

```
CL.{BuildingType}.{Period}.{Material}
```

| Segment | Values | Meaning |
|---------|--------|---------|
| `CL` | fixed | Country code — Chile |
| `BuildingType` | `SFH`, `MFH`, `AB` | Typology (see §1) |
| `Period` | `preN`, `intN`, `DS50` | Normative period (see §2) |
| `Material` | `mad`, `lad`, `hor` | Materialidad (see §3) |

**Example:** `CL.SFH.intN.lad` = Chilean single-family home, built 2000–2015, ladrillo.

---

## 1. Building type

| Code | Full name | Storeys | Ref. area (m²) | Apartments |
|------|-----------|---------|----------------|------------|
| `SFH` | Single Family Home — vivienda unifamiliar | 1–2 | 60–70 | 1 |
| `MFH` | Multi-Family Home — edificio bajo | 4 | 55–65 | 8 |
| `AB` | Apartment Block — edificio en altura | 12–14 | 52–62 | 24–28 |

Reference areas (`A_C_Ref`) are prototype estimates; they should be replaced by SII parcel medians (MERLIN_RCP Task 0.1) before production use.

---

## 2. Normative period

| Code | Years | Regulation context | Thermal envelope |
|------|-------|--------------------|-----------------|
| `preN` | 1900–1999 | Pre-normative: no thermal requirements | Poor — U_Wall 2.3–3.4, U_Win 5.8 W/m²K |
| `intN` | 2000–2015 | Reglamentación Térmica (RT 2007) — first mandatory standards | Moderate — U_Wall ~1.9, U_Win 3.5 W/m²K |
| `DS50` | 2016–2030 | DS50 Eficiencia Energética en Viviendas (current standard) | Good — U_Wall 0.6, U_Win 2.8 W/m²K |

---

## 3. Materialidad

| Code | Material | Thermal notes | Infiltration rate n (1/h) |
|------|----------|---------------|--------------------------|
| `mad` | Madera — wood frame | Lightweight; good insulation potential but high air leakage if unsealed | 0.50–0.80 |
| `lad` | Ladrillo — brick masonry | Dense; moderate thermal mass; medium air tightness | 0.25–0.50 |
| `hor` | Hormigón — concrete | Pre-norma walls were thin and poorly insulating despite the material; tightest air envelope | 0.18–0.30 |

> **Note on `hor` U_Wall:** concrete walls in the pre-norma stock were thin (~15 cm, uninsulated), giving U_Wall ≈ 3.4 W/m²K — higher than brick or wood of the same era.  
> For `intN` and `DS50`, all three materials converge to similar U_Wall values because added insulation dominates; infiltration remains the main differentiator.

---

## 4. Complete archetype table

| ID | Type | Period | Material | Storeys | A_C_Ref (m²) | U_Wall | U_Roof | U_Floor | U_Win | g_gl_n | n_Inf |
|----|------|--------|----------|---------|--------------|--------|--------|---------|-------|--------|-------|
| CL.SFH.preN.mad | SFH | 1900–1999 | Madera | 1 | 60 | 2.7 | 2.5 | 1.4 | 5.8 | 0.87 | 0.80 |
| CL.SFH.preN.lad | SFH | 1900–1999 | Ladrillo | 1 | 60 | 2.3 | 2.5 | 1.4 | 5.8 | 0.75 | 0.50 |
| CL.SFH.preN.hor | SFH | 1900–1999 | Hormigón | 1 | 60 | 3.4 | 2.5 | 1.4 | 5.8 | 0.75 | 0.30 |
| CL.SFH.intN.mad | SFH | 2000–2015 | Madera | 1 | 65 | 1.9 | 1.5 | 0.8 | 3.5 | 0.75 | 0.60 |
| CL.SFH.intN.lad | SFH | 2000–2015 | Ladrillo | 1 | 65 | 1.9 | 1.5 | 0.8 | 3.5 | 0.75 | 0.50 |
| CL.SFH.intN.hor | SFH | 2000–2015 | Hormigón | 1 | 65 | 1.9 | 1.5 | 0.8 | 3.5 | 0.75 | 0.30 |
| CL.SFH.DS50.mad | SFH | 2016–2030 | Madera | 2 | 70 | 0.6 | 0.6 | 0.5 | 2.8 | 0.60 | 0.50 |
| CL.SFH.DS50.lad | SFH | 2016–2030 | Ladrillo | 2 | 70 | 0.6 | 0.6 | 0.5 | 2.8 | 0.60 | 0.40 |
| CL.SFH.DS50.hor | SFH | 2016–2030 | Hormigón | 2 | 70 | 0.6 | 0.6 | 0.5 | 2.8 | 0.60 | 0.25 |
| CL.MFH.preN.mad | MFH | 1900–1999 | Madera | 4 | 55 | 2.7 | 2.5 | 1.4 | 5.8 | 0.87 | 0.70 |
| CL.MFH.preN.lad | MFH | 1900–1999 | Ladrillo | 4 | 55 | 2.3 | 2.5 | 1.4 | 5.8 | 0.75 | 0.45 |
| CL.MFH.preN.hor | MFH | 1900–1999 | Hormigón | 4 | 55 | 3.4 | 2.5 | 1.4 | 5.8 | 0.75 | 0.25 |
| CL.MFH.intN.mad | MFH | 2000–2015 | Madera | 4 | 60 | 1.9 | 1.5 | 0.8 | 3.5 | 0.75 | 0.55 |
| CL.MFH.intN.lad | MFH | 2000–2015 | Ladrillo | 4 | 60 | 1.9 | 1.5 | 0.8 | 3.5 | 0.75 | 0.45 |
| CL.MFH.intN.hor | MFH | 2000–2015 | Hormigón | 4 | 60 | 1.9 | 1.5 | 0.8 | 3.5 | 0.75 | 0.25 |
| CL.MFH.DS50.mad | MFH | 2016–2030 | Madera | 4 | 65 | 0.6 | 0.6 | 0.5 | 2.8 | 0.60 | 0.45 |
| CL.MFH.DS50.lad | MFH | 2016–2030 | Ladrillo | 4 | 65 | 0.6 | 0.6 | 0.5 | 2.8 | 0.60 | 0.35 |
| CL.MFH.DS50.hor | MFH | 2016–2030 | Hormigón | 4 | 65 | 0.6 | 0.6 | 0.5 | 2.8 | 0.60 | 0.22 |
| CL.AB.preN.mad | AB | 1900–1999 | Madera | 12 | 52 | 2.7 | 2.5 | 1.4 | 5.8 | 0.87 | 0.60 |
| CL.AB.preN.lad | AB | 1900–1999 | Ladrillo | 12 | 52 | 2.3 | 2.5 | 1.4 | 5.8 | 0.75 | 0.35 |
| CL.AB.preN.hor | AB | 1900–1999 | Hormigón | 12 | 52 | 3.4 | 2.5 | 1.4 | 5.8 | 0.75 | 0.20 |
| CL.AB.intN.mad | AB | 2000–2015 | Madera | 12 | 58 | 1.9 | 1.5 | 0.8 | 3.5 | 0.75 | 0.45 |
| CL.AB.intN.lad | AB | 2000–2015 | Ladrillo | 12 | 58 | 1.9 | 1.5 | 0.8 | 3.5 | 0.75 | 0.35 |
| CL.AB.intN.hor | AB | 2000–2015 | Hormigón | 12 | 58 | 1.9 | 1.5 | 0.8 | 3.5 | 0.75 | 0.18 |
| CL.AB.DS50.mad | AB | 2016–2030 | Madera | 14 | 62 | 0.6 | 0.6 | 0.5 | 2.8 | 0.60 | 0.35 |
| CL.AB.DS50.lad | AB | 2016–2030 | Ladrillo | 14 | 62 | 0.6 | 0.6 | 0.5 | 2.8 | 0.60 | 0.28 |
| CL.AB.DS50.hor | AB | 2016–2030 | Hormigón | 14 | 62 | 0.6 | 0.6 | 0.5 | 2.8 | 0.60 | 0.18 |

All U-values in W/m²K. `g_gl_n` = solar transmittance of glazing (dimensionless). `n_Inf` = air infiltration rate (1/h).

---

## 5. Geometry approach

Areas in the CSV are prototype estimates derived from:

```
A_Roof_1  = A_C_Ref / n_Storey
A_Floor_1 = A_C_Ref / n_Storey
A_Wall_1  = 4 × sqrt(A_C_Ref / n_Storey) × n_Storey × 2.4 m   (ceiling height)
A_Window_1 = A_Wall_1 × WWR
```

Window-to-wall ratios (WWR): SFH = 0.15, MFH = 0.17, AB = 0.20.  
Window area is distributed equally across the four cardinal orientations (25% each).

These values must be replaced by SII parcel medians before production use (MERLIN_RCP Task 0.1).

---

## 6. How zone-specific U-values work

The CSV stores zone-neutral default U-values. MERLIN_RCP overrides them per simulation call:

```python
cfg = tsib.BuildingConfiguration({
    "ID":      "CL.SFH.preN.mad",
    "country": "CL",
    "a_ref":   60,
    "weatherData": tmy,
    "weatherID": "...",
    # Zone-specific overrides:
    "U_Wall_1":    2.7,
    "U_Roof_1":    2.5,
    "U_Floor_1":   1.4,
    "U_Window_1":  5.8,
    "n_Infiltration": 0.80,
    "g_gl_n":      0.87,
})
```

This allows 27 geometry archetypes × 7 thermal zones without needing 189 CSV rows.
