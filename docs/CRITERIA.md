# Challenge criteria (Factored AI & Data Hackathon 2026)

[Index](README.md) · [Workflow](WORKFLOW.md) · [Architecture](ARCHITECTURE.md) · [Data](DATA.md) · [API](API.md)

What the challenge requires, taken from `docs/challenge/Factored AI & Data Hackathon 2026.md` and `docs/challenge/Datathon_2026_Kickoff.pdf`, and the state of each item. Every met item says where its evidence is. **Last updated on 2026-10-04 against the code and the documents in this folder.**

## At a glance

| Section | Met | Open |
|---|---:|---:|
| Mandatory scope | 6 | 0 |
| Working system (minimum requirements) | 5 | 0 |
| Controlled automation | 4 | 0 |
| Data and ML | 4 | 0 |
| Quality measurement and failure handling | 3 | 0 |
| Path to production (honesty, not a real implementation) | 4 | 0 |
| Data and execution boundaries | 6 | 1 |
| Submission (before Oct 5) | 0 | 6 |
| **Total** | **32** | **7** |

What is open, in order of impact: the **deployment** of this version and the **submission** (public repository, slides, video and sending). The evaluation is in [Evaluation](EVALUATION.md) and the path to production in [Path to production](PRODUCTION.md). The deployment procedure is in [Deployment](DEPLOY.md).

## Mandatory scope

- [x] One coherent banking workflow (accounts/payments, cards, disputes, or credit). Implementing more than one earns no bonus. (Transaction disputes, `WORKFLOW.md`. There is no second workflow.)
- [x] A normal case resolved automatically (safe automated resolution). (Declined or Reversed under USD 500: Bruno and Carla in `infra/gcp/scripts/e2e.py`, 11 of 11 against the local stack.)
- [x] An ambiguous or unsupported case: the system asks for clarification or explicitly abstains. (Several candidates: it asks for clarification and offers a choice. No candidates or out of scope: it escalates. Covered in `agent/tests/test_graph.py` and in e2e.)
- [x] A case that needs human intervention gets a structured handoff. (Approved charge, fraud, amount over the threshold, unknown amount: a `handoff` with the request, facts, actions, evidence and open questions.)
- [x] Interaction demonstrated in **Spanish and Portuguese**. (e2e includes a Portuguese case, and language detection and the fixed replies exist in es and pt. Measurement by language is in the evaluation.)
- [x] Report the data limits or language coverage found. (`DATA.md`, `WORKFLOW.md`: no MXN in transactions, no Portuguese in the history, inconsistent `complaints.affected_product_id`, no exact duplicates.)

## Working system (minimum requirements)

- [x] Keeps conversational context. (LangGraph memory per conversation and customer. Limit: it is in process memory and is lost on restart. The history the customer sees is stored in `agent.conversation_messages`.)
- [x] Clarifies ambiguity (does not assume). (`clarify` with candidates. It never picks one on its own.)
- [x] Answers with information grounded in permitted data (account, transaction, policy) and does not hallucinate facts. (Replies come from verified facts. The model only drafts a resolved case and its draft passes through `agent/app/grounding.py`.)
- [x] Uses tools when the workflow requires it. (The agent reaches data only through the backend over HTTP, never Postgres.)
- [x] Reports only actions whose result the system verified (it does not trust what the LLM "says" happened). (The `verify` node rereads the case from the backend before saying it was recorded. If that fails, it escalates.)

## Controlled automation

- [x] Defines explicitly what it can answer alone, what needs confirmation, and when it must abstain or hand off to a human. (`docs/WORKFLOW.md`, the paths and escalation tables.)
- [x] Permissions and policies are enforced **outside** the model's generated text (deterministic code, not the prompt). (Deterministic guardrail in `agent/app/guardrail.py`, ownership in the backend. The model does not decide policy.)
- [x] The handoff to a human delivers the request, verified facts, actions taken, supporting evidence and unresolved questions, not a raw transcript dump. (Structure in [Workflow](WORKFLOW.md), shown by the `/admin` console.)
- [x] **Does not apply:** the workflow is disputes and does not touch credit. If it did, conversation, predictive risk and eligibility policy would be separated. The conversational model NEVER invents eligibility rules or approves credit on its own.

## Data and ML

- [x] A repeatable data pipeline: schema contracts, quality checks, lineage, refresh and freshness policy. (Airflow DAG with DuckDB: it rebuilds bronze from S3 on every run. The dbt tests (keys, relationships, accepted values, ranges and business rules) gate publishing, and if a silver test fails `gold` is not published. Row-level lineage in `_source_key`. The freshness policy is explicit in [Architecture](ARCHITECTURE.md) (static snapshot, reload on demand). Still to do: harden the `gold` contracts to typed ones with `contract: enforced`.)
- [x] At least one learned component evaluated against an appropriate baseline. (Intent classification: model against keywords, 228 blind cases and 40 adversarial ones, with intervals and a paired test. [Evaluation](EVALUATION.md#1-the-component-intent-classification).) (Also `ml/eval/`: an intent and language classifier with confidence against the keywords, and a ranker of the disputed transaction (weighted sum and GBM) against `narrow_candidates`, with reports and failures in `ml/eval/reports/`. Summary in [ML components](ML_FINDINGS.md), section 12.)
- [x] Valid labels or relevance judgments, with no leakage (for example, not using `is_fraud` as input if the system is supposed to "detect" it). (Labels by construction or by a separately written policy oracle. `is_fraud` does not exist in the cases. The sets were read one by one and cleaned, by the evaluation's author and not by a third party. [Evaluation](EVALUATION.md#how-it-was-evaluated).) (In `ml/eval/`: the generators remove `is_fraud` and `fraud_score` and verify it. The ranker uses no columns that come after the outcome. `fraud_score` was dropped for leakage, [ML components](ML_FINDINGS.md) section 4.2.)
- [x] Justify representations, metrics, thresholds and evaluation splits. (There is no training, so there is no train and test split. The sets were written before running, and anything adjusted afterward was validated with a new set. [Evaluation](EVALUATION.md#how-it-was-evaluated).) (In `ml/eval/`: a priori, interpretable weights, abstention with a threshold calibrated on dev (`INTENT_MIN_CONFIDENCE`, asymmetric cost 5 to 1) and splits stratified by cell (intent) and by customer (ranker).)

## Quality measurement and failure handling

- [x] Evaluation on held-out cases. (549 end-to-end cases against the real backend and database, with and without the model. They are team-generated cases.) (Also `ml/eval/`: dev and test sets with thresholds frozen on dev.)
- [x] Include: incorrect or missing data, expired sessions, unauthorized access attempts, prompt injection, tool failures, multilingual ambiguity. (Nonexistent data 24, expired session 6, other customers' data 20, injection 12, backend failure 12 and clarification in es and pt 31: [Evaluation](EVALUATION.md#2-the-full-system-end-to-end).)
- [x] Report: successful outcomes, unsafe outcomes, handoff behavior, latency, cost, with sample sizes and explicit limits. (With sample sizes, intervals and explicit limits. The full run was repeated with the model after the fixes. What is not independent is stated in the limits.)

## Metrics to report (the challenge's exact definitions)

- **Safe automated resolution:** the % of in-scope cases that reach a correct, policy-compliant resolution WITHOUT human intervention. Also report what % of cases were attempted for automation.
- **Containment:** the % of cases that end without a transfer (this ALONE does not prove the problem was solved, so report it together with real resolution).
- **Escalation quality:** correct transfers plus useful context in the handoff. Report missed and unnecessary transfers where reference labels exist.
- **Unsafe outcomes:** unauthorized disclosures or actions, or materially incorrect results, with counts and denominators. Zero failures in a small sample does NOT mean zero risk (say so explicitly).
- **Operating efficiency:** p50 and p95 latency and cost per attempted case and per successfully resolved case, end to end. If there are no successful resolutions, use "not defined" and do not invent a number.
- Compare results by language and by authorized customer segment, and flag small-sample limits.
- Clearly separate offline measurement, simulation and business savings projection. Never present an offline comparison as a "measured improvement in production".

## Path to production (honesty, not a real implementation)

- [x] Tracing of every decision (audit evidence = sources + policy rules + execution records. The model's hidden chain of thought does NOT count as evidence). (`agent.trace_log` per step, with no user text or model reasoning. The case stores its events and evidence.)
- [x] Bounded retries and a safe fallback. (Pipeline: loads retry twice and `gold` keeps the last valid data. Agent: 3 attempts with a 2 s connection timeout and a worst case of 6.9 s. If the backend does not answer, `outcome: unavailable` with a safe message and no changes.)
- [x] Reproducible setup. (Everything as code: Terraform in `infra/gcp/`, Dockerfiles, CI that builds the images and runs the tests. The steps are in `infra/gcp/README.md` and [Deployment](DEPLOY.md).)
- [x] Explain capacity limits, monitoring, access controls, data retention and what is missing for real production. ([Path to production](PRODUCTION.md): each section separates what exists from what is missing. No retention policy is applied and no load test was run, and both are stated there.)

## Architecture freedom (what is NOT mandatory)

- Training a new model is not required.
- Multi-agent is not required.
- A minimum number of tools is not required.
- Streaming is not required.
- Demand forecasting is not required.
- A dashboard is not required.
- (But if a pretrained model or retrieval is used, the same rigor must be shown: component selection, intent and relevance labels, representations, leakage prevention, held-out evaluation, error analysis.)

## Data and execution boundaries

- [x] Only the organizer-approved dataset (synthetic LATAM Bank) and permitted external resources.
- [x] Identify which inputs are real, de-identified, synthetic or team-generated. (`DATA.md`, "Provenance": everything is synthetic from the organizer, and anything the team generates is labeled separately.)
- [x] Do not include real private records, credentials or restricted data in the public submission or in requests to external models. (A PDF with AWS keys was removed from the repo and from its history. On 2026-10-04 all 130 commits were searched for credential patterns (AWS, OpenRouter, GitHub, private keys) and for the real values in the local `.env`: 0 matches. The `.env` files are not versioned. The search should be repeated right before the repository is made public.)
- [x] Sandbox services and simulated banking tools are acceptable if their contracts and limits are documented. (`docs/API.md`. The OpenAPI contract is versioned and a test fails if it drifts.)
- [ ] Authentication with a trusted test session or an identity service. A customer ID or number ALONE does not prove identity. **Partial:** there is a signed JWT session with an expiry and a role, and demo accounts with a password (argon2id) and lockout after failed attempts. But the chat login still accepts customer plus ID number. It is a sandbox, so the submission must say so and not present it as real identity.
- [x] Per-customer record access permissions enforced in the service and tool layer, not in the prompt. (Every backend query is filtered by the customer in the token. There are cross-access tests in the backend and the agent.)
- [x] Moving real money or making live credit decisions is neither required nor authorized. (Nothing in the system moves money, and the backend is read-only.)

## Submission (before Oct 5)

- [ ] A public GitHub repo: `factored-hackathon-2026-[team name]`. **Warning: the `factored-hackathon-2026-bitcoders` repo is private right now (a deliberate choice during development). Make it public before submitting, or confirm with the organizer whether they accept a collaborator invitation instead.**
- [ ] A link where the tool is deployed (a real deployment, not only local).
- [ ] A 4 to 6 slide presentation with details of the tool.
- [ ] A pitch video (mandatory) of **no more than 3 minutes**, demonstrating the working solution and explaining the core architectural decisions. (The challenge page sets the limit at 3 minutes.)
- [ ] Send everything to hackathon.admin@factored.ai.
- [ ] "Submit your tool no matter what!!!" Submit even if it is incomplete.

## Evaluation criteria ("Evaluation Criteria" slide and the challenge page)

- Above all, the solution must work.
- Rationale and overall project documentation.
- **Technical Judgment:** architecture, trade-offs, reliability, safety and production readiness. ([Architecture](ARCHITECTURE.md), [Security](SECURITY.md), [Path to production](PRODUCTION.md))
- **AI Engineering:** backend, frontend, system integration and deployment.
- **Data Engineering:** quality, pipelines, data preparation and reproducibility.
- **Machine Learning:** modeling, evaluation, baselines and performance. ([Evaluation](EVALUATION.md), [ML components](ML_FINDINGS.md))
- **Data Analytics:** metrics, insights, visualization and decision support. (Metrics and inbox in the `/admin` console, [Data](DATA.md), `/data-docs`.)

Other rules from the challenge page: Spanish and Portuguese are mandatory, one workflow only, teams of **up to 4 people**, and any language, framework, model or cloud. The challenge period ends on **October 5**, and the page gives no time or time zone.

## Data that conditions the evaluation

Historical text is templated and `is_fraud` is ground truth, not input. So the evaluation of the learned component uses live text labeled by the team, with the structured fields as the baseline. The detail is in [Data](DATA.md).
