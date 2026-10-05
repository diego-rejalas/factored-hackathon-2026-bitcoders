"use client";

import { ArrowsOut, DownloadSimple, Pause, Play, SpeakerHigh, SpeakerSlash } from "@phosphor-icons/react";
import { useEffect, useRef, useState } from "react";

import { Window } from "@/components/site/window";

const fmt = (s: number) => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}`;
const btn = "grid min-h-11 min-w-11 place-items-center border-2 border-ink bg-white px-2 hover:bg-cyan focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2";

// The pitch video in a window of the page, with its own controls instead of the browser's. It is a plain <video>, so the
// file can be swapped for any other without touching this component.
export function VideoPlayer({ src, poster, title, label, downloadHref, size }: { src: string; poster: string; title: string; label: string; downloadHref: string; size: string }) {
  const video = useRef<HTMLVideoElement>(null);
  const box = useRef<HTMLDivElement>(null);
  const [playing, setPlaying] = useState(false);
  const [started, setStarted] = useState(false);
  const [time, setTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [muted, setMuted] = useState(false);

  // The browser may have loaded the metadata before the page woke up, so read it once on mount as well.
  useEffect(() => {
    const el = video.current;
    if (el && el.readyState >= 1) setDuration(el.duration);
  }, []);

  const toggle = () => {
    const v = video.current;
    if (!v) return;
    if (v.paused) void v.play();
    else v.pause();
  };

  return (
    <Window title={title} tone="white">
      <div ref={box} className="bg-ink">
        <div className="relative aspect-video bg-black">
          <video
            ref={video}
            src={src}
            poster={poster}
            preload="metadata"
            playsInline
            aria-label={label}
            onClick={toggle}
            onPlay={() => {
              setPlaying(true);
              setStarted(true);
            }}
            onPause={() => setPlaying(false)}
            onEnded={() => setPlaying(false)}
            onLoadedMetadata={(e) => setDuration(e.currentTarget.duration)}
            onTimeUpdate={(e) => setTime(e.currentTarget.currentTime)}
            className="size-full cursor-pointer object-contain"
          />
          {!playing && (
            <button
              type="button"
              onClick={toggle}
              aria-label={started ? "Resume the video" : "Play the video"}
              className="absolute inset-0 m-auto grid size-20 place-items-center border-2 border-ink bg-cyan shadow-[6px_6px_0_var(--ink)] hover:bg-white focus-visible:outline focus-visible:outline-4 focus-visible:outline-offset-4 focus-visible:outline-white"
            >
              <Play size={36} weight="fill" aria-hidden />
            </button>
          )}
        </div>
        <div className="flex items-center gap-1.5 border-t-2 border-ink bg-win p-1.5 sm:gap-2 sm:p-2">
          <button type="button" onClick={toggle} aria-label={playing ? "Pause" : "Play"} className={btn}>
            {playing ? <Pause size={22} weight="fill" aria-hidden /> : <Play size={22} weight="fill" aria-hidden />}
          </button>
          <input
            type="range"
            min={0}
            max={duration || 0}
            step={0.1}
            value={time}
            onChange={(e) => {
              const v = video.current;
              if (v) v.currentTime = Number(e.target.value);
            }}
            aria-label="Seek"
            aria-valuetext={`${fmt(time)} of ${fmt(duration)}`}
            className="scrub min-h-11 min-w-0 flex-1"
            style={{ ["--p" as string]: duration ? `${(time / duration) * 100}%` : "0%" }}
          />
          <p className="shrink-0 font-mono text-sm tabular-nums">
            {fmt(time)} / {fmt(duration)}
          </p>
          <button
            type="button"
            onClick={() => {
              const v = video.current;
              if (!v) return;
              v.muted = !v.muted;
              setMuted(v.muted);
            }}
            aria-label={muted ? "Unmute" : "Mute"}
            aria-pressed={muted}
            className={btn}
          >
            {muted ? <SpeakerSlash size={22} aria-hidden /> : <SpeakerHigh size={22} aria-hidden />}
          </button>
          <button type="button" onClick={() => void box.current?.requestFullscreen?.()} aria-label="Full screen" className={btn}>
            <ArrowsOut size={22} aria-hidden />
          </button>
        </div>
      </div>
      <a href={downloadHref} download className="mt-3 inline-flex min-h-11 items-center gap-2 font-mono text-sm underline underline-offset-4 hover:bg-ink hover:text-white focus-visible:outline focus-visible:outline-2">
        <DownloadSimple size={18} aria-hidden />
        Download the video ({size})
      </a>
    </Window>
  );
}
