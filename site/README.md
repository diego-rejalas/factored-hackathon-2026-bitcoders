# Landing page

A Next.js app (static export) with Tailwind v4 and shadcn-style components. It gathers the pitch video, the slides, the repository, the live demo and the team on one page.

```bash
cd site
pnpm install
pnpm dev            # http://localhost:3000
pnpm build          # writes the whole site to out/
npx serve out       # to look at the build
```

## Links that are not final

The video, the slides PDF and the two LinkedIn profiles are in `lib/links.ts`. An empty one shows as "Soon" and cannot be clicked. Fill one in and every button that uses it turns on. To publish the slides, put the PDF in `public/` and set `pdf: "/bitcoders-pitch.pdf"`.

## Publishing

`out/` is plain static files, so any static host works (GitHub Pages, a Cloud Storage bucket, Vercel). For a GitHub Pages project URL, build with `NEXT_PUBLIC_BASE_PATH=/<repo> pnpm build`. GitHub Pages needs the repository to be public.

## Notes

- The theme follows the system: dark is the product's own look, with a light variant.
- Motion appears once, as sections enter the view. Users who ask for reduced motion get a plain fade.
- The screenshots in `images/` are real captures of the running application on synthetic data.
- `components/ui/` holds the shadcn-style `button`, `badge` and `card`, written by hand in the shadcn pattern and styled with the same variables as the theme.
