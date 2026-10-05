# Pitch video and slides

[Index](README.md) · [Criteria](CRITERIA.md) · [Evaluation](EVALUATION.md)

The organizers' guidance for the submission: pitch it to a bank investor, as a product that solves a real problem. **Video: 90% product and creativity, 10% technical**, told as *Why, What, How*, with editing and delivery weighing the most. Do not just record the screen and explain it. Use animation, transitions and mockups, and make it feel like a launch. **Slides: 60% product and creativity, 40% technical**, with the technical side always tied to the value it delivers.

The submission page asks for exactly this: a **4 to 6 slide presentation** that explains the approach, the results and the key technical decisions, and a **video pitch of no longer than 3 minutes** that demonstrates the working solution and explains the core architectural decisions. The organizers' tip (90% product) and the page's wording (show the working solution, explain the core architectural decisions) fit together: the video is a launch film of the real product, and it names the architectural decisions in one short, plain beat instead of walking through the system.

**Everything is delivered in English** (the organizers confirmed it): the narration, the on-screen text and the slides. The product still speaks Spanish and Portuguese in the demo, because the challenge requires it, so add short English subtitles over those moments (the customer's message and the reply) so a jury member who does not read them follows the story.

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
| 2:20 to 2:40 | **How** (10%): the core architectural decisions | The agent flow and the Google Cloud diagram, each for a few seconds, animated in | "Three decisions make this safe. The policy is code, outside the model. The agent can reach data only through a private backend that checks who is asking. And it rereads the bank's record before it reports anything as done. All of it runs on Google Cloud, defined as code." |
| 2:40 to 2:55 | **Close** | The login screen, dark, then the tagline over the hexagon mark | "It is a prototype on synthetic data. But the idea scales: be fast where it is safe, and human where it matters." |

## How to make it feel like a launch

- **Do not show a raw screen recording.** Every app shot goes inside a device mockup, with a slow push-in, and a callout that names the thing it points at. Cut at the moment of the answer, not before it.
- **Cold open, transitions and closing card with Higgsfield.** See the next section for the exact shots, prompts and commands. Generated people and scenes are synthetic: say so in the video description, and never use them to suggest real customers.
- **Sound:** one music bed that lifts at the reveal (0:40) and drops under the voice at the demo. Record the voice in a quiet room, in one pass per beat, and cut on the breath.
- **Kinetic text** for the Why and Trust beats, so the video still reads with the sound off.
- **Real product, real data.** The captures of the application come from the local stack, which runs the same code with the demo customers (nothing is created in `prod`), at 1920×1080 with 2x resolution, in dark mode, logging in through the scenario dropdown so the customer's name shows. Reproduce them with `pitch-assets/_capture-script.mjs`.

## Selling techniques applied

What the research agrees on, and where it shows up in the script above. Sources are linked at the end of the section.

| Technique | What it means | Where it is in the script |
|---|---|---|
| **The customer is the hero, the product is the guide** (StoryBrand) | Open on a person with a problem, not on the product. The product arrives as the guide with a plan | The cold open is one customer at night. Give her a name on screen (Ana) and keep her through the whole video |
| **Problem, agitate, solve** | Name the problem, make the audience feel its weight, then present the solution as the way out | 0:00 to 0:40 is the problem and its weight. The solution does not appear until the reveal at 0:40 |
| **Start with why it matters, never with features** (Apple keynotes) | Lead with a promise that answers a real frustration. Specs come last, if at all | The promise is "fast where it is safe, human where it matters". No feature list anywhere |
| **A staged reveal** | Hold the product back, build curiosity, then show it in one clean moment | Cut to black at 0:40, then the product rises on a device |
| **One idea, repeated** | A single memorable line that every beat supports | "It knows which disputes it must never decide alone" |
| **The surprise is the refusal** | The memorable moment is the assistant choosing not to answer. That is unusual for a bot and it is the product's value | The approved charge at 1:25: the assistant hands the case to a person, and the card slides in |
| **Show, do not tell, with the real product** | A demo of the core action beats any explanation | The three demo moments use the real app, inside mockups |
| **Honest proof** | One credible number, with its limit, beats a pile of metrics | "0 of 372", plus the sentence that a small sample never proves zero risk |
| **A clear call to action** | End on what happens next | The closing line and the repository |

**A tension to resolve on purpose.** Hackathon guides often say the demo is the most important minute. The organizers here say 90% product and creativity and only 10% technical. Do both by making the demo a **product film**: the real app, cropped and animated, in short beats, with the customer's outcome as the caption. Never narrate how it works while the screen runs.

**Optional framing: a six-sentence story.** If the narration needs a spine, fill in the Pixar pitch: once upon a time a customer trusted her bank. Every day she checked her card without thinking. One day a charge appeared that she did not recognize. Because of that she waited, and the bank's team drowned in questions that were mostly simple. Because of that the safe ones needed an answer in seconds and the risky ones needed a person with the facts. Until finally an assistant that knows the difference.

Sources: [steps for a product launch presentation](https://www.zoho.com/show/chronicles/step-by-step-guide-to-creating-a-product-lauch-presentation.html), [startup pitch video tactics](https://advids.co/blog/startup-pitch-video), [lessons from Apple's product presentations](https://www.crappypresentations.com/presentation-tips-and-tricks/apple-product-presentations), [how to present like Steve Jobs](https://thenarrativeedge.substack.com/p/how-to-present-like-steve-jobs-the), [creating the best demo video for a hackathon](https://tips.hackathon.com/article/creating-the-best-demo-video-for-a-hackathon-what-to-know), [hackathon demo tips for a 3-minute pitch](https://reskilll.com/blogs/hackathon-demo-presentation-tips-pitch-3-minutes-win-2026/), [storytelling frameworks for pitch decks](https://mcginty.net/blog16/).

## Captured assets

Taken once from the real application, kept outside the repository in `pitch-assets/` (the video and the slides reuse them). Stills are 3840×2160 (2x), clips are 1920×1080 `webm`. The sidebar shows the history with the conversation just recorded, one per scene.

| File | What it shows | Used in |
|---|---|---|
| `01-login-dark-dropdown.png` | Login in dark mode with the scenario dropdown open | reveal (0:40), slide 2, closing card |
| `02-resolved-pt.png` and `.webm` | A reversed charge resolved in Portuguese, with the case card | demo moment one (0:55) |
| `03-handoff-es.png` and `.webm` | An approved charge: the handoff card | demo moment two (1:25) |
| `04-candidates.png` | The assistant asking which charge | slide 2 |
| `05-admin-inbox.png` | The specialist inbox, many cases | demo moment two, slide 2 |
| `06-case-detail.png` and `.webm` | The case detail with facts, rule, message and trace, scrolling | demo moment two (1:40), slide 2 |
| `07-chat-light.png` | The chat in the light theme | slide 2 |
| `08-admin-metrics.png` | The metrics view: 49 cases, 22.4% resolved alone, 77.6% derived, 6 closed by specialists | Trust beat only if shown as a demo, never as a result (see below) |

**The metrics screen is demo traffic, not a measurement.** It comes from 85 messages sent through the local agent, and 6 cases were closed by hand. The only measured numbers are the ones in [Evaluation](EVALUATION.md).

## Making the generated shots with Higgsfield

The CLI (`higgsfield`, alias `hf`) and its skills are installed. It is **not signed in yet**: run `higgsfield auth login` (opens a browser), then choose the billing workspace with `higgsfield workspace set <workspace_id>`. Model names and prices change, so check them before generating:

```bash
higgsfield model list --video          # image and video models you can use
higgsfield model get <model>           # the parameters it accepts (duration, aspect ratio...)
higgsfield generate cost <model> --prompt "..."     # what a job will cost, before it runs
higgsfield generate create <model> --prompt "..." --wait --wait-timeout 20m   # run it and wait for the file
```

The skills' own description names Seedance for video and GPT Image or Nano Banana for stills, and the CLI's help shows `seedance_2_0` in an example. Treat those as starting points and confirm against `model list`. Use 16:9 for every shot.

### What to generate (only what the real app cannot show)

| # | Shot | Length | Where it goes | Prompt to start from |
|---|---|---|---|---|
| G1 | Cold open | 6 to 8 s | 0:00 to 0:08 | "Close shot, night, a dark bedroom. A phone lights a woman's face from below, she reads a notification, her expression turns uneasy. Shallow depth of field, cool blue light, handheld, cinematic, no visible text or logos." |
| G2 | Cold open, the hesitation | 5 to 6 s | 0:08 to 0:14 | "Macro on a thumb hovering over the call button of a phone in a dark room, the screen glow on the skin, slow push-in, quiet and tense." |
| G3 | Bank side, the pile of tickets | 5 s | 0:20 to 0:25 | "Abstract overhead view of many identical cards sliding in a grid on a dark surface, one card turns red and rises, clean, minimal, soft light." |
| G4 | Transition into the reveal | 3 to 4 s | 0:38 to 0:41 | "A dark screen, a white hexagon outline draws itself, then expands to fill the frame, crisp lines, deep navy and white, no text." |
| G5 | Closing still | image | 2:50 to 2:55 | "A single white hexagon mark on a deep navy background with a soft glow, centered, plenty of empty space, no text." (Better: place the real logo from the repository over a generated navy background in the editor.) |

Consistency: the woman in G1 and G2 should be the same person. Generate them from the same reference image (`--image-references ./ref.png`) or in one session, and keep the same wardrobe words in both prompts. If the two do not match, cut G2 to the hand only, with no face. Never name or imitate a real person.

### Words on screen and voice

- Do the on-screen text (the kinetic lines of the Why and Trust beats) in the editor, not in the generated video: generated text is often misspelled.
- The narration is recorded by a person. If there is no time to record, Higgsfield's `voices` command lists text-to-speech voices (`higgsfield voices`), but a human voice sells better and is safer for names like "LATAM Bank".
- The brand mark in the corner is the real Factored logo (`frontend/public/factored-logo.png`).

### Edit order

1. Lay down the narration, then the music bed (it lifts at 0:40, ducks under the voice at the demo).
2. Place G1 to G3 over the Why beat, cut on the narration's breaths.
3. Cut to black at 0:38, G4 into the product at 0:41.
4. Put each captured clip inside a device frame, with a slow push-in and one callout, for the demo moments.
5. Add the kinetic text, then the closing still.
6. Export at 1080p, 3 minutes at most, and rewatch once with the sound off.

### Rules for the generated footage

- Say in the video description that the opening scenes are AI-generated. They depict no real customer.
- Check each generated clip for stray text, logos or distorted hands before using it, and regenerate rather than patch.
- Keep the generation spend small: run `generate cost` first and generate each shot once or twice, not dozens of times.

## Optional: a launch-video skill

The `product-launch-video` skill (HeyGen's HyperFrames) is installed. It captures a URL, picks a design preset, drafts a storyboard and renders the video from HTML, with animation and captions, and it asks for approval at three points. It fits the "launch event" brief well. It is also a large pipeline with its own tooling and sign-in, so use it only if there is time to run its gates and check the render. The fallback is an ordinary editor with the stills and clips above.

## What not to claim

A measured improvement in production, real identity (the login is a sandbox), time saved, or any savings figure. The evaluation is offline and the data is synthetic. Everything quantitative in the video comes from [Evaluation](EVALUATION.md): 549 cases and 0 of 372 are the only numbers it uses.

## Slides (4 to 6, 60% product and 40% technical)

1. **The problem.** The cold open's still, and one line: the customer who cannot sleep, and the bank that must tell fraud from a simple question.
2. **The product.** Two or three framed screens: the customer chat in Portuguese, the handoff card, the specialist console. Caption each with what it does for the customer or the specialist.
3. **The judgment.** The three paths (resolves, asks, escalates) and the rules that send a case to a person. This is the slide that shows the product has a point of view.
4. **How it works.** The agent flow and the Google Cloud diagram side by side. One line: policy is code, the model only helps, and the agent reaches data only through a private backend.
5. **Proof and honesty.** The key results (549 cases, 0 of 372 unsafe resolutions with its upper bound, 100% against 49% on intent) next to the limits: synthetic data, a sandbox login, no load test.
6. **What a real bank needs next.** The first three items from the path to production, and the repository link.
