import Image from "next/image";
import { Browser, FilePdf, GithubLogo, PlayCircle } from "@phosphor-icons/react/dist/ssr";

import { Agents } from "@/components/site/agents";
import { BrandChip } from "@/components/site/brand-chip";
import { LinkButton, LinkRow } from "@/components/site/link-button";
import { Drift, Float, PointerLayer } from "@/components/site/parallax";
import { SlideViewer } from "@/components/site/slide-viewer";
import { VideoPlayer } from "@/components/site/video-player";
import { Window } from "@/components/site/window";
import { Zoom } from "@/components/site/zoom";
import { FILES, LINKS } from "@/lib/links";

import caseDetail from "@/images/case-detail.jpg";
import chatHandoff from "@/images/chat-handoff.jpg";
import chatResolved from "@/images/chat-resolved.jpg";
import bitcoders from "@/images/bitcoders-logo.png";
import logo from "@/images/logo.png";
import architecture from "@/images/architecture.png";
import poster from "@/images/pitch-poster.jpg";
import slide1 from "@/images/slides/slide-1.jpg";
import slide2 from "@/images/slides/slide-2.jpg";
import slide3 from "@/images/slides/slide-3.jpg";
import slide4 from "@/images/slides/slide-4.jpg";
import slide5 from "@/images/slides/slide-5.jpg";
import slide6 from "@/images/slides/slide-6.jpg";

const wrap = "mx-auto w-[min(1180px,100%-2.5rem)]";
const big = "font-display font-bold leading-[0.9] tracking-[-0.045em]";
const chip = "inline-flex min-h-11 min-w-11 items-center justify-center bg-white px-3 text-[1.05rem] font-medium hover:bg-ink hover:text-white focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2";

const slides = [
  { src: slide1, title: "LATAM Bank dispute assistant" },
  { src: slide2, title: "Most disputes are simple. A few are fraud." },
  { src: slide3, title: "A customer writes in Spanish or Portuguese" },
  { src: slide4, title: "The model helps. The rules decide." },
  { src: slide5, title: "What we measured: 372 of 372" },
  { src: slide6, title: "A prototype on synthetic data" },
];

const screens = [
  {
    title: "chat.app",
    desk: "on-lilac",
    tone: "lilac",
    name: "The customer writes",
    text: "In Spanish or Portuguese, in plain words. The assistant finds the charge and checks it against the policy.",
    image: chatResolved,
    alt: "A customer reports a charge in Portuguese and the assistant answers with the case card",
  },
  {
    title: "handoff.app",
    desk: "on-mint",
    tone: "mint",
    name: "A person takes it",
    text: "An approved charge never closes alone. The customer is told a person will review it, and the case moves to the queue with the facts attached.",
    image: chatHandoff,
    alt: "An approved charge handed to a person, with the handoff card",
  },
  {
    title: "case.app",
    desk: "on-butter",
    tone: "butter",
    name: "The case arrives prepared",
    text: "Verified facts, the rule that applied, the customer's message and the agent's trace, on one screen.",
    image: caseDetail,
    alt: "The specialist's case detail with verified facts and the agent's trace",
  },
];

export default function Home() {
  return (
    <>
      <a href="#main" className="absolute -left-[999px] z-[60] inline-flex min-h-11 items-center bg-ink px-5 text-white focus:left-4 focus:top-4">
        Skip to the content
      </a>

      <header className="sticky top-0 z-40 flex flex-wrap items-stretch justify-between gap-x-1 gap-y-1 max-md:bg-ink max-md:p-1">
        <BrandChip logo={logo} />
        <nav aria-label="Main" className="order-3 flex h-11 w-full gap-1 scrollbar-hide overflow-x-auto overflow-y-hidden md:order-none md:w-auto">
          <a href="#agents" className={chip}>Agents</a>
          <a href="#screens" className={chip}>Screens</a>
          <a href="#pitch" className={chip}>Pitch</a>
          <a href="#architecture" className={chip}>Build</a>
          <a href="#proof" className={chip}>Numbers</a>
          <a href="#team" className={chip}>Team</a>
        </nav>
        <div className="flex gap-1">
          <a href={LINKS.demo} className={chip}>Live demo</a>
          <a href={LINKS.repo} className={`${chip} !bg-ink !text-white hover:!bg-white hover:!text-ink max-md:!bg-cyan max-md:!text-ink`}>Code</a>
        </div>
      </header>

      <main id="main">
        <section id="top" data-tone="lilac" className="sky relative -mt-12 overflow-hidden px-5 pb-20 pt-28 md:pb-32 md:pt-32">
          <Float from={0} to={160} className="pointer-events-none absolute -left-28 top-24 size-[520px]">
            <div aria-hidden className="halftone size-full opacity-[0.16] md:opacity-60" />
          </Float>
          <Float from={0} to={90} className="pointer-events-none absolute -right-24 top-0 size-[460px]">
            <div aria-hidden className="halftone size-full opacity-[0.16] md:opacity-60" />
          </Float>

          <div className={`${wrap} relative grid items-center gap-14 md:grid-cols-[1.1fr_0.9fr]`}>
            <div>
              <h1 className={`${big} text-balance text-[clamp(2.6rem,6vw,5.6rem)]`}>Fast where it is safe, human where it matters.</h1>
              <p className="mt-7 max-w-[30rem] text-lg font-medium max-md:font-semibold max-md:text-ink">
                A dispute assistant for LATAM Bank, in Spanish and Portuguese. It closes the safe cases in seconds and hands the rest to a person, case ready.
              </p>
              <div className="mt-8 flex flex-wrap gap-3">
                <LinkButton to="demo" icon={<Browser size={18} aria-hidden />}>Try the live demo</LinkButton>
                <LinkButton to="video" variant="outline" icon={<PlayCircle size={18} aria-hidden />}>Watch the video</LinkButton>
              </div>
            </div>

            <div className="relative md:h-[520px]">
              <PointerLayer depth={26} className="relative md:absolute md:left-0 md:top-0 md:w-[88%]">
                <Float from={0} to={-60}>
                  <Window title="handoff.app" className="md:-rotate-2">
                    <Zoom src={chatHandoff} alt="An approved charge handed to a person, with the case card" title="handoff.app" sizes="(min-width: 900px) 480px, 90vw" />
                  </Window>
                </Float>
              </PointerLayer>
              <PointerLayer depth={-40} className="relative mt-8 md:absolute md:bottom-0 md:right-0 md:mt-0 md:w-[64%]">
                <Float from={0} to={-130}>
                  <Window title="chat.app" tone="mint" className="md:rotate-3">
                    <Zoom src={chatResolved} alt="A resolved charge in Portuguese, with the case card" title="chat.app" sizes="(min-width: 900px) 360px, 90vw" />
                  </Window>
                </Float>
              </PointerLayer>
            </div>
          </div>
        </section>

        <section id="agents" data-tone="cyan" aria-labelledby="h-try" className="on-cyan overflow-x-clip py-20 md:py-28">
          <div className={wrap}>
            <h2 id="h-try" className={`${big} text-[clamp(2.4rem,6vw,5.2rem)]`}>Agents decision</h2>
            <p className="mb-10 mt-5 max-w-[38rem] text-lg font-medium">
              Pick a message, in Spanish or Portuguese, and press Send. Watch the robots hand the case along. The model robots read the message and write the reply. The one in the middle is plain code, and only the backend writes to the bank.
            </p>
            <div className="relative border-2 border-ink p-4 pt-10 md:p-8 md:pt-12">
              <span className="absolute left-0 top-0 bg-ink px-2 font-pixel text-xl leading-6 text-white">robots.desk</span>
              <Agents />
            </div>
          </div>
        </section>

        <div id="screens">
          {screens.map((s, i) => (
            <section key={s.title} data-tone={s.tone} aria-labelledby={`h-screen-${i}`} className={`${s.desk} relative overflow-hidden py-20 md:py-28`}>
              <Float from={-40} to={120} className={`pointer-events-none absolute size-[420px] ${i % 2 ? "-left-20 top-6" : "-right-24 top-10"}`}>
                <div aria-hidden className="halftone size-full opacity-[0.14] md:opacity-40" />
              </Float>
              <div className={`${wrap} relative grid items-center gap-10 md:grid-cols-[0.8fr_1.2fr] md:gap-16`}>
                <div className={i % 2 ? "md:order-2" : ""}>
                  <h2 id={`h-screen-${i}`} className={`${big} text-[clamp(2.2rem,5vw,4.4rem)]`}>{s.name}</h2>
                  <p className="mt-5 max-w-[26rem] text-lg font-medium">{s.text}</p>
                  <p className="mt-5 font-mono text-sm">Click the screen to enlarge it.</p>
                </div>
                <Float from={60} to={-60} className={s.image === caseDetail ? "mx-auto w-full max-w-[460px]" : ""}>
                  <Window title={s.title} tone="white">
                    <Zoom src={s.image} alt={s.alt} title={s.title} />
                  </Window>
                </Float>
              </div>
            </section>
          ))}
        </div>

        <section id="pitch" data-tone="cyan" aria-labelledby="h-pitch" className="on-cyan overflow-x-clip py-20 md:py-28">
          <div className={wrap}>
            <h2 id="h-pitch" className={`${big} text-[clamp(2.4rem,6vw,5.2rem)]`}>The pitch</h2>
            <p className="mb-10 mt-5 max-w-[34rem] text-lg font-medium">The three-minute video and the six slides, here on the page. Both can be downloaded.</p>
            <div className="grid items-start gap-8 lg:grid-cols-[1.2fr_1fr] [&>*]:min-w-0">
              <VideoPlayer
                src={FILES.video}
                poster={poster.src}
                title="pitch.mp4"
                label="The pitch video, 2 minutes 50 seconds, in English"
                downloadHref={FILES.video}
                size="18 MB"
              />
              <SlideViewer slides={slides} deckHref={FILES.deck} size="110 KB" />
            </div>
          </div>
        </section>

        <section id="architecture" data-tone="butter" aria-labelledby="h-arch" className="on-butter overflow-x-clip py-20 md:py-28">
          <div className={wrap}>
            <h2 id="h-arch" className={`${big} text-[clamp(2.4rem,6vw,5.2rem)]`}>Where it runs</h2>
            <p className="mb-10 mt-5 max-w-[40rem] text-lg font-medium">
              Customers reach one load balancer on Google Cloud. The agent and the backend are private services, the database has only a private address, and the landing and the video are on Cloudflare. All of it is Terraform.
            </p>
            <div className="grid items-start gap-8 lg:grid-cols-[1.6fr_1fr] [&>*]:min-w-0">
              <Window title="architecture.png" tone="white">
                <Zoom
                  src={architecture}
                  alt="Architecture diagram: the customer reaches Cloud Armor and a load balancer on Google Cloud, which sends the app to the frontend and the agent on Cloud Run. The agent calls a private backend, read-only on the database. An Airflow VM loads the data. The landing, the pitch video and the app's DNS record are on Cloudflare."
                  title="architecture.png"
                  sizes="(min-width: 1024px) 700px, 90vw"
                />
                <p className="mt-3 font-mono text-sm">Click the diagram to enlarge it.</p>
              </Window>
              <div className="grid gap-5">
                {[
                  { tone: "bg-mint", title: "The policy is code", text: "The rules sit outside the model. The model reads the message and drafts the reply, and a draft that breaks a rule is replaced by a fixed text." },
                  { tone: "bg-lilac", title: "One way to the data", text: "The agent reaches the bank only through a private backend that checks who is asking. The database has a private address, and each service has its own role." },
                  { tone: "bg-coral", title: "Checked in production", text: "A suite of 32 checks asks the live system the demo's questions: the edge, access, the policy in Spanish and Portuguese, safety and the replies." },
                ].map((c) => (
                  <div key={c.title} className={`${c.tone} border-2 border-ink p-5 shadow-[6px_6px_0_var(--ink)]`}>
                    <h3 className="font-semibold">{c.title}</h3>
                    <p className="mt-2 text-sm font-medium leading-snug">{c.text}</p>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </section>

        <section id="proof" data-tone="paper" aria-labelledby="h-proof" className="overflow-x-clip px-5 py-24 md:py-36">
          <div className={wrap}>
            <h2 id="h-proof" className="sr-only">What we measured, and what we did not</h2>
            <div className="brackets px-4 py-10 md:px-8 md:py-14">
              <Drift from={100}>
                <p className={`${big} text-[clamp(3.4rem,12vw,10.5rem)]`}>372 of 372.</p>
              </Drift>
              <p className="mt-6 max-w-[34rem] text-lg font-medium">
                Test cases where it must not resolve alone, and it never did. A small sample never proves zero risk: the upper bound is about 1%.
              </p>
            </div>
            <div className="mt-14 grid gap-8 md:grid-cols-3">
              {[
                { label: "Cases tested", bg: "bg-mint", text: "549, end to end. Offline results on cases the team generated, not a production measurement." },
                { label: "Intent classification", bg: "bg-butter", text: "100% with the model against 49% with keywords, on a blind set of 228 messages." },
                { label: "Still missing", bg: "bg-coral", text: "The data is synthetic, the login is a sandbox, and there is no load test or alerting. The repository lists what a real bank would need first." },
              ].map((c) => (
                <div key={c.label} className={`${c.bg} border-2 border-ink p-5 shadow-[6px_6px_0_var(--ink)]`}>
                  <p className="font-mono text-sm">{c.label}</p>
                  <p className="mt-8 text-[1.15rem] font-medium leading-snug">{c.text}</p>
                </div>
              ))}
            </div>
          </div>
        </section>

        <section id="team" data-tone="lilac" aria-labelledby="h-close" className="on-lilac py-20 md:py-28">
          <div className={wrap}>
            <h2 id="h-close" className={`${big} mb-12 text-[clamp(2.4rem,6vw,5.2rem)]`}>Everything in one place.</h2>
            <div className="grid items-start gap-8 md:grid-cols-2">
              <Window title="team.txt" tone="white">
                <div className="flex flex-wrap items-center gap-5">
                  <Image
                    src={bitcoders}
                    alt="BitCoders logo: a hooded figure at a laptop inside a hexagon, with the tagline Code // Win"
                    className="size-32 border-2 border-ink bg-[#04070d]"
                  />
                  <p className="max-w-[16rem] font-mono text-sm">Built by team bitcoders for the Factored AI and Data Hackathon 2026.</p>
                </div>
                <div className="mt-5 grid gap-1">
                  {[
                    { name: "Diego Rejalas", href: LINKS.diego },
                    { name: "Felix Morales", href: LINKS.felix },
                  ].map((p) => (
                    <div key={p.name} className="flex items-center justify-between gap-4 border-t border-ink py-1">
                      <b className="font-semibold">{p.name}</b>
                      {p.href ? (
                        <a href={p.href} className="inline-flex min-h-11 items-center font-mono text-sm underline underline-offset-4 hover:bg-ink hover:text-white focus-visible:outline focus-visible:outline-2">LinkedIn</a>
                      ) : (
                        <span className="font-mono text-sm">LinkedIn, soon</span>
                      )}
                    </div>
                  ))}
                </div>
              </Window>
              <Window title="links.txt" tone="white">
                <LinkRow to="video" icon={<PlayCircle aria-hidden />}>The pitch video</LinkRow>
                <LinkRow to="pdf" icon={<FilePdf aria-hidden />}>The slides</LinkRow>
                <LinkRow to="repo" icon={<GithubLogo aria-hidden />}>The code</LinkRow>
                <LinkRow to="demo" icon={<Browser aria-hidden />}>The live demo</LinkRow>
              </Window>
            </div>
          </div>
        </section>
      </main>

      <footer className="on-cyan px-5 pb-12 pt-12">
        <div className={wrap}>
          <Window title="about" tone="white" className="w-[min(380px,100%)]">
            <p className="font-mono text-sm">
              LATAM Bank dispute assistant, version 1.0.
              <br />
              Made by team bitcoders.
            </p>
          </Window>
        </div>
      </footer>
    </>
  );
}
