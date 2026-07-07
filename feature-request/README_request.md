# Cambios propuestos para el fork tsib_fcr

Este README resume los cambios que conviene implementar directamente en el fork `tsib_fcr` para que la integracion con MERLIN_RCP sea mas limpia, mantenible y comparable con validaciones. El foco es simulacion termica 5R1C y ACS. La electricidad residencial queda fuera del alcance principal porque aun esta en etapa inicial de supuestos y calibracion.

## Objetivo

Reducir la cantidad de logica termica duplicada en MERLIN_RCP y mover al fork las capacidades que pertenecen naturalmente al motor fisico:

- simulacion directa 5R1C con setpoints horarios;
- manejo robusto de perfiles internos relevantes para el balance termico;
- soporte claro para ACS termica util;
- lectura y propagacion de `t_mains` desde TMY;
- resultados horarios consistentes y faciles de consumir desde MERLIN.

MERLIN_RCP deberia seguir controlando escenarios, perfiles socio-demograficos, calibracion, agregacion comunal, salidas GIS y energia final por tecnologia.

## Estado actual en MERLIN_RCP

Actualmente MERLIN_RCP usa `tsib_fcr` como base, pero agrega varias capas externas en:

```text
scripts/simular_edificios_tsib_fcr.py
```

Los principales ajustes externos son:

- construccion de perfiles horarios de ocupacion;
- setpoints horarios de calefaccion/refrigeracion segun ocupacion;
- ganancias internas dinamicas por personas y artefactos;
- ACS horaria por persona con `T_mains`;
- conversion de refrigeracion termica a electricidad con COP externo;
- simulacion comunal optimizada por grupos arquetipo-personas.

El punto mas fragil es que MERLIN replica internamente parte de `Building5R1C.sim_demand_direct()` solo para permitir setpoints horarios. Ese cambio deberia moverse al fork.

## Cambios prioritarios en el fork

### 1. Soportar setpoints horarios en `sim_demand_direct`

Prioridad: alta.

Problema actual:

`Building5R1C.sim_demand_direct()` usa setpoints constantes desde la configuracion interna:

```text
bT_comf_lb
bT_comf_ub
```

MERLIN necesita setpoints horarios para representar ocupacion, ausencia y periodo de sueno. Hoy se replica la logica interna del metodo directo en MERLIN, lo que genera deuda tecnica.

Propuesta:

Permitir argumentos opcionales:

```python
model.sim_demand_direct(
    heating_setpoint=None,
    cooling_setpoint=None,
)
```

Comportamiento esperado:

- Si `heating_setpoint is None`, usar `bT_comf_lb` constante como hoy.
- Si `cooling_setpoint is None`, usar `bT_comf_ub` constante como hoy.
- Si se entrega una serie/array horario, debe tener el mismo largo que `model.times`.
- Aceptar `pd.Series`, `np.ndarray`, listas o escalares.
- Validar que `cooling_setpoint > heating_setpoint` en cada hora, o aplicar margen minimo documentado.
- No depender de `-inf` o `+inf` para representar equipos apagados. Si se desea modo off, usar cotas finitas o una mascara explicita de disponibilidad.

Caso MERLIN para vivienda sin ocupacion:

MERLIN quiere representar que no hay demanda de calefaccion ni refrigeracion cuando no hay personas en la vivienda. Conceptualmente esto es:

```text
calefaccion: off
refrigeracion: off
```

En la implementacion actual de MERLIN se aproxima con setpoints finitos extremos:

```text
heating_setpoint_away = -20 C
cooling_setpoint_away = 60 C
```

MERLIN no interpola linealmente entre setpoints ocupado/fuera. Aunque los perfiles de ocupacion son fraccionales, primero se aproximan a conteos enteros de personas activas, durmiendo y fuera, manteniendo que la suma sea igual a las personas por vivienda. Si el conteo deja cero personas presentes (`active_persons = 0` y `sleeping_persons = 0`), HVAC queda apagado. Si hay personas presentes, el setpoint de calefaccion puede interpolar solo entre personas activas y durmiendo. Esto evita que el valor extremo de apagado afecte artificialmente horas parcialmente ocupadas.

No se usan infinitos reales porque el metodo directo 5R1C resuelve balances algebraicos hora a hora y `-inf/+inf` puede contaminar temperaturas, cargas o criterios de convergencia con `NaN`. En el fork seria mejor soportar el apagado de equipos de forma explicita con una mascara de disponibilidad:

```python
model.sim_demand_direct(
    heating_setpoint=heating_setpoint,
    cooling_setpoint=cooling_setpoint,
    heating_available=heating_available,
    cooling_available=cooling_available,
)
```

Si no se implementa esa mascara, se debe documentar oficialmente que el modo off se representa con setpoints finitos extremos validados, aplicados solo cuando no hay personas presentes despues de la aproximacion a conteos enteros.

Ejemplo de uso esperado desde MERLIN:

```python
model = tsib.Building5R1C(cfg)
model.sim_demand_direct(
    heating_setpoint=heating_setpoint_series,
    cooling_setpoint=cooling_setpoint_series,
)
results = model.detailedResults
```

Resultados esperados:

```text
Heating Load
Cooling Load
Electricity Load
T_air
T_s
T_m
Heating Setpoint
Cooling Setpoint
```

Criterios de aceptacion:

- Con setpoints `None`, los resultados deben ser identicos al comportamiento actual.
- Con setpoints constantes entregados como array, deben coincidir con el caso constante interno.
- Con setpoints horarios, no debe requerir solver Pyomo externo.
- El modo off no debe requerir infinitos reales.
- Si se entregan setpoints no finitos (`NaN`, `inf`, `-inf`), el fork debe rechazarlos con un error claro o convertirlos mediante una regla documentada.
- Debe mantenerse la ruta directa sin optimizacion.

### 2. Exponer resultados horarios de temperatura y setpoints

Prioridad: alta.

Problema actual:

MERLIN necesita auditar por que aparece demanda en ciertas horas. Para eso requiere temperatura interior y setpoints usados.

Propuesta:

Agregar siempre al `detailedResults`:

```text
T_air
T_s
T_m
Heating Setpoint
Cooling Setpoint
```

Si el fork ya reporta `T_air`, `T_s` y `T_m`, solo falta asegurar nombres estables y documentarlos. Los setpoints usados deberian quedar reportados aunque sean constantes.

Criterios de aceptacion:

- Todos los arrays tienen el mismo largo que el indice temporal.
- Los nombres quedan documentados.
- MERLIN no necesita recomputar ni reconstruir setpoints para auditar la simulacion.

### 3. Formalizar `Q_ig` como perfil horario de ganancias internas

Prioridad: media-alta.

Problema actual:

`Q_ig` ya entra al balance termico 5R1C, pero conviene documentar y validar explicitamente que puede ser:

- escalar;
- array horario;
- `pd.Series` con indice temporal.

Propuesta:

Normalizar internamente `Q_ig` a un array horario en la preparacion del modelo. Si llega escalar, expandirlo a todo el ano. Si llega serie, alinear con `weather.index` o validar longitud.

No se propone que el fork genere perfiles de ocupacion. Solo debe aceptar una serie de ganancias internas ya construida por MERLIN u otro consumidor.

Criterios de aceptacion:

- `Q_ig = 0.3` sigue funcionando.
- `Q_ig = np.full(8760, 0.3)` funciona.
- `Q_ig = pd.Series(..., index=weather.index)` funciona.
- Errores claros si el largo no coincide.

### 4. Incorporar ACS termica util como calculo soportado por el fork

Prioridad: alta para integracion ACS.

Problema actual:

MERLIN calcula ACS fuera del fork porque el camino directo no devuelve ACS como resultado principal. Esto esta bien como prototipo, pero dificulta comparar escenarios y mantener una API unica.

Propuesta:

Agregar una funcion o metodo dedicado para ACS termica util, independiente de sistemas/equipos:

```python
tsib.calculate_dhw_load(
    index,
    persons,
    liters_per_person_day,
    target_temp_c,
    t_mains,
    profile=None,
    holidays=None,
)
```

O como metodo asociado al edificio:

```python
model.calculate_dhw_load(
    liters_per_person_day=40,
    target_temp_c=55,
    profile=dhw_profile,
    t_mains=t_mains,
)
```

Formula base:

```text
liters_h = persons * liters_per_person_day * profile_h
deltaT_h = max(target_temp_c - t_mains_h, 0)
Q_DHW_h = liters_h * deltaT_h * 0.001163
```

Unidades:

```text
liters_h: L/h
target_temp_c: degC
t_mains_h: degC
Q_DHW_h: kWh/h, equivalente a kW promedio horario
```

La funcion debe devolver:

```text
DHW Load
DHW Liters
DHW DeltaT
T_mains
```

Criterios de aceptacion:

- Si el perfil diario suma 1, el volumen diario debe ser `persons * liters_per_person_day`.
- Si `t_mains` cambia hora a hora, la energia debe cambiar hora a hora.
- Si `t_mains` tiene nulos, el comportamiento debe ser configurable: error, interpolacion o fallback.
- La demanda ACS reportada debe ser energia termica util, no energia final.

### 5. Soportar `t_mains` en el adaptador TMY

Prioridad: alta para ACS.

Problema actual:

MERLIN detecta y propaga `t_mains` desde la tabla TMY comunal. Si este manejo queda solo en MERLIN, cualquier otro consumidor del fork debe repetirlo.

Propuesta:

Actualizar el adaptador TMY chileno para conservar una columna estandar:

```text
t_mains
```

Nombres de entrada aceptables:

```text
t_mains
tmains
tmain
t_water_mains
t_mains_c
temp_mains
temp_water_mains
t_red
temp_red
temperatura_red
t_agua_red
temp_agua_red
```

Comportamiento recomendado:

- Si existe una columna valida, conservarla como `t_mains`.
- Si hay nulos parciales, permitir estrategia configurable:
  - `raise`;
  - `interpolate`;
  - `fallback_from_tdry`.
- Si no existe, no inventar silenciosamente. Emitir warning claro o exigir que el usuario entregue `t_mains` para ACS.

Fallback posible:

```text
t_mains_estimada = media_movil_30_dias(tdry)
```

Ese fallback debe quedar marcado como estimado, no como dato observado.

Criterios de aceptacion:

- `bd_tmy_to_tsib()` conserva `t_mains` cuando viene en la tabla.
- No rompe TMY antiguos sin `t_mains`.
- La fuente de `t_mains` queda identificada en metadata o atributo.

### 6. Separar demanda termica util y energia final

Prioridad: media.

Problema actual:

El fork calcula carga termica. MERLIN convierte refrigeracion a electricidad con COP y eventualmente necesitara convertir calefaccion/ACS a energia final por tecnologia. Esa conversion no debe confundirse con la demanda termica.

Propuesta:

Mantener en el fork resultados de demanda util:

```text
Heating Load
Cooling Load
DHW Load
```

Opcionalmente, agregar funciones auxiliares de sistema, pero claramente separadas:

```python
convert_thermal_to_final(load, efficiency=None, cop=None)
```

Para MERLIN, por ahora basta con que el fork entregue demanda util consistente.

Criterios de aceptacion:

- `Cooling Load` sigue siendo termico.
- `DHW Load` es termico util.
- La electricidad de refrigeracion no se suma dentro del motor termico salvo que se use un modulo de sistema separado.

## Cambios secundarios recomendados

### 7. API de perfiles robusta

Prioridad: media.

Agregar utilidades internas para normalizar perfiles:

```python
normalize_profile_to_annual_energy(profile, annual_kwh)
normalize_daily_shape(index, daily_shape_weekday, daily_shape_weekend, holidays)
as_hourly_series(value, index, name)
```

Esto no implica que el fork defina los perfiles residenciales de MERLIN. Solo evita que cada integracion escriba validaciones distintas.

### 8. Documentar y exponer mejor los perfiles estocasticos existentes

Prioridad: media.

`tsib` original ya contiene una ruta de perfiles de hogar mediante `getHouseholdProfiles()` y `BuildingModel._get_occupancy_profile()`. Esa ruta genera perfiles horarios de ocupacion activa, ocupacion no activa, electricidad, ACS y ganancias por artefactos. Tambien permite variaciones mediante `state_seed`, `varyoccupancy` y `mean_load`, y puede agregar perfiles de varios departamentos cuando `n_apartments > 1`.

Para MERLIN_RCP, esto sugiere una mejora futura: en vez de usar un unico perfil promedio por vivienda, se podria generar un conjunto de perfiles estocasticos o perfiles tipo por edificio y agregarlos antes de llamar al motor termico. Sin embargo, esto debe mantenerse como una decision metodologica de MERLIN, no como un perfil residencial fijo dentro del fork.

Lo que si conviene en el fork es:

- documentar claramente la API existente de `getHouseholdProfiles()`;
- asegurar que los perfiles generados sean faciles de usar con `Building5R1C`;
- permitir inyectar perfiles externos ya agregados por MERLIN;
- mantener separadas las capacidades del motor fisico y los supuestos conductuales.

### 9. Modo de validacion reproducible

Prioridad: media.

Agregar ejemplos oficiales que reproduzcan el caso de validacion del fork:

```text
examples/chile/validation_direct_5r1c.py
examples/chile/validation_dhw.py
```

El ejemplo termico deberia fijar:

- edificio/arquetipo usado;
- TMY;
- `Q_ig`;
- setpoints;
- resultado anual esperado.

Esto permite distinguir claramente:

- validacion del motor;
- escenario residencial MERLIN con perfiles horarios.

### 10. Documentar unidades y convenciones

Prioridad: media.

Documentar en el fork:

| Variable | Unidad | Comentario |
|---|---:|---|
| `Q_ig` | kW | Ganancia interna sensible horaria. |
| `elecLoad` | kWh/h o kW promedio horario | Carga electrica reportada, no necesariamente calor interno. |
| `hotWaterLoad` / `DHW Load` | kWh/h | Demanda termica util ACS. |
| `Heating Load` | kWh/h | Demanda termica util calefaccion. |
| `Cooling Load` | kWh/h | Demanda termica util refrigeracion. |
| `t_mains` | degC | Temperatura de agua de red. |
| `T_air` | degC | Temperatura interior del nodo aire. |

## Que NO conviene mover al fork por ahora

Estos elementos deberian seguir en MERLIN_RCP:

- perfiles sinteticos de ocupacion residencial;
- calibracion de electricidad anual, por ejemplo `2500 kWh/vivienda-ano`;
- formula preliminar que combina electricidad base con ocupacion;
- fraccion de electricidad que entra como ganancia interna, actualmente 15%;
- COP o SEER de equipos de refrigeracion;
- penetracion tecnologica de calefaccion, ACS o aire acondicionado;
- escalamiento comunal y agregacion espacial;
- exportacion CSV/GIS/GeoPackage;
- calibracion contra consumos observados.

Razon: esos elementos son supuestos de escenario, comportamiento, calibracion o postproceso. No son parte basica del motor termico 5R1C.

## Propuesta de implementacion por etapas

### Etapa 1: setpoints horarios

Implementar:

- argumentos opcionales en `sim_demand_direct`;
- validacion de longitudes;
- reporte de setpoints usados;
- tests de igualdad contra comportamiento actual.

Resultado esperado:

MERLIN elimina su copia local de `_sim_demand_direct_with_setpoints()` y vuelve a llamar directamente:

```python
model.sim_demand_direct(
    heating_setpoint=heating_setpoint,
    cooling_setpoint=cooling_setpoint,
)
```

### Etapa 2: ACS util

Implementar:

- funcion ACS termica util;
- soporte de `t_mains`;
- perfiles diarios normalizados;
- ejemplo minimo de ACS.

Resultado esperado:

MERLIN deja de calcular ACS manualmente o, al menos, usa la funcion oficial del fork.

### Etapa 3: adaptador TMY y ejemplos Chile

Implementar:

- conservacion de `t_mains` en `bd_tmy_to_tsib`;
- ejemplo termico Chile;
- ejemplo ACS Chile;
- documentacion de unidades.

Resultado esperado:

La integracion MERLIN queda apoyada en APIs publicas del fork y no en replicas internas.

## Checklist para PR en tsib_fcr

- [ ] `sim_demand_direct()` acepta setpoints horarios opcionales.
- [ ] `sim_demand_direct()` mantiene resultados identicos si no se entregan setpoints.
- [ ] `detailedResults` incluye setpoints usados.
- [ ] `Q_ig` acepta escalar, array o serie horaria.
- [ ] ACS util se puede calcular con `t_mains` horario.
- [ ] `bd_tmy_to_tsib()` conserva `t_mains` si existe.
- [ ] Hay ejemplo reproducible de simulacion termica Chile.
- [ ] Hay ejemplo reproducible de ACS Chile.
- [ ] Las unidades quedan documentadas.
- [ ] MERLIN puede remover la funcion local que replica el metodo directo 5R1C.

## Resultado esperado para MERLIN_RCP

Despues de estos cambios, MERLIN deberia construir los supuestos de escenario y llamar al fork de forma simple:

```python
cfg["Q_ig"] = internal_gains_profile

model = tsib.Building5R1C(cfg)
model.sim_demand_direct(
    heating_setpoint=heating_setpoint,
    cooling_setpoint=cooling_setpoint,
)

dhw = tsib.calculate_dhw_load(
    index=weather.index,
    persons=n_persons_unit,
    liters_per_person_day=40,
    target_temp_c=55,
    t_mains=weather["t_mains"],
    profile=dhw_profile,
)
```

Con eso, MERLIN mantiene control sobre ocupacion, escenarios, calibracion y salidas, mientras `tsib_fcr` se encarga de la fisica termica y ACS util de forma estable.
