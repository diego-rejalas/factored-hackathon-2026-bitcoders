# Documentación

Asistente de disputas de transacciones de LATAM Bank, para el Factored AI & Data Hackathon 2026 (equipo bitcoders). Esta carpeta es la única de documentación del repositorio. El enunciado del reto está en [`../doc/`](../doc/) y no se edita.

## Por dónde empezar

| Si quieres... | Lee |
|---|---|
| Entender qué hace el asistente y cuándo escala | [Workflow](WORKFLOW.md) |
| Ver cómo está construido y desplegado | [Arquitectura](ARCHITECTURE.md) |
| Saber qué dice el dataset y qué limitaciones tiene | [Datos](DATA.md) |
| Llamar a las APIs o revisar el contrato | [API](API.md) |
| Revisar los controles y los hallazgos de seguridad | [Seguridad](SECURITY.md) |
| Ver cómo se midió el sistema y con qué resultados | [Evaluación](EVALUATION.md) |
| Ver la evaluación de los componentes de ML (intención y ranking) | [Componentes de ML](ML_FINDINGS.md) |
| Saber qué falta para producción real | [Ruta a producción](PRODUCTION.md) |
| Desplegar a producción, paso a paso | [Despliegue](DEPLOY.md) |
| Comprobar qué pide el reto y qué falta | [Criterios](CRITERIA.md) |
| Ejecutarlo en tu máquina | [Desarrollo local](LOCAL_DEV.md) |

## Mapa del repositorio

| Carpeta | Contenido |
|---|---|
| `backend/` | Capa de herramientas: FastAPI, permisos por titularidad, casos y consola del especialista |
| `agent/` | Agente conversacional: LangGraph, guardrail determinista, trazas e historial |
| `frontend/` | Next.js: chat del cliente y consola `/admin` |
| `data/` | Pipeline: etapas en `pipeline/` y proyecto dbt en `dbt/` |
| `ml/eval/` | Conjuntos retenidos y evaluación de los componentes de ML (intención y ranking de transacciones) |
| `agent/eval/` | Evaluación del sistema de punta a punta y del clasificador de intención |
| `infra/gcp/` | Terraform por ambiente (`dev`, `qa`, `prod`) y módulos |
| `infra/gcp/airflow/` | Imagen y DAG de Airflow que corre en la VM |
| `docs/diagrams/` | Diagramas de arquitectura y de linaje |

## Diagramas

![Arquitectura en GCP](diagrams/gcp-architecture.png)

El linaje de las tablas del pipeline está en [`diagrams/dbt-lineage.svg`](diagrams/dbt-lineage.svg).
