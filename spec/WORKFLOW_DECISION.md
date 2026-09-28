# Decisión de workflow — pendiente de voto del equipo

Consolida el estado de la elección de workflow después de perfilar las 13 tablas
completas (no solo la muestra inicial). Ver `DATA_FINDINGS.md` para el detalle
de calidad de datos y `spec/evidence/` para la auditoría estática de Codex.
Este documento es la base para que el equipo vote y quede registrada la
justificación.

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

## Pendiente de decidir por el equipo

1. **Confirmar Opción A** (o votar en contra con justificación — la evidencia
   de arriba respalda A, pero la decisión final es del equipo).
2. **Monto umbral** para forzar escalamiento por disputa (no hay dato que lo
   sugiera solo, es una decisión de producto).
3. **Alcance del guardrail determinista**: qué intents puede resolver el
   agente sin humano (Declined/Reversed simple) vs cuáles siempre escalan
   (fraude, montos altos, ambigüedad no resuelta).
4. Una vez confirmado: escribir los modelos gold reales para disputas,
   arrancar `backend/` (tool layer) y `agent/` (LangGraph + guardrail +
   TypeSafe, ver `ARCHITECTURE.md`).
