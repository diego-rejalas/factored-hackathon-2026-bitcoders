# frontend/ — chat UI

Deploy en Vercel. Pega a `POST /chat` y `POST /session` de `../agent/` — **nunca** a `../backend/` ni a Postgres directo. **Implementado**: Next.js (App Router) + TypeScript.

## Qué muestra

- **Login de prueba:** `customer_id` + `document_number` → `POST /session` del agent (sandbox, sin IdP real).
- **Chat:** burbujas, badge de `outcome` (resuelto / aclaración) y **banner de handoff con `case_id`** cuando `outcome=escalated`.
- **Sesión expirada:** un 401 del agent vuelve al login con aviso.
- Estados vacío, cargando y error. El texto del asistente llega en el idioma del usuario (es/pt) — sin selector obligatorio.

## Variables

| Variable | Qué es |
|---|---|
| `NEXT_PUBLIC_AGENT_URL` | URL del agent (único backend que esta app contacta). En Vercel se configura como variable de proyecto. |

## Desarrollo y verificación

```bash
pnpm install          # desde frontend/
pnpm build            # verificación (también corre en CI)
pnpm dev              # dev server
```

Nota: pnpm 11 aplica una política de trust (`no-downgrade`) configurada en esta máquina; `frontend/pnpm-workspace.yaml` fija `trustPolicyIgnoreAfter` (único lugar que pnpm 11 honra a nivel proyecto) para que `pnpm install && pnpm build` funcione sin flags locales (ver comentario adentro).

## Deploy (Vercel)

1. Importar el repo en Vercel con **Root Directory = `frontend`** (framework preset: Next.js — detecta `pnpm build` solo).
2. Setear `NEXT_PUBLIC_AGENT_URL` a la URL pública del servicio `agent` en Railway.
3. Deploy. No se necesita `vercel.json`: la configuración por defecto de Next.js alcanza.
