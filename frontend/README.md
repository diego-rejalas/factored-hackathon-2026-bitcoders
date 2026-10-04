# frontend/ — customer support + admin console

Deploy en Vercel. Pega a `POST /chat` y `POST /session` de `../agent/` — **nunca** a `../backend/` ni a Postgres directo. **Implementado**: Next.js (App Router) + TypeScript.

## Cliente (`/`)

- **Login de prueba:** `customer_id` + `document_number` → `POST /session` del agent; incluye selector determinista de escenarios desde `/meta/demo-scenarios` (sandbox, sin IdP real).
- **Chat:** candidatas con comercio/monto/fecha/estado, caso verificado, handoff legible y badge de outcome; el idioma es/pt se adapta a la respuesta del agente.
- **Mis casos:** lista propia más la línea de tiempo de eventos del caso.
- **Sesión expirada:** un 401 del agent vuelve al login con aviso.
- Estados de carga, vacío y error; foco visible, navegación por teclado, `aria-live`, objetivos táctiles y `prefers-reduced-motion`.

## Especialistas (`/admin`)

- Login de sandbox separado (credenciales configuradas en backend `ADMIN_USERS`).
- Bandeja de casos escalados/en curso, filtro por estado e idioma, detalle del handoff, auditoría y traza estructurada del agente.
- `claim → in_progress → close` requiere nota; el cierre pide resultado y confirmación.
- Métricas de backend + agent trace: tasas con denominadores, latencia p50/p95, idioma, outcomes y frescura ETL. Sin muestra/costos/labels de referencia, se muestra “No definido” o se explica la limitación.
- Sin IdP real ni credenciales de producción; el rate-limit backend es por proceso y el token solo vive en memoria del navegador.

## Variables

| Variable | Qué es |
|---|---|
| `AGENT_URL` | URL del agent en runtime (Cloud Run; única API que conoce el navegador). |
| `NEXT_PUBLIC_AGENT_URL` | Alternativa de compatibilidad para builds/Vercel y desarrollo local. |

## Desarrollo y verificación

```bash
pnpm install          # desde frontend/
pnpm build            # verificación (también corre en CI)
pnpm dev              # dev server
```

Nota: pnpm 11 aplica una política de trust (`no-downgrade`) configurada en esta máquina; `frontend/pnpm-workspace.yaml` fija `trustPolicyIgnoreAfter` (único lugar que pnpm 11 honra a nivel proyecto) para que `pnpm install && pnpm build` funcione sin flags locales (ver comentario adentro).

## Deploy (Vercel)

1. Para GCP, desplegar el servicio Cloud Run `frontend` y configurar `AGENT_URL` (Terraform lo establece al endpoint público del agent/ALB).
2. Para otro host, setear `NEXT_PUBLIC_AGENT_URL` a la URL del servicio `agent`.
3. No se necesita `vercel.json`: la configuración por defecto de Next.js alcanza.
