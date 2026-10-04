# Datos

*Qué contiene el dataset de LATAM Bank, qué se verificó a escala completa y qué limitaciones cambian el diseño.*

[Índice](README.md) · [Workflow](WORKFLOW.md) · [Arquitectura](ARCHITECTURE.md)

## Procedencia

Todo lo que entra al sistema es **sintético y lo entrega el organizador**: el dataset LATAM Bank v1.0.0, 13 tablas en un bucket de S3 de solo lectura. No hay datos reales ni de-identificados. Los nombres, documentos, teléfonos y correos son ficticios. Lo que el equipo genere (casos de evaluación, enunciados de usuario) se rotula aparte como generado por el equipo.

## Volúmenes

Cargados y verificados contra S3, tabla por tabla.

| Tabla | Filas | | Tabla | Filas |
|---|---:|---|---|---:|
| `digital_events` | 15.620.994 | | `call_transcripts` | 171.321 |
| `transactions` | 4.425.008 | | `customers` | 150.000 |
| `campaign_sends` | 1.746.801 | | `complaints` | 67.095 |
| `call_center_interactions` | 686.296 | | `daily_exchange_rates` | 13.164 |
| `products` | 400.000 | | `service_agents` / `branches` / `marketing_campaigns` | 1.200 / 350 / 200 |
| `satisfaction_surveys` | 212.759 | | **Total** | **~23,5 millones** |

Las cifras del resumen del organizador son nominales y no coinciden con el contenido (por ejemplo, ~5 millones de transacciones y ~10 millones de eventos). Se verificó que las filas leídas de los CSV son idénticas a las cargadas en las 13 tablas. Hay 1.097 archivos por tabla particionada (uno por día), salvo `campaign_sends`, que tiene 1.083. Todos los archivos de una tabla comparten un único encabezado: no hay cambios de esquema entre fechas.

## Lo que cambió el diseño

| Hallazgo | Evidencia | Consecuencia |
|---|---|---|
| **El texto histórico es plantilla** | `call_transcripts`: 95 % con la misma intención, `consulta_general`; `complaints.description` siempre `"Queja relacionada con {categoría}"` | No se puede entrenar ni evaluar un clasificador de intención sobre el texto histórico. Se usa el texto vivo de la conversación y los campos estructurados como línea base |
| **No hay duplicados exactos** | 0 `transaction_id` repetidos; 0 grupos con mismo cliente, monto y comercio | Se descartó el caso "cargo duplicado". El caso auto-resuelto pasó a ser una transacción `Declined` o `Reversed` que el cliente cree cobrada: **266 mil** candidatas |
| **`affected_product_id` es inservible** | Apunta al producto de otro cliente en 44.570 de 44.570 quejas con valor | La transacción de una disputa nunca sale de `complaints` |
| **La titularidad sí es fiable** | Transacción a producto a cliente: 4.425.008 de 4.425.008 consistentes | Es la base para autorizar acceso a los movimientos propios |
| **No hay MXN** | 0 filas en MXN en transacciones y productos, aunque el 49,9 % de los clientes es mexicano; sí existe el par MXN en tipos de cambio | Se documenta, no se convierte. México tiene 66.236 productos de crédito, todos en USD |
| **`amount_usd` nulo en el 57 %** | 100 % nulo si la moneda es USD (el monto ya está en dólares) y ~5 % en ARS y COP | `amount_effective_usd` se deriva; si no se conoce, nunca cuenta como cero |
| **`merchant_name` nulo en el 76,7 %** | Medido sobre transacciones | La identificación usa monto aproximado, fecha y estado; el comercio suma solo si existe |
| **`is_fraud` y `fraud_score` son verdad de referencia** | ~0,13 % de transacciones marcadas fraude en una muestra | Nunca son entrada del agente: sería fuga de etiquetas |
| **No hay portugués en los datos** | Ninguna tabla, ni clientes ni transcripciones; solo 129 de 1.200 agentes hablan portugués | El portugués se resuelve en la capa del agente |
| **El rechazo no se explica con el producto** | Las 4.425.008 transacciones están sobre productos `Active` | Explicar un rechazo se limita al significado del código de respuesta |

## Transacciones

- Estados: `Approved` 91,99 %, `Declined` 5,00 %, `Pending` 2,00 %, `Reversed` 1,01 %.
- Códigos de rechazo repartidos casi por igual entre `51` (fondos insuficientes), `14` (tarjeta inválida), `54` (tarjeta vencida) y `05` (no autorizada por el emisor); vacío en ~5 %. Los significados son los del estándar ISO 8583 y son un supuesto del equipo: el organizador no define los códigos.
- Cobertura del 2023-06-17 al 2026-06-18, un snapshot cerrado. No hay llegadas tardías (`process_date - transaction_date` vale 0 o -1 día, nunca positivo).

## Sin señal predictiva de mora

Sobre `products` y `customers`, la mora (30 o más días, o bloqueado o suspendido) es plana frente a `credit_score` (17,4 % con puntaje menor a 550; 16,6 % con 780 o más), el ingreso y la utilización. La correlación entre `credit_score` y `days_past_due` es -0,004. Por eso, un modelo de riesgo de crédito sobre estos datos no tendría qué aprender. Además, no hay reglas de elegibilidad aprobadas por el organizador: cualquier política de crédito sería sintética.

## Otras limitaciones registradas

| Tabla | Limitación |
|---|---|
| `customers` | `registration_branch_id`: solo 5 de 150.000 existen en `branches`. Nulos altos en `landline_phone` (50 %), `detected_accent` (30 %), `estimated_monthly_income` (20 %), `credit_score` (15 %) |
| `complaints` | `origin_interaction_id` siempre vacío; `claimed_amount` no coincide con ninguna transacción; las 5 categorías pesan casi lo mismo (17,7 % a 18,3 %), así que "cargo no reconocido más cobro indebido = 36,5 %" es un artefacto de uniformidad |
| `call_center_interactions` | `contact_reason` es idéntico a `reason_category`. Resolución en el primer contacto 76,6 % y escalamiento 10,0 %, planos por motivo |
| `branches` | 100 % "Urbana"; la documentación habla de urbana, suburbana y rural |
| Reglas de negocio | 7.510 productos de crédito con saldo mayor al límite; 772 quejas cerradas sin fecha de cierre; 52.454 interacciones a la vez escaladas y resueltas |
| Tipos | Seis columnas enteras llegan como decimal (`"26.0"`), siempre con `.0`; se convierten sin pérdida |

## Qué se modeló y qué no

Cinco de las 13 tablas llegan a `gold` (`customers`, `products`, `transactions`, `complaints`, `call_center_interactions`). Es deliberado: ninguna de las otras aportó señal útil a un workflow candidato y el reto premia profundidad sobre cobertura.

## Pendiente de verificar

- La moneda real del ingreso por país (se asume MXN para México).
- Los 14 días sin archivo en `campaign_sends`: no se sabe si es intencional; es irrelevante para este workflow.
- La distribución de valores entre particiones: el encabezado no cambia, pero no se comparó el contenido por fecha.
