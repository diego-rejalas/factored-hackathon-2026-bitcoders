# LATAM Bank: asistente de disputas

<p align="center">
  <img src="https://skillicons.dev/icons?i=python,fastapi,nextjs,ts,postgres,duckdb,airflow,docker,terraform,gcp,githubactions&perline=11" alt="Python, FastAPI, Next.js, TypeScript, PostgreSQL, DuckDB, Airflow, Docker, Terraform, Google Cloud, GitHub Actions" />
</p>

Asistente de atención al cliente bancario que resuelve solo las disputas de transacciones seguras y deriva el resto a una persona con el caso armado. Prototipo del **Factored AI & Data Hackathon 2026**, equipo *bitcoders*, sobre el dataset sintético LATAM Bank.

- **Un cliente** cuenta, en español o portugués, un cargo que no reconoce. El agente identifica la transacción, aplica una política determinista y responde con hechos verificados.
- **Resuelve solo** lo claro y bajo USD 500 (una transacción rechazada o revertida). **Escala** un cobro aprobado, un posible fraude, un monto alto o un caso ambiguo, con un traspaso estructurado.
- **Un especialista** toma los casos escalados en la consola `/admin`, con la evidencia, la auditoría y la traza del agente.
- La política, los permisos y la identidad viven en código. El modelo de lenguaje es opcional y solo redacta.

## Cómo funciona

**El agente.** La política es código y el modelo solo ayuda: clasifica, redacta y mira si hay fraude, pero no decide.

![Flujo del agente](docs/diagrams/agent-flow.svg)

**El pipeline de datos.** Del S3 del organizador a las tablas `gold` que lee el backend, con una compuerta de pruebas antes de publicar.

![Flujo del pipeline](docs/diagrams/pipeline-flow.svg)

**El despliegue.** Todo en Google Cloud, definido con Terraform.

![Arquitectura en GCP](docs/diagrams/gcp-architecture.svg)

## Documentación

Todo está en [`docs/`](docs/README.md).

| | |
|---|---|
| [Workflow](docs/WORKFLOW.md) | Qué resuelve solo, cuándo escala y qué recibe la persona |
| [Arquitectura](docs/ARCHITECTURE.md) | Cómo está construido y desplegado en GCP |
| [Datos](docs/DATA.md) | Qué dice el dataset y sus limitaciones |
| [API](docs/API.md) | Contrato entre la interfaz, el agente y el backend |
| [Evaluación](docs/EVALUATION.md) | Cómo se midió el sistema y con qué resultados |
| [Componentes de ML](docs/ML_FINDINGS.md) | Clasificación de intención y ranking de transacciones frente a sus líneas base (`ml/eval/`) |
| [Seguridad](docs/SECURITY.md) | Controles y hallazgos de Checkov y Trivy |
| [Ruta a producción](docs/PRODUCTION.md) | Qué existe y qué falta para producción real |
| [Despliegue](docs/DEPLOY.md) | Desplegar a producción, paso a paso |
| [Criterios](docs/CRITERIA.md) | Qué pide el reto y qué falta |
| [Desarrollo local](docs/LOCAL_DEV.md) | Ejecutarlo en tu máquina |

El enunciado del reto está en [`doc/`](doc/) (material del organizador, no se edita).

## Estructura

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
| `docs/` | Documentación y diagramas |

## Probar

```bash
cd backend  && python -m pytest    # capa de herramientas (la base va simulada; con PG_TEST_HOST también corre contra PostgreSQL)
cd agent    && python -m pytest    # agente y guardrail (backend y modelo simulados)
cd frontend && pnpm build          # compilación y tipos de la interfaz
```

Para levantar todo en local con datos de ejemplo, ver [`docs/LOCAL_DEV.md`](docs/LOCAL_DEV.md).
