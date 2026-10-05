# Evaluation

[Index](README.md) · [Workflow](WORKFLOW.md) · [Data](DATA.md) · [Path to production](PRODUCTION.md) · [Criteria](CRITERIA.md)

*What was measured, how, with what results and what cannot be concluded. This is an **offline** measurement on cases the team generated. It is not a production measurement or a savings projection.*

## Summary

| Question | Answer | Where |
|---|---|---|
| Does a model classify intent better than keywords? | **Yes, by a wide margin on text that does not use those words:** 100% (228 of 228) against 49.1% on the blind set. On 40 hand-written adversarial cases, 95.0% against 87.5%, a difference that is not significant at that size | [Component](#1-the-component-intent-classification) |
| Does the full system follow the policy? | In the first run: **99.2%** of 384 disputes with the model and **90.1%** without it. After fixing what was found and merging the team's work: 548 of 549 with the model and 90.6% of disputes without it | [System](#2-the-full-system-end-to-end) |
| Did it resolve anything that should have gone to a person? | **0 of 372** cases. With that sample, the true risk could be as high as 1% | [Unsafe outcomes](#unsafe-outcomes) |
| What did the evaluation find? | **Nine real defects**, all fixed with tests, among them a backend 500 error that had existed from the start and a classifier crash with a model that would have broken the chat with any key | [Findings](#3-what-was-found) |
| How much of this is independent evidence? | **Less than it looks:** the 100% after the fixes is measured on the same cases that surfaced them. What is independent is the blind intent set and the third fraud set | [Limits](#4-limits) |

## How it was evaluated

**What the "learned component" is.** The agent decides with code. The model does three things: it classifies the intent of a message (structured output with language and confidence, abstaining below 0.5), it gives a second look for fraud that can only add caution, and it drafts the reply for an already resolved case. The component evaluated against a baseline is **intent classification**: `anthropic/claude-haiku-4.5` (through OpenRouter) against the Spanish and Portuguese keywords the agent uses without a model. No model was trained.

**Why there is no training set or split.** There is nothing to train, so there is no leakage between training and test. The separation that matters is a different one: the test sets were written **before** anything was run, and neither the model's prompt nor the keyword list was touched for them. What was adjusted afterward was validated, when possible, with a new set that had not been seen.

**Labels without leakage.** `is_fraud` and `fraud_score` do not exist in `gold` or in the cases. The expected outcome of each case is derived from the policy (transaction status and amount), restated independently in `agent/eval/fixture.py`, and is not read from the agent. The messages are paraphrased by a model other than the classifier (`openai/gpt-4o-mini`) from the transaction data, without telling it the status, because a customer does not know it.

**Data.** Everything is invented by the team and labeled as such:

| Set | Cases | How it was made |
|---|---:|---|
| Intents, blind | 228 | A model unrelated to the classifier writes messages per intent, in Spanish and Portuguese, half of them **without** the usual banking words. All 241 were reviewed one by one and 13 doubtful ones were removed (`intent_blind.excluded.json`) |
| Intents, adversarial | 40 | By hand: injections, requests for other customers' data, slang, typos, noise, two languages mixed |
| Fraud, sets 2 and 3 | 36 and 34 | Generated after seeing the first results, to validate the fixes. 14 and 15 doubtful ones removed (`fraud_fresh*.excluded.json`). No message repeats across sets |
| End to end | 549 | 12 customers and 96 transactions invented with a seed (`fixture.py`). 384 messages that state the amount, plus clarifications, fraud, out of scope, greetings, injections, other customers' data, nonexistent data, expired sessions and tool failures |

**Metrics.** The challenge's own: safe automatic resolution (and what share of the in-scope cases was attempted), containment, escalation quality, unsafe outcomes with their denominator, and latency and cost. Each proportion carries its 95% Wilson interval. The comparison between two classifiers on the same cases uses the exact McNemar test. A proportion with no denominator is reported as "not defined", not as zero. The USD 500 threshold is a product decision and the oracle applies it inclusively.

Every number in this document can be recomputed from the per-case files in `agent/eval/results/`. How to repeat it: `agent/eval/README.md`.

**There is another, complementary evaluation.** `ml/eval/` (in [ML components](ML_FINDINGS.md)) measures the intent classifier with confidence and abstention and the ranker of the disputed transaction, on its own sets with splits by cell and by customer and thresholds calibrated only in development. This evaluation measures the full system against the real backend and database, and the classifier on a different set. Both use team-generated cases. They are not averaged or mixed.

## 1. The component: intent classification

Four labels: dispute, case status, greeting and out of scope.

| | Keywords | Model | Cases |
|---|---:|---:|---:|
| **Blind set**, accuracy | 49.1% (CI 42.7 to 55.6) | **100%** (CI 98.3 to 100) | 228 |
| Macro F1 | 0.479 | 1.000 | |
| Spanish / Portuguese | 53.9% / 44.3% | 100% / 100% | 115 / 113 |
| Natural messages / **without banking jargon** | 52.3% / 42.7% | 100% / 100% | 153 / 75 |
| *By label:* dispute / status / greeting / out of scope | 61.7 / **13.3** / 59.0 / 65.0% | 100% on all four | 47 / 60 / 61 / 60 |
| **Adversarial set**, accuracy | 87.5% (CI 73.9 to 94.5) | 95.0% (CI 83.5 to 98.6) | 40 |

- On the blind set, **116 cases are got right only by the model and none only by the keywords** (exact McNemar, p below 0.001).
- On the adversarial set, 4 are got right only by the model and 1 only by the keywords (p = 0.38), so **with 40 cases no difference can be claimed**.
- The model failed two adversarial cases: an English message ("I do not recognise a charge") it called out of scope, and `?`, which it called a greeting. Both had low confidence (0.1 and 0.3), so **the agent escalates them by abstention** and does not answer them.
- **Abstention.** With the default threshold (confidence 0.5), 9 of the 40 adversarial cases (22.5%) are escalated to a person. On the 31 that remain, the model gets all 31 right (CI 89.0 to 100). On the blind set it does not abstain on any.
- The keywords fail mostly on **case status** (13%): customers ask "how is what I reported going" without saying "case" or "claim".
- This section measures the **production path**: the structured classification, which returns intent, language and confidence. The call takes p50 1.25 s and p95 1.45 s, and costs 0.00059 USD per classified message.

**How to read it.** The 100% is a ceiling, not a promise. The interval's lower bound is 98.3%, another language model wrote the messages, and the task is easy for a model. And the baseline **was not strengthened**: it is the keyword list unchanged. A longer list would close part of the gap. What was measured is "the model against these rules", not "the model against the best possible rules".

## 2. The full system, end to end

It ran against the real backend and database of the local stack, in two configurations: **without a model** (keywords, rules and fixed texts) and **with a model** (it classifies, gives the second fraud look and drafts, as with an OpenRouter key). Each case is a new conversation. Cases that would collide with each other (same customer and transaction) run in rounds, with the cases table emptied between them.

### First run, before any fix (the retained measurement)

| Category | Cases | Without model | With model |
|---|---:|---:|---:|
| Dispute with a stated amount | 384 | 90.1% | **99.2%** |
| Clarification (message without an amount) | 31 | 61.3% | 96.8% |
| Nonexistent data | 24 | 100% | 100% |
| Out of scope | 24 | 62.5% | 100% |
| Greeting | 12 | 58.3% | 100% |
| **Fraud** | 24 | 83.3% | **45.8%** |
| Instruction injection | 12 | 100% | 100% |
| Asking for another customer's data | 12 | 100% | 100% |
| Picking someone else's transaction in the app | 8 | 100% | 100% |
| Expired session (must give 401) | 6 | 100% | 100% |
| Backend failure (must warn and change nothing) | 12 | 100% | 100% |

### Final run, with the merged code

Same cases, with one exception: the **out of scope** oracle changed from "escalate" to "decline" (section 3, defect 5). This run includes the confidence-aware classification and candidate-ranking work that was integrated afterward (see [ML components](ML_FINDINGS.md)).

| Category | Cases | Without model | With model |
|---|---:|---:|---:|
| Dispute with a stated amount | 384 | 90.6% | **99.7%** (383/384) |
| Clarification | 31 | 61.3% | 100% |
| Fraud | 24 | 100%\* | 100%\* |
| Out of scope (must decline) | 24 | 62.5% | 100% |
| Greeting | 12 | 58.3% | 100% |
| Nonexistent data, injection, other customers' data, someone else's transaction, expired session, backend failure | 74 | 100% | 100% |
| **Total** | **549** | | **548 of 549** (CI 99.0 to 100) |

The one failure with the model: a request for details of an approved USD 767.43 charge that the model called "out of scope". It was declined instead of going to a person. This is not an unsafe outcome, but it is a dispute that was not handled.

\* Those fraud phrases were written from these same cases, so this is a regression test and not an independent measurement. The independent one is in section 3.

### The challenge's metrics (final run, 384 disputes with an amount)

Of the 384, 92 are for a transaction the policy lets it resolve alone and 292 for one that must go to a person.

| Metric | Without model | With model |
|---|---:|---:|
| **Safe automatic resolution**, out of what the policy allows to automate | 87.0% (80/92; CI 78.6 to 92.4) | **100%** (92/92; CI 96.0 to 100) |
| Out of all in-scope cases | 20.8% (80/384) | 24.0% (92/384) |
| Attempted for automation / of that, correct | 20.8% / 100% | 24.0% / 100% |
| **Containment** (end without a transfer) / of that, correct | 27.1% / 76.9% | 24.0% / 100% |
| **Escalation**: transferred when it should have | 91.8% (268/292; CI 88.1 to 94.4) | 99.7% (291/292; CI 98.1 to 99.9) |
| Missed / unnecessary transfers | 0 of 292 / 0 of 92 | 0 of 292 / 0 of 92 |
| The handoff reason matches the policy | 100% | 100% |

Containment alone proves nothing. 24% is low on purpose, because 76% of the fixture's disputes must go to a person (already approved charges or over USD 500).

### Unsafe outcomes

| What | With and without model | Upper bound (95%) |
|---|---:|---:|
| Resolved alone something the policy sends to a person or that it should not have resolved | **0 of 372** | 1.0% |
| Showed another customer's data | 0 of 20 | **16.1%** |
| Promised money or deadlines in a reply | 0 of 543 | 0.7% |

**Zero failures in a small sample does not mean zero risk.** With 20 cases of access to other customers' data, all that can be said is that the risk is probably low, not that it is nil. The absence of failures comes from code controls (ownership in the backend, the policy in the guardrail, the draft checks), not from the model "behaving well".

### Language

| Disputes with an amount | Without model | With model |
|---|---:|---:|
| Spanish | 98.4% (189/192) | 99.5% (191/192) |
| Portuguese | **82.8%** (159/192) | 100% (192/192) |

Without a model, Portuguese performs clearly worse, because the keyword list has fewer forms in that language. It was not compared by customer segment (country): the fixture's customers are invented and there is no sample per country.

### Handoff quality

| Field | First run | Final |
|---|---:|---:|
| request, open questions, reason and policy limit | 100% | 100% |
| actions taken and case id | 86.7% | 100% |
| evidence (the candidate transaction) | 83.3% | 91.8% |
| **verified facts** | **0%** | **100%** |

Evidence is missing when no transaction was identified (a fraud report that names none), and it is correct that there is none.

### Efficiency

Measured on the local stack at concurrency 4, over the 384 disputes. **This is not Cloud Run latency.**

| | Without model | With model |
|---|---:|---:|
| Latency p50 / p95 | 0.32 s / 0.42 s | 1.50 s / 4.22 s |
| Cost per case (549 cases, all categories) | 0 | **0.00093 USD** |
| Cost per case resolved alone | 0 | **no more than 0.0056 USD** |
| Tokens | 0 | 356,195 input and 31,128 output, 1,153 calls |

The cost per resolved case is an **upper bound**: it divides the spend of the whole run (including the categories that are not resolved) by the 92 correct resolutions. It is the cost of the model calls and does not include infrastructure. The cost rose from 0.00052 to 0.00093 USD per case over the course of the work: the second fraud look adds one call per message (it runs at the same time as the classification, so it adds no waiting) and the structured classification prompt is longer than the earlier one.

## 3. What was found

Nine real defects. None let anything unsafe through, and all were fixed with tests that fail without the fix.

| # | Defect | How it was found | Fix |
|---|---|---|---|
| 1 | **A year was read as an amount.** In "10 de junho de 2026 … 27.65 USD" the agent took 2026 as the amount | The evaluation (3 of 384 cases) | A written date no longer counts as an amount. An amount that looks like a year (`cobro de 2026`) still counts |
| 2 | **Fraud without the usual words did not escalate.** "Someone used my card without my permission" or "I was hacked" were treated as a dispute and the agent asked to clarify: 13 of 24 cases with the model | The evaluation | More phrases in the list, and a second look with the model that **can only add caution** (a "yes" sends the case to a person, while a "no" or a failure leaves the list's verdict as it was) |
| 3 | **The handoff carried no verified facts** (0%) and no customer message | The evaluation | It carries the transaction confirmed by the backend, the effective amount, the date, the rule applied and the message (300 characters). The console shows it |
| 4 | **`GET /me/transactions?days=N` returned 500 every time.** Any message with "ayer", "ontem" or "hace 3 días" ended in `unavailable` | An evaluation case that failed the same way in both runs. It was first taken for a transient failure, and it was not | The SQL parameters needed typing. It existed from the start: the tests with the in-memory store never executed that SQL. There is now a test against a real PostgreSQL |
| 5 | **An out-of-scope question ("what is the weather?") answered that "this case was escalated and a person continues from here"**, although no case or handoff existed and nobody was going to handle it | The user, testing | It is declined with a fixed text in their language (`outcome: declined`), with no case and no false claim |
| 6 | **A greeting showed the label "resolved automatically"** | The user | The label appears only if there is a case or an escalation |
| 7 | **Language was recognized by ten long words:** "Quero aumentar o limite do cartão" was answered in Spanish | While writing a test | Letters and words that exist only in Portuguese |
| 8 | **`escalate` overwrote any state:** a new report could undo a specialist's closure | While documenting the API | An `in_progress` or `closed` case answers 409 and does not change. One that is `open`, `auto_resolved` or `escalated` still escalates |
| 9 | **The structured classification with a model crashed on every call.** The prompt has literal JSON braces and was built with `str.format`, which raised `KeyError`: with an OpenRouter key configured, the understanding step failed and **the whole chat returned an error for any message**. Without a key (as production was at the time) it did not show | Running the merged tree with the model. The code arrived in the integration of the classification work. The tests used a fake model that never reached that line | The prompt is built without `str.format`. A test builds the real prompt (with braces in the customer's message) and fails without the fix |

### Validating the fraud fixes

| Set | Without model | With model, before | With model, after |
|---|---:|---:|---:|
| Set 2 (36): validation of the first fix | 47.2% | 47.2% | 80.6% (29/36; CI 65.0 to 90.2) |
| **Set 3 (34): independent**, written after the second fix | 55.9% (19/34; CI 39.5 to 71.1) | 55.9% | **100%** (34/34; CI 89.8 to 100) |

The failures that remained in set 2 (a leaked password, a phishing link, a lost wallet) were messages the classifier called "out of scope". The second fix extended the second look to those messages. Because that was designed while looking at set 2, the independent measurement is set 3.

## 4. Limits

- **The data is team-generated.** No message comes from a real customer. The generator is another language model, which shares style biases with the classifier. That the model gets 100% shows the task is easy for it, not that it is easy in production.
- **The sets were cleaned by whoever ran the evaluation**, an AI assistant working with the team, reading each message. No third party validated the labels.
- **The 100% of the final run is not independent.** The 549 cases are the same ones with which defects 1 to 4 were found and fixed. It counts as a regression test. The independent evidence is the blind intent set (the system was not touched for it), fraud set 3, and defects 5 and 6, which a person found by typing in the chat and which the evaluation would not have seen, because its oracle expected "escalate" for out-of-scope requests.
- **The oracle was written by whoever wrote the policy.** A misunderstanding of the policy would be on both sides. The adversarial set was written knowing the keyword list.
- **The fixture has few distinct transactions.** Only 23 of 96 can be resolved on their own, and each has 4 phrasings. There is variety of wording, not of cases, and the phrasings of one transaction are not independent, so the Wilson intervals **understate** the uncertainty.
- **A single model.** It was not compared with others. The code's fallback list starts with `gpt-4o-mini`, while the evaluation used `claude-haiku-4.5`, which is also the Terraform default. The classification prompt was not tuned either.
- **The baseline was not strengthened**, as said above.
- **A single load configuration:** local, concurrency 4, one test client per case.
- **The second fraud look was not measured against false positives outside the evaluation.** Within it, none of the 92 disputes the policy lets it resolve alone was over-escalated. With real messages, a model may escalate too much. That costs an escalation, not a risk, but it has to be watched.
- **A draft check was added after the evaluation and was not re-measured.** A draft that shows an internal name (`auto_resolved`, `Reversed` and similar) is now replaced by the fixed template. A model draft in the demo did exactly that. The check can only swap a draft for the template, so it cannot add risk, but the 548 of 549 figure was measured without it.
- **It is an offline measurement.** There is no business savings projection, and no improvement is presented as measured in production.
