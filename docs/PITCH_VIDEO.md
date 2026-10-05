# Pitch video and slides

[Index](README.md) · [Criteria](CRITERIA.md) · [Evaluation](EVALUATION.md)

The organizers' guidance for the submission: pitch it to a bank investor, as a product that solves a real problem. **Video: 90% product and creativity, 10% technical**, told as *Why, What, How*, with editing and delivery weighing the most. Do not just record the screen and explain it. Use animation, transitions and mockups, and make it feel like a launch. **Slides: 60% product and creativity, 40% technical**, with the technical side always tied to the value it delivers.

The video limit is **3 minutes**. This script runs about **2 minutes 55 seconds** (roughly 330 spoken words). Narration is in English. The product speaks Spanish and Portuguese on screen, which the challenge requires.

## The idea

One line: **an assistant that knows which disputes it should never decide alone.** Fast answers are easy. The product is the judgment: it resolves the safe cases in seconds and hands the rest to a person with the case already prepared. Build the whole video around that contrast, and keep the engineering to ten percent.

## Script

| Time | Beat | Picture | Narration |
|---|---|---|---|
| 0:00 to 0:20 | **Why** (the customer) | Generated cinematic cold open: a phone lights up in a dark room, a charge the person does not recognize, a hand hovering over the call button. No UI yet. Quiet music | "It is eleven at night. A charge you do not recognize. You will not sleep until someone tells you what it is." |
| 0:20 to 0:40 | **Why** (the bank) | Kinetic text over a stack of identical tickets, then one highlighted in red | "For the bank, most of these are simple. A few are fraud. The hard part is not answering fast. It is knowing which ones a machine must never decide." |
| 0:40 to 0:55 | **What** (the reveal) | Cut to black, then the product rises on a device mockup, with the Factored mark and the title "LATAM Bank dispute assistant" | "So we built an assistant that answers the safe ones in seconds, and hands the rest to a person." |
| 0:55 to 1:25 | **What**, moment one | Screen capture of the real app, framed in a phone mockup with slow zoom and animated callouts. The language toggle flips to Portuguese, the customer types, the answer appears with the case card | "Customers write in Spanish or Portuguese. It finds the transaction, checks the rules, records the case, and confirms it from the bank's own system before it says a word." |
| 1:25 to 1:55 | **What**, moment two | An approved charge. The reply: a person has it. The handoff card slides in. Cut to the specialist console, the case opens with facts, rule and message already there | "An approved charge, or anything that smells like fraud, never resolves alone. The specialist opens a case that is already prepared: what was verified, which rule sent it here, and what the customer said." |
| 1:55 to 2:20 | **Trust** | Three rules appear as animated cards: approved charges, 500 dollars, fraud. Then one number, large: "0 of 372 unsafe resolutions" | "The model helps. The rules decide. We tested 549 cases, and in 372 where it must not resolve alone, it never did. A small sample never proves zero risk, so we say that too." |
| 2:20 to 2:40 | **How** (10%) | The agent flow and the Google Cloud diagram, each for a few seconds, animated in | "A private banking backend, an agent whose policy is code, a data pipeline from the organizer's bucket, all on Google Cloud and defined as code." |
| 2:40 to 2:55 | **Close** | The login screen, dark, then the tagline over the hexagon mark | "It is a prototype on synthetic data. But the idea scales: be fast where it is safe, and human where it matters." |

## How to make it feel like a launch

- **Do not show a raw screen recording.** Every app shot goes inside a device mockup, with a slow push-in, and a callout that names the thing it points at. Cut at the moment of the answer, not before it.
- **Cold open and transitions with Higgsfield.** The CLI and skills are installed (`higgsfield-generate`, `higgsfield-brandkit`). Ask for: the 20-second cold open (phone in a dark room), a short abstract transition built on the hexagon motif, and a closing still. Authenticate first with `higgsfield auth login`. Generated people and scenes are synthetic: say so in the video description, and never use them to suggest real customers.
- **Sound:** one music bed that lifts at the reveal (0:40) and drops under the voice at the demo. Record the voice in a quiet room, in one pass per beat, and cut on the breath.
- **Kinetic text** for the Why and Trust beats, so the video still reads with the sound off.
- **Real product, real data.** The captures come from `prod` (the load balancer URL from `terraform output edge_url`) in dark mode at 1440×900, with Carla `CLI-00232W4ZDQPP` for a reversed charge and Ana `CLI-00MT1OY089RA` for the escalation. Create the escalated case before recording so the specialist console has something in it, and sign in as `ops` ahead of time.

## What not to claim

A measured improvement in production, real identity (the login is a sandbox), time saved, or any savings figure. The evaluation is offline and the data is synthetic. Everything quantitative in the video comes from [Evaluation](EVALUATION.md): 549 cases and 0 of 372 are the only numbers it uses.

## Slides (4 to 6, 60% product and 40% technical)

1. **The problem.** The cold open's still, and one line: the customer who cannot sleep, and the bank that must tell fraud from a simple question.
2. **The product.** Two or three framed screens: the customer chat in Portuguese, the handoff card, the specialist console. Caption each with what it does for the customer or the specialist.
3. **The judgment.** The three paths (resolves, asks, escalates) and the rules that send a case to a person. This is the slide that shows the product has a point of view.
4. **How it works.** The agent flow and the Google Cloud diagram side by side. One line: policy is code, the model only helps, and the agent reaches data only through a private backend.
5. **Proof and honesty.** The key results (549 cases, 0 of 372 unsafe resolutions with its upper bound, 100% against 49% on intent) next to the limits: synthetic data, a sandbox login, no load test.
6. **What a real bank needs next.** The first three items from the path to production, and the repository link.
