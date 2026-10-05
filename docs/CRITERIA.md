# Criterios del reto (Factored AI & Data Hackathon 2026)

[Índice](README.md) · [Workflow](WORKFLOW.md) · [Arquitectura](ARCHITECTURE.md) · [Datos](DATA.md) · [API](API.md)

Lo que el reto exige, extraído de `docs/challenge/Factored AI & Data Hackathon 2026.md` y `docs/challenge/Datathon_2026_Kickoff.pdf`, y en qué estado está cada ítem. Cada ítem cumplido dice dónde está la evidencia. **Se actualizó el 2026-10-04 contra el código y los documentos de esta carpeta.**

## De un vistazo

| Sección | Cumplidos | Abiertos |
|---|---:|---:|
| Alcance obligatorio | 6 | 0 |
| Sistema funcional (requisitos mínimos) | 5 | 0 |
| Automatización controlada | 4 | 0 |
| Datos y ML | 4 | 0 |
| Medición de calidad y manejo de fallas | 3 | 0 |
| Ruta a producción (honestidad, no implementación real) | 4 | 0 |
| Fronteras de datos y ejecución | 6 | 1 |
| Entrega (submission, antes de Oct 5) | 0 | 6 |
| **Total** | **32** | **7** |

Lo abierto, en orden de impacto: el **despliegue** de esta versión y la **entrega** (repositorio público, diapositivas, video y envío). La evaluación está en [Evaluación](EVALUATION.md) y la ruta a producción en [Ruta a producción](PRODUCTION.md).

## Alcance obligatorio

- [x] Un solo workflow bancario coherente (cuentas/pagos, tarjetas, disputas, o crédito). Implementar más de uno NO da bonus. (Disputas de transacciones, `WORKFLOW.md`; no hay un segundo workflow.)
- [x] Caso normal resuelto de forma automática (safe automated resolution). (Declined o Reversed bajo USD 500: Bruno y Carla en `infra/gcp/scripts/e2e.py`, 11 de 11 contra el stack local.)
- [x] Caso ambiguo o no soportado → el sistema pide aclaración o se abstiene explícitamente. (Varias candidatas: pide aclaración y ofrece elegir; sin candidatas o fuera de alcance: escala. Cubierto en `agent/tests/test_graph.py` y en e2e.)
- [x] Caso que requiere intervención humana → handoff estructurado. (Cobro aprobado, fraude, monto sobre el umbral, monto desconocido: `handoff` con solicitud, hechos, acciones, evidencia y preguntas abiertas.)
- [x] Interacción demostrada en **español y portugués**. (e2e incluye un caso en portugués; la detección de idioma y las respuestas fijas están en es y pt. Falta medir por idioma en la evaluación.)
- [x] Reportar limitaciones de datos o cobertura de idioma encontradas. (`DATA.md`, `WORKFLOW.md`: sin MXN en transacciones, sin portugués en histórico, `complaints.affected_product_id` inconsistente, sin duplicados exactos)

## Sistema funcional (requisitos mínimos)

- [x] Mantiene contexto conversacional. (Memoria de LangGraph por conversación y cliente. Límite: está en memoria del proceso, se pierde al reiniciar; el historial que ve el cliente sí se guarda en `agent.conversation_messages`.)
- [x] Aclara ambigüedad (no asume). (`clarify` con candidatas; nunca elige una por su cuenta.)
- [x] Responde con información fundamentada en datos permitidos (cuenta, transacción, política) — no alucina hechos. (Las respuestas salen de hechos verificados; el modelo solo redacta un caso resuelto y su borrador pasa por `agent/app/grounding.py`.)
- [x] Usa herramientas (tools) cuando el workflow lo requiere. (El agente solo accede a datos por el backend HTTP, nunca a Postgres.)
- [x] Reporta solo acciones cuyo resultado el sistema verificó (no confía en lo que "dice" el LLM que pasó). (Nodo `verify`: relee el caso del backend antes de decir que se registró; si falla, escala.)

## Automatización controlada

- [x] Define explícitamente qué puede responder solo, qué requiere confirmación, y cuándo debe abstenerse o transferir a humano. (`docs/WORKFLOW.md`, tabla de autonomía.)
- [x] Permisos y políticas se hacen cumplir **fuera** del texto generado por el modelo (código determinista, no el prompt). (Guardrail determinista en `agent/app/guardrail.py`; titularidad en el backend; el modelo no decide la política.)
- [x] El handoff a humano entrega: la solicitud, hechos verificados, acciones tomadas, evidencia de soporte, preguntas sin resolver — no un dump crudo de transcript. (Estructura en [Workflow](WORKFLOW.md); la consola `/admin` la muestra.)
- [x] **No aplica:** el workflow es disputas y no toca crédito. Si el workflow tocara crédito: separar conversación / riesgo predictivo / política de elegibilidad. El modelo conversacional NUNCA inventa reglas de elegibilidad ni aprueba crédito por su cuenta.

## Datos y ML

- [x] Pipeline de datos repetible: contratos de esquema, checks de calidad, linaje, política de actualización/frescura. (DAG de Airflow con DuckDB: reconstruye bronze desde S3 en cada corrida; los tests de dbt (claves, relaciones, valores aceptados, rangos y reglas de negocio) y, si falla uno de silver, no se publica `gold`; linaje por fila en `_source_key`; política de frescura explícita en [Arquitectura](ARCHITECTURE.md) (snapshot estático, recarga a demanda). Falta endurecer los contratos de `gold` a tipados con `contract: enforced`)
- [x] Al menos un componente aprendido evaluado contra un baseline apropiado. (Clasificación de intención: modelo contra palabras clave, 228 casos ciegos y 40 adversariales, con intervalos y prueba pareada. [Evaluación](EVALUATION.md#1-el-componente-clasificación-de-intención).) (Además, `ml/eval/`: clasificador de intención e idioma con confianza contra las palabras clave, y ranker de la transacción disputada (suma ponderada y GBM) contra `narrow_candidates`, con informes y fallos en `ml/eval/reports/`; resumen en [Componentes de ML](ML_FINDINGS.md), sección 12.)
- [x] Labels o juicios de relevancia válidos, sin leakage (ej. no usar `is_fraud` como input si se supone que el sistema lo "detecta"). (Etiquetas por construcción o por un oráculo de la política escrito aparte; `is_fraud` no existe en los casos; los conjuntos se leyeron uno por uno y se depuraron (lo hizo el autor de la evaluación, no un tercero). [Evaluación](EVALUATION.md#cómo-se-evaluó).) (En `ml/eval/`: los generadores quitan `is_fraud` y `fraud_score` y lo verifican; el ranker no usa columnas posteriores al resultado; `fraud_score` se descartó por fuga, [Componentes de ML](ML_FINDINGS.md) sección 4.2.)
- [x] Justificar representaciones, métricas, umbrales, y splits de evaluación. (No hay entrenamiento, así que no hay partición de entrenamiento y prueba: los conjuntos se escribieron antes de ejecutar y lo ajustado después se validó con un conjunto nuevo. [Evaluación](EVALUATION.md#cómo-se-evaluó).) (En `ml/eval/`: pesos a priori e interpretables, abstención con umbral calibrable en dev (`INTENT_MIN_CONFIDENCE`, costo asimétrico 5 a 1) y particiones estratificadas por celda (intención) y por cliente (ranker).)

## Medición de calidad y manejo de fallas

- [x] Evaluación sobre casos held-out. (549 casos de punta a punta contra el backend y la base reales, con y sin modelo. Son casos generados por el equipo.) (También `ml/eval/`: conjuntos dev y test con umbrales congelados en dev.)
- [x] Incluir: datos incorrectos/faltantes, sesiones expiradas, intentos de acceso no autorizado, prompt injection, fallos de herramientas, ambigüedad multilingüe. (Datos inexistentes 24, sesión vencida 6, datos ajenos 20, inyección 12, fallo del backend 12 y aclaración en es y pt 31: [Evaluación](EVALUATION.md#2-el-sistema-completo-de-punta-a-punta).)
- [x] Reportar: resultados exitosos, resultados inseguros, comportamiento de handoff, latencia, costo — con tamaños de muestra y limitaciones explícitas. (Con tamaños de muestra, intervalos y límites explícitos. La corrida completa se repitió con el modelo después de las correcciones; lo que no es independiente está dicho en los límites.)

## Métricas a reportar (definiciones exactas del reto)

- **Safe automated resolution:** % de casos en-alcance que llegan a resolución correcta y conforme a política SIN intervención humana. Reportar también qué % de casos se intentó automatizar.
- **Containment:** % de casos que terminan sin transferencia (esto solo NO prueba que el problema se resolvió — reportarlo junto con resolución real).
- **Escalation quality:** transferencias correctas + contexto útil en el handoff. Reportar transferencias perdidas (missed) e innecesarias donde haya labels de referencia.
- **Unsafe outcomes:** divulgaciones/acciones no autorizadas o resultados materialmente incorrectos — con conteos y denominadores. Cero fallos en muestra chica NO significa cero riesgo (decirlo explícitamente).
- **Operating efficiency:** latencia p50/p95 y costo por caso intentado y por caso resuelto exitosamente, end-to-end. Si no hay resoluciones exitosas, usar "not defined", no inventar un número.
- Comparar resultados por idioma y segmento de cliente autorizado; señalar limitaciones de muestra chica.
- Separar claramente: medición offline, simulación, y proyección de ahorro de negocio — nunca presentar una comparación offline como "mejora medida en producción".

## Ruta a producción (honestidad, no implementación real)

- [x] Tracing / trazabilidad de cada decisión (evidencia de auditoría = fuentes + reglas de política + registros de ejecución; el chain-of-thought oculto del modelo NO cuenta como evidencia). (`agent.trace_log` por paso, sin texto de usuario ni razonamiento del modelo; el caso guarda sus eventos y evidencia.)
- [x] Reintentos acotados (bounded retries) y fallback seguro. (Pipeline: las cargas reintentan 2 veces y `gold` conserva el último dato válido. Agente: 3 intentos con tiempo de conexión de 2 s y peor caso de 6.9 s; si el backend no responde, `outcome: unavailable` con un mensaje seguro y sin cambios.)
- [x] Setup reproducible. (Todo como código: Terraform en `infra/gcp/`, Dockerfiles, CI que construye las imágenes y corre las pruebas; los pasos están en `infra/gcp/README.md`.)
- [x] Explicar límites de capacidad, monitoreo, controles de acceso, retención de datos, y qué falta para producción real. ([Ruta a producción](PRODUCTION.md): cada sección separa lo que existe de lo que falta. No hay política de retención aplicada y no se hizo una prueba de carga; ambas cosas están dichas ahí.)

## Libertad de arquitectura (lo que NO es obligatorio)

- No hace falta entrenar un modelo nuevo.
- No hace falta multi-agente.
- No hace falta un número mínimo de tools.
- No hace falta streaming.
- No hace falta forecasting de demanda.
- No hace falta dashboard.
- (Pero si se usa un modelo pre-entrenado o retrieval, hay que demostrar el mismo rigor igual: selección de componentes, labels de intención/relevancia, representaciones, prevención de leakage, evaluación held-out, análisis de errores.)

## Fronteras de datos y ejecución

- [x] Solo el dataset organizador-aprobado (LATAM Bank sintético) y recursos externos permitidos.
- [x] Identificar qué inputs son reales, de-identificados, sintéticos, o generados por el equipo. (`DATA.md`, "Procedencia de los datos": todo es sintético del organizador; lo que genere el equipo se rotulará aparte)
- [x] No incluir registros privados reales, credenciales, o datos restringidos en la entrega pública ni en requests a modelos externos. (Un PDF con llaves de AWS se sacó del repo y de la historia. El 2026-10-04 se buscaron en los 130 commits los patrones de credenciales (AWS, OpenRouter, GitHub, llaves privadas) y los valores reales del `.env` local: 0 coincidencias. Los `.env` no están versionados. Conviene repetir la búsqueda justo antes de hacer público el repositorio.)
- [x] Servicios sandbox / tools de banca simulados son aceptables si sus contratos y límites están documentados. (`docs/API.md`; el contrato OpenAPI está versionado y una prueba falla si se desvía.)
- [ ] Autenticación con sesión de prueba confiable o servicio de identidad — un ID/número de cliente solo NO prueba identidad. **Parcial:** hay sesión JWT firmada con vencimiento y rol, y cuentas de demostración con contraseña (argon2id) y bloqueo por intentos; pero el ingreso del chat sigue aceptando cliente + número de documento. Es un sandbox, hay que decirlo así en la entrega y no presentarlo como identidad real.
- [x] Permisos de acceso a registros de cada cliente enforced en la capa de servicio/tool, no en el prompt. (Cada consulta del backend se filtra por el cliente del token; hay pruebas de acceso cruzado en backend y agente.)
- [x] No se requiere ni autoriza mover dinero real ni decisiones de crédito en vivo. (Nada en el sistema mueve dinero; el backend es de solo lectura)

## Entrega (submission, antes de Oct 5)

- [ ] Repo público de GitHub: `factored-hackathon-2026-[nombre del equipo]`. **⚠️ El repo `factored-hackathon-2026-bitcoders` está en privado ahora mismo (decisión deliberada durante desarrollo) — volverlo público antes de entregar, o confirmar con el organizador si aceptan invitación como colaborador en su lugar.**
- [ ] Link donde el tool está desplegado (deploy real, no solo local).
- [ ] Presentación de 4-6 slides con detalles del tool.
- [ ] Video pitch (obligatorio) de **no más de 3 minutos**, demostrando la solución funcionando y explicando decisiones arquitectónicas core. (La página del reto fija el límite en 3 minutos.)
- [ ] Enviar todo a hackathon.admin@factored.ai.
- [ ] "Submit your tool no matter what!!!" — entregar aunque esté incompleto.

## Criterios de evaluación (slide "Evaluation Criteria" y página del reto)

- Ante todo, la solución debe funcionar.
- Racional y documentación general del proyecto.
- **Technical Judgment:** arquitectura, trade-offs, confiabilidad, seguridad y preparación para producción. ([Arquitectura](ARCHITECTURE.md), [Seguridad](SECURITY.md), [Ruta a producción](PRODUCTION.md))
- **AI Engineering:** backend, frontend, integración del sistema y despliegue.
- **Data Engineering:** calidad, pipelines, preparación y reproducibilidad de los datos.
- **Machine Learning:** modelado, evaluación, líneas base y rendimiento. ([Evaluación](EVALUATION.md), [Componentes de ML](ML_FINDINGS.md))
- **Data Analytics:** métricas, insights, visualización y apoyo a la decisión. (Métricas y bandeja de la consola `/admin`, [Datos](DATA.md), `/data-docs`.)

Otras reglas de la página del reto: español y portugués obligatorios, un solo workflow, equipos de **hasta 4 personas**, y cualquier lenguaje, framework, modelo o nube. El período del reto termina el **5 de octubre**; la página no da hora ni zona horaria.

## Datos que condicionan la evaluación

El texto histórico es plantilla y `is_fraud` es verdad de referencia, no entrada: por eso la evaluación del componente aprendido usa texto vivo rotulado por el equipo y los campos estructurados como línea base. El detalle está en [Datos](DATA.md).
