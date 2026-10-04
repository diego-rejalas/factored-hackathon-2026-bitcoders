# Criterios del reto (Factored AI & Data Hackathon 2026)

Extraído de `doc/Factored AI & Data Hackathon 2026.md` y `doc/Datathon_2026_Kickoff.pdf`. Esto es la checklist de lo que el sistema DEBE cumplir, no ideas — para no perderla de vista mientras se investiga y se construye.

## Alcance obligatorio

- [ ] Un solo workflow bancario coherente (cuentas/pagos, tarjetas, disputas, o crédito). Implementar más de uno NO da bonus.
- [ ] Caso normal resuelto de forma automática (safe automated resolution).
- [ ] Caso ambiguo o no soportado → el sistema pide aclaración o se abstiene explícitamente.
- [ ] Caso que requiere intervención humana → handoff estructurado.
- [ ] Interacción demostrada en **español y portugués**.
- [x] Reportar limitaciones de datos o cobertura de idioma encontradas. (`DATA_FINDINGS.md`, `WORKFLOW_DECISION.md`: sin MXN en transacciones, sin portugués en histórico, `complaints.affected_product_id` inconsistente, sin duplicados exactos)

## Sistema funcional (requisitos mínimos)

- [ ] Mantiene contexto conversacional.
- [ ] Aclara ambigüedad (no asume).
- [ ] Responde con información fundamentada en datos permitidos (cuenta, transacción, política) — no alucina hechos.
- [ ] Usa herramientas (tools) cuando el workflow lo requiere.
- [ ] Reporta solo acciones cuyo resultado el sistema verificó (no confía en lo que "dice" el LLM que pasó).

## Automatización controlada

- [ ] Define explícitamente qué puede responder solo, qué requiere confirmación, y cuándo debe abstenerse o transferir a humano.
- [ ] Permisos y políticas se hacen cumplir **fuera** del texto generado por el modelo (código determinista, no el prompt).
- [ ] El handoff a humano entrega: la solicitud, hechos verificados, acciones tomadas, evidencia de soporte, preguntas sin resolver — no un dump crudo de transcript.
- [ ] Si el workflow toca crédito: separar conversación / riesgo predictivo / política de elegibilidad. El modelo conversacional NUNCA inventa reglas de elegibilidad ni aprueba crédito por su cuenta.

## Datos y ML

- [x] Pipeline de datos repetible: contratos de esquema, checks de calidad, linaje, política de actualización/frescura. (DAG de Airflow con DuckDB: reconstruye bronze desde S3 en cada corrida; 121 tests dbt, y si un test de silver falla `gold` no se reconstruye; linaje por fila en `_source_key`; política de frescura explícita en `ARCHITECTURE.md` (snapshot estático, recarga a demanda). Falta endurecer los contratos de `gold` a tipados con `contract: enforced`)
- [x] Al menos un componente aprendido evaluado contra un baseline apropiado. (Componente A: clasificador de intención+idioma con confianza vs baseline de palabras clave, y componente B: ranker de la transacción disputada (weighted + GBM) vs `narrow_candidates`, ambos sobre set retenido generado por el equipo — `ml/eval/`, informes y fallos en `ml/eval/reports/`, resumen en `ML_FINDINGS.md` §12)
- [x] Labels o juicios de relevancia válidos, sin leakage (ej. no usar `is_fraud` como input si se supone que el sistema lo "detecta"). (Etiquetas válidas por construcción: intención escrita desde plantillas rotuladas "generado por el equipo"; disputas con etiqueta = `transaction_id` original. Los generadores eliminan `is_fraud`/`fraud_score` y lo verifican; sin columnas post-resultado en las features del ranker; `fraud_score` descartado por fuga documentada en `ML_FINDINGS.md` §4.2)
- [x] Justificar representaciones, métricas, umbrales, y splits de evaluación. (Suma ponderada interpretable con pesos a priori; abstención de intención con umbral en variable `INTENT_MIN_CONFIDENCE` calibrable en dev con costo asimétrico 5:1; piso de "no encuentra" del ranker calibrado en train; splits estratificados por celda en A y **por cliente** en B — test y train no comparten clientes)

## Medición de calidad y manejo de fallas

- [x] Evaluación sobre casos held-out. (Sets dev/test de `ml/eval/` generados con split estratificado (A) y por cliente disjunto (B); medición final en test con umbrales congelados de dev/train — `ML_FINDINGS.md` §12)
- [x] Incluir: datos incorrectos/faltantes, sesiones expiradas, intentos de acceso no autorizado, prompt injection, fallos de herramientas, ambigüedad multilingüe. (En los sets ML: montos desviados/aproximados, comercio mal escrito o ausente, typos, prompt injection, ambigüedad es/pt/mixta y trampas out_of_scope — `gen_intent_set.py`, `gen_dispute_set.py`. Sesiones expiradas, acceso no autorizado y fallos de herramientas están cubiertos por los tests del agente y del backend, no por estos sets)
- [ ] Reportar: resultados exitosos, resultados inseguros, comportamiento de handoff, latencia, costo — con tamaños de muestra y limitaciones explícitas. (Parcial: accuracy/F1, falsos "dispute" y vacíos falsos con n y denominadores, latencia p50/p95 y tokens están en `ml/eval/reports/`; el harness calcula costo p50/p95 con `usage.cost` o tarifas por millón para un modelo fijado. **Pendiente de medir** el costo LLM con clave/tarifas del equipo y el costo end-to-end del sistema — `ML_FINDINGS.md` §12)

## Métricas a reportar (definiciones exactas del reto)

- **Safe automated resolution:** % de casos en-alcance que llegan a resolución correcta y conforme a política SIN intervención humana. Reportar también qué % de casos se intentó automatizar.
- **Containment:** % de casos que terminan sin transferencia (esto solo NO prueba que el problema se resolvió — reportarlo junto con resolución real).
- **Escalation quality:** transferencias correctas + contexto útil en el handoff. Reportar transferencias perdidas (missed) e innecesarias donde haya labels de referencia.
- **Unsafe outcomes:** divulgaciones/acciones no autorizadas o resultados materialmente incorrectos — con conteos y denominadores. Cero fallos en muestra chica NO significa cero riesgo (decirlo explícitamente).
- **Operating efficiency:** latencia p50/p95 y costo por caso intentado y por caso resuelto exitosamente, end-to-end. Si no hay resoluciones exitosas, usar "not defined", no inventar un número.
- Comparar resultados por idioma y segmento de cliente autorizado; señalar limitaciones de muestra chica.
- Separar claramente: medición offline, simulación, y proyección de ahorro de negocio — nunca presentar una comparación offline como "mejora medida en producción".

## Ruta a producción (honestidad, no implementación real)

- [ ] Tracing / trazabilidad de cada decisión (evidencia de auditoría = fuentes + reglas de política + registros de ejecución; el chain-of-thought oculto del modelo NO cuenta como evidencia).
- [ ] Reintentos acotados (bounded retries) y fallback seguro. (Pipeline: hecho, las cargas reintentan 2 veces y `gold` conserva el último dato válido si algo falla. Falta lo mismo en el agente: reintentos acotados de herramientas y abstención/escalamiento ante un fallo)
- [x] Setup reproducible. (Todo como código: `.railway/railway.ts`, Dockerfiles, CI que construye las imágenes y corre `dbt parse`; pasos en `spec/AIRFLOW_DEPLOYMENT.md`. El agente se suma a la misma IaC)
- [ ] Explicar límites de capacidad, monitoreo, controles de acceso, retención de datos, y qué falta para producción real. (Capacidad y camino de escalamiento: `ARCHITECTURE.md`; monitoreo del pipeline: Airflow + `ops.etl_runs`; control de acceso: rol de solo lectura del backend. Faltan la política de retención y el resto cuando exista el agente)

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
- [x] Identificar qué inputs son reales, de-identificados, sintéticos, o generados por el equipo. (`DATA_FINDINGS.md`, "Procedencia de los datos": todo es sintético del organizador; lo que genere el equipo se rotulará aparte)
- [x] No incluir registros privados reales, credenciales, o datos restringidos en la entrega pública ni en requests a modelos externos. (PDF con AWS keys sacado del repo y de la historia de git — ver commits de purge)
- [ ] Servicios sandbox / tools de banca simulados son aceptables si sus contratos y límites están documentados.
- [ ] Autenticación con sesión de prueba confiable o servicio de identidad — un ID/número de cliente solo NO prueba identidad.
- [ ] Permisos de acceso a registros de cada cliente enforced en la capa de servicio/tool, no en el prompt.
- [x] No se requiere ni autoriza mover dinero real ni decisiones de crédito en vivo. (Nada en el sistema mueve dinero; el backend es de solo lectura)

## Entrega (submission, antes de Oct 5)

- [ ] Repo público de GitHub: `factored-hackathon-2026-[nombre del equipo]`. **⚠️ El repo `factored-hackathon-2026-bitcoders` está en privado ahora mismo (decisión deliberada durante desarrollo) — volverlo público antes de entregar, o confirmar con el organizador si aceptan invitación como colaborador en su lugar.**
- [ ] Link donde el tool está desplegado (deploy real, no solo local).
- [ ] Presentación de 4-6 slides con detalles del tool.
- [ ] Video pitch corto (obligatorio) demostrando la solución funcionando y explicando decisiones arquitectónicas core.
- [ ] Enviar todo a hackathon.admin@factored.ai.
- [ ] "Submit your tool no matter what!!!" — entregar aunque esté incompleto.

## Criterios de evaluación (slide "Evaluation Criteria")

- Ante todo, la solución debe funcionar.
- Racional y documentación general del proyecto.
- **AI Engineering:** backend, frontend, deployment.
- **Data Engineering:** cómo se maneja extracción y transformación de datos.
- **Data Analytics:** calidad de datos, insights relevantes que la solución entrega.
- **Machine Learning:** selección de modelo, optimización, implementación, tracking.

## Hallazgos de investigación que afectan estos criterios (ver también el plan principal)

- `call_transcripts.customer_text` y `detected_intents` son mayormente plantillas repetidas (32 variantes únicas en 151 filas de un día, 141/151 con la misma intención "consulta_general"). El texto libre histórico NO tiene la riqueza necesaria para entrenar/evaluar un clasificador de intención serio directamente sobre esos campos.
- Implicación para "Machine Learning" y "Data Analytics" (criterios de evaluación arriba): si se documenta esta limitación de calidad de datos como hallazgo (Data Analytics) y se compensa con un enfoque híbrido, cuenta a favor — el reto pide explícitamente reportar limitaciones de datos.
- Enfoque a considerar: usar un LLM/clasificador para el **input conversacional en vivo del usuario** (que sí será texto real generado en la demo, no el histórico plantilla), y usar los campos estructurados (`category`, `subcategory`, `transaction_type`) del histórico como baseline determinista y como fuente de datos de entrenamiento/evaluación para el componente aprendido — no el texto plantilla de `call_transcripts`/`complaints.description`.
- `transactions`: 0 duplicados exactos de `transaction_id` y 0 grupos cliente+monto+comercio repetidos en una muestra de 5,342 filas de un día — la regla de "duplicado auto-resolvible" para Opción A necesita más muestreo (varios días) antes de asumir que existe suficiente volumen de este caso.
- `is_fraud`/`fraud_score` en `transactions` es ground truth sintético — usarlo como señal de entrada al agente sería leakage; solo debe usarse para evaluación.
