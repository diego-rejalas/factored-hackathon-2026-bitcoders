# Cloudflare: the landing, the pitch video and the app's name

What lives outside Google Cloud, as Terraform. It was made by hand first and then adopted into the state.

| Resource | What it is |
|---|---|
| `cloudflare_pages_project.landing` | The Pages project that serves the landing, a static export of `site/` |
| `cloudflare_r2_bucket.media` | The bucket of the pitch video. A bucket answers range requests and Pages does not, and a video that ignores them cannot be skipped through |
| `cloudflare_r2_managed_domain.media` | The bucket's public `r2.dev` address. For development, rate-limited by Cloudflare: enough for the evaluation, not for a real audience |
| `cloudflare_dns_record.app` | The app's name, an A record to the load balancer, **without** Cloudflare's proxy: with it on, the name would resolve to Cloudflare and Google could not issue the certificate |

The landing's files are not planned by Terraform. They are published with `wrangler pages deploy` (see `site/README.md`).

## Nothing about the account is in the code

Every value is a variable, and the workflow reads each one from a repository variable or secret, so the repository can be public. `account_id` and `zone_id` are **secrets**: the log is public, and GitHub hides a secret but shows a variable.

| Variable | Repository variable or secret |
|---|---|
| `account_id` | `CF_ACCOUNT_ID` |
| `zone_id` | `CF_ZONE_ID` |
| `app_hostname` | `EDGE_DOMAIN` (the same name the load balancer uses) |
| `edge_ip` | `EDGE_IP` (the `ip_address` output of `infra/gcp/envs/prod`) |
| `pages_project_name` | `CF_PAGES_PROJECT` |
| `r2_bucket_name` | `CF_R2_BUCKET` |

The token is the repository **secret** `CLOUDFLARE_API_TOKEN`, an API token with Pages Edit, R2 Edit and DNS Edit on that account and zone (and nothing else). Create it in the Cloudflare dashboard and set it with `gh secret set CLOUDFLARE_API_TOKEN`.

## State

The bucket that holds the GCP state, under the prefix `cloudflare`, reached with the same federation as `gcp-deploy.yml`. Plan and apply both run as the deployment account (which only accepts `main`), because the first run has to create the state object and the read-only account cannot write. The bucket's name is not in the code: `terraform init -backend-config="bucket=<the state bucket>"`.

## Run it

The workflow `Cloudflare (landing and video)`, by hand, with `plan` or `apply`. Plan first and read it.

What was created by hand was adopted into the state with a one-time `import.tf` (the Pages project, the bucket and the DNS record, three imports and no destruction), and that file is gone. The managed domain has no import; the resource enables it, which was a no-op for a bucket that already had it. A plan now says "No changes".

By hand: `cp terraform.tfvars.example terraform.tfvars`, fill it in, `export CLOUDFLARE_API_TOKEN=...`, `terraform init -backend-config="bucket=..."`, `terraform plan`.
