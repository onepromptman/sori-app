# Build and host Sori

Run the following from the repository root to build the web release.
The build uses Python's standard library.

```sh
python3 browser/build.py build/sori-web
```

`Sori-setup.zip` includes the local setup guide and server. `Sori-web.zip`
contains the static site for hosting. The `site/` folder contains the
same site files. Both ZIPs include the license and the font license.

Run the web slide import tests with Node.js 22 or newer.

```sh
node --test browser/slides/slides.test.mjs
```

## GitHub Pages

In the repository's **Settings > Pages**, choose **GitHub Actions** as
the source. In **Actions**, run [Publish Sori web](../.github/workflows/pages.yml)
on `main`. It builds and deploys the static site.

Verify the deployed link in Safari on a Mac and in Chrome. Open the
sample, transcribe an audio file, and import a PowerPoint from a clean
browser profile before sharing the link. People using the deployed URL
open Sori directly in the browser.

[GitHub Pages setup](https://docs.github.com/en/pages/getting-started-with-github-pages/configuring-a-publishing-source-for-your-github-pages-site)
