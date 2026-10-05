# Landing page

A single static page (`index.html`) with the pitch video, the slides, the repository, the live demo and the team. No build step and no dependencies.

Open `site/index.html` in a browser to see it. The four links that are not final live in the `LINKS` object at the bottom of the file (the video, the slides PDF and the two LinkedIn profiles). A link left empty shows its button as "soon". Fill one in and it turns on.

To publish it, serve the `site/` folder as is. GitHub Pages works once the repository is public (Settings, Pages, deploy from the `main` branch and the `/site` folder is not offered by default, so use a workflow or copy the folder to `docs/`). Any static host also works, for example a Cloud Storage bucket with website hosting.

The screenshots are real captures of the running application on synthetic data.
