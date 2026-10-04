# Revisión del pipeline y del modelado dbt

**Fecha:** 2026-09-30. **Alcance:** ingesta (Airflow + loader S3 a bronze), transformación (dbt, silver y gold), despliegue (Railway) y calidad de datos. Todo lo de abajo se midió contra el estado real: repo en `main`, Postgres de Railway con las 13 tablas cargadas y una corrida completa de la DAG. Es una revisión de ingeniería de datos, no cambia código por sí sola. Las correcciones propuestas están al final, en orden.

## Estado actual (2026-10-01)

Después de esta revisión el pipeline se rehízo: **Airflow orquesta, DuckDB extrae y carga a Postgres, dbt transforma** (ver `ARCHITECTURE.md`). Se probó también un job único sin orquestador (DuckDB + dbt-duckdb, ~4 minutos) y se descartó por decisión del equipo de mantener Airflow como orquestador. Esta tabla dice qué quedó de cada hallazgo.

| Hallazgo original | Estado |
|---|---|
| P0.1 los tests corrían después de publicar | **Resuelto.** `dbt build` prueba cada modelo antes de los dependientes: si un test de silver falla, gold no se reconstruye y conserva el último dato válido. |
| P0.2 silver cubría 5 de 13 tablas | **Resuelto.** 13 modelos silver y 121 tests. |
| P0.3 sin linaje de carga, y cada corrida releía todo S3 para no insertar nada | **Resuelto por otro camino.** Sin tabla de control: cada fila trae su objeto de S3 en `_source_key`. La recarga es completa y DuckDB lee S3 en paralelo. |
| P0.4 un solo usuario con todos los privilegios | **Parcial.** El backend usa un rol de solo lectura (`backend_ro`: `SELECT` sobre `gold` y `ops`, sin acceso a `silver` ni `bronze`). Falta un rol de escritura limitado para dbt y para la carga. |
| P1.5 documentación desactualizada | **Resuelto.** `sources.yml` declara las 13 tablas con conteos reales. |
| P1.6 tests débiles | **Resuelto.** Claves foráneas, valores aceptados, rangos y reglas de negocio; los defectos conocidos corren como advertencias con su conteo. |
| P1.7 sin contratos de modelo | **Abierto.** La sintaxis deprecada de los tests sí se corrigió; falta `contract: enforced` con tipos. |
| P1.8 gold es copia de silver | **Abierto en lo semántico** (gold sigue siendo pass-through hasta elegir workflow). |
| P1.9 `profiles.yml` (`dev`, schema `bronze`) | **Resuelto.** Target `prod`, schema por defecto `silver`. |
| P1.10 sin reintentos ni lock | **Resuelto.** Las cargas reintentan 2 veces, `dbt build` corre con un candado en el runner. |
| P2 CI sin `dbt parse` | **Resuelto.** El CI construye las imágenes de Airflow y dbt, comprueba que el DAG importe y corre `dbt parse` dentro de la imagen de dbt. |
| `amount_usd` nulo en ~5% de ARS y COP | **Abierto.** Falta derivarlo en silver. |

## 1. Por qué hay 10 modelos y no 13

Los 10 modelos son 5 vistas silver (`stg_*`) y 5 tablas gold. Las otras 8 tablas de bronze (`branches`, `service_agents`, `marketing_campaigns`, `daily_exchange_rates`, `call_transcripts`, `satisfaction_surveys`, `campaign_sends`, `digital_events`) no tienen modelo.

Conviene separar las dos capas:

- **Gold:** modelar solo lo que consume el workflow es correcto. El reto premia profundidad en un workflow, no cobertura.
- **Silver:** no hay razón para dejar tablas sin tipos, contrato ni tests. Una tabla en bronze sin modelo es una tabla sin dueño. Además, sin silver de `branches` y `service_agents` no se pueden testear las claves foráneas a sucursal y agente. Silver debería cubrir las 13 tablas (mismo patrón, costo bajo).

## 2. Lo que funciona

- Medallion con nombres correctos (`bronze`, `silver`, `gold`) y gold nombrado por entidad, no por "clean".
- Bronze todo en texto, carga idempotente con `COPY` a tabla temporal más `INSERT ... ON CONFLICT DO NOTHING`, y contadores separados `rows_read` / `rows_inserted`.
- dbt como servicio propio y macro `generate_schema_name` para tener schemas exactos.
- 35 tests pasando; hallazgos de calidad documentados en `sources.yml` y en `DATA_FINDINGS.md`.
- Las 13 cargas corren en paralelo (13 tareas concurrentes, 394 s de pared para releer todo S3).
- Índices declarados en los modelos gold, con el lookup por cliente en 0,47 ms sobre 4,4M filas.

## 3. Hallazgos por prioridad

### P0, integridad y seguridad

1. **Los tests corren después de publicar.** `infra/dbt/app.py` ejecuta `dbt run` y luego `dbt test`. Gold ya fue sobrescrito cuando se evalúa la calidad: un dato malo llega a gold y recién después falla la corrida. Acción: usar `dbt build`, que testea cada modelo antes de construir los dependientes y omite lo que depende de un fallo.
2. **Cobertura de silver: 5 de 13 tablas.** Ver sección 1.
3. **Sin linaje de carga, y cada corrida relee todo.** Bronze no guarda `_source_key`, `_ingested_at` ni el etag del archivo, así que no se puede responder de qué archivo salió una fila (el reto pide linaje). Además cada corrida descarga los ~5 GB completos para insertar cero filas: 394 s perdidos, 275 s solo en `digital_events`, que ningún workflow usa. Acción: tabla `bronze._ingest_log(table, source_key, etag, rows_read, rows_inserted, loaded_at)`, columnas de linaje en bronze, y saltar archivos ya cargados con el mismo etag.
4. **Un solo usuario con todos los privilegios.** Loader, dbt y las consultas usan el superusuario `postgres`. Acción: un rol de dbt (lee bronze, escribe silver y gold) y un rol de solo lectura sobre gold para `backend/`. `silver.stg_transactions` expone `is_fraud` y `fraud_score`: mover esas etiquetas a un schema `eval` sin permisos para el tool layer, así la regla "el agente no ve fraude" la hace cumplir la base de datos y no solo una convención.

### P1, calidad y mantenimiento

5. **Documentación desactualizada.** `sources.yml` declara 5 de 13 fuentes y sus conteos son falsos (5.000.000 / 80.000 / 800.000 frente a 4.425.008 / 67.095 / 686.296 reales).
6. **Tests débiles.** Solo hay claves, valores aceptados y FKs a `customers`. Faltan `transactions.product_id` hacia `products` (hoy 0 huérfanos, buen test de regresión), rangos de valores y las reglas de negocio de la sección 4. No hay `packages.yml` (`dbt_utils`, `dbt_expectations`).
7. **Sin contratos de modelo** (`contract: enforced` con tipos de columna). Además 11 tests usan la sintaxis deprecada: los argumentos deben ir bajo `arguments:`.
8. **Gold es una copia 1 a 1 de silver.** Duplica 1,6 GB, reconstruye `transactions` completa en cada corrida (112 s) y no agrega campos de negocio.
9. **`profiles.yml`** nombra el target `dev` en producción y usa `bronze` como schema por defecto, donde caen los artefactos de tests.
10. **Airflow y dbt sin resiliencia.** La DAG no define `retries`, `execution_timeout` ni alertas. `run_dbt` es una llamada HTTP síncrona de hasta 900 s y el servicio dbt lanza un `subprocess` por request: dos POST simultáneos corren dos dbt sobre las mismas tablas. Acción: un lock en el servicio dbt y reintentos acotados en la DAG.

### P2

11. CI solo construye imágenes Docker: falta `dbt parse` dentro de la imagen de dbt.
12. No se genera `dbt docs` (página de linaje).

## 4. Hallazgos de datos nuevos

Medidos en esta revisión (también registrados en `DATA_FINDINGS.md`):

- **`customers.registration_branch_id`: 149.995 de 150.000 huérfanos.** Son 150.000 IDs distintos con formato válido y solo 5 existen en `branches`. El resto de las FKs a sucursal y agente tienen 0 huérfanos. Campo inservible.
- **`amount_usd`:** nulo en 57% de las transacciones. Es 100% nulo en las de USD (el monto ya está en dólares) y ~5% en ARS y COP, **99.477 huecos reales**. Hay que derivarlo en silver con una bandera.
- **No hay llegadas tardías.** `process_date - transaction_date` vale solo 0 o -1 día, nunca positivo. El -1 (25%) es un borde de fecha por zona horaria.
- **`response_code`:** Approved trae `00` (3.867.312) o nulo (203.369, 5%). Pending (88.343, 2,0%) y Reversed llevan códigos de rechazo 05, 14, 51 o 54.
- **Reglas rotas:** 7.510 productos de crédito con saldo mayor al límite, 772 quejas Resolved o Closed sin `resolution_date`, 52.454 interacciones a la vez escaladas y resueltas.
- Mezcla de estados: Approved 91,99%, Declined 5,00%, Pending 2,00%, Reversed 1,01%.
- Almacenamiento: bronze 7,3 GB más gold 1,6 GB, 9,0 GB en total de 30 GB de volumen.

## 5. Decisiones sobre el alcance

### Modelos incrementales (no se hacen)

Hoy cada corrida de dbt reconstruye por completo cada tabla gold: borra y vuelve a crear con un `SELECT` sobre todo silver. Un modelo **incremental** procesa solo las filas nuevas o cambiadas (por ejemplo, los días nuevos) y las fusiona por una clave única.

No lo hacemos porque el dataset es un snapshot estático que termina el 2026-06-18, la tabla más grande (4,4M filas) se reconstruye en 112 s, y un incremental agrega riesgos sin beneficio visible: manejo de clave única, filas viejas desactualizadas, y la necesidad de un `--full-refresh` cada vez que cambia la lógica. Si el volumen creciera, el primer candidato sería `transactions` incremental por `process_date`. Se documenta como camino de escalamiento.

### Airflow (se mantiene)

Se llegó a mover la metadata de Airflow a un Postgres propio (`airflow-db`), a limitar los redeploys con `watchPatterns` y, por un momento, a retirar Airflow a favor de un job único de DuckDB. El equipo decidió mantener Airflow como orquestador, con DuckDB para la extracción y la carga y dbt para la transformación. `watchPatterns` se mantiene en todos los servicios (redeploy solo si cambian sus rutas).

## 6. Plan sugerido

En orden de retorno sobre esfuerzo:

1. Silver para las 13 tablas, tests de FK y de rangos, y cambiar a `dbt build`.
2. `bronze._ingest_log` y columnas de linaje en bronze.
3. Roles de mínimo privilegio y schema `eval` para las etiquetas de fraude.
4. Derivar `amount_usd` completo en silver, y agregar lock y reintentos en dbt y Airflow.
5. CI con `dbt parse` dentro de la imagen, y corregir las descripciones de `sources.yml`.

## 7. Correcciones a afirmaciones previas

- Se supuso que Airflow ejecutaba las tareas en serie (SequentialExecutor) y no es así: se midieron 13 tareas concurrentes.
- Gold reducido a 5 tablas es una decisión válida, pero silver reducido a 5 no lo es (sección 1).
