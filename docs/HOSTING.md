# Where Sori runs

## Try the ZIP

1. Save [Sori-setup.zip](https://github.com/onepromptman/sori-app/releases/download/v3.4.2/Sori-setup.zip)
   in Downloads. Open ChatGPT Desktop in **Codex** on
   **This computer**, or Claude Desktop in **Claude Code** using your local
   computer.
2. Paste this message:

   > Set up Sori from Sori-setup.zip in Downloads on this computer. Follow
   > SETUP.txt, then open Sori in my browser.

The assistant opens Sori in your default browser. Use a local assistant
session with file and command access. The [setup guide](../browser/SETUP.txt)
is included in the ZIP.

Click **Open sample**.
The reader pairs the sample transcript with a short lesson. Next, choose
an audio file and click **Transcribe**. The first job downloads Whisper.
The audio, transcript, and imported training files stay in that browser.
To make slides, copy the request into ChatGPT or Claude and bring the
downloaded deck or guide back into Sori under the transcript.

## Publish one link

1. In the public repo, open **Settings > Pages** and choose **GitHub Actions**
   as the source. Under **Actions**, run the manual
   [Publish Sori web workflow](../.github/workflows/pages.yml) on `main`.
2. Open the URL from the deployment in Safari on a Mac and in Chrome.
   From a clean browser profile, open the sample, transcribe an audio file,
   and import a PowerPoint. Share the verified URL as **Open Sori**.

People who open that link only need a browser. ChatGPT and Claude are optional
for making slides. See [GitHub Pages setup](https://docs.github.com/en/pages/getting-started-with-github-pages/configuring-a-publishing-source-for-your-github-pages-site)
and [the web build instructions](../browser/README.md).

## Desktop edition

Run the desktop edition on your own computer. The launcher opens a browser
tab for the local Python process, which binds to 127.0.0.1 and uses
per-launch authentication. Do not expose that process with a public
reverse proxy. Keep your computer on during transcription or scheduled work.

The captions-only cloud scripts are a separate advanced route. They require
your own environment and storage, and are not a hosted multi-user Sori product.
Review [cloud instructions](../cloud/README.md) and their validation limits.
Never put your local data folder, credentials or source recordings in a release.
