# Hallazgos de investigación sobre el dataset real (S3)

Investigación hecha bajando muestras reales del bucket `factored-datathon-2026-s3-157725502942-us-east-2-an` (credenciales read-only del data dictionary). Objetivo: verificar supuestos antes de comprometernos a un workflow. Actualizar este doc si se investiga más.

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

## Próximos pasos de investigación sugeridos (si hay tiempo antes de votar)

- Revisar distribución completa de `case_type`/`category` en `complaints` sobre varios días (no solo uno) para confirmar volumen real por categoría.
- Confirmar si existe algún campo o tabla con texto de portugués real (no visto en la muestra — `call_transcripts.detected_language` observado hasta ahora es español).
- **Confirmado:** `transactions.currency` en ~25,000 filas (5 días) tampoco trae MXN (solo USD/COP/ARS) — misma ausencia que en `products`. Es limitación de datos real del dataset sintético, no error de muestreo: documentarla explícitamente en la entrega ("report limitations in the supplied data"), sea cual sea el workflow elegido.
