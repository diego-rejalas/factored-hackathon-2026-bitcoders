# frontend/: customer chat and specialist console

Next.js 16 (App Router) and TypeScript, with no Tailwind. It runs on Cloud Run (`output: standalone`). From the browser it calls **only the agent** (`POST /session`, `POST /chat`, `GET /me/*`, `GET /admin/*`), and never the backend or Postgres. The interface is in Spanish and Portuguese for customers and in Spanish for specialists, so the quoted UI labels below are in Spanish.

## Customer (`/`)

- **Login:** `customer_id` plus a document number (a sandbox, with no identity provider). The **demo scenarios** come from `/meta/demo-scenarios` and appear as cards.
- **An assistant-style chat:** a sidebar with *Nueva conversación* (new conversation), *Mis casos* (my cases) and recent conversations (stored in the agent and reopened), a central column, a floating composer that grows and sends on Enter, suggested questions, a typing indicator and a reply that appears word by word.
- **Cards:** the candidate transactions to choose from, the case with its evidence (the transaction and what was decided, with detail on hover) and the handoff to a person.
- **Language:** Spanish or Portuguese, following what the agent detects.
- **Theme:** light or dark. It follows the system, and a button changes it and remembers the choice.
- **Expired session:** a 401 from the agent returns to the login with a notice.
- **Accessibility:** visible focus, keyboard navigation, `aria-live`, 44 px touch targets and `prefers-reduced-motion`.

## Specialists (`/admin`)

- A separate sandbox login (`ADMIN_USERS` in the backend).
- An inbox of escalated and in-progress cases, with filters, and a detail view with the handoff, the audit trail and the agent's trace.
- `claim → in_progress → close`: closing requires a note and an outcome.
- Backend and agent metrics with their denominators. Without enough sample they show "No definido" (not defined).
- There is no real identity provider, and the token lives only in the browser's memory.

## Variables

| Variable | What it is |
|---|---|
| `AGENT_URL` | The agent's URL at run time (Cloud Run). It is the only API the browser knows |
| `NEXT_PUBLIC_AGENT_URL` | An alternative for local development |

## Development and verification

```bash
pnpm install          # from frontend/
pnpm build            # compile and type check (also runs in CI)
pnpm dev              # development server
pnpm start            # serves the build
```

`pnpm-workspace.yaml` sets `trustPolicyIgnoreAfter` so that `pnpm install` works with pnpm 11's trust policy without local flags. If `pnpm` fails to download its own version, see [`docs/LOCAL_DEV.md`](../docs/LOCAL_DEV.md).

## Deployment

On GCP it is the `frontend` Cloud Run service. Terraform sets `AGENT_URL` to the agent, behind the load balancer. For another host, define `AGENT_URL` or `NEXT_PUBLIC_AGENT_URL`.
