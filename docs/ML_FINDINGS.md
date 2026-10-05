# ML findings: what can be learned from the data and which component to evaluate

[Index](README.md) · [Data](DATA.md) · [System evaluation](EVALUATION.md) · [Criteria](CRITERIA.md)

Research notes for the ML engineer. They gather what was measured on the LATAM Bank dataset (synthetic, from the organizer), what the challenge says about ML, what other teams did publicly, and the proposal of components to evaluate. Every number in section 4 came from probe scripts run against `silver.*`. Those scripts are no longer in the tree (see section 10 to recover them).

## 1. Summary

- **The challenge requires evaluating at least one learned component against an appropriate baseline**, but it **accepts pretrained or retrieval-based components**: you demonstrate it through component selection, intent labels, representations, leakage prevention and evaluation on a held-out set. Training your own model is not required.
- **The data holds almost no predictive signal.** Fraud, SLA breach, repeat complaints, resolution delay, escalation, wait time and abandonment are predicted no better than chance (AUC 0.49 to 0.50, R² 0.00) with a gradient boosting model and a temporal split.
- **The only real, clean signal** is that the contact reason (`contact_reason`, 6 values) explains whether a call is resolved (AUC 0.76) and, to a lesser degree, later dissatisfaction (AUC 0.65). It amounts to a table of rates by reason, and a complex model adds nothing.
- **There are two leakage traps in the data:** `fraud_score` (generated from the label) and the columns measured after the call (sentiment, duration).
- **There are no labels for "which transaction was disputed"**, no natural duplicate transactions, and no text with real intent (the texts are templates, 100% Spanish, no Portuguese). Anything that depends on those needs team-generated data.
- **Proposal:** components that can be evaluated with labels that are valid by construction (a team-generated set, labeled as such): (A) intent and language classification, es/pt, with confidence and abstention; (B) identifying the disputed transaction from a free-text description; (C) a priority calibrated by contact reason as a secondary signal. **Executed (2026-10-04, §12):** A and B were measured against a baseline on our own held-out set. A was integrated with abstention, and B was integrated only as an ordering of the ambiguous pool. The LLM run of A is in [Evaluation](EVALUATION.md). TypeSafe's Jev was never evaluated (no key was ever available), and the code that called it was removed.

## 2. What the challenge asks for (`docs/challenge/Factored AI & Data Hackathon 2026.md`)

- Line 23: pick a bounded problem, use the data to explain why it matters, **establish a baseline** and measure whether the approach improves service quality and operational efficiency.
- Line 46 (criterion 4, "solid data and ML"): a repeatable pipeline with contracts, quality checks, lineage and a freshness policy. **Evaluate at least one learned component against an appropriate baseline.** Use valid labels or relevance judgments and prevent leakage.
- Line 54: for a pretrained or retrieval-based solution, demonstrate those skills with **component selection, relevance or intent labels, representations, leakage prevention, evaluation on a held-out set**.
- Line 68: compare the baseline and the proposed system **on the same held-out workload**. Report the number and mix of cases, label quality, model and prompt versions, variability across repeated runs, and **include the failures**. If a model acts as a judge, validate it.
- Metrics the challenge asks for: safe automatic resolution, containment, escalation quality, unsafe outcomes, latency and cost (p50 and p95).
- Portuguese: the dataset has no Portuguese rows, and the system must receive and answer it all the same (a limit to document).

## 3. What data there is (relevant to ML)

Provenance: everything is **synthetic and from the organizer** (see [Data](DATA.md), "Provenance"). Whatever the team generates is labeled separately as "team-generated".

| Table (silver) | Rows | Relevant to |
|---|---|---|
| `stg_transactions` | 4,425,008 | disputes. It carries `is_fraud` and `fraud_score` (only in silver, not in gold) |
| `stg_complaints` | 67,095 | complaints. `description` and `resolution` are template text. `affected_product_id` points to another customer's product in 100% of cases |
| `stg_call_center_interactions` | 686,296 | `contact_reason` (== `reason_category`, 6 values), `was_resolved`, `was_escalated`, `requires_followup`, sentiment, duration, wait |
| `stg_call_transcripts` | 171,321 | template text, 95% intent `consulta_general`, 100% Spanish |
| `stg_satisfaction_surveys` | 212,759 (CSAT 127,856; NPS 63,668; CES 21,235) | links 100% to an interaction (`interaction_id`) |
| `stg_customers` | 150,000 | status: Active 127,700, Inactive 14,914, Suspended 4,407, Closed 2,979 |

Related project rules ([Criteria](CRITERIA.md), `AGENTS.md`): `is_fraud` and `fraud_score` are never agent inputs, and the agent reaches data only through the backend.

## 4. Measurements

Common method: scikit-learn gradient boosting (`HistGradientBoosting`), **a 70/30 temporal split** (train on the oldest data, test on the most recent), AUC as the metric on the final 30%. An AUC of 0.50 equals chance. Unless noted, columns that come after the outcome are excluded from the features.

### 4.1 Fraud (`is_fraud`)

- 4,425,008 transactions, 4,316 frauds (0.10%). The rate is the same in Approved, Declined, Pending and Reversed (0.08% to 0.10%).
- Sample: all frauds plus 20% of the rest (887,674 rows). Training has 3,123 positives and the test has 1,193.
- Features: amount, amount in USD, currency, channel, transaction type and category, merchant category, transaction country, status, response code, hour, day of week, country different from the customer's, segment, credit score, product type.
- **Result: AUC 0.491, PR-AUC 0.0043 against 0.0045 for the random baseline.** The amount alone gives 0.497. No variable moves the fraud rate beyond 0.0039 to 0.0061 (noise).

### 4.2 `fraud_score` is an artifact of the label (leakage by construction)

- The scale is 0 to 100 (not 0 to 1). It is null in 885,157 transactions (20%).
- **Non-fraudulent** transactions have a score between 0 and 30 (average 15.0). Fraudulent ones have between 0.01 and 99.99 (average 49.5).
- **All 2,373 transactions with a score above 30 are fraud, and none are non-fraudulent.** That covers 55% of the frauds (2,373 of 4,316).
- The other 1,943 frauds (1,052 with a score of 30 or less, 891 with no score) cannot be told apart from the non-fraudulent ones by any variable.
- Reading: the score was generated conditioned on the label. Calibrating it or putting a threshold on it "learns" a rule already embedded in the data, and violates the challenge's rule against using `is_fraud` as an input to what the system is supposed to detect. Another public team presents it as a 37% improvement over a fixed threshold. We dropped it and documented it.

### 4.3 Complaints (`stg_complaints`, n = 67,095, split by `creation_date`)

| Target | Rate | AUC |
|---|---|---|
| `sla_breached` | 0.201 | 0.501 |
| `is_repeat_complainer` | 0.150 | 0.493 |
| resolution delay above the median (n = 15,363, resolved only) | 0.471 | 0.494 |

`compensation_granted > 0` (4,641 positives) was not evaluated: the script skipped it because of a filtering error in the test, and it remains pending. `requires_followup` does not exist in complaints.

### 4.4 Calls (`stg_call_center_interactions`, n = 686,296, split by `interaction_date`)

| Target | Rate | AUC |
|---|---|---|
| `was_escalated` | 0.100 | **0.499** |
| `was_resolved` | 0.766 | 0.764 |
| `requires_followup` | 0.348 | 0.677 |
| duration above the median | 0.428 | 0.880 (which column explains it was not broken down) |

Which variables explain `was_resolved` (AUC of a single-variable model, 30% sample):

| Variable | AUC | Note |
|---|---|---|
| `contact_reason` / `reason_category` | 0.764 | Transactional 91.5%, Product 89.5%, Technical 69.6%, Commercial 65.8%, Retention 60.1%, **Complaint 43.7%** |
| `duration_seconds` | 0.678 | **measured during or after the call: leakage** |
| `detected_sentiment` / `sentiment_score` | 0.613 / 0.611 | **after the fact: leakage.** Neutral resolves 82.6% and the other four sentiments about 64% |
| `interaction_type`, `channel` | ~0.50 | flat (76% to 77%) |
| `agent_used_accent` | 0.503 | no signal |

For `requires_followup` the order is the same (reason 0.679, duration 0.621, sentiment 0.576).

Conclusion: the only pre-call signal is the contact reason, with 6 categories. A GBM does not beat a table of rates by reason.

### 4.5 Surveys, wait and abandonment

- **Surveys, `main_score <= 3` over all surveys: AUC 0.959. Invalid result.** It mixes three different scales (CSAT, NPS, CES) and keeps columns derived from the score. It was redone restricted to CSAT (see 4.7).
- Natural duplicates: **zero pairs** (same customer, merchant and amount, in one day) in June 2025. The "duplicate charge" case would exist only if we injected it.

### 4.6 Texts

According to [Data](DATA.md): complaint descriptions and resolutions are 5 template phrases (one per category). Transcripts are templates, 95% with the intent `consulta_general`, and 100% Spanish. They are no use for training an intent classifier or for validating Portuguese.

### 4.7 CSAT, wait time and customer churn

- **Dissatisfied CSAT (`main_score <= 2`, only CSAT surveys linked to their interaction, n = 127,856, rate 0.313).** In CSAT the scores take only the values 1 to 4 (4,422; 35,646; 73,313; 14,475), not 1 to 7. With all the interaction's variables, AUC is 0.794, but almost all of it comes from after-the-fact outcomes: `was_resolved` alone gives 0.792 and `requires_followup` 0.748 (both are known after the call: leakage). With **only pre-call variables** (interaction type, channel, reason, wait, country, segment, credit score), AUC is **0.653**, and almost all of it is the contact reason (0.655). The same pattern as in 4.4.
- **Wait time** (`wait_time_seconds`, mean 120 s, standard deviation 59 s) from type, channel, reason, hour and day: **R² = 0.00**. No variable explains it.
- **Churn** (`Closed` or `Inactive` against `Active`, rate 0.119) from segment, country, credit score, income, number of products, complaints and calls: **AUC 0.503**. No signal.

### 4.8 CreditGuard's delinquency model (credit proposal, option D)

The dropped credit proposal (see [Workflow](WORKFLOW.md)) suggested a LightGBM per-customer delinquency probability against a score baseline. It was repeated with a split by customer:

| Test | Result |
|---|---|
| Per product (125,317 products with a credit limit, delinquency 14.3%) with all variables | AUC 0.504 |
| Per product, a single variable (score, utilization, segment, rate, status, type) | AUC 0.497 to 0.503 |
| Per customer (84,970 customers, delinquency 19.8%), all variables | AUC 0.635 |
| Per customer, without the number of products | AUC 0.519 |
| Per customer, only the number of products | AUC 0.631 |
| The proposal's baseline (score below 620 or utilization above 80%) | AUC 0.504 |

Delinquency per customer by number of products: 14.0% (1), 27.1% (2), 37.3% (3), 45.3% (4), 53.6% (5). This matches an independent 14.3% probability per product: 1 minus 0.857 to the power k gives 14%, 27%, 37%, 46%, 54%. So **the signal is an aggregation artifact**: the model counts products. A table of rates by number of products matches it, so it is not a component that beats an appropriate baseline. It is also outside workflow A, and the challenge does not authorize live credit decisions. It is documented as a negative result.

## 5. Leakage and traps (checklist for any model)

1. `is_fraud` and `fraud_score`: never as a feature and never as a component that "detects" fraud.
2. Columns that come after the fact: `duration_seconds`, `detected_sentiment`, `sentiment_score`, `was_resolved`, `resolution`, `resolution_date`, `resolution_days`, complaint `status`. Do not use them to predict the outcome.
3. Mixed survey scales (CSAT, NPS, CES): separate by `survey_type`. In CSAT the score runs from 1 to 4. `was_resolved` and `requires_followup` cannot predict satisfaction (they come after).
4. Splits: always temporal. Test customers must not appear in training when the target is per customer.
5. A complaint's `affected_product_id` does not belong to the customer (100%), so it cannot link a complaint to a transaction or product.
6. There is no "disputed transaction" label: every dispute evaluation uses team-generated cases.

## 6. What other teams did (public repositories, as a reference only)

Teams in this same hackathon published their repositories. The following was taken from the public READMEs. It was not verified and no code is reused.

- **Dispute priority at intake** with a RandomForest. They report macro-F1 of 0.245 against 0.166 for the majority class, with a chronological split and 11,543 training cases. They themselves call it a "modest improvement". They state that part of the demo customer's history is synthetic and that there is no Portuguese.
- **Isotonic calibration of `fraud_score`:** they say it catches 281 of 494 frauds with 100% precision, 37% better than the bank's fixed threshold. It is the artifact in section 4.2.
- Another team mentions a "label validity study" and a calibrated decision layer with a deterministic policy, with no visible detail.
- Common to all: synthetic or mixed evaluation cases, no Portuguese in the data, a deterministic policy engine, typed LLM output.

## 7. Proposed components

Principle: choose components that have **labels valid by construction** (we write them, or derive them from real records with controlled noise), and always compare against a simple baseline on the same held-out set.

### A. Intent and language of the query (es/pt), with confidence and abstention

- Input: the customer's message. Output: intent (unrecognized charge, charge for a declined or reversed transaction, duplicate, wrong amount, status query, out of scope), language (es, pt, other), ambiguity, urgency, and whether there is an attempt to manipulate the agent.
- Candidates: (1) keywords and rules with dictionary language detection (the baseline), (2) a local classifier on multilingual embeddings, (3) TypeSafe's Jev, (4) an LLM with structured output.
- Value: it is the input to the guardrail's policy. The challenge requires Spanish and Portuguese. It allows measuring calibration and abstention.
- Risk: it is an easy task. The value is in the **hard set**: ambiguous messages, mixed Spanish and Portuguese, out of scope, instruction injection, missing data, typos.

### B. Identify the disputed transaction from a free-text description

- Input: text ("they charged me about 500 pesos at such a merchant last week") plus the customer's transactions. Output: a ranking of candidates.
- Labels: take a real transaction, generate the description with noise (approximate amount, misspelled name, vague date) and verify recovery. Valid by construction, labeled as "team-generated".
- Baseline: exact or rule-based matching (merchant, exact amount). Model: merchant text similarity plus a ranker (GBM) with amount closeness, date, status and merchant.
- Metric: hit at first place and at the top three, on held-out customers.
- Reference in the dispute literature: a weighted sum of matching descriptors (merchant, amount, date, currency) over a threshold.

### C. Escalation priority calibrated by contact reason

- Trained on the 686 thousand calls, temporal split, a pre-call feature: the contact reason. It measures the Brier score against the global rate.
- Modest and explainable. It serves as a secondary handoff signal, never as a decision.

### Dropped with evidence (for the slides)

CreditGuard's delinquency model (section 4.8): AUC 0.504 per product, and the 0.635 per customer is only the product count.

Fraud, SLA breach, repeat complaints, resolution delay, call escalation, wait time and churn: AUC 0.49 to 0.50 (R² 0.00 for wait). `fraud_score`: leakage by construction. Duplicates: they do not exist naturally. Saying so with the numbers is part of the rigor score.

## 8. Jev (TypeSafe)

References: [intent routing](https://docs.typesafe.ai/patterns/intent-routing), [use-case map](https://docs.typesafe.ai/concepts/use-case-map), [models](https://docs.typesafe.ai/models.md), [Jev 1.13 limitations](https://docs.typesafe.ai/model-jaggedness/jev-1.13.md), [quickstart](https://docs.typesafe.ai/introduction/quickstart.md).

- What it is: a hosted classifier (Jev 1.13). Python SDK `pip install typesafe-sdk`, with the API key in the `TYPESAFE_API_KEY` variable (console `console.typesafe.ai/keys`).
- Use: `client.system_one(state=<text>, questions={...})` with `Choice` questions (one option among several), `Score` (a level on a scale) and `Noul` (a yes or no probability). It evaluates all of them in parallel in one call. Each answer carries confidence and probabilities. The recommended pattern is "code decides": if confidence is below a threshold, escalate to a human.
- Cost and limits: 42 USD per billion input tokens, output free. 40 requests per second, 100,000 tokens per second, a 64,000-token context. Declared latency of about 150 ms.
- Privacy: they state they do not train on customer data, with zero retention for enterprise customers.
- Declared limitations: English performs best and other languages are "handled, but not as well" (they recommend testing with your own content). It is **not robust against prompt injection**. It is unreliable with numbers, dates and comparisons. It does badly on multi-step reasoning. The probabilities of `Choice` and `Noul` are not directly comparable. Large irrelevant context degrades accuracy.
- Implications: the defense against injection has to be another, deterministic layer. Amounts and dates are resolved by code. The system has to keep working without the key (a local alternative, bounded retries, a safe fallback). Only simulated customers' messages are sent to an external service, never database records.
- Decision: by measurement and not by opinion, comparing against the local alternatives on the same held-out set and by language. No key was ever available, so it was not measured and the code was removed.

## 9. Evaluation design (proposal)

1. A **held-out set** generated by the team and labeled "team-generated": normal, ambiguous, escalation, out-of-scope, injection, expired-session and missing-data cases, in Spanish and Portuguese, with the same workload for the baseline and the system. Report the number and mix of cases and the label quality (double review of a sample).
2. **Component metrics (A):** precision and macro-F1 by intent and language, recall on out of scope and on injection, false "resolve", calibration (confidence against accuracy, ECE), p50 and p95 latency and cost.
3. **Component metrics (B):** hit at first and third place, by noise type and by currency.
4. **System metrics (the challenge's):** safe automatic resolution, containment, escalation quality, unsafe outcomes, latency and cost.
5. **Reproducibility:** pin model and prompt versions, repeat runs to measure variability, and report the failures.
6. **Validity:** if an LLM acts as a judge, validate it against human labels on a sample.

## 10. Reproducing the measurements

The probe scripts (`fraud_probe.py`, `target_scan.py`, `cc_drivers.py`, `more_probes.py`, `credit_probe.py`) were removed from the tree when the documentation was consolidated. They are in the git history, under `ml/probes/` in the commit before `f97a119`. They read the connection from the `DBT_PG_*` environment variables, hold no credentials and only read from `silver.*`:

```bash
git ls-tree --name-only f97a119^ ml/probes/   # list them
git checkout f97a119^ -- ml/probes            # restore them
python -m venv .venv && .venv/bin/pip install scikit-learn pandas numpy psycopg2-binary
export $(cat data/dbt/.env | xargs)   # DBT_PG_HOST, DBT_PG_PORT, DBT_PG_USER, DBT_PG_PASSWORD, DBT_PG_DATABASE
```

The scripts expect a file with `export KEY=value` lines named in the `ENVF` variable (for example `ENVF=data/dbt/.env`).

| Script | What it measures |
|---|---|
| `fraud_probe.py` | section 4.1: fraud with a GBM and a temporal split |
| `target_scan.py` | sections 4.3, 4.4 and 4.5: complaint, call and survey targets |
| `cc_drivers.py` | section 4.4: variables that explain `was_resolved` and `requires_followup` |
| `more_probes.py` | section 4.7: CSAT (threshold 2), wait and churn |
| `credit_probe.py` | section 4.8: CreditGuard's delinquency model per product and per customer |

The `fraud_score` figures (section 4.2) come from direct SQL queries on `silver.stg_transactions` (threshold 30, counts per label).

## 11. Open questions for the ML engineer

Decided answers (2026-10-04, see §12 for the execution):

1. Pretrained accepted: **yes** (the document's line 54 allows it expressly).
2. Set: **at least 60 cases per normal cell in A (40 in test), at least 50 per noise type in B**, with an automatic second-lexicon checker plus a 10% sample for manual double review, adversaries included.
3. Component B: **it came into scope**, measured and partly integrated (it only orders).
4. Confidence threshold: `INTENT_MIN_CONFIDENCE=0.5` by default. The fine calibration with an asymmetric cost (false auto-resolve 5 : over-escalate 1) runs with the team's LLM key on dev.
5. Published set: **yes**, `ml/eval/data/*.jsonl`, synthetic, with no PII and no fraud columns.
6. `fraud_score`: it stays **dropped**. The leakage is documented in §4.2.

## 12. Executed evaluation of components A and B (2026-10-04)

A team-generated held-out set (`ml/eval/data/`, seed 20261004, reproducible, with no PII and no `is_fraud` or `fraud_score`, which the generators verify). The harness is in `ml/eval/eval_intent.py` and `ml/eval/eval_ranker.py`, and the reports with failures included are in `ml/eval/reports/`. The test never adjusts prompts or thresholds: calibration runs only on dev (A) or train (B).

### 12.1 Component A: intent and language (840 messages, 552 test)

Candidates: the production baseline (keywords plus es/pt substring), a structured LLM with confidence (OpenRouter, temperature 0, JSON output) and local embeddings plus logistic regression (optional). The tables below are the baseline's numbers on test. The LLM run on the system's own sets is in [Evaluation](EVALUATION.md). It has not been run on this set.

| Metric | Baseline (test, n=552) |
|---|---|
| intent accuracy | 0.681 |
| intent macro-F1 | 0.677 |
| out_of_scope recall | 0.735 |
| false "dispute" (false auto-resolve) | 36 (traps + ambiguous) |
| manipulation caught (not dispute) | 0.889 |
| language es / pt / mixed | 1.000 / 0.283 / 0.000 |
| latency p50/p95 (ms) | 0.01 / 0.017 |

Reading: the baseline is perfect on template Spanish, **fails on real Portuguese (0.283) and cannot produce "mixed" (0.000)**, and it falls for the traps that use dispute vocabulary ("does the ATM charge a fee?" gives dispute). That is where the confidence-aware component earns its value: abstention (`confidence < INTENT_MIN_CONFIDENCE`) escalates in `decide` by a code rule, always after the deterministic fraud override.

Integration (`agent/app/intents.py`, `agent/app/graph.py`): `classify_detailed` returns {intent, language, confidence, source, abstain}. The trace records the component, the prompt version, the confidence, the classifier latency and the node's total latency. Without a key or without valid JSON it falls back to the baseline with the usual behavior (no abstention). A confirmation "yes" overrides abstention. Tests: `agent/tests/test_intents.py` (no LLM).

### 12.2 Component B: the disputed transaction (399 cases, 193 test)

A synthetic candidate pool with the measured distributions (statuses 92/5/2/1, null merchant 76.7%, null effective USD ~57%, see [Data](DATA.md)). Candidates: the production baseline (`narrow_candidates` plus ordering by date), an interpretable weighted sum (difflib + amount + date + channel) and a light GBM trained on train (split by customer).

| Metric (test, n=193) | baseline | weighted | GBM |
|---|---|---|---|
| top-1 (labeled) | 0.259 | 0.559 | **0.729** |
| top-3 (labeled) | 0.277 | 0.900 | 0.900 |
| correct "not found" (unrelated) | **0.870** | 0.000 | 0.609 |
| false empties (labeled) | 0.582 | 0.006 | 0.059 |
| reordering the baseline's pool: pool 2+ (n=25) | 0.040 (date) | **0.600** | 0.600 |
| reordering the pool: pool 1 (n=46) | 0.935 | 0.935 (same by construction) | 0.935 |

Key readings:

- The baseline is **conservative by design**. Faced with an amount off by ±10-20%, it reduces to empty 58% of the labeled cases (it asks to clarify, which is safe but does not identify) and it gets 93% right when it leaves exactly one candidate.
- **Integration decision (conditional, fulfilled):** the weighted ranker (stdlib, `agent/app/ranking.py`) comes in **only to order** the pool with 2+ candidates in `decide` (`graph.py`), where ordering by date is right 4% of the time and the ranker 60%. The 0/1/2+ decision remains `narrow_candidates`, `is_corroborated` does not change, and "not found" is identical to the baseline by construction. **The ranker orders and does not authorize.**
- The GBM (0.729 global top-1) is **not integrated**: it needs scikit-learn in the agent image, and its standalone "not found" (0.609) degrades the baseline's 0.870. It stays documented as a result: better global ranking, worse defense against claims about nonexistent transactions.
- The standalone weighted ranker does not work as a substitute for narrowing (its "not found" is 0.000), which is why the integration is ordering only.

Honest limits: the pool is synthetic (this environment had no database credentials; `gen_dispute_set.py` accepts `--source duckdb:` or `--source postgres` to regenerate it with real `gold` transactions). The ranker's "not found" floor was calibrated on train. The LLM cost is computed from `usage.cost` or from configured per-million rates for a fixed model, and stays N/A without a key or rates. The intent set has the double-review sample marked and pending the human pass. The complete failures are in `ml/eval/reports/*_failures_*.jsonl`.
