import Image from "next/image";
import {
  Browser,
  CheckCircle,
  FilePdf,
  GithubLogo,
  PlayCircle,
  Question,
  UserCheck,
} from "@phosphor-icons/react/dist/ssr";

import { CountUp } from "@/components/site/count-up";
import { LinkButton, LinkRow } from "@/components/site/link-button";
import { Reveal } from "@/components/site/reveal";
import { ScrollWords } from "@/components/site/scroll-words";
import { Walkthrough } from "@/components/site/walkthrough";
import { LINKS } from "@/lib/links";

import caseDetail from "@/images/case-detail.jpg";
import chatHandoff from "@/images/chat-handoff.jpg";
import chatResolved from "@/images/chat-resolved.jpg";
import logo from "@/images/logo.png";

const frame = "overflow-hidden rounded-2xl border border-border bg-card shadow-frame";
const wrap = "mx-auto w-[min(1180px,100%-2.5rem)]";
const h2 = "text-balance text-[clamp(1.8rem,4vw,2.8rem)] font-bold leading-[1.1] tracking-tight";

const decisions = [
  {
    icon: <CheckCircle size={28} weight="fill" aria-hidden />,
    tone: "bg-ok",
    title: "Resolves alone",
    when: "A declined or reversed charge, the only candidate, under USD 500.",
    result: "Closed in seconds, after it rereads the bank's record.",
  },
  {
    icon: <Question size={28} weight="fill" aria-hidden />,
    tone: "bg-primary",
    title: "Asks first",
    when: "Zero or several candidates, or a detail missing.",
    result: "One question per turn, two rounds at most. It never guesses.",
  },
  {
    icon: <UserCheck size={28} weight="fill" aria-hidden />,
    tone: "bg-warn",
    title: "Hands to a person",
    when: "An approved or pending charge, suspected fraud, USD 500 or more, or an unknown amount.",
    result: "A specialist gets the case with the facts and the rule prepared.",
  },
];

const steps = [
  {
    title: "The customer writes",
    text: "In Spanish or Portuguese, in plain words. The assistant finds the transaction and checks it against the policy.",
    image: chatResolved,
    alt: "A customer reports a charge in Portuguese and the assistant answers with the case card",
  },
  {
    title: "The policy decides",
    text: "A declined charge under USD 500 closes in seconds. An approved charge never does: it goes to a person.",
    image: chatHandoff,
    alt: "An approved charge handed to a person, with the handoff card",
  },
  {
    title: "A person receives the case",
    text: "The specialist opens it with the verified facts, the rule that applied, the customer's message and the agent's trace.",
    image: caseDetail,
    alt: "The specialist's case detail with verified facts and the agent's trace",
  },
];

export default function Home() {
  return (
    <>
      <a
        href="#main"
        className="absolute -left-[999px] z-30 inline-flex min-h-11 items-center rounded-full bg-foreground px-5 text-background focus:left-4 focus:top-4"
      >
        Skip to the content
      </a>

      <header className="sticky top-0 z-20 border-b border-border/60 bg-background/80 backdrop-blur-md">
        <div className={`${wrap} flex h-16 items-center gap-6`}>
          <a href="#top" className="flex min-h-11 items-center gap-3 rounded-lg font-semibold focus-visible:ring-2 focus-visible:ring-ring">
            <Image src={logo} alt="" width={30} height={30} className="rounded-lg bg-white" />
            LATAM Bank dispute assistant
          </a>
          <nav aria-label="Main" className="ml-auto hidden gap-5 text-[0.95rem] text-muted-foreground md:flex">
            {[
              ["#judgment", "How it decides"],
              ["#walkthrough", "Walkthrough"],
              ["#proof", "The proof"],
              ["#team", "Team"],
            ].map(([href, label]) => (
              <a
                key={href}
                href={href}
                className="inline-flex min-h-11 min-w-11 items-center justify-center rounded-lg px-2 transition-colors hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring"
              >
                {label}
              </a>
            ))}
          </nav>
        </div>
      </header>

      <main id="main">
        {/* Hero: the line, one sentence, two actions, and the two screens that tell the story layered on the right. */}
        <div id="top" className={`${wrap} pb-20 pt-12 md:pb-28 md:pt-16`}>
          <Reveal>
            <h1 className="max-w-[24ch] text-balance text-[clamp(2.3rem,6vw,4.8rem)] font-bold leading-[1.03] tracking-[-0.03em]">
              Fast where it is safe, human where it matters.
            </h1>
          </Reveal>
          <div className="mt-10 grid items-center gap-12 md:grid-cols-[0.78fr_1.22fr] md:gap-10">
            <Reveal delay={0.1}>
              <p className="mb-7 max-w-[26rem] text-[clamp(1.1rem,2vw,1.3rem)] text-muted-foreground">
                Resolves safe disputes in seconds, in Spanish and Portuguese. Hands the rest to a person, case ready.
              </p>
              <div className="flex flex-wrap gap-3">
                <LinkButton to="video" icon={<PlayCircle size={20} aria-hidden />}>Watch the video</LinkButton>
                <LinkButton to="demo" variant="outline" icon={<Browser size={20} aria-hidden />}>Try the live demo</LinkButton>
              </div>
            </Reveal>
            <Reveal delay={0.2}>
              <div className="relative pb-[18%] md:pb-[22%]">
                <div className={`${frame} ml-auto w-[82%]`}>
                  <Image src={caseDetail} alt="The specialist's case detail" priority className="aspect-[16/10] w-full object-cover object-top" />
                </div>
                <div className={`${frame} absolute bottom-0 left-0 w-[78%]`}>
                  <Image src={chatHandoff} alt="An approved charge handed to a person, with the case card" priority sizes="(min-width: 900px) 640px, 90vw" className="w-full" />
                </div>
              </div>
            </Reveal>
          </div>
        </div>

        {/* Why: told as you scroll. */}
        <section aria-label="The problem" className="py-20 md:py-32">
          <div className={wrap}>
            <div className="max-w-[56rem]">
              <ScrollWords
                parts={[
                  { text: "It is eleven at night. A charge you do not recognize. For the bank, most of these are simple and a few are fraud." },
                  { text: "The hard part is knowing which ones a machine must never decide.", className: "text-primary" },
                ]}
              />
            </div>
          </div>
        </section>

        {/* Policy: a full-width decision table, three rows. */}
        <section id="judgment" aria-labelledby="h-judge" className="py-16 md:py-24">
          <div className={wrap}>
            <Reveal>
              <h2 id="h-judge" className={h2}>The model helps. The rules decide.</h2>
              <p className="mb-10 mt-4 max-w-2xl text-muted-foreground">
                The policy is code, outside the model. The model reads the message and drafts the reply, and its second look for fraud can only add caution.
              </p>
            </Reveal>
            <ul className="border-t border-border">
              {decisions.map((d, i) => (
                <li key={d.title}>
                  <Reveal delay={i * 0.06}>
                    <div className="grid items-start gap-3 border-b border-border py-7 transition-colors hover:bg-card/60 md:grid-cols-[260px_1fr_1fr] md:gap-8 md:px-3">
                      <div className="flex items-center gap-4">
                        <span className={`grid size-12 shrink-0 place-items-center rounded-full text-primary-foreground ${d.tone}`}>{d.icon}</span>
                        <h3 className="text-xl font-semibold">{d.title}</h3>
                      </div>
                      <p className="text-lg">{d.when}</p>
                      <p className="text-lg text-muted-foreground">{d.result}</p>
                    </div>
                  </Reveal>
                </li>
              ))}
            </ul>
          </div>
        </section>

        {/* Walkthrough: one screen stays, the story scrolls beside it. */}
        <section id="walkthrough" aria-labelledby="h-walk" className="py-16 md:py-24">
          <div className={wrap}>
            <Reveal>
              <h2 id="h-walk" className={`${h2} mb-10 md:mb-14`}>From a message to a prepared case</h2>
            </Reveal>
            <Walkthrough steps={steps} />
          </div>
        </section>

        {/* Proof: plain type, the numbers and their limits. */}
        <section id="proof" aria-labelledby="h-proof" className="py-16 md:py-24">
          <div className={wrap}>
            <Reveal>
              <h2 id="h-proof" className={h2}>Measured, and honest about it</h2>
              <p className="mt-3 max-w-xl text-muted-foreground">Offline results on cases the team generated. This is not a production measurement.</p>
            </Reveal>
            <div className="mt-10 grid gap-8 md:grid-cols-3 md:gap-12">
              <Reveal>
                <div className="border-t border-border pt-4">
                  <b className="block text-[clamp(2.4rem,5.5vw,4rem)] font-bold leading-none tracking-[-0.03em] tabular-nums text-primary"><CountUp to={549} /></b>
                  <span className="mt-3 block max-w-[22rem] text-muted-foreground">cases tested end to end</span>
                </div>
              </Reveal>
              <Reveal delay={0.06}>
                <div className="border-t border-border pt-4">
                  <b className="block text-[clamp(2.4rem,5.5vw,4rem)] font-bold leading-none tracking-[-0.03em] tabular-nums text-primary"><CountUp to={372} /> of 372</b>
                  <span className="mt-3 block max-w-[22rem] text-muted-foreground">
                    test cases where it must not resolve alone, and it never did. A small sample never proves zero risk: the upper bound is about 1%.
                  </span>
                </div>
              </Reveal>
              <Reveal delay={0.12}>
                <div className="border-t border-border pt-4">
                  <b className="block text-[clamp(2.4rem,5.5vw,4rem)] font-bold leading-none tracking-[-0.03em] tabular-nums text-primary">100% vs 49%</b>
                  <span className="mt-3 block max-w-[22rem] text-muted-foreground">intent classification, model against keywords, on a blind set of 228 messages</span>
                </div>
              </Reveal>
            </div>
            <Reveal>
              <p className="mt-10 max-w-3xl text-muted-foreground">
                <strong className="text-foreground">What it is not yet.</strong> The data is synthetic, the login is a sandbox, and there is no load test or alerting. The repository lists what a real bank would need first.
              </p>
            </Reveal>
          </div>
        </section>

        <section id="team" aria-labelledby="h-close" className="bg-muted py-16 md:py-24">
          <div className={`${wrap} grid gap-10 md:grid-cols-[0.9fr_1.1fr] md:gap-20`}>
            <Reveal>
              <h2 id="h-close" className={h2}>See it, read it, run it.</h2>
              <p className="mt-4 max-w-[26rem] text-muted-foreground">Built by team bitcoders for the Factored AI and Data Hackathon 2026.</p>
              <div className="mt-8 grid gap-2">
                {[
                  { name: "Diego Rejalas", initials: "DR", href: LINKS.diego },
                  { name: "Felix Morales", initials: "FM", href: LINKS.felix },
                ].map((p) => (
                  <div key={p.name} className="flex items-center gap-4">
                    <span aria-hidden className="grid size-11 place-items-center rounded-full bg-primary text-sm font-bold text-primary-foreground">{p.initials}</span>
                    <div>
                      <b className="block">{p.name}</b>
                      {p.href ? (
                        <a href={p.href} className="inline-flex min-h-11 items-center rounded-lg text-sm text-primary hover:underline focus-visible:ring-2 focus-visible:ring-ring">LinkedIn</a>
                      ) : (
                        <span className="inline-flex min-h-11 items-center text-sm text-muted-foreground">LinkedIn, soon</span>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </Reveal>
            <Reveal delay={0.1}>
              <div>
                <LinkRow to="video" icon={<PlayCircle aria-hidden />}>The pitch video</LinkRow>
                <LinkRow to="pdf" icon={<FilePdf aria-hidden />}>The slides</LinkRow>
                <LinkRow to="repo" icon={<GithubLogo aria-hidden />}>The code</LinkRow>
                <LinkRow to="demo" icon={<Browser aria-hidden />}>The live demo</LinkRow>
              </div>
            </Reveal>
          </div>
        </section>
      </main>

      <footer className="border-t border-border py-7 text-sm text-muted-foreground">
        <div className={wrap}>Synthetic data. Nothing here moves real money.</div>
      </footer>
    </>
  );
}
