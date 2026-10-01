# Hallazgos de ML: qué se puede aprender de los datos y qué componente evaluar

Documento para el ML engineer. Reúne lo que se midió sobre el dataset LATAM Bank (sintético, del organizador), lo que dice el reto sobre ML, lo que hicieron otros equipos públicamente, y la propuesta de componentes a evaluar. Todo número de la sección 4 sale de los scripts de `ml/probes/` corridos contra `silver.*` (ver sección 10 para reproducirlos).

## 1. Resumen

- **El reto exige evaluar al menos un componente aprendido contra una línea base apropiada**, pero **acepta componentes preentrenados o basados en recuperación**: se demuestra con la selección del componente, las etiquetas de intención, las representaciones, la prevención de fuga y la evaluación sobre un set retenido. No hace falta entrenar un modelo propio.
- **Los datos casi no contienen señal predictiva.** Fraude, incumplimiento de SLA, reclamos reincidentes, demora de resolución, escalamiento, tiempo de espera y abandono se predicen igual que al azar (AUC 0,49 a 0,50, R² 0,00) con un modelo de gradient boosting y partición temporal.
- **La única señal real y limpia** es que el motivo de contacto (`contact_reason`, 6 valores) explica si una llamada se resuelve (AUC 0,76) y, en menor medida, la insatisfacción posterior (AUC 0,65). Equivale a una tabla de tasas por motivo; un modelo complejo no agrega nada.
- **Hay dos trampas de fuga en los datos**: `fraud_score` (generado a partir de la etiqueta) y las columnas que se miden después de la llamada (sentimiento, duración).
- **No existen etiquetas de "qué transacción se disputó"**, ni transacciones duplicadas naturales, ni texto con intención real (los textos son plantillas, 100% español, sin portugués). Todo lo que dependa de eso exige datos generados por el equipo.
- **Propuesta**: componentes evaluables con etiquetas válidas por construcción (set generado por el equipo, rotulado como tal): (A) clasificación de intención e idioma, es/pt, con confianza y abstención; (B) identificación de la transacción disputada a partir de una descripción libre; (C) prioridad calibrada por motivo de contacto como señal secundaria. Candidato para (A): Jev de TypeSafe, a comparar con un clasificador local de embeddings y con un LLM de salida estructurada.

## 2. Lo que pide el reto (`doc/Factored AI & Data Hackathon 2026.md`)

- Línea 23: elegir un problema acotado, usar los datos para explicar por qué importa, **establecer una línea base** y medir si el enfoque mejora calidad de servicio y eficiencia operativa.
- Línea 46 (criterio 4, "datos y ML sólidos"): pipeline repetible con contratos, chequeos de calidad, linaje y política de frescura. **Evaluar al menos un componente aprendido contra una línea base apropiada.** Usar etiquetas o juicios de relevancia válidos y prevenir la fuga.
- Línea 54: para una solución preentrenada o basada en recuperación, demostrar esas competencias con **selección del componente, etiquetas de relevancia o intención, representaciones, prevención de fuga, evaluación sobre un set retenido**.
- Línea 68: comparar línea base y sistema propuesto **sobre la misma carga retenida**; reportar cantidad y mezcla de casos, calidad de las etiquetas, versiones de modelo y de prompt, variabilidad entre corridas repetidas, e **incluir los fallos**. Si un modelo actúa de juez, validarlo.
- Métricas pedidas en el reto: resolución automática segura, contención, calidad del escalamiento, resultados inseguros, latencia y costo (p50 y p95).
- Portugués: el dataset no tiene ninguna fila en portugués; el sistema debe recibirlo y responderlo igual (limitación a documentar).

## 3. Qué datos hay (relevante para ML)

Procedencia: todo es **sintético y del organizador** (ver `spec/DATA_FINDINGS.md`, "Procedencia de los datos"). Lo que genere el equipo se rotula aparte como "generado por el equipo".

| Tabla (silver) | Filas | Relevante para |
|---|---|---|
| `stg_transactions` | 4.425.008 | disputas; trae `is_fraud` y `fraud_score` (solo en silver, no en gold) |
| `stg_complaints` | 67.095 | reclamos (PQR); `description` y `resolution` son texto plantilla; `affected_product_id` apunta al producto de otro cliente en el 100% de los casos |
| `stg_call_center_interactions` | 686.296 | `contact_reason` (== `reason_category`, 6 valores), `was_resolved`, `was_escalated`, `requires_followup`, sentimiento, duración, espera |
| `stg_call_transcripts` | 171.321 | texto plantilla, 95% intención `consulta_general`, 100% español |
| `stg_satisfaction_surveys` | 212.759 (CSAT 127.856; NPS 63.668; CES 21.235) | se enlaza 100% con una interacción (`interaction_id`) |
| `stg_customers` | 150.000 | estado: Active 127.700, Inactive 14.914, Suspended 4.407, Closed 2.979 |

Reglas del proyecto relacionadas (`spec/CRITERIA.md`, `AGENTS.md`): `is_fraud` y `fraud_score` nunca son entrada del agente; el agente solo accede a datos por el backend.

## 4. Mediciones

Método común: gradient boosting de scikit-learn (`HistGradientBoosting`), **partición temporal 70/30** (se entrena con lo más antiguo, se prueba con lo más reciente), métrica AUC en el 30% final. AUC 0,50 equivale a azar. Salvo que se indique, las columnas posteriores al resultado se excluyen de las características.

### 4.1 Fraude (`is_fraud`)

- 4.425.008 transacciones, 4.316 fraudes (0,10%). La tasa es igual en Approved, Declined, Pending y Reversed (0,08% a 0,10%).
- Muestra: todos los fraudes más 20% de las demás (887.674 filas). Entrenamiento 3.123 positivos, prueba 1.193.
- Características: monto, monto en USD, moneda, canal, tipo y categoría de transacción, categoría del comercio, país de la transacción, estado, código de respuesta, hora, día de la semana, país distinto al del cliente, segmento, score crediticio, tipo de producto.
- **Resultado: AUC 0,491; PR-AUC 0,0043 contra 0,0045 de la línea base aleatoria.** El monto solo da 0,497. Ninguna variable mueve la tasa de fraude más allá de 0,0039 a 0,0061 (ruido).

### 4.2 `fraud_score` es un artefacto de la etiqueta (fuga por construcción)

- Escala de 0 a 100 (no 0 a 1). Nulo en 885.157 transacciones (20%).
- Las transacciones **no fraudulentas** tienen score entre 0 y 30 (promedio 15,0). Las fraudulentas, entre 0,01 y 99,99 (promedio 49,5).
- **Todas las 2.373 transacciones con score mayor a 30 son fraude; cero no fraudulentas.** Eso cubre el 55% de los fraudes (2.373 de 4.316).
- Los otros 1.943 fraudes (1.052 con score de 30 o menos, 891 sin score) no se distinguen de las no fraudulentas con ninguna variable.
- Lectura: el score se generó condicionado a la etiqueta. Calibrarlo o ponerle un umbral "aprende" una regla ya incrustada en los datos y viola la regla del reto sobre no usar `is_fraud` como entrada de lo que el sistema debería detectar. Otro equipo público lo presenta como mejora de 37% sobre un umbral fijo; nosotros lo descartamos y lo documentamos.

### 4.3 Reclamos (`stg_complaints`, n = 67.095, partición por `creation_date`)

| Objetivo | Tasa | AUC |
|---|---|---|
| `sla_breached` | 0,201 | 0,501 |
| `is_repeat_complainer` | 0,150 | 0,493 |
| demora de resolución mayor que la mediana (n = 15.363, solo resueltos) | 0,471 | 0,494 |

No se evaluó `compensation_granted > 0` (4.641 positivos): el script lo omitió por un error de filtrado en la prueba, queda pendiente. `requires_followup` no existe en reclamos.

### 4.4 Llamadas (`stg_call_center_interactions`, n = 686.296, partición por `interaction_date`)

| Objetivo | Tasa | AUC |
|---|---|---|
| `was_escalated` | 0,100 | **0,499** |
| `was_resolved` | 0,766 | 0,764 |
| `requires_followup` | 0,348 | 0,677 |
| duración mayor que la mediana | 0,428 | 0,880 (no se descompuso qué columna lo explica) |

Qué variables explican `was_resolved` (AUC de un modelo con una sola variable, 30% de muestra):

| Variable | AUC | Observación |
|---|---|---|
| `contact_reason` / `reason_category` | 0,764 | Transaccional 91,5%, Producto 89,5%, Técnico 69,6%, Comercial 65,8%, Retención 60,1%, **Queja 43,7%** |
| `duration_seconds` | 0,678 | **se mide durante o después de la llamada: fuga** |
| `detected_sentiment` / `sentiment_score` | 0,613 / 0,611 | **posterior: fuga**. Neutral resuelve 82,6%; los otros cuatro sentimientos, cerca de 64% |
| `interaction_type`, `channel` | ~0,50 | planos (76% a 77%) |
| `agent_used_accent` | 0,503 | sin señal |

Para `requires_followup` el orden es igual (motivo 0,679; duración 0,621; sentimiento 0,576).

Conclusión: la señal pre-llamada es solo el motivo de contacto, con 6 categorías. Un GBM no supera a una tabla de tasas por motivo.

### 4.5 Encuestas, espera y abandono

- **Encuestas, `main_score <= 3` sobre todas las encuestas: AUC 0,959. Resultado no válido.** Mezcla tres escalas distintas (CSAT, NPS, CES) y conserva columnas derivadas del puntaje. Se rehízo restringido a CSAT (ver 4.7).
- Duplicados naturales: **cero pares** (mismo cliente, comercio y monto, en un día) en junio de 2025. El caso "cargo duplicado" solo existiría si lo inyectamos.

### 4.6 Textos

Según `spec/DATA_FINDINGS.md`: las descripciones y resoluciones de reclamos son 5 frases plantilla (una por categoría); las transcripciones son plantilla, 95% con la intención `consulta_general`, 100% en español. No sirven para entrenar un clasificador de intención ni para validar portugués.

### 4.7 CSAT, tiempo de espera y abandono de clientes

- **CSAT insatisfecho (`main_score <= 2`, solo encuestas CSAT enlazadas a su interacción, n = 127.856, tasa 0,313).** En CSAT las notas solo toman los valores 1 a 4 (4.422; 35.646; 73.313; 14.475), no 1 a 7. Con todas las variables de la interacción, AUC 0,794, pero casi todo viene de resultados posteriores: `was_resolved` solo da 0,792 y `requires_followup` 0,748 (ambas se conocen después de la llamada: fuga). Con **solo variables previas a la llamada** (tipo de interacción, canal, motivo, espera, país, segmento, score crediticio), AUC **0,653**, y casi todo es el motivo de contacto (0,655). Mismo patrón que en 4.4.
- **Tiempo de espera** (`wait_time_seconds`, promedio 120 s, desviación 59 s) desde tipo, canal, motivo, hora y día: **R² = 0,00**. Ninguna variable lo explica.
- **Abandono** (`Closed` o `Inactive` contra `Active`, tasa 0,119) desde segmento, país, score crediticio, ingreso, número de productos, de reclamos y de llamadas: **AUC 0,503**. Sin señal.

### 4.8 Modelo de mora de CreditGuard (propuesta de crédito, opción D)

`spec/CREDIT_WORKFLOW_PROPOSAL.md` proponía un LightGBM de probabilidad de mora por cliente contra una línea base de score. Se repitió con partición por cliente:

| Prueba | Resultado |
|---|---|
| Por producto (125.317 productos con límite de crédito, mora 14,3%) con todas las variables | AUC 0,504 |
| Por producto, una sola variable (score, utilización, segmento, tasa, estado, tipo) | AUC 0,497 a 0,503 |
| Por cliente (84.970 clientes, mora 19,8%), todas las variables | AUC 0,635 |
| Por cliente, sin el número de productos | AUC 0,519 |
| Por cliente, solo el número de productos | AUC 0,631 |
| Línea base de la propuesta (score menor a 620 o utilización mayor a 80%) | AUC 0,504 |

Mora por cliente según su número de productos: 14,0% (1), 27,1% (2), 37,3% (3), 45,3% (4), 53,6% (5). Coincide con una probabilidad independiente de 14,3% por producto: 1 menos 0,857 elevado a k da 14%, 27%, 37%, 46%, 54%. Es decir, **la señal es un artefacto de agregación**: el modelo cuenta productos. Una tabla de tasas por número de productos lo iguala, así que no es un componente que supere una línea base apropiada. Además queda fuera del workflow A y el reto no autoriza decisiones de crédito en vivo. Se documenta como resultado negativo.

## 5. Fuga y trampas (checklist para cualquier modelo)

1. `is_fraud` y `fraud_score`: nunca como característica ni como componente que "detecte" fraude.
2. Columnas posteriores al hecho: `duration_seconds`, `detected_sentiment`, `sentiment_score`, `was_resolved`, `resolution`, `resolution_date`, `resolution_days`, `status` de reclamos. No usar para predecir el resultado.
3. Mezcla de escalas en encuestas (CSAT, NPS, CES): separar por `survey_type`; en CSAT la nota va de 1 a 4. `was_resolved` y `requires_followup` no pueden predecir la satisfacción (posteriores).
4. Particiones: siempre temporales; los clientes de prueba no deben aparecer en entrenamiento cuando el objetivo es por cliente.
5. `affected_product_id` de reclamos no pertenece al cliente (100%): no sirve para enlazar un reclamo con una transacción o producto.
6. No hay ninguna etiqueta de "transacción disputada": toda evaluación de disputas usa casos generados por el equipo.

## 6. Qué hicieron otros equipos (repositorios públicos, solo como referencia)

Equipos de este mismo hackathon publicaron sus repositorios. Lo siguiente se tomó de los README públicos; no se verificó ni se reutiliza código.

- **Prioridad de la disputa al ingreso** con RandomForest. Reportan macro-F1 0,245 contra 0,166 de la clase mayoritaria, con partición cronológica y 11.543 casos de entrenamiento. Ellos mismos lo llaman "mejora modesta". Declaran que parte de la historia del cliente demo es sintética y que no hay portugués.
- **Calibración isotónica del `fraud_score`**: dicen atrapar 281 de 494 fraudes con 100% de precisión, 37% mejor que el umbral fijo del banco. Es el artefacto de la sección 4.2.
- Otro equipo menciona un "estudio de validez de etiquetas" y una capa de decisión calibrada con política determinista, sin detalle visible.
- Común a todos: casos de evaluación sintéticos o mixtos, ningún portugués en los datos, motor de política determinista, salida del LLM tipada.

## 7. Componentes propuestos

Principio: elegir componentes que tengan **etiquetas válidas por construcción** (las escribimos o las derivamos de registros reales con ruido controlado), y comparar siempre contra una línea base simple en el mismo set retenido.

### A. Intención e idioma de la consulta (es/pt), con confianza y abstención

- Entrada: mensaje del cliente. Salida: intención (cargo no reconocido, cobro de una transacción rechazada o revertida, duplicado, monto incorrecto, consulta de estado, fuera de alcance), idioma (es, pt, otro), ambigüedad, urgencia, y si hay intento de manipulación del agente.
- Candidatos: (1) palabras clave y reglas con detección de idioma por diccionario (línea base); (2) clasificador local sobre embeddings multilingües; (3) Jev de TypeSafe; (4) LLM con salida estructurada.
- Valor: es la entrada de la política del guardrail; el reto exige español y portugués; permite medir calibración y abstención.
- Riesgo: es una tarea fácil. El valor está en el **set difícil**: mensajes ambiguos, español y portugués mezclados, fuera de alcance, inyección de instrucciones, datos faltantes, errores de escritura.

### B. Identificar la transacción disputada desde una descripción libre

- Entrada: texto ("me cobraron unos 500 pesos en tal comercio la semana pasada") más las transacciones del cliente. Salida: ranking de candidatas.
- Etiquetas: se toma una transacción real, se genera la descripción con ruido (monto aproximado, nombre mal escrito, fecha vaga) y se verifica la recuperación. Válidas por construcción; rotuladas como "generadas por el equipo".
- Línea base: coincidencia exacta o por reglas (comercio, monto exacto). Modelo: similitud de texto del comercio más un ranker (GBM) con cercanía de monto, de fecha, estado y comercio.
- Métrica: acierto en el primer lugar y en los tres primeros, sobre clientes retenidos.
- Referencia en la literatura de disputas: suma ponderada de descriptores coincidentes (comercio, monto, fecha, moneda) sobre un umbral.

### C. Prioridad de escalamiento calibrada por motivo de contacto

- Entrenada sobre las 686 mil llamadas, partición temporal, característica pre-llamada: motivo de contacto. Mide Brier score contra la tasa global.
- Modesta y explicable; sirve como señal secundaria del handoff, nunca como decisión.

### Descartado con evidencia (para las diapositivas)

Modelo de mora de CreditGuard (sección 4.8): AUC 0,504 por producto; el 0,635 por cliente es solo el conteo de productos.

Fraude, incumplimiento de SLA, reclamos reincidentes, demora de resolución, escalamiento de llamadas, tiempo de espera, abandono: AUC 0,49 a 0,50 (R² 0,00 en espera). `fraud_score`: fuga por construcción. Duplicados: no existen de forma natural. Decirlo con los números es parte del puntaje de rigor.

## 8. Jev (TypeSafe)

Referencias: [intent routing](https://docs.typesafe.ai/patterns/intent-routing), [use-case map](https://docs.typesafe.ai/concepts/use-case-map), [modelos](https://docs.typesafe.ai/models.md), [limitaciones de Jev 1.13](https://docs.typesafe.ai/model-jaggedness/jev-1.13.md), [inicio rápido](https://docs.typesafe.ai/introduction/quickstart.md).

- Qué es: clasificador hospedado (Jev 1.13). SDK de Python `pip install typesafe-sdk`; clave de API en variable `TYPESAFE_API_KEY` (consola `console.typesafe.ai/keys`).
- Uso: `client.system_one(state=<texto>, questions={...})` con preguntas `Choice` (una opción entre varias), `Score` (nivel en una escala) y `Noul` (probabilidad de sí o no). Evalúa todas en paralelo en una llamada. Cada respuesta trae confianza y probabilidades; el patrón recomendado es "el código decide": si la confianza es menor a un umbral, escalar a un humano.
- Costo y límites: 42 USD por mil millones de tokens de entrada, salida sin costo; 40 solicitudes por segundo, 100.000 tokens por segundo, contexto de 64.000 tokens. Latencia declarada alrededor de 150 ms.
- Privacidad: declaran que no entrenan con los datos de los clientes; retención cero para clientes empresariales.
- Limitaciones declaradas: el inglés rinde mejor y los otros idiomas "se manejan, pero no igual de bien" (recomiendan probar con contenido propio); **no es robusto frente a prompt injection**; no es confiable con números, fechas ni comparaciones; mal con tareas de razonamiento de varios pasos; las probabilidades de `Choice` y `Noul` no son directamente comparables; el contexto irrelevante grande degrada la precisión.
- Implicaciones: la defensa contra inyección debe ser otra capa determinista; montos y fechas los resuelve el código; el sistema debe seguir funcionando sin la clave (alternativa local, reintentos acotados, respaldo seguro); a un servicio externo solo se envían mensajes de clientes simulados, nunca registros de la base.
- Decisión: no por opinión sino por medición, comparando con las alternativas locales sobre el mismo set retenido y por idioma.

## 9. Diseño de la evaluación (propuesta)

1. **Set retenido** generado por el equipo, rotulado "generado por el equipo": casos normales, ambiguos, escalamiento, fuera de alcance, inyección, sesión expirada, datos faltantes, en español y portugués, con la misma carga para línea base y sistema. Reportar cantidad y mezcla de casos y calidad de etiquetas (doble revisión de una muestra).
2. **Métricas de componente (A):** precisión y macro-F1 por intención e idioma; recall en fuera de alcance y en inyección; falsos "resolver"; calibración (confianza contra acierto, ECE); latencia y costo p50 y p95.
3. **Métricas de componente (B):** acierto en el primer y tercer lugar; por tipo de ruido; por moneda.
4. **Métricas de sistema (las del reto):** resolución automática segura, contención, calidad del escalamiento, resultados inseguros, latencia y costo.
5. **Reproducibilidad:** fijar versiones de modelo y de prompt, repetir corridas para medir variabilidad, y reportar los fallos.
6. **Validez:** si un LLM actúa de juez, validarlo contra etiquetas humanas en una muestra.

## 10. Reproducir las mediciones

Scripts en `ml/probes/` (leen la conexión de variables de entorno `DBT_PG_*`; no contienen credenciales; solo lectura contra `silver.*`):

```bash
python -m venv .venv && .venv/bin/pip install scikit-learn pandas numpy psycopg2-binary
export $(cat data/dbt/.env | xargs)   # DBT_PG_HOST, DBT_PG_PORT, DBT_PG_USER, DBT_PG_PASSWORD, DBT_PG_DATABASE
```

Los scripts esperan un archivo con líneas `export CLAVE=valor` indicado en la variable `ENVF` (por ejemplo `ENVF=data/dbt/.env`).

| Script | Qué mide |
|---|---|
| `fraud_probe.py` | sección 4.1: fraude con GBM y partición temporal |
| `target_scan.py` | secciones 4.3, 4.4 y 4.5: objetivos de reclamos, llamadas y encuestas |
| `cc_drivers.py` | sección 4.4: variables que explican `was_resolved` y `requires_followup` |
| `more_probes.py` | sección 4.7: CSAT (umbral 2), espera y abandono |
| `credit_probe.py` | sección 4.8: modelo de mora de CreditGuard por producto y por cliente |

Las cifras de `fraud_score` (sección 4.2) salen de consultas SQL directas sobre `silver.stg_transactions` (umbral 30, conteos por etiqueta).

## 11. Preguntas abiertas para el ML engineer

1. ¿Se acepta que el componente aprendido sea preentrenado (Jev, embeddings o LLM) y que el trabajo de ML sea la selección, el set de evaluación y la calibración? El reto lo permite expresamente.
2. ¿Qué tan grande y cómo se construye el set retenido (tamaño mínimo por intención e idioma, doble etiquetado, casos adversos)?
3. ¿Se evalúa el componente B (identificar la transacción) o se deja solo A y C por tiempo?
4. ¿Qué umbral de confianza y qué costo asimétrico (falso "resolver" contra falso "escalar") usamos para la abstención?
5. ¿Se publica el set retenido en el repo (es generado por el equipo, sin datos reales) para que el evaluador reproduzca?
6. ¿Se mantiene la decisión de no usar `fraud_score` (recomendado), o el equipo prefiere mostrar la comparación y explicar la fuga en las diapositivas?
