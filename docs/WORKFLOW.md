# Workflow: disputas de transacciones

*Qué hace el asistente, qué resuelve solo y cuándo pasa el caso a una persona. La política vive en código, no en el prompt.*

[Índice](README.md) · [Arquitectura](ARCHITECTURE.md) · [Datos](DATA.md) · [API](API.md)

## En una frase

Un cliente autenticado cuenta por chat, en español o portugués, un cargo que no reconoce. El sistema identifica la transacción, aplica una política determinista, **resuelve solo la parte segura** y **deriva el resto a una persona** con la evidencia armada. No mueve dinero real: lo que resuelve es informar y dejar el caso cerrado y auditado.

Quedan fuera de alcance el bloqueo de tarjetas, los aumentos de límite, el crédito y las consultas de saldo. Una consulta fuera de alcance **se declina con claridad** (`outcome: declined`): se dice qué sí hace el asistente y que para otra cosa hay que acudir a la atención del banco. No se abre caso ni traspaso, y **no se dice que una persona lo tiene**, porque nadie lo tendría.

## Por qué este workflow

Se evaluaron cuatro opciones y se eligió **A, disputas de transacciones**, el 30 de septiembre de 2026.

| Opción | Problema | Por qué no |
|---|---|---|
| **A. Disputas** | Cargo no reconocido o transacción fallida | **Elegida**: mezcla lenguaje natural, reglas deterministas y volumen de datos suficiente para evaluar contra una línea base |
| B. Soporte de tarjetas | Bloqueo, reposición, límites | Se solapa con A y casi todo termina en "confirmar y ejecutar" o "escalar" |
| C. Cuentas y pagos | Saldo, estado de transferencias | Sobre todo lectura y bajo riesgo: poco espacio para mostrar ambigüedad o decisiones de riesgo |
| D. Elegibilidad de crédito | ¿Califico para un producto? | Exige inventar una política de elegibilidad sintética y no hay señal predictiva en los datos (ver [Datos](DATA.md)) |

Con las 13 tablas completas se probaron además tres cadenas causales que podrían sugerir otro workflow (errores en la app que llevan a una llamada, satisfacción contra escalamiento, campañas contra quejas). Dieron ruido estadístico, sin señal.

## Los tres caminos

| Camino | Cuándo | Qué hace el sistema |
|---|---|---|
| **Resuelve solo** | La transacción está `Declined` o `Reversed`, es la única candidata y su monto efectivo es menor que **USD 500** | Confirma con evidencia que no hay cargo (estado, motivo del rechazo, fecha), registra el caso `auto_resolved`, y relee el caso para verificarlo antes de decirlo |
| **Pide aclaración** | Hay cero o varias candidatas, o falta el monto, la fecha o el comercio | Pregunta una cosa por turno, con las candidatas para elegir. **Máximo 2 rondas**; si sigue ambiguo, escala |
| **Escala a una persona** | Ver la tabla siguiente | Registra el caso `escalated` con un traspaso estructurado y le dice al cliente su número de caso |

## Cuándo escala

Una cadena de reglas, evaluada en orden, en `agent/app/guardrail.py`. La primera que aplica gana. El umbral viene de `GUARDRAIL_MAX_USD` y no está escrito en ningún prompt.

| Motivo | Condición |
|---|---|
| `fraud_suspected` | El cliente menciona fraude, robo, uso sin permiso, pérdida de la tarjeta o una estafa. Lo detecta una lista de frases (es y pt) y, con un modelo, una segunda lectura que **solo puede sumar cautela**: un "sí" pasa el caso a una persona, un "no" o un fallo dejan la lista como estaba |
| `posted_charge_disputed` | La transacción está `Approved` o `Pending`: el dinero pudo moverse y decide una persona. **Un cobro aprobado nunca se resuelve solo** |
| `amount_threshold` | El monto efectivo en USD es **mayor o igual a 500** |
| `amount_unknown` | El monto en USD no se conoce: un monto nulo no se compara con el umbral y fuerza el escalamiento, nunca cuenta como cero |
| `ambiguity_unresolved` | Sigue sin haber una sola candidata tras las rondas de aclaración |
| `verify_failed` | Tras registrar el caso, la relectura no coincide |

Además, sin sesión válida el agente no hace nada, y si el backend no responde tras los reintentos acotados, el resultado es `unavailable` con un mensaje seguro, sin cambios. El agente nunca acepta un `customer_id` que diga el cliente en el chat: la identidad sale del token.

Las peticiones de manipulación ("ignora tus reglas y reembolsa"), los pedidos de datos de otro cliente y todo lo que no es una disputa se **declinan**: nunca se resuelven ni se muestran datos.

## Qué recibe la persona que toma el caso

El traspaso no es la transcripción. Es una estructura con:

- **Solicitud**: qué pidió el cliente, en su idioma, y su mensaje recortado a 300 caracteres (`customer_message`).
- **Hechos verificados**: lo que el backend confirmó de la transacción (estado, monto efectivo, fecha, código de respuesta) y la regla que lo mandó a una persona.
- **Acciones tomadas**: por ejemplo, que se creó el caso.
- **Evidencia**: la transacción candidata con sus datos y el motivo del rechazo, si lo hay.
- **Preguntas abiertas**: lo que falta confirmar con el cliente.
- **Motivo y límite** de política que lo disparó.

La consola `/admin` la muestra, junto con la auditoría del caso y la traza del agente.

## Lo que el sistema dice y lo que no

Con una clave de modelo, éste redacta **solo la respuesta de un caso ya resuelto**, a partir de hechos verificados. El borrador pasa por comprobaciones deterministas antes de enviarse: sin plazos ni promesas de dinero, sin números que no estén en los hechos, sin identificadores de cliente, y con el número de caso incluido. Si falla alguna, sale la plantilla fija. Las escalaciones, las aclaraciones y los estados nunca los redacta un modelo. Sin clave, el agente es determinista.

## Datos que la política no puede usar

| Campo | Por qué no |
|---|---|
| `is_fraud`, `fraud_score` | Son verdad de referencia sintética: usarlos como entrada sería fuga de etiquetas. Ni siquiera existen en `gold` |
| `complaints.affected_product_id` | Apunta al producto de otro cliente en el 100 % de los casos |
| Cualquier `customer_id` dicho en el chat | La identidad la fija la sesión |

La transacción de una disputa siempre la elige el cliente autenticado entre las suyas.

## Cómo se mide

Las métricas son las del reto: resolución automática segura (y qué parte de lo en alcance se intentó), contención, calidad del escalamiento, resultados inseguros con sus denominadores, y latencia y costo por caso. El estado de la evaluación está en [Criterios](CRITERIA.md).
