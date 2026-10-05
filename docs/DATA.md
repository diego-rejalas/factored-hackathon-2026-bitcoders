# Data

*What the LATAM Bank dataset contains, what was verified at full scale and which limits change the design.*

[Index](README.md) · [Workflow](WORKFLOW.md) · [Architecture](ARCHITECTURE.md)

## Provenance

Everything that enters the system is **synthetic and supplied by the organizer**: the LATAM Bank dataset v1.0.0, 13 tables in a read-only S3 bucket. There is no real or de-identified data. Names, ID numbers, phone numbers and emails are fictitious. Anything the team generates (evaluation cases, user utterances) is labeled separately as team-generated.

## Volumes

Loaded and verified against S3, table by table.

| Table | Rows | | Table | Rows |
|---|---:|---|---|---:|
| `digital_events` | 15,620,994 | | `call_transcripts` | 171,321 |
| `transactions` | 4,425,008 | | `customers` | 150,000 |
| `campaign_sends` | 1,746,801 | | `complaints` | 67,095 |
| `call_center_interactions` | 686,296 | | `daily_exchange_rates` | 13,164 |
| `products` | 400,000 | | `service_agents` / `branches` / `marketing_campaigns` | 1,200 / 350 / 200 |
| `satisfaction_surveys` | 212,759 | | **Total** | **~23.5 million** |

The figures in the organizer's summary are nominal and do not match the contents (for example, ~5 million transactions and ~10 million events). The rows read from the CSV files were verified to be identical to the ones loaded into the 13 tables. Each partitioned table has 1,097 files (one per day), except `campaign_sends`, which has 1,083. All files of a table share a single header, so there are no schema changes between dates.

## What changed the design

| Finding | Evidence | Consequence |
|---|---|---|
| **Historical text is templated** | `call_transcripts`: 95% share the same intent, `consulta_general`; `complaints.description` is always `"Queja relacionada con {category}"` | An intent classifier cannot be trained or evaluated on the historical text. The live conversation text and the structured fields serve as the baseline |
| **There are no exact duplicates** | 0 repeated `transaction_id`; 0 groups with the same customer, amount and merchant | The "duplicate charge" case was dropped. The auto-resolved case became a `Declined` or `Reversed` transaction that the customer believes was charged: **266 thousand** candidates |
| **`affected_product_id` is unusable** | It points to another customer's product in 44,570 of 44,570 complaints with a value | The transaction of a dispute never comes from `complaints` |
| **Ownership is reliable** | Transaction to product to customer: 4,425,008 of 4,425,008 consistent | It is the basis for authorizing access to a customer's own transactions |
| **There is no MXN** | 0 MXN rows in transactions and products, although 49.9% of customers are Mexican. The MXN pair does exist in exchange rates | Documented, not converted. Mexico has 66,236 credit products, all in USD |
| **`amount_usd` is null in 57%** | 100% null when the currency is USD (the amount is already in dollars) and ~5% in ARS and COP | `amount_effective_usd` is derived. If it is unknown, it never counts as zero |
| **`merchant_name` is null in 76.7%** | Measured on transactions | Identification uses approximate amount, date and status. The merchant helps only when present |
| **`is_fraud` and `fraud_score` are ground truth** | ~0.13% of transactions flagged as fraud in a sample | They are never agent inputs, since that would leak labels |
| **There is no Portuguese in the data** | No table has it, neither customers nor transcripts. Only 129 of 1,200 agents speak Portuguese | Portuguese is handled in the agent layer |
| **A decline is not explained by the product** | All 4,425,008 transactions sit on `Active` products | Explaining a decline is limited to the meaning of the response code |

## Transactions

- Statuses: `Approved` 91.99%, `Declined` 5.00%, `Pending` 2.00%, `Reversed` 1.01%.
- Decline codes are split almost evenly between `51` (insufficient funds), `14` (invalid card), `54` (expired card) and `05` (not authorized by the issuer), and empty in ~5%. The meanings come from the ISO 8583 standard and are a team assumption: the organizer does not define the codes.
- Coverage runs from 2023-06-17 to 2026-06-18, a closed snapshot. There are no late arrivals (`process_date - transaction_date` is 0 or -1 day, never positive).

## No predictive signal for delinquency

On `products` and `customers`, delinquency (30 or more days past due, or blocked or suspended) is flat against `credit_score` (17.4% with a score below 550; 16.6% with 780 or more), income and utilization. The correlation between `credit_score` and `days_past_due` is -0.004. A credit risk model on this data would have nothing to learn. There are also no eligibility rules approved by the organizer, so any credit policy would be synthetic.

## Other recorded limits

| Table | Limit |
|---|---|
| `customers` | `registration_branch_id`: only 5 of 150,000 exist in `branches`. High nulls in `landline_phone` (50%), `detected_accent` (30%), `estimated_monthly_income` (20%) and `credit_score` (15%) |
| `complaints` | `origin_interaction_id` is always empty. `claimed_amount` matches no transaction. The 5 categories weigh almost the same (17.7% to 18.3%), so "unrecognized charge plus improper charge = 36.5%" is an artifact of uniformity |
| `call_center_interactions` | `contact_reason` is identical to `reason_category`. First-contact resolution is 76.6% and escalation 10.0%, both flat across reasons |
| `branches` | 100% "Urbana", while the documentation mentions urban, suburban and rural |
| Business rules | 7,510 credit products with a balance above the limit; 772 closed complaints with no close date; 52,454 interactions both escalated and resolved |
| Types | Six integer columns arrive as decimals (`"26.0"`), always with `.0`. They are converted without loss |

## What was modeled and what was not

Five of the 13 tables reach `gold` (`customers`, `products`, `transactions`, `complaints`, `call_center_interactions`). This is deliberate: none of the others gave a useful signal to a candidate workflow, and the challenge rewards depth over coverage.

## Still to verify

- The real income currency by country (MXN is assumed for Mexico).
- The 14 days with no file in `campaign_sends`. It is unknown whether this is intentional, and it is irrelevant to this workflow.
- The distribution of values across partitions. The header does not change, but contents were not compared by date.
