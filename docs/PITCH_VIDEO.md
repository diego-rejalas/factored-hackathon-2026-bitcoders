# Pitch video script (3 minutes maximum)

[Index](README.md) · [Criteria](CRITERIA.md) · [Evaluation](EVALUATION.md)

The challenge page sets the limit at **3 minutes**. This script runs about **2 minutes 50 seconds** at a calm pace (roughly 380 spoken words). Narration is in English, the demo runs in Spanish and Portuguese, which is what the challenge requires. Every number below comes from [Evaluation](EVALUATION.md). Do not add numbers that are not there.

## Before recording

- Production is the demo target: the load balancer URL from `terraform output edge_url`. Start from the login screen, in dark mode, at 1440×900.
- Customers (see [Local development](LOCAL_DEV.md); `e2e.py` passed with the same ids against `prod`): Carla `CLI-00232W4ZDQPP` for a reversed charge that resolves, Bruno `CLI-0064RNKCVQCN` for a declined one, Ana `CLI-00MT1OY089RA` for the cases that escalate.
- Have the `/admin` console open in a second tab, already signed in as `ops`, with one escalated case in the inbox. Make that case first.
- Keep three diagrams ready as full-screen images: `docs/diagrams/agent-flow.png`, `pipeline-flow.png`, `gcp-architecture.png`.

## Script

| Time | Screen | Narration |
|---|---|---|
| 0:00 to 0:15 | A title card (see "Higgsfield" below), then the login screen | "Banks lose hours on one question: *I do not recognize this charge.* We built an assistant that answers the safe cases on its own, in Spanish and Portuguese, and hands the rest to a person with the case already prepared." |
| 0:15 to 0:35 | Slide or `docs/WORKFLOW.md` table of the three paths | "We picked one workflow, transaction disputes, and made it small and honest. It resolves a declined or reversed transaction under 500 dollars. It escalates an approved charge, suspected fraud, a high amount, or anything ambiguous. Those rules are code, not a prompt." |
| 0:35 to 1:00 | Switch the toggle to PT, pick the scenario from the dropdown, send the reversed-charge message | "Here is a customer writing in Portuguese. The agent finds the transaction, checks it against the policy, records the case, and rereads it from the backend before it says anything is resolved." |
| 1:00 to 1:25 | Ana: the approved charge, then the fraud wording | "An approved charge is never resolved alone. And when the customer says someone used their card, it escalates, even if the model had read it as a normal dispute." |
| 1:25 to 1:45 | Second tab: `/admin`, open the escalated case | "The specialist sees what the agent verified, the rule that sent the case here, the customer's message, and the agent's trace. Not a transcript dump." |
| 1:45 to 2:05 | `agent-flow.png`, then `gcp-architecture.png` | "The model only helps: it classifies intent, takes a second look for fraud that can only add caution, and drafts the reply, which passes deterministic checks. The agent reaches data only through a private backend with per-customer permissions. Everything runs on Google Cloud, in Terraform, with a pipeline from the organizer's S3 to the tables the backend reads." |
| 2:05 to 2:35 | The results table from `EVALUATION.md` | "We measured it on 549 cases we generated. Zero of 372 unsafe resolutions, with an upper bound of about 1 percent, because a small sample never proves zero risk. Intent classification: 100 percent against 49 percent for keywords on a blind set. Portuguese without the model drops to 83 percent, and we say so. The evaluation also found nine real defects, including a backend error that had been there from the start." |
| 2:35 to 2:55 | `docs/PRODUCTION.md` headings | "This is a prototype on synthetic data. The login is a sandbox. There is no load test, no alerting and no retention policy yet. We wrote down what a real bank would need first." |
| 2:55 to 3:00 | Closing card with the repo name | "Thank you. The code, the evaluation and the deployment steps are in the repository." |

## Notes for the take

- **Do not claim** a measured improvement in production, real identity, or a savings figure. The evaluation is offline and the data is synthetic.
- **Pace:** the 0:35 to 1:25 demo is the part that needs to be real and uncut. If a reply is slow, cut to the result rather than waiting.
- **If you run long,** cut the architecture slide first (1:45 to 2:05) and keep the evaluation, because honesty about limits is part of the score.
- Before submitting, rewatch once with sound off: the screen should still tell the story.

## Higgsfield (optional)

The Higgsfield CLI and skills are installed. Use them only for the **title card and the closing card**, never for the product itself: the demo must be the real application. Authenticate once with `higgsfield auth login`, then ask for a short abstract motion backdrop for the title card (about 4 seconds, dark, a hexagon motif to match the Factored logo) and a still for the close. Generated footage must be labeled as generated if you describe it anywhere.
