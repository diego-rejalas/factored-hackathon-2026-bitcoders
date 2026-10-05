# Landing page

A Next.js app (static export) with Tailwind v4 and shadcn-style components. It gathers the pitch video, the slides, the repository, the live demo and the team on one page.

```bash
cd site
pnpm install
pnpm dev            # http://localhost:3000
pnpm build          # writes the whole site to out/
npx serve out       # to look at the build
```

## Links

`lib/links.ts` holds the links. The video and the slides are served from `public/` and play in the page; the two LinkedIn profiles and the repository are written there. An empty link shows as "Soon" and cannot be clicked.

The address of the live app is not in the code. Set `NEXT_PUBLIC_DEMO_URL` when you build, or put it in `.env.local` (ignored by git; `.env.example` shows the name). Without it the "Live demo" buttons show "Soon".

The pitch video comes from `NEXT_PUBLIC_VIDEO_URL` when it is set, and from `public/` otherwise. Use a host that answers range requests (an object-storage bucket, YouTube, Vimeo): a host that ignores them, like Cloudflare Pages, plays the video but cannot skip through it.

## Publishing

`out/` is plain static files, so any static host works (GitHub Pages, a Cloud Storage bucket, Vercel). For a GitHub Pages project URL, build with `NEXT_PUBLIC_BASE_PATH=/<repo> pnpm build`. GitHub Pages needs the repository to be public.

## Notes

- The theme follows the system: dark is the product's own look, with a light variant.
- Motion appears once, as sections enter the view. Users who ask for reduced motion get a plain fade.
- The screenshots in `images/` are real captures of the running application on synthetic data.
- `components/ui/` holds the shadcn-style `button`, `badge` and `card`, written by hand in the shadcn pattern and styled with the same variables as the theme.
