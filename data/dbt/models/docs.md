{% docs __overview__ %}
# LATAM Bank data platform (dbt project `latam_bank`)

Data layer of an AI-first banking customer-service prototype. It turns the organizer-provided **synthetic** LATAM Bank dataset (v1.0.0, 13 tables as CSV files on S3, Mexico, Colombia and Argentina) into typed, tested tables that the backend tool layer reads. The agent never queries Postgres directly; it goes through the backend, which reads `gold` only with a read-only role.

## Data flow

| Layer | Schema | Built by | Content |
|---|---|---|---|
| S3 | read-only bucket | organizer | 13 CSV tables, one file per day for the 7 partitioned tables |
| Bronze | `bronze` | Airflow DAG `latam_bank_pipeline` with DuckDB (`read_csv` straight into Postgres) | Faithful copy of the 13 tables, every column as text, plus `_source_key` and `_ingested_at` for lineage. Nothing reads bronze except dbt. |
| Silver | `silver` | dbt, models `stg_*` (views) | One typed view per bronze table: real data types, empty strings turned into NULL, 'Mexico' conformed to 'México' where the macro is applied. Carries the data tests (keys, relationships, accepted values, ranges, business rules). |
| Gold | `gold` | dbt, tables | Five backend-ready tables: `customers`, `products`, `transactions`, `complaints`, `call_center_interactions`. Enforced contracts (types and primary keys), indexed by customer. |

Gold is a pass-through of silver today; the business joins arrive with the chosen workflow. `dbt build` tests each model before building its dependents: if a silver test fails, gold is not rebuilt and keeps the last valid data.

## Freshness policy

- The data is a **static, closed snapshot**: facts run from 2023-06-17 to 2026-06-18 and nothing new arrives. There are no late arrivals (`process_date` minus `transaction_date` is 0 or -1 day) and no schema changes between dates.
- Updates are an **on-demand full reload** (the DAG is triggered by hand, no schedule). Each run rebuilds bronze from S3, and gold is only rebuilt if the silver tests pass.
- "Fresh" therefore means the time of the last successful run, stored in `ops.etl_runs` and exposed by the backend at `GET /meta/data`. There is no age threshold to monitor because the source does not change.

## Leakage rule

`is_fraud` and `fraud_score` are evaluation ground truth. They exist only in the silver model `stg_transactions` and are excluded from gold, so neither the backend nor the agent can see them. Never use them as input of the agent, its tools or any trained component.

## Columns not to use (known data defects)

| Column | Why |
|---|---|
| `customers.registration_branch_id` | 149,995 of 150,000 values do not exist in `branches`. |
| `complaints.affected_product_id` | Belongs to another customer in 100% of the 44,570 rows that have it (random assignment). |
| `complaints.origin_interaction_id` | Empty in all 67,095 rows. |
| `complaints.claimed_amount` | Matches no transaction (0 of 21,751) and is not scaled by currency. |
| `complaints.description`, `complaints.resolution`, `call_transcripts` text and `detected_intents` | Templated text with 5 to 546 distinct values and a single intent; not real free text. |
| `call_center_interactions.contact_reason` | Identical to `reason_category` in every row. |
| `products.currency`, `transactions.currency` | Never MXN, although half of the customers are Mexican; Mexican customers always appear in USD. |
| `transactions.amount_usd` | NULL for all USD rows and 5% of ARS and COP rows; derive it with `daily_exchange_rates`. |
| `transactions.latitude`, `transactions.longitude`, `branches.latitude`, `branches.longitude` | Many values close to zero, inconsistent with the country. |
| `branches.geographic_zone`, `has_atms`, `has_teller_windows` | Constant in all 350 rows. |
| `service_agents.assigned_branch_id` | 831 of 833 values do not exist in `branches`. |

## Conventions

- Descriptions follow the pattern purpose, grain, primary key, source, coverage and how we use it. Measured data-quality findings are kept out of the prose, in each model's `meta.data_quality` list.
- Category labels are in Spanish exactly as delivered (for example `Cuenta Ahorro`, `Transaccional`); descriptions translate them.
- Counts and percentages were measured on the full load of 2026-09-30.
- Columns with personal data are tagged `meta.contains_pii: true`; all of that data is fictitious.
- Tables outside the customer-service scope (`marketing_campaigns`, `campaign_sends`, `digital_events`) are documented but not exposed in gold.
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
Date of the daily source file the row was read from (the dataset is delivered as one CSV per day, 1,097 days from 2023-06-17 to 2026-06-17). It is a load partition, not the business event time: use the timestamp column of the table for that.
{% enddocs %}

{% docs country_name %}
Country name in Spanish: `México`, `Colombia` or `Argentina`. The source spells Mexico both 'Mexico' and 'México' depending on the table; where silver applies the `normalize_country` macro it is conformed to 'México'.
{% enddocs %}

{% docs ts_no_tz %}
Stored without time zone; the dataset does not state which zone it uses.
{% enddocs %}

{% docs pii_synthetic %}
Personal data by nature (PII) but fictitious: the dataset is synthetic and no value belongs to a real person.
{% enddocs %}

{% docs fraud_ground_truth %}
Evaluation ground truth for fraud, present only in the silver model `stg_transactions` and excluded from gold. It must never be an input of the agent, its tools or any model (it would be label leakage); use it only to build evaluation sets.
{% enddocs %}

{% docs bronze_source_key %}
S3 object (full key, including the day partition) the row was read from. Row-level lineage added by the loader; not part of the organizer dataset.
{% enddocs %}

{% docs bronze_ingested_at %}
Timestamp at which the loader wrote the row into bronze. Lineage column added by the loader; not part of the organizer dataset.
{% enddocs %}
