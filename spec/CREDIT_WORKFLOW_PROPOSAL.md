# Propuesta de Workflow: CreditGuard AI
## Asistente Bancario de Elegibilidad, Evaluación y Salud Crediticia con Gobernanza Tripartita

**Estado:** Propuesta de diseño para revisión y voto del equipo  
**Fecha:** 2026-09-28  
**Autor:** Antigravity (Pair Programming Assistant)  
**Relación con otros specs:** Complementa `spec/ARCHITECTURE.md`, contrasta con `spec/WORKFLOW_DECISION.md` y se fundamenta en `spec/DATA_FINDINGS.md` y `spec/CRITERIA.md`.

---

## 1. Resumen Ejecutivo (BLUF)

Se propone seleccionar como workflow definitivo del hackathon **CreditGuard AI: Información, Elegibilidad y Gestión de Salud Crediticia (Préstamos Personales y Aumento de Línea de Tarjeta)**. 

Frente a la alternativa de disputas de transacciones (Opción A, debilitada tras confirmar cero duplicados reales y texto de quejas plantilla), el vertical de créditos ofrece una base empírica inmensamente más rica en el dataset real: **400.000 productos financieros** con balances, límites y moras cuantitativas, junto a **150.000 clientes** con variables sociodemográficas y de solvencia. 

Esta propuesta implementa con máxima fidelidad la **cláusula mandatoria de gobernanza crediticia** del hackathon:
> *"For credit-related workflows, separate conversation handling, predictive risk estimates, and eligibility policy. The conversational model must not invent eligibility rules or independently approve credit."*

La arquitectura garantiza una separación física y lógica entre el Agente Conversacional (LangGraph), el Motor de Scoring Predictivo (Machine Learning) y el Motor Determinista de Políticas (Backend Tool Layer).

---

## 2. Alineación con las Bases Oficiales del Hackathon

La solución aborda directamente las exigencias documentadas en `doc/Factored AI & Data Hackathon 2026.md` y `spec/CRITERIA.md`:

| Criterio del Hackathon | Implementación en CreditGuard AI |
|---|---|
| **Un solo workflow coherente** | Gestión integral de crédito al consumo: consulta de cupo, simulación de préstamo y aumento de línea. |
| **Gobernanza de crédito estricta** | El LLM jamás evalúa ni aprueba crédito. Toda decisión emana de endpoints HTTP deterministas con reglas auditables. |
| **Separación de capas** | Capa 1: Diálogo (LangGraph) ──► Capa 2: Riesgo Predictivo (LightGBM) ──► Capa 3: Política Bancaria (FastAPI). |
| **Soporte Multilingüe (ES / PT)** | Diálogo adaptativo en español (regionalismos MX/CO/AR) y portugués; asignación de handoff a agentes con soporte pt (10.75% del pool). |
| **Explicabilidad sin caja negra** | Emisión de cartas estructuradas de rechazo (*Adverse Action Notices*) con códigos de motivo regulatorios claros, no CoT oculto. |
| **Rigor de Datos y ML** | Feature Store en dbt (`gold.credit_profiles`) y modelo supervisado evaluado contra un baseline heurístico con split *held-out*. |

---

## 3. Fundamentación en el Dataset Real (`spec/DATA_FINDINGS.md`)

A diferencia de otros flujos que carecen de señal en los datos crudos, el dataset sintético de LATAM Bank contiene evidencia estructural masiva para crédito:

1. **Universo de Productos (`products`, 400.000 filas):**
   - **Tarjeta de Crédito:** 100.102 registros.
   - **Préstamo Personal:** 19.960 registros.
   - **Préstamo Hipotecario:** 11.910 registros.
   - **Métricas cuantitativas clave:** `current_balance`, `credit_limit`, `interest_rate`, `days_past_due` y estados (`Active`, `Blocked`, `Suspended`).
2. **Perfiles de Clientes (`customers`, 150.000 filas):**
   - `credit_score`: Valores reales entre 300 y 850 (con 15.0% de nulos).
   - `estimated_monthly_income`: Ingresos mensuales (con 20.0% de nulos).
   - Segmentación: `segment`, `occupation`, `education_level`, `country`.
3. **Manejo de Casos Thin-File y Calidad de Datos:**
   - El 15% de clientes sin `credit_score` y 20% sin ingresos declarados constituyen la oportunidad perfecta para demostrar el manejo de **clientes con historial insuficiente (*thin-file*)**, activando caminos seguros de aclaración o abstención.
   - **Limitación documentada:** El gap confirmado de ausencia de moneda `MXN` en productos y transacciones se documenta formalmente; el agente opera en USD/COP/ARS y señala de forma transparente las restricciones de divisa.

---

## 4. Arquitectura y Gobernanza Tripartita

La política y las decisiones de crédito viven **estrictamente fuera del prompt del LLM**:

```
┌────────────────────────────────────────────────────────┐
│                        CLIENTE                         │
│         Frontend Web / Chat Multilingüe (Vercel)       │
└───────────────────────────┬────────────────────────────┘
                            │ HTTPS (POST /chat)
                            ▼
┌────────────────────────────────────────────────────────┐
│             VERTICAL 4: AGENT ORCHESTRATOR             │
│              (FastAPI + LangGraph en Railway)          │
│                                                        │
│  ┌──────────────────────────────────────────────────┐  │
│  │ 1. Comprensión Semántica (Español / Portugués)   │  │
│  ├──────────────────────────────────────────────────┤  │
│  │ 2. Guardrail Determinista (Decide)               │  │
│  │    - Validación de sesión de prueba confiable    │  │
│  │    - Verificación de intención permitida         │  │
│  ├──────────────────────────────────────────────────┤  │
│  │ 3. Formateo de Respuesta al Cliente              │  │
│  │    - Explicación de condiciones verificadas      │  │
│  │    - Prohibición de auto-aprobación de crédito   │  │
│  └────────────────────────┬─────────────────────────┘  │
└───────────────────────────┼────────────────────────────┘
                            │ HTTP Interno (Tool Client)
                            ▼
┌────────────────────────────────────────────────────────┐
│             VERTICAL 3: BACKEND TOOL LAYER             │
│                  (FastAPI en Railway)                  │
│                                                        │
│  Endpoint: POST /credit/evaluate-application           │
│                                                        │
│  ┌──────────────────────────────────────────────────┐  │
│  │ COMPONENTE B: Motor Predictivo de Riesgo (ML)    │  │
│  │   - Modelo LightGBM: Probabilidad de Mora        │  │
│  │   - Baseline Heurístico de Corte de Score        │  │
│  ├──────────────────────────────────────────────────┤  │
│  │ COMPONENTE C: Motor Determinista de Políticas    │  │
│  │   - Regla 1: DTI (Deuda/Ingreso) ≤ 40%           │  │
│  │   - Regla 2: Sin días de mora (days_past_due = 0)│  │
│  │   - Regla 3: Score crediticio mínimo ≥ 620       │  │
│  │   - Resultado: PRE_APPROVED / BORDERLINE /       │  │
│  │                INSUFFICIENT_DATA / DENIED        │  │
│  └────────────────────────┬─────────────────────────┘  │
└───────────────────────────┼────────────────────────────┘
                            │ SQL Queries
                            ▼
┌────────────────────────────────────────────────────────┐
│               VERTICAL 2: DATA PIPELINE                │
│                 (Postgres en Railway)                  │
│                                                        │
│  Schema data.gold.* (Materializado con dbt):           │
│  - gold.customers (Datos demográficos saneados)        │
│  - gold.credit_profiles (Features financieras)         │
│  - gold.trace_log (Pistas de auditoría de decisiones)  │
└────────────────────────────────────────────────────────┘
```

---

## 5. Los 3 Escenarios Mandatorios de Evaluación

El sistema contempla de forma exhaustiva los tres caminos de resolución exigidos por el hackathon:

### Caso 1: Resolución Automatizada Segura (*Safe Automated Resolution*)
- **Contexto:** Cliente solvente solicita simulación de préstamo o ampliación de límite de tarjeta.
- **Flujo:**
  1. El cliente pregunta: *"Gostaria de saber se posso solicitar um empréstimo pessoal de 5.000 USD"* o *"Quiero aumentar el cupo de mi tarjeta"*.
  2. El agente extrae la intención y delega la evaluación al backend (`POST /credit/evaluate-application`).
  3. El backend verifica en `gold.credit_profiles`:
     - `credit_score` = 750 (Excelente).
     - `days_past_due` = 0 (Al día).
     - Utilización de tarjeta = 18%.
     - DTI proyectado = 26% (por debajo del límite del 40%).
     - Probabilidad de mora estimada por ML = 1.8% (Bajo riesgo).
  4. El motor de políticas emite dictamen: `PRE_APPROVED` con un paquete de condiciones fijas (tasa del 14.5% E.A., plazo a 24 meses).
  5. El agente comunica la simulación de forma clara y basada únicamente en los datos devueltos por la herramienta.

### Caso 2: Ambigüedad y Abstención Segura (*Clarification / Safe Abstention*)
- **Contexto:** Cliente con información incompleta en el sistema (*thin-file*) o solicitud en parámetros inválidos.
- **Flujo:**
  1. El cliente consulta sobre su elegibilidad, pero en `customers` tiene `estimated_monthly_income = NULL` o `credit_score = NULL` (15-20% de la base).
  2. El backend identifica ausencia de variables críticas y retorna: `STATUS_INSUFFICIENT_DATA` junto con `missing_fields: ["estimated_monthly_income"]`.
  3. El guardrail bloquea cualquier intento de estimar o aprobar la solicitud.
  4. El agente se abstiene responsablemente y pide aclaración: *"Para poder evaluar tu capacidad de crédito necesitamos verificar tus ingresos mensuales. ¿Podrías indicarme tu ingreso mensual aproximado y si cuentas con comprobantes de pago?"*.

### Caso 3: Escalamiento Estructurado a Asesor Humano (*Human-in-the-Loop*)
- **Contexto:** Cliente en zona de riesgo limítrofe (*borderline*), con historial de morosidad buscando refinanciamiento, o interacción en portugués que supera los umbrales de auto-servicio.
- **Flujo:**
  1. Cliente con score intermedio (590) y `days_past_due = 15` solicita refinanciar su deuda de tarjeta.
  2. El motor de políticas determina: `REQUIRES_HUMAN_UNDERWRITER`.
  3. El backend compila un reporte formal de decisión adversa (*Adverse Action Summary*).
  4. El agente transfiere la conversación a la cola humana, enrutando preferentemente a un agente con perfil de idioma portugués o especialista en cobranzas:
     ```json
     {
       "escalation_id": "ESC-CRED-2026-0819",
       "timestamp": "2026-09-28T19:30:00Z",
       "customer_id": "CUST-94812",
       "session_language": "pt",
       "request_type": "debt_refinancing",
       "verified_facts": {
         "credit_score": 590,
         "active_debt_balance": 4850.00,
         "credit_limit": 5000.00,
         "credit_utilization": 0.97,
         "days_past_due": 15,
         "estimated_income": 1800.00,
         "calculated_dti": 0.52
       },
       "policy_verdict": "BORDERLINE_OVER_DTI",
       "rejection_reasons": [
         "Ratio Deuda/Ingreso superior al umbral máximo permitido (52% vs 40%)",
         "Mora activa registrada en tarjeta de crédito (15 días)"
       ],
       "recommended_action": "Evaluar reestructuración de pasivo con extensión de plazo",
       "unresolved_customer_questions": [
         "Solicita exoneración de intereses moratorios devengados"
       ]
     }
     ```

---

## 6. Estrategia de Machine Learning y Evaluación

El reto exige explícitamente evaluar al menos un componente aprendido contra un baseline adecuado, evitando data leakage:

### A. Definición del Problema Predictivo
- **Objetivo:** Predecir la **propensión a mora severa** (`is_delinquent_target = 1` si `days_past_due > 30` o el producto pasa a `Suspended/Blocked`).
- **Población de Modelado:** Clientes titulares de préstamos o tarjetas en `products`.

### B. Prevención Estricta de Fuga de Datos (*Data Leakage Prevention*)
- Se excluyen rigurosamente las variables de resultado futuro y auditoría sintética: `is_fraud`, `fraud_score`, y campos de resolución de quejas.
- Las variables de entrada son únicamente observables en el momento de la solicitud: historial de transacciones pasadas, ratio de utilización actual, antigüedad del cliente (`registration_date`), score externo saneado y variables demográficas.

### C. Benchmark: Baseline vs. Modelo Aprendido
- **Baseline Determinista:** Regla fija de la industria basada en cortes univariados:
  $$\text{Riesgo Alto} \iff (\text{credit\_score} < 620) \lor (\text{utilization} > 80\%)$$
- **Componente Aprendido:** Clasificador supervisado multivariado (**LightGBM / Logistic Regression** calibrada).
- **Esquema de Validación:** Split estratificado 80% Train / 20% Held-out Test aislado por cliente.
- **Métricas de Rendimiento a Reportar:**
  - ROC-AUC y PR-AUC (debido al desbalance natural de mora).
  - Brier Score (para calibración de probabilidad).
  - Reducción de tasa de falsos positivos frente al baseline determinista.

---

## 7. Modelado de Datos (dbt — Capa Gold)

Se define el nuevo modelo de negocio en dbt: `data/dbt/models/gold/credit_profiles.sql`:

```sql
with customers as (
    select * from {{ ref('stg_customers') }}
),

products as (
    select * from {{ ref('stg_products') }}
),

credit_aggregates as (
    select
        customer_id,
        count(product_id)                                  as total_credit_products,
        sum(case when product_type = 'Tarjeta Crédito' then current_balance else 0 end) as credit_card_balance,
        sum(case when product_type = 'Tarjeta Crédito' then credit_limit else 0 end)    as total_credit_limit,
        sum(case when product_type in ('Préstamo Personal', 'Préstamo Hipotecario') then current_balance else 0 end) as loan_balance,
        max(coalesce(days_past_due, 0))                    as max_days_past_due,
        bool_or(product_status in ('Blocked', 'Suspended')) as has_impaired_product
    from products
    where product_type in ('Tarjeta Crédito', 'Préstamo Personal', 'Préstamo Hipotecario')
    group by customer_id
)

select
    c.customer_id,
    c.country,
    c.segment,
    c.credit_score,
    c.estimated_monthly_income,
    coalesce(ca.total_credit_products, 0)                  as total_credit_products,
    coalesce(ca.credit_card_balance, 0)                    as total_credit_card_balance,
    coalesce(ca.total_credit_limit, 0)                     as total_credit_limit,
    coalesce(ca.loan_balance, 0)                           as total_loan_balance,
    coalesce(ca.max_days_past_due, 0)                      as max_days_past_due,
    coalesce(ca.has_impaired_product, false)               as has_impaired_product,
    
    -- Métricas financieras derivadas
    case 
        when coalesce(ca.total_credit_limit, 0) > 0 
        then round(ca.credit_card_balance / ca.total_credit_limit, 4)
        else 0 
    end as revolving_utilization_ratio,
    
    case 
        when coalesce(c.estimated_monthly_income, 0) > 0 
        then round((coalesce(ca.credit_card_balance * 0.05, 0) + coalesce(ca.loan_balance * 0.03, 0)) / c.estimated_monthly_income, 4)
        else null 
    end as estimated_dti_ratio,
    
    -- Banderas de auditoría y calidad
    (c.credit_score is null or c.estimated_monthly_income is null) as is_thin_file
from customers c
left join credit_aggregates ca on c.customer_id = ca.customer_id;
```

---

## 8. Tabla Comparativa: Disputas (Opción A) vs. Crédito (Opción Propuesta)

| Dimensión | Opción A: Disputas de Transacciones | CreditGuard AI: Crédito y Elegibilidad |
|---|---|---|
| **Soporte Empírico en Datos** | ⚠️ Débil: 0 duplicados exactos hallados en 4.4M filas. Depende solo de casos `Declined/Reversed`. | ✅ Muy fuerte: 400k productos (100k tarjetas, 31k préstamos) y 150k clientes con balances y scores reales. |
| **Componente de Machine Learning** | Difícil de fundamentar con rigor (los textos de quejas y transcripciones son plantillas repetidas). | ✅ Natural y riguroso: scoring predictivo de propensión a mora vs baseline determinista sin data leakage. |
| **Alineación con la Rúbrica de Seguridad** | Aplica reglas estándar de verificación de montos. | ✅ Cumple la cláusula más exigente del reto: desacoplar diálogo, riesgo predictivo y política bancaria. |
| **Aprovechamiento Multilingüe** | Traducción genérica de reclamo. | Integración con el 10.75% de agentes humanos con soporte en portugués identificados en `service_agents`. |
| **Generación de Valor de Negocio** | Gestión pasiva y mitigación de pérdidas operativas. | Colocación crediticia responsable, incremento de volumen de negocio y prevención activa de mora. |

---

## 9. Plan de Implementación Inmediato

Aprovechando la arquitectura ya desplegada en Railway (`.railway/railway.ts`):

1. **Vertical 2 (dbt):**
   - Incorporar `models/gold/credit_profiles.sql` y sus pruebas de esquema (`schema.yml`).
2. **Vertical 3 (`backend/`):**
   - Crear `app/routes/credit.py` con `POST /credit/evaluate-application` y `GET /customers/{id}/credit-profile`.
   - Implementar el motor determinista de políticas de crédito y generación de *Adverse Action Notices*.
3. **Machine Learning (`backend/ml/` o módulo de scoring):**
   - Entrenar y persistir el modelo de propensión de mora con LightGBM; documentar el benchmark contra el baseline de regla fija.
4. **Vertical 4 (`agent/`):**
   - Configurar el grafo en LangGraph (`understand -> decide -> act -> verify -> escalate`).
   - Definir la tabla de guardrails en `guardrail.py` para bloquear inferencias no autorizadas de crédito.
5. **Vertical 5 (`frontend/`):**
   - Adaptar la interfaz de chat en Vercel para visualizar la tarjeta de simulación crediticia y el estado del handoff en tiempo real.
