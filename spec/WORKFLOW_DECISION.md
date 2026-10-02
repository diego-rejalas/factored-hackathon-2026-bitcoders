# Decisión de workflow — Opción A confirmada

Consolida el estado de la elección de workflow después de perfilar las 13 tablas
completas (no solo la muestra inicial). Ver `DATA_FINDINGS.md` para el detalle
de calidad de datos y `spec/evidence/` para la auditoría estática de Codex.

**Estado: confirmada por el equipo (2026-09-30).** Se implementó el slice
vertical completo en `feat/app-layer` (`backend/` + `agent/` + `frontend/`).
La decisión de producto sobre el umbral de escalamiento quedó en **$500 USD
efectivo** (`GUARDRAIL_MAX_USD`), y el alcance del guardrail es el que se
detalla abajo. La evaluación con casos held-out queda para un branch posterior.

## Las 4 opciones originales (para votar)

| # | Workflow | Problema | Riesgo/nota |
|---|---|---|---|
| **A** | Disputas de transacciones | Cliente reporta cargo no reconocido o transacción fallida/duplicada | Recomendada — ver evidencia abajo |
| **B** | Soporte de tarjetas | Bloqueo/reposición de tarjeta, cargos no reconocidos, aumento de límite | Se solapa con A (cargos no reconocidos) sin aportar profundidad extra; casi todo termina en "confirmar y ejecutar" o "escalar" |
| **C** | Cuentas/pagos | Consulta de saldo, estado de transferencia, historial de movimientos | Mayormente lectura, bajo riesgo — menos diferenciada, poco espacio para mostrar ambigüedad real o decisiones de riesgo |
| **D** | Info/elegibilidad de crédito | Cliente pregunta si califica para un producto de crédito | El reto exige separar conversación/riesgo/política — bien implementado demuestra rigor, pero mayor carga de diseño (política de elegibilidad sintética a inventar) con solo días de plazo |

## Recomendación: Opción A — Disputas de transacciones

Reforzada, no solo elegida por descarte. Con las 13 tablas cargadas a escala
completa, ninguna combinación nueva (digital_events, satisfaction_surveys,
call_transcripts, campaign_sends, branches, service_agents,
daily_exchange_rates, marketing_campaigns) aportó señal cruzada real para un
workflow alternativo o híbrido — ver "Hipótesis descartadas" abajo. Opción A
sigue siendo la más fuerte: profundidad de NLP + reglas deterministas +
volumen de datos suficiente para evaluación con baseline.

### Los 3 casos obligatorios del reto (actualizados con datos reales)

1. **Caso normal (auto-resuelto)** — **redefinido**: transacción con
   `transaction_status` en `Declined`/`Reversed` que el cliente reporta como
   cobrada. 266k transacciones candidatas (Declined 5.0% + Reversed 1.0% de
   4.425.008). La hipótesis original ("duplicado exacto: mismo monto/comercio/
   ±1 día") se descartó — **0 duplicados exactos encontrados** en toda la tabla.
2. **Caso ambiguo**: cliente no recuerda el monto exacto, o hay más de una
   transacción candidata → el agente pide aclaración antes de actuar, no
   asume.
3. **Caso escalamiento a humano**: sospecha de fraude, disputa por encima de
   un monto umbral, o ambigüedad no resuelta tras aclaración → handoff con
   transcript resumido + evidencia de transacciones + intento de resolución
   documentado (auditable, no chain-of-thought oculto).

### Guardrails que ya sabemos que hacen falta (de auditorías previas)

- `complaints.affected_product_id` apunta a un producto de **otro** cliente en
  el 100% de los casos (44.570/44.570, confirmado a escala completa) — nunca
  usarlo para mostrar, inferir ni autorizar información de producto.
- `transactions↔products`: ownership 100% consistente (4.425.008/4.425.008) —
  sí es una relación confiable para autorizar acceso a movimientos propios.
- `is_fraud`/`fraud_score` nunca son input del agente ni de sus tools (ya
  excluidos de `gold.transactions`).
- Identidad del cliente siempre viene de una sesión de prueba confiable, nunca
  de un `customer_id` que el chat proponga.
- Sin MXN en ninguna transacción (0/4.425.008) pese a ~50% clientes
  mexicanos — bug de dataset, se documenta, no se inventa conversión.
- Portugués: no existe en los datos históricos (`call_transcripts` 100% en
  español). El soporte pt es responsabilidad de la capa del agente
  (traducción de intención), no algo que el dataset ya cubra — 10.75% de
  `service_agents` habla pt, útil para el handoff a humano en pt.

## Hipótesis de workflow alternativo — descartadas con evidencia

Investigadas para ver si alguna de las 8 tablas sin modelar sugería un 5to
workflow o reforzaba B/C/D por sobre A. Las 3 cadenas causales probadas dieron
ruido estadístico, no señal:

| Hipótesis | Resultado |
|---|---|
| `digital_events` (Error) → `call_center_interactions` mismo día/día siguiente | 0% / 0% / 2.2% en 3 días muestreados — sin correlación |
| `satisfaction_surveys.main_score` vs `was_escalated` | 3.526 vs 3.527 promedio sobre 212.759 filas — cero diferencia |
| `campaign_sends` → `complaints` dentro de 2 días | 0% / 0.23% sobre 1.746.801 envíos — marketing irrelevante para soporte |

Otros hallazgos que no cambian la decisión pero quedan documentados:

- `call_transcripts.detected_intents`: 95% "consulta_general" — sin taxonomía
  de intención más rica que `complaints.category`.
- `daily_exchange_rates`: tiene pares con MXN, pero sin transacciones/productos
  en MXN no tiene con qué unirse — decorativa.
- `branches`: 100% "Urbana" (350/350) — sin señal geográfica real.
- `call_center_interactions`: FCR 76.6%, escalación 10.0% — buen baseline
  descriptivo para el reporte de evaluación final (containment/escalation),
  independiente del workflow elegido.

## Estado de la capa gold (dbt)

Solo 5 de 13 tablas bronze tienen modelo (`gold.customers`, `gold.products`,
`gold.transactions`, `gold.complaints`, `gold.call_center_interactions`) —
intencional, no pendiente: ninguna de las 8 restantes aportó señal útil para
ningún workflow candidato, y el reto premia profundidad sobre cobertura.

Los 5 modelos gold actuales son **pass-through puro** de silver (`select *`,
sin joins) — se vuelven el modelo real de negocio (join disputas +
transacciones + verificación de titularidad) recién cuando se confirme
Opción A.

## Decisiones registradas (2026-09-30)

1. **Opción A confirmada** — disputas de transacciones.
2. **Umbral de escalamiento: $500 USD efectivo** — decisión de producto (no hay
   dato que lo sugiera solo). Vive en `GUARDRAIL_MAX_USD` (env del servicio
   `agent`), nunca hardcodeada en el prompt.
3. **Alcance del guardrail (implementado en `agent/app/guardrail.py`):**
   auto-resuelve SOLO una transacción `Declined`/`Reversed` del propio cliente,
   única candidata sin ambigüedad y con monto efectivo < $500; aclara (máx 2
   rondas) con 0 o >1 candidatas; escala SIEMPRE fraude/robo/"no fui yo"
   (es/pt), montos ≥ umbral, ambigüedad no resuelta e intents fuera de
   alcance. Sin mover dinero.
4. **Implementado:** `backend/` (tool layer con enforcement de titularidad),
   `agent/` (LangGraph + guardrail + TypeSafe opcional, ver los README de cada
   carpeta). Los joins de negocio (disputas + transacciones) viven en las
   queries del backend sobre las 5 gold actuales; los modelos gold siguen
   pass-through — modelarlos queda para el branch de evaluación.
