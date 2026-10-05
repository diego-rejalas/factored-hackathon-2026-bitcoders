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

import { LinkButton, LinkRow } from "@/components/site/link-button";
import { Reveal } from "@/components/site/reveal";
import { Card, CardDescription, CardTitle } from "@/components/ui/card";
import { LINKS } from "@/lib/links";

import caseDetail from "@/images/case-detail.jpg";
import chatHandoff from "@/images/chat-handoff.jpg";
import chatResolved from "@/images/chat-resolved.jpg";
import logo from "@/images/logo.png";

const frame = "overflow-hidden rounded-2xl border border-border bg-card shadow-frame";

const paths = [
  {
    icon: <CheckCircle size={26} weight="fill" aria-hidden />,
    tone: "bg-ok",
    title: "Resolves alone",
    text: "A declined or reversed charge, the only candidate, under USD 500. It rereads the bank's record before it says so.",
    offset: "",
  },
  {
    icon: <Question size={26} weight="fill" aria-hidden />,
    tone: "bg-primary",
    title: "Asks first",
    text: "Zero or several candidates, or a detail missing. Two rounds at most, then it escalates. It never guesses.",
    offset: "md:ml-10",
  },
  {
    icon: <UserCheck size={26} weight="fill" aria-hidden />,
    tone: "bg-warn",
    title: "Hands to a person",
    text: "An approved or pending charge, suspected fraud, USD 500 or more, or an unknown amount. The specialist gets the case prepared.",
    offset: "md:ml-20",
  },
];

const figures = [
  { big: "549", text: "cases tested end to end" },
  {
    big: "372 of 372",
    text: "test cases where it must not resolve alone, and it never did. A small sample never proves zero risk: the upper bound is about 1%.",
  },
  { big: "100% vs 49%", text: "intent classification, model against keywords, on a blind set of 228 messages" },
];

export default function Home() {
  return (
    <>
      <a
        href="#main"
        className="absolute -left-[999px] z-30 rounded-full bg-foreground px-4 py-2 text-background focus:left-4 focus:top-4"
      >
        Skip to the content
      </a>

      <header className="sticky top-0 z-20 border-b border-border/60 bg-background/80 backdrop-blur-md">
        <div className="mx-auto flex h-16 w-[min(1180px,100%-2.5rem)] items-center gap-6">
          <a href="#top" className="flex items-center gap-3 font-semibold">
            <Image src={logo} alt="" width={30} height={30} className="rounded-lg bg-white" />
            LATAM Bank dispute assistant
          </a>
          <nav aria-label="Main" className="ml-auto hidden gap-7 text-[0.95rem] text-muted-foreground md:flex">
            <a className="transition-colors hover:text-foreground" href="#judgment">How it decides</a>
            <a className="transition-colors hover:text-foreground" href="#product">The product</a>
            <a className="transition-colors hover:text-foreground" href="#proof">The proof</a>
            <a className="transition-colors hover:text-foreground" href="#team">Team</a>
          </nav>
        </div>
      </header>

      <main id="main">
        <div id="top" className="mx-auto w-[min(1180px,100%-2.5rem)] pb-16 pt-12 md:pb-24 md:pt-20">
          <Reveal>
            <h1 className="max-w-[24ch] text-balance text-[clamp(2.3rem,6vw,4.6rem)] font-bold leading-[1.04] tracking-[-0.03em]">
              Fast where it is safe, human where it matters.
            </h1>
          </Reveal>
          <div className="mt-10 grid items-start gap-10 md:grid-cols-[0.8fr_1.2fr] md:gap-14">
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
              <div className={frame}>
                <Image src={chatHandoff} alt="The assistant handing an approved charge to a person, with the case card" priority sizes="(min-width: 900px) 700px, 100vw" />
              </div>
            </Reveal>
          </div>
        </div>

        <section id="judgment" aria-labelledby="h-judge" className="py-16 md:py-24">
          <div className="mx-auto grid w-[min(1180px,100%-2.5rem)] items-start gap-10 md:grid-cols-[0.85fr_1.15fr] md:gap-20">
            <Reveal className="md:sticky md:top-24">
              <h2 id="h-judge" className="text-balance text-[clamp(1.8rem,4vw,2.8rem)] font-bold leading-[1.1] tracking-tight">
                The model helps. The rules decide.
              </h2>
              <p className="mt-4 max-w-[24rem] text-muted-foreground">
                The policy is code, outside the model. The model reads the message and drafts the reply, and its second look for fraud can only add caution.
              </p>
            </Reveal>
            <div className="grid gap-4">
              {paths.map((p, i) => (
                <Reveal key={p.title} delay={i * 0.06} className={p.offset}>
                  <Card className="grid grid-cols-[52px_1fr] gap-4 p-6">
                    <span className={`grid size-[52px] place-items-center rounded-full text-primary-foreground ${p.tone}`}>{p.icon}</span>
                    <div>
                      <CardTitle className="mb-1">{p.title}</CardTitle>
                      <CardDescription>{p.text}</CardDescription>
                    </div>
                  </Card>
                </Reveal>
              ))}
            </div>
          </div>
        </section>

        <section id="product" aria-labelledby="h-product" className="py-16 md:py-24">
          <div className="mx-auto w-[min(1180px,100%-2.5rem)]">
            <Reveal>
              <h2 id="h-product" className="text-[clamp(1.8rem,4vw,2.8rem)] font-bold leading-[1.1] tracking-tight">Three screens from the running app</h2>
              <p className="mb-9 mt-3 max-w-xl text-muted-foreground">
                Real captures on synthetic data. The interface speaks Spanish and Portuguese, as the challenge asks.
              </p>
            </Reveal>
            <div className="grid gap-5 md:grid-cols-[1.35fr_1fr] md:grid-rows-2">
              <Reveal className="md:row-span-2">
                <figure>
                  <div className={frame}>
                    <Image src={chatResolved} alt="A reversed charge resolved in Portuguese, with the case card" className="aspect-[4/3] w-full object-cover object-top" />
                  </div>
                  <figcaption className="max-w-[34rem] pt-3 text-muted-foreground">
                    <strong className="block text-lg text-foreground">A reversed charge, in Portuguese</strong>
                    It checks the rules and rereads the record before it says anything is resolved.
                  </figcaption>
                </figure>
              </Reveal>
              <Reveal delay={0.08}>
                <figure>
                  <div className={frame}>
                    <Image src={chatHandoff} alt="An approved charge handed to a person" className="aspect-[16/10] w-full object-cover object-top" />
                  </div>
                  <figcaption className="pt-3 text-muted-foreground">
                    <strong className="block text-lg text-foreground">An approved charge</strong>
                    It never resolves this alone. A person takes the case.
                  </figcaption>
                </figure>
              </Reveal>
              <Reveal delay={0.16}>
                <figure>
                  <div className={frame}>
                    <Image src={caseDetail} alt="The specialist's case detail with verified facts and the agent's trace" className="aspect-[16/10] w-full object-cover object-top" />
                  </div>
                  <figcaption className="pt-3 text-muted-foreground">
                    <strong className="block text-lg text-foreground">The specialist&apos;s view</strong>
                    Verified facts, the rule that applied, the message and the trace.
                  </figcaption>
                </figure>
              </Reveal>
            </div>
          </div>
        </section>

        <section id="proof" aria-labelledby="h-proof" className="py-16 md:py-24">
          <div className="mx-auto w-[min(1180px,100%-2.5rem)]">
            <Reveal>
              <h2 id="h-proof" className="text-[clamp(1.8rem,4vw,2.8rem)] font-bold leading-[1.1] tracking-tight">Measured, and honest about it</h2>
              <p className="mt-3 max-w-xl text-muted-foreground">Offline results on cases the team generated. This is not a production measurement.</p>
            </Reveal>
            <div className="mt-9 grid gap-8 md:grid-cols-3 md:gap-12">
              {figures.map((f, i) => (
                <Reveal key={f.big} delay={i * 0.06}>
                  <div className="border-t border-border pt-4">
                    <b className="block text-[clamp(2.2rem,5vw,3.6rem)] font-bold leading-none tracking-[-0.03em] tabular-nums text-primary">{f.big}</b>
                    <span className="mt-3 block max-w-[22rem] text-muted-foreground">{f.text}</span>
                  </div>
                </Reveal>
              ))}
            </div>
            <Reveal>
              <p className="mt-10 max-w-3xl text-muted-foreground">
                <strong className="text-foreground">What it is not yet.</strong> The data is synthetic, the login is a sandbox, and there is no load test or alerting. The repository lists what a real bank would need first.
              </p>
            </Reveal>
          </div>
        </section>

        <section id="team" aria-labelledby="h-close" className="bg-muted py-16 md:py-24">
          <div className="mx-auto grid w-[min(1180px,100%-2.5rem)] gap-10 md:grid-cols-[0.9fr_1.1fr] md:gap-20">
            <Reveal>
              <h2 id="h-close" className="text-[clamp(1.8rem,4vw,2.8rem)] font-bold leading-[1.1] tracking-tight">See it, read it, run it.</h2>
              <p className="mt-4 max-w-[26rem] text-muted-foreground">Built by team bitcoders for the Factored AI and Data Hackathon 2026.</p>
              <div className="mt-8 grid gap-4">
                {[
                  { name: "Diego Rejalas", initials: "DR", href: LINKS.diego },
                  { name: "Felix Morales", initials: "FM", href: LINKS.felix },
                ].map((p) => (
                  <div key={p.name} className="flex items-center gap-4">
                    <span aria-hidden className="grid size-11 place-items-center rounded-full bg-primary text-sm font-bold text-primary-foreground">{p.initials}</span>
                    <div>
                      <b className="block">{p.name}</b>
                      {p.href ? (
                        <a href={p.href} className="text-sm text-primary hover:underline">LinkedIn</a>
                      ) : (
                        <span className="text-sm text-muted-foreground">LinkedIn, soon</span>
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
        <div className="mx-auto w-[min(1180px,100%-2.5rem)]">Synthetic data. Nothing here moves real money.</div>
      </footer>
    </>
  );
}
