# Hallazgos de investigación sobre el dataset real (S3)

Investigación hecha bajando muestras reales del bucket `factored-datathon-2026-s3-157725502942-us-east-2-an` (credenciales read-only del data dictionary). Objetivo: verificar supuestos antes de comprometernos a un workflow. Actualizar este doc si se investiga más.

## Procedencia de los datos

Todo lo que entra al sistema hoy es **sintético y lo entrega el organizador** (dataset LATAM Bank v1.0.0, 13 tablas, bucket de S3 de solo lectura). No hay datos reales, ni de-identificados, ni generados por el equipo en el pipeline. Los nombres, documentos, teléfonos y correos de `customers` son ficticios. Lo que el equipo genere más adelante (enunciados de usuario para la evaluación, casos sintéticos con etiquetas conocidas) se rotulará como **generado por el equipo** y se mantendrá separado del dato del organizador.

## Texto libre es plantilla, no señal real

- `call_transcripts`: muestra de 151 filas (un día) → solo 32 variantes únicas de `customer_text`, y 141/151 filas comparten el mismo `detected_intents` = `consulta_general`. El campo de intención detectada casi no varía.
- `complaints.description`: siempre el mismo patrón `"Queja relacionada con {category}"` — no es texto libre real del cliente. `resolution` casi siempre vacío o una de ~3 frases genéricas.
- **Implicación:** no se puede entrenar/evaluar un clasificador de intención serio sobre el texto histórico tal cual. La señal de negocio real está en los campos estructurados: `complaints.category`/`subcategory`, `call_center_interactions.contact_reason`/`reason_category`, `transactions.transaction_type`/`transaction_category`.
- **Camino recomendado:** usar un LLM para interpretar el **input conversacional en vivo** del usuario en la demo (eso sí es texto real generado en el momento), y usar los campos estructurados del histórico como baseline determinista + fuente de evaluación. Documentar esta limitación de datos explícitamente — el reto lo pide ("report limitations in the supplied data").

## "Cargo duplicado" no aparece como patrón detectable

- Revisado: 5 días de `transactions` (~25,000 filas) + el archivo completo de `customers` (150,000 filas).
- Cero `transaction_id` duplicados (mismo día o cruzando días).
- Cero grupos de mismo `customer_id` + `amount` + `merchant_name` + `transaction_type` repetidos.
- Cero `customer_id`/`document_number` duplicados en `customers`.
- **Implicación:** la idea original de "duplicado exacto → reembolso automático" (Opción A del plan) no tiene todavía evidencia de que el patrón exista en volumen suficiente. Si se elige disputas de transacciones, hay que definir el caso "auto-resolvible" con otra regla (ej. transacción `Declined`/`Reversed` que el cliente reporta como cobrada, o comparar contra `daily_exchange_rates`/`amount_usd` para detectar error de conversión) — no asumir que "duplicados" es el caso fácil sin más muestreo.
- El "~2% duplicados" documentado en el dataset no se manifestó en las tablas y campos revisados con estas definiciones; puede estar en otras tablas (`products`, `digital_events`, `campaign_sends`) o requerir otra definición de "duplicado" (ej. duplicado por reingesta/ETL con mismo `transaction_id` pero distinto `process_date`, que tampoco apareció). Pendiente de más muestreo si el equipo decide depender de esto.

## `is_fraud` / `fraud_score` son ground truth, no señal de entrada

- 7 de 5,342 transacciones (~0.13%) marcadas `is_fraud=True` en la muestra de un día.
- Usar estos campos como input al agente sería leakage (el agente "adivinaría" con el resultado ya dado). Solo sirven para construir el eval set / medir precisión de una regla propia de detección, nunca como feature de decisión en producción del agente.

## Calidad de datos en `customers` (nulls reales, confirma el ~5% documentado, con variación fuerte por campo)

| Campo | % nulo |
|---|---|
| landline_phone | 50.0% |
| detected_accent | 29.9% |
| estimated_monthly_income | 20.0% |
| credit_score | 15.0% |
| education_level | 12.0% |
| postal_code / occupation | 10.0% |
| marital_status | 8.0% |
| address | 4.9% |
| mobile_phone | 3.1% |
| email | 2.0% |

`detected_accent` nulo en ~30% de clientes es relevante si el workflow elegido quiere apoyarse en "accent-aware routing/detección" como diferenciador — casi un tercio de los clientes no lo tiene.

## `products.csv` (400,000 filas, completo)

- `product_type` en español, 8 tipos: Cuenta Ahorro (120,203), Tarjeta Crédito (100,102), Cuenta Corriente (99,979), Tarjeta Débito (39,938), Préstamo Personal (19,960), Préstamo Hipotecario (11,910), Inversión (5,859), Seguro (2,049).
- `product_status`: Active 339,965 / Closed 32,039 / **Blocked 19,935 (~5%)** / Suspended 8,061. El volumen de productos bloqueados (~5%) da buen soporte de datos si se elige Opción B (soporte de tarjetas — "mi tarjeta está bloqueada").
- Cero `product_id` duplicados en las 400k filas.
- Nulls: `credit_limit` 68.7% y `days_past_due` 68.7% (esperado, solo aplica a productos de crédito), `expiration_date` 66.7%, `last_transaction_date` 23.6%, `interest_rate` 10.0%.
- **Anomalía encontrada:** `currency` en `products` solo trae USD (220,501), COP (107,975), ARS (71,524) — **cero filas en MXN**, pese a que México es uno de los 3 países del dataset y la documentación dice soporte MXN/COP/ARS/USD. Posible bug/gap real del dataset sintético — a reportar como "limitación de datos encontrada" si se usa esta tabla, y a verificar antes de asumir que hay productos mexicanos con moneda local.

## `digital_events` (muestra de un día, 8,810 filas)

- `event_type`: PageView 3,414, Click 2,048, Login 1,350, Logout 1,345, FormSubmit 339, Error 194, Purchase 120.
- `event_category`: Authentication 2,695, Navigation 2,317, Product 2,131, Transaction 1,667.
- `channel`: Android App, iOS App, Desktop Web, Mobile Web — bien distribuido, sin un canal dominante.
- Cero `event_id` duplicados en la muestra.
- Tabla más útil como señal de contexto (¿el cliente ya intentó resolver esto por la app antes de llamar?) que como corazón de un workflow propio — soporta Opción C (cuentas/pagos) como evidencia complementaria, no como base suficiente por sí sola.

## Cobertura completa: las 13 tablas revisadas

Con esta pasada quedan las 13 tablas del dataset revisadas con datos reales de S3 (no solo el data dictionary). Resumen de lo que faltaba:

### `branches` (350, completo)
- `branch_type`: Express 130, Corporate 129, Premium 48, Main 43. `branch_status`: Active 336, Temporarily Closed 14.
- **Anomalía:** `geographic_zone` es 100% "Urbana" en las 350 filas — el dictionary documenta "Urban, Suburban, Rural" pero Suburban/Rural no aparecen nunca. Otra limitación de datos a reportar si el workflow usa zona geográfica.

### `service_agents` (1,200, completo)
- `native_accent`: mexican 600, colombian 360, argentine 240. `agent_type`: Phone 588, Digital 251, In-Person 230, Hybrid 131.
- **Dato clave para el requisito de portugués del reto:** 129/1,200 agentes (10.75%) hablan portugués (`español, portugués` 68 + `español, inglés, portugués` 61). Es la única evidencia real de portugués en todo el dataset — no hay clientes, transcripts ni texto en portugués en ninguna tabla revisada. Confirma que el soporte de portugués del prototipo tiene que resolverse en la capa del agente/LLM (traducción en vivo), no hay datos históricos en portugués de los que apoyarse.
- Nulls altos: `specialty` 39.7%, `assigned_branch_id` 30.6% (agentes remotos/digitales sin sucursal, tiene sentido).

### `marketing_campaigns` (200, completo)
- Poco relevante para los 4 workflows candidatos (es para el track de marketing analytics, no customer service). `campaign_status` mayormente Completed (172/200).

### `daily_exchange_rates` (13,164, completo)
- Sí incluye pares con MXN (`MXN→USD`, `USD→MXN`, `MXN→COP`, etc. — 1,097 filas cada par). La tasa de cambio para pesos mexicanos existe y está completa.

### 🔴 Hallazgo grave confirmado: MXN no existe en transacciones ni productos, pese a que la mitad de los clientes son mexicanos
- `customers.country`: México 74,907 (49.9%), Colombia 45,251 (30.2%), Argentina 29,842 (19.9%) — de 150,000 clientes.
- `products.currency` (400,000 filas, completo): solo USD/COP/ARS — **cero MXN**.
- `transactions.currency` (~25,000 filas, 5 días): solo USD/COP/ARS — **cero MXN**.
- Pero `daily_exchange_rates` sí tiene el par MXN completo, y la mitad de la base de clientes es mexicana.
- **Esto es un bug/gap real del dataset sintético v1.0.0**, no una interpretación mía: los productos y transacciones de los ~75k clientes mexicanos están registrados en USD/COP/ARS en vez de MXN. Cualquier workflow que use `transactions` o `products` debe: (a) reportarlo explícitamente como limitación de datos encontrada (el reto lo pide), y (b) decidir si se hace un workaround (ej. inferir moneda esperada por `customers.country` y tratarlo como inconsistencia a manejar en el pipeline) o simplemente se documenta y no se corrige.

### `call_center_interactions` (590 filas, 1 día)
- `contact_reason` y `reason_category` son literalmente los mismos 6 valores (Transaccional, Producto, Queja, Técnico, Comercial, Retención) — `contact_reason` NO es más granular que la categoría, pese a que el dictionary los describe como campos distintos. Menos señal estructurada de la que parecía en el diccionario.
- `was_resolved` (FCR): 447/590 = 75.8%. `was_escalated`: 56/590 = 9.5%. Estos dos son buenos candidatos de baseline real para "containment"/"escalation rate" en la evaluación, sea cual sea el workflow.
- `detected_sentiment`: mayoría Neutral (376), Negativo+Muy Negativo 126 (21%).

### `satisfaction_surveys` (183 filas, 1 día)
- `survey_type`: CSAT 117, NPS 50, CES 16. `nps_category` vacío en 135/183 (solo se llena cuando `survey_type`=NPS, tiene sentido, no es un null real de calidad).

### `campaign_sends` (1,974 filas, 1 día)
- No relevante para los 4 workflows candidatos — es soporte del track de marketing, no de customer service.

## Verificación a escala completa (2026-09-30, 13 tablas cargadas en `bronze`)

Las secciones anteriores salen de muestras de 1 a 5 días. Todo lo de abajo se midió sobre las tablas completas en Postgres (`bronze.*` y `gold.*`). Donde una cifra de arriba difiere, **manda esta sección**.

### Volúmenes cargados

| Tabla | Filas cargadas |
|---|---|
| customers | 150.000 |
| products | 400.000 |
| transactions | 4.425.008 |
| complaints | 67.095 |
| call_center_interactions | 686.296 |
| call_transcripts | 171.321 |
| satisfaction_surveys | 212.759 |
| campaign_sends | 1.746.801 |
| digital_events | 15.620.994 |
| branches / service_agents / marketing_campaigns / daily_exchange_rates | 350 / 1.200 / 200 / 13.164 |

**Las cifras del resumen del organizador son nominales, no el contenido real.** Habla de ~5M transacciones, ~80k quejas, ~800k interacciones, ~200k transcripts y ~250k encuestas (14-16% más que lo cargado) y de ~10M `digital_events` (56% menos que lo cargado). Se verificó contra S3: en la corrida de carga del 2026-09-28, `rows_read` (filas leídas de los CSV) es **idéntico** a las filas de bronze en las 13 tablas (ej. transactions 4.425.008 leídas y 4.425.008 cargadas). Si los archivos trajeran claves primarias repetidas, se leerían más filas de las que quedan en bronze; no ocurre. El loader no descartó nada, y S3 no contiene "~2% de duplicados" a nivel de clave primaria.

**Cobertura por archivo:** 1.097 archivos (un archivo por día) en cada tabla particionada, salvo `campaign_sends` con 1.083: faltan 14 días. En las 7 tablas particionadas, todos los archivos comparten un único encabezado (0 cambios de esquema entre fechas), así que la "evolución de esquema" que menciona el organizador no aparece en los encabezados.

### Quejas (`complaints`)

| Hallazgo | Evidencia |
|---|---|
| `affected_product_id` apunta al producto de otro cliente | 44.570 de 44.570 con valor (66,4% de las quejas); 0,00% coincide con el dueño |
| El producto equivocado es aleatorio, no recuperable | mismo país 37,93% (azar 38,00%); misma sucursal 0,28% (azar ~0,29%); IDs opacos (`PRD-XXXXXXXXXXXX`), sin offset que corregir |
| `origin_interaction_id` siempre vacío | 0 de 67.095 con valor, no hay cruce con `call_center_interactions` |
| `claimed_amount` no se relaciona con ninguna transacción | 0 de 21.751 coinciden con alguna transacción del cliente; 0 de 14.388 con transacciones del dueño del producto o del producto mismo |
| `subcategory` no aporta granularidad | es 1 a 1 con `category` (5 pares fijos) y está vacía en 9,98% |
| Las 5 categorías pesan casi lo mismo | 17,7% a 18,3% cada una |
| "Cargo no reconocido + Cobro indebido = 36,5%" es artefacto de uniformidad | 18,33% + 18,17%, dos de cinco categorías parejas; no indica más disputas que otras quejas |
| Resultados idénticos entre tipos de queja | SLA incumplido 19,9-20,4%, resolución 15,4-15,9 días, `Escalated` ~5%, en todas |
| `complaints.customer_id` válido | 67.095 de 67.095 existen en `customers`; 1,24 quejas por cliente en promedio |

**Decisión de diseño:** la transacción o producto de una disputa lo elige el cliente autenticado entre los suyos. Nunca sale de `complaints`. Las quejas solo se usan a nivel de cliente.

### Transacciones (`transactions`)

- `transaction_status`: Declined 221.234 (5,00%), Reversed 44.750 (1,0%). Son la base del caso auto-resuelto (266k candidatas).
- `response_code` de Declined y Reversed reparte casi igual entre 51, 14, 54 y 05 (~52,5k cada uno en Declined) y queda vacío en ~5% (10.962 Declined, 2.310 Reversed).
- **El rechazo es independiente del producto:** las 4.425.008 transacciones están sobre productos `Active`. No hay relación entre rechazo y estado o saldo del producto, así que explicar un rechazo se limita al significado del código.
- Titularidad transacción-producto consistente al 100% (4.425.008 de 4.425.008): relación apta para autorizar acceso a movimientos propios.
- Cero duplicados exactos de `transaction_id`; los tests `unique` de dbt pasan en las 5 tablas modeladas.
- Cero filas en MXN (solo USD/COP/ARS).

### Crédito (`products` + `customers`)

- **Sin señal predictiva de mora.** Tasa de mora `>=30` días o estado Blocked/Suspended: 17,4% con score <550, 16,5%, 16,4%, 16,5%, 16,6% con 780+; por terciles de ingreso 16,4 / 16,5 / 16,7%; por utilización plana salvo 80%+ con 18,3% (n=1.905). Correlación `credit_score` vs `days_past_due` = -0,004.
- **`total_credit_products` no es señal de riesgo, es agregación.** La mora por cliente calza con independencia pura `1-(1-p)^n` (n=1: 11,68% observado vs 11,86% esperado; n=2: 22,75% vs 22,31%; n=3: 31,73% vs 31,53%) y la tasa **por producto** es plana (11,4% a 12,1%) sin importar cuántos productos tenga el cliente. El AUC de `n` solo es 0,63 porque la etiqueta `max(dpd)` se calcula sobre los mismos productos que se cuentan: fuga por construcción.
- `days_past_due`: rango 0 a 180, pico exacto en 30 (~3.100 productos), 5% nulo entre productos de crédito (nulo no es cero). Sus tramos caben en las situaciones 1 a 3 de la clasificación de deudores del BCRA.
- `credit_score`: nulo 15,0% (22.492), mínimo real 422 (la documentación sugiere 300). `estimated_monthly_income`: nulo 20,0% (30.033).
- **Monedas:** México tiene 66.236 productos de crédito, todos en USD, con ingreso en escala MXN (mediana 39.219; Argentina 801.955 ARS, Colombia 9,19M COP). Argentina y Colombia usan ~90% moneda local y ~10% USD. 3.461 de 87.770 clientes con crédito (3,9%) tienen productos en más de una moneda. Cualquier DTI o suma de saldos requiere normalizar con `daily_exchange_rates`.
- No hay reglas de elegibilidad aprobadas por el organizador: cualquier política de crédito es sintética y debe rotularse así.

### Interacciones, transcripts y otras tablas

- `call_center_interactions`: Transaccional 35,0% (resuelto 91,5%), Producto 22,0% (89,6%), Queja 17,1% (43,6%, 435 s), Técnico 15,0% (69,9%), Comercial 8,0% (65,2%), Retención 3,0% (60,2%). FCR global 76,6% y escalamiento 10,0%, **plano por motivo** (9,8% a 10,1%). `contact_reason` es idéntico a `reason_category`.
- `call_transcripts` (171.321): 95% `consulta_general` (162.864), 100% en español, sin portugués.
- `satisfaction_surveys` (212.759): `main_score` promedio 3,526 sin escalamiento vs 3,527 con escalamiento, sin relación.
- Sin cadenas causales entre tablas: `digital_events` con error a contacto al call center 0% a 2,2%; `campaign_sends` a quejas en 2 días 0% a 0,23%.
- `branches` 100% "Urbana"; `daily_exchange_rates` tiene MXN pero nada en MXN con qué cruzar; `service_agents` con portugués 129 de 1.200 (10,75%).

### Hallazgos adicionales de la revisión del pipeline (2026-09-30)

- **`customers.registration_branch_id` es inservible:** 150.000 IDs distintos con formato válido, solo 5 existen en `branches` (149.995 huérfanos). Las demás FKs a sucursal y agente (`transactions.branch_id`, `products.opening_branch_id`, `complaints.related_branch_id`, `*.agent_id`) tienen 0 huérfanos.
- **`transactions.amount_usd` nulo en 57%:** 100% nulo cuando `currency = USD` (el monto ya está en dólares) y ~5% en ARS y COP (99.477 huecos reales). Hay que derivarlo en silver.
- **No hay llegadas tardías:** `process_date - transaction_date` vale solo 0 o -1 día (25% con -1, borde de fecha por zona horaria), nunca positivo.
- **`response_code` por estado:** Approved trae `00` (3.867.312) o nulo (203.369, 5% de las Approved); Pending y Reversed llevan códigos 05, 14, 51 o 54. Mezcla de estados: Approved 91,99%, Declined 5,00%, Pending 2,00% (88.343), Reversed 1,01%.
- **Reglas de negocio rotas:** 7.510 productos de crédito con saldo mayor al límite; 772 quejas Resolved o Closed sin `resolution_date`; 52.454 interacciones a la vez escaladas y resueltas.
- Las fechas de hechos cubren 2023-06-17 a 2026-06-18 en transacciones, quejas e interacciones: es un snapshot estático.

Detalle de la revisión y plan de corrección en `archive/PIPELINE_REVIEW.md`.

### Calidad de tipos en la carga

Seis columnas enteras llegan con formato decimal (`"26.0"`): `credit_score`, `duration_seconds`, `wait_time_seconds`, `resolution_days`, `resolution_satisfaction`, `days_past_due`. En todas las filas el decimal es `.0` (0 valores con decimal real), por eso `stg_*` las castea vía `::numeric::int` sin perder información.

### Pendiente de verificar (no afirmar hasta medirlo)

- Moneda real del ingreso por país (se asume MXN para México).
- Los 14 días sin archivo en `campaign_sends`: se desconoce si es intencional. Irrelevante para el workflow elegido.
- Contenido de columnas entre particiones (el encabezado no cambia, pero no se comparó la distribución de valores por fecha).

## Próximos pasos de investigación sugeridos

- Decidir si `affected_product_id` sale de `gold.complaints` (propuesto: sí, con un test dbt en `warn` que mida el defecto).
