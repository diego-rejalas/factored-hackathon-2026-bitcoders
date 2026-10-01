{% docs __overview__ %}
# LATAM Bank data platform (dbt project `latam_bank`)

Data layer of an AI-first banking customer-service prototype. It turns the organizer-provided **synthetic** LATAM Bank dataset (CSV files on S3; Mexico, Colombia and Argentina) into typed, tested tables that the backend tool layer reads. The agent never queries Postgres directly; the backend reads `gold` only, with a read-only role.

## Data flow

| Layer | Schema | Built by | Content |
|---|---|---|---|
| S3 | read-only bucket | organizer | One CSV table each (daily files for the partitioned tables) |
| Bronze | `bronze` | Airflow DAG `latam_bank_pipeline` (DuckDB) | Faithful copy, every column as text, plus `_source_key` and `_ingested_at`. Read only by dbt. |
| Silver | `silver` | dbt `stg_*` views | Typed view per bronze table: real types, empty strings as NULL, 'Mexico' conformed to 'México' where the macro is applied. Carries the data tests. |
| Gold | `gold` | dbt tables | Backend-ready `customers`, `products`, `transactions`, `complaints`, `call_center_interactions`. Enforced contracts, indexed by customer. |

`dbt build` tests each model before its dependents: if a silver test fails, gold is not rebuilt and keeps the last valid data.

## Where facts live

- Descriptions hold only stable facts: meaning, grain, keys, units, meaning of NULL.
- Allowed values of a categorical column are enforced by `accepted_values` tests (warn severity where the source is known to drift or be dirty); descriptions list the values without counts.
- Known data defects are covered by warn-severity tests where possible and summarised, without numbers, in each model's `meta.data_quality`.
- Counts, null percentages, distinct values and min/max are never typed in prose; query the data for them.

## Freshness policy

The data is a **static, closed snapshot** (no late arrivals, no schema changes between dates). Updates are an **on-demand full reload**: the DAG is triggered by hand, bronze is rebuilt from S3, and gold is rebuilt only if the silver tests pass. "Fresh" means the time of the last successful run, stored in `ops.etl_runs` and exposed by the backend at `GET /meta/data`.

## Leakage rule

`is_fraud` and `fraud_score` are evaluation ground truth. They exist only in the silver model `stg_transactions` and are excluded from gold. Never use them as input of the agent, its tools or any trained component.

## Columns not to use (known data defects)

| Column | Why |
|---|---|
| `customers.registration_branch_id` | Does not join to `branches`. |
| `complaints.affected_product_id` | Belongs to another customer (random assignment). |
| `complaints.origin_interaction_id` | Always empty. |
| `complaints.claimed_amount` | Matches no transaction and is not scaled by currency. |
| `complaints.description`, `complaints.resolution`, `call_transcripts` text and `detected_intents` | Templated text, not real free text. |
| `call_center_interactions.contact_reason` | Identical to `reason_category`. |
| `products.currency`, `transactions.currency` | Never MXN; Mexican customers always appear in USD. |
| `transactions.amount_usd` | NULL for USD rows and some ARS and COP rows; derive it with `daily_exchange_rates`. |
| `transactions.latitude`, `transactions.longitude`, `branches.latitude`, `branches.longitude` | Many values near zero, inconsistent with the country. |
| `branches.geographic_zone`, `has_atms`, `has_teller_windows` | Constant. |
| `service_agents.assigned_branch_id` | Mostly does not exist in `branches`. |

## Conventions

- Descriptions are short: meaning, grain, primary key, role. Data-quality notes live in `meta.data_quality`, without numbers.
- Category labels are in Spanish exactly as delivered (for example `Cuenta Ahorro`); descriptions gloss them in English.
- Columns with personal data are tagged `meta.contains_pii: true`; all of that data is fictitious.
- `marketing_campaigns`, `campaign_sends`, `digital_events`, `call_transcripts` and `satisfaction_surveys` are documented but not exposed in gold.
{% enddocs %}

{% docs customer_id_fk %}
Customer the record belongs to. References `customers.customer_id`. Format `CLI-` followed by 12 uppercase alphanumeric characters.
{% enddocs %}

{% docs product_id_fk %}
Bank product the record refers to. References `products.product_id`. Format `PRD-` followed by 12 uppercase alphanumeric characters.
{% enddocs %}

{% docs branch_id_fk %}
Branch the record refers to. References `branches.branch_id`. Format `SUC-` followed by 8 uppercase alphanumeric characters.
{% enddocs %}

{% docs agent_id_fk %}
Service agent the record refers to. References `service_agents.agent_id`. Format `AGT-` followed by 10 uppercase alphanumeric characters.
{% enddocs %}

{% docs interaction_id_fk %}
Contact-center interaction the record refers to. References `call_center_interactions.interaction_id`. Format `INT-` followed by 16 uppercase alphanumeric characters.
{% enddocs %}

{% docs process_date_partition %}
Date of the daily source file the row was read from (the dataset is delivered as one CSV per day). It is a load partition, not the business event time: use the timestamp column of the table for that.
{% enddocs %}

{% docs country_name %}
Country name in Spanish: `México`, `Colombia` or `Argentina`. The source spells Mexico two ways; silver conforms it to 'México' with the `normalize_country` macro where applied.
{% enddocs %}

{% docs ts_no_tz %}
Stored without time zone; the dataset does not state which zone it uses.
{% enddocs %}

{% docs pii_synthetic %}
Personal data by nature (PII) but fictitious: the dataset is synthetic and no value belongs to a real person.
{% enddocs %}

{% docs fraud_ground_truth %}
Fraud evaluation ground truth, never an agent input; excluded from gold (silver `stg_transactions` only).
{% enddocs %}

{% docs bronze_source_key %}
S3 object (full key, including the day partition) the row was read from. Row-level lineage added by the loader; not part of the organizer dataset.
{% enddocs %}

{% docs bronze_ingested_at %}
Timestamp at which the loader wrote the row into bronze. Lineage column added by the loader; not part of the organizer dataset.
{% enddocs %}
