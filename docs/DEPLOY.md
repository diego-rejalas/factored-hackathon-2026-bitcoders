# Deploying to production

[Index](README.md) · [Architecture](ARCHITECTURE.md) · [Path to production](PRODUCTION.md) · [Security](SECURITY.md)

*What changes, what to do before, how to apply, what to do after and how to roll back. Meant to be run top to bottom. Each step says who does it and why.*

## What changes

The `prod` `plan` says so. It ran from GitHub with the read-only account and applied nothing: **3 resources to add, 5 to change, 0 to destroy.**

| Change | What it is |
|---|---|
| `frontend`, `agent` and `backend` services and the `etl` job | A new image (the commit's) and new variables. The agent switches to `anthropic/claude-haiku-4.5`, the model the [Evaluation](EVALUATION.md) measured |
| Airflow VM | Only the image tag in its metadata changes. The VM stays stopped until it is used |
| Secret `factored-prod-admin-users` and its read permission for the backend | **New and empty (`NOT_SET`).** It has to be loaded, or the `/admin` console answers 503 |

An earlier `plan` showed 3 destroys: the Airflow VM access of whoever operates it. Those were permissions that a local `apply` had granted with a variable the GitHub workflow did not pass. It now passes it, from the repository variable `AIRFLOW_ADMIN_MEMBERS`. Without it, applying from GitHub removes access from whoever had it.

**Data.** The backend migrations run at startup, once and under a lock:

- `0003` leaves **a single case per customer and transaction**: it closes the older ones if there were duplicates. It cannot be undone.
- `0005` allows cases with no transaction, admits the `in_progress` status and repairs handoffs stored as text.

## Before applying

| # | Step | Who |
|---|---|---|
| 1 | Look at the duplicates `0003` would close (below). If they are test cases, it does not matter | You |
| 2 | Optional but recommended: in GitHub, **Settings, Environments, prod**, add required reviewers. Today anyone with write permission can apply to `prod` | You |
| 3 | Confirm that `AIRFLOW_ADMIN_MEMBERS` exists: `gh variable list` | You |

**Look at the duplicates** (this starts the VM, queries and stops it):

```bash
ENVIRONMENT=prod ./infra/gcp/scripts/airflow_vm.sh start
cat <<'PY' | gcloud compute ssh factored-prod-airflow --zone us-east4-a --project bitcoders-factored-hackathon \
    --tunnel-through-iap --quiet --command "sudo docker exec -i airflow-scheduler-1 python -"
import os, psycopg2
c = psycopg2.connect(host=os.environ["PG_HOST"], port=os.environ["PG_PORT"], dbname=os.environ["PG_DATABASE"],
                     user=os.environ["PG_USER"], password=os.environ["PG_PASSWORD"], sslmode="require")
cur = c.cursor()
cur.execute("select count(*) from app.disputes"); print("cases:", cur.fetchone()[0])
cur.execute("""select customer_id, transaction_id, count(*) from app.disputes
               where transaction_id is not null and status <> 'closed'
               group by 1, 2 having count(*) > 1""")
print("transactions with more than one open case:", cur.fetchall())
PY
```

## Apply

```bash
gh workflow run "GCP deploy" --ref main -f environment=prod -f terraform_action=apply -f run_etl=false
gh run watch            # pick the run
```

In order, it creates the image registry if missing, builds the five images with the commit as the tag, pushes them, plans, **checks the plan with Checkov**, applies that same plan and checks health (`/` and `/agent/health` through the load balancer, and that the backend answers 403 without credentials). It takes about 8 minutes. It applies only from `main`.

`run_etl=true` also reruns the job that loads the data. It is not needed, because `gold` is already loaded.

## After applying

**1. Database permissions.** `roles.sql` changed (read permissions for the console). With the VM on:

```bash
ENVIRONMENT=prod ./infra/gcp/scripts/db_roles.sh
```

**2. The two secrets.**

```bash
# Specialist console: user:bcrypt-hash, several separated by commas. The password is not written anywhere.
python3 -c "import bcrypt,getpass; print('ops:'+bcrypt.hashpw(getpass.getpass('password: ').encode(), bcrypt.gensalt()).decode())" \
  | gcloud secrets versions add factored-prod-admin-users --data-file=- --project bitcoders-factored-hackathon

# Language model: without this key the agent works without a model (90.6% of disputes, 82.8% in Portuguese)
printf '%s' "$OPENROUTER_API_KEY" \
  | gcloud secrets versions add factored-prod-openrouter-api-key --data-file=- --project bitcoders-factored-hackathon
```

**3. Make the services read the new secrets.** Cloud Run reads a secret when an instance starts:

```bash
for s in backend agent; do
  gcloud run services update factored-prod-$s --region us-east4 --project bitcoders-factored-hackathon \
    --update-labels redeploy=$(date +%s)
done
```

**4. Verify.**

```bash
AGENT_URL="$(cd infra/gcp/envs/prod && terraform output -raw edge_url)/agent" python3 infra/gcp/scripts/e2e.py   # 11 scenarios, must exit 0
```

And by hand, in the browser with the load balancer URL: sign in as a demo customer, then try a case that resolves, one that escalates, one in Portuguese, and the `/admin` console with the user you loaded.

**Production suite.** `BASE_URL=https://<your address> python3 infra/gcp/scripts/prod_suite.py` asks the deployed system the questions a person clicking through the demo would meet, using the same demo customers the login offers (`/agent/meta/demo-scenarios`), and exits non-zero if a check fails. It covers the edge (HTTPS, the redirect, the certificate and its expiry, the files in `public/`), authentication, the policy outcomes in Spanish and Portuguese, safety (a prompt injection, another customer's data, an out-of-scope question) and the replies themselves (no internal names, no promise of time or money), and it reports the latency of every turn. A WARN does not fail the run. It has no dependencies.

It makes the agent open or escalate dispute cases, as any customer message does, and lists the case ids it caused. `--no-writes` skips the checks that do, and `--json FILE` saves the results. It is not the 549-case evaluation: it is a check that the live system answers well, in about a minute.

**5. Stop the VM** if it was started: `./infra/gcp/scripts/airflow_vm.sh stop` (it also stops by itself at 03:00).

## The landing, the video and the app's name (Cloudflare)

These are not part of the Google Cloud apply. They are Terraform in `infra/cloudflare`, with their own state (the same bucket, the prefix `cloudflare`) and their own workflow, `Cloudflare (landing and video)`, run by hand.

1. **Once:** create an API token with Pages Edit, R2 Edit and DNS Edit on the account and the zone, and nothing else. Set it with `gh secret set CLOUDFLARE_API_TOKEN`. Set the repository variables listed in [`infra/cloudflare/README.md`](../infra/cloudflare/README.md).
2. Run the workflow with `plan` and read it. The first run **adopts** what was made by hand: it shows three imports and no destruction.
3. Run it with `apply`. Afterwards delete `infra/cloudflare/import.tf` in a follow-up change.
4. The landing's files are published with `wrangler pages deploy` (see `site/README.md`). The pitch video is an object in the bucket: `wrangler r2 object put <bucket>/<name> --file <video> --remote`, and the site reads its address from `NEXT_PUBLIC_VIDEO_URL`.

The app's name needs a DNS record to the load balancer's address, **without** the proxy. Add the name to the load balancer first (`EDGE_ADDITIONAL_DOMAINS`, then `EDGE_DOMAIN`), as described above, and wait for its certificate to be `ACTIVE` before relying on it.

## Rolling back

- **Services.** Cloud Run keeps earlier revisions, and the switch is immediate:

  ```bash
  gcloud run revisions list --service factored-prod-agent --region us-east4 --project bitcoders-factored-hackathon
  gcloud run services update-traffic factored-prod-agent --to-revisions=<previous-revision>=100 \
    --region us-east4 --project bitcoders-factored-hackathon
  ```

  The same applies to `backend` and `frontend`.
- **Database.** Migrations only move forward. What `0003` did (closing duplicate cases) does not come back. The database backups keep the earlier state if it is ever needed (point-in-time recovery in `prod`).
- **Secrets.** To go back to an earlier version, disable the new one: `gcloud secrets versions disable <n> --secret ...`.

## What is not verified

- **The deployment itself.** The `plan` and the local tests do not replace a real `apply`. Check the result of the run before relying on any of this.
- **The path through the load balancer** with this version. The managed certificate can take a while to provision after domain changes (this deployment does not change the domain).
- **`e2e.py` against the edge.** Its 11 scenarios passed against the local stack and against `prod` in the earlier deployment. Pointing `AGENT_URL` at the load balancer's `/agent` is the intended way, not the one that was tested.
