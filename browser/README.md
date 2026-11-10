# Sori web edition

From the repository root, run `python browser/build.py build/sori-web`.
The build produces `site/` and two ZIPs with Sori's artwork and fonts.
`Sori-web.zip` contains the static site for HTTPS hosting. `Sori-setup.zip`
contains the site and the [local trial guide](SETUP.txt) for a desktop
assistant. See [hosting and trial instructions](../docs/HOSTING.md).
The hosted app needs no backend, API key, account, or installer.

For local development, serve the built site on a loopback HTTP origin.
Use `text/javascript` or `application/javascript` for JavaScript assets.

- **Audio:** Whisper Tiny runs in a WebAssembly worker. The first job fetches
  a pinned runtime and model from jsDelivr and Hugging Face. Sori processes
  audio in this browser. Audio files are limited to 150 MB and two hours.
- **Podcasts:** Paste RSS or Atom, or choose a saved feed file up to 16 MB. The browser
  fetches feeds and episode audio directly when publishers allow it. A
  publisher can allow the feed and still block its media. In that case, open
  the audio and import a copy you can access. Direct episode downloads are
  limited to 100 MB.
- **YouTube:** Sori recognizes and stores video, channel, and playlist links.
  Use a podcast feed or import media you can access to transcribe. Sori does
  not fetch YouTube captions or audio in the web edition.
- **Slides:** Copy or download a request and submit it to Claude or ChatGPT.
  Download the resulting files and import them under the same transcript.
  Sori keeps the imported deck and guide and can check optional submitted
  quotes and figures against the transcript. That check does not inspect the
  complete deck. No chat account is needed until you choose a chat service.
- **Library:** The list pairs transcripts with their training files. Open
  the sample to see a fictional transcript and a short lesson together.
  Transcripts, sources, and returned files live in IndexedDB. Tabs on the
  same site update together. Download copies you want to keep outside
  the browser. Clearing site data removes the library.

Chrome on Windows was tested through local audio transcription. A Mac Safari
transcription run is part of the release check.
