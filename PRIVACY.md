# Privacy and data flow

## Web edition

Sori stores the web library in your browser. Audio is decoded and
transcribed on the device. The runtime and speech model download from
jsDelivr and Hugging Face. Adding an RSS feed or opening episode audio
makes a request to that publisher or media host.

Sori only copies or downloads the text you choose to share with a chat.
Your chat provider receives it when you submit it there. Files you bring
back to Sori are stored in the same browser library.

## Desktop edition

Sori is a local browser app. Its server listens only on your own computer.
It has no hosted account, analytics, advertising, or telemetry service.

| Action | What leaves your computer |
|---|---|
| Follow a feed or fetch an episode | Requests to that publisher and its media host, including your IP address |
| Transcribe a local recording | No recording upload by Sori; the selected speech model downloads if needed |
| Make slides | Sori copies the request and transcript to your clipboard and opens the chat you choose. The chat receives the text when you paste and submit it. |
| First launch or use of a new speech model | Requests to download the speech model |
| Use the optional CLI with its API mode | Transcript text and episode metadata go to Anthropic using your API key. API charges apply. |

Transcripts, decks, subscription URLs and settings stay in your Sori folder.
Backup or sync software you configure may copy this folder. If you saved an
API key in an earlier release or for the CLI, the local `credentials.json` file
holds it as unencrypted JSON. See [CLI settings](docs/CLI.md) to clear it.

Closing the tab leaves the local app running. Use Settings > Stop to stop it.

Logs are local diagnostics and may include source host names, file names and
error messages. Review and redact logs before sharing. Do not publish your
Sori data folder, credentials, personal library, or private recordings.

Only process content you are allowed to use. A publicly available podcast
does not automatically permit redistributing its transcript or a derived deck.
Review generated material against the source before sharing or relying on it.

The public release is built from tracked source files in a fresh staging folder.
It excludes user state and the optional private rendering engine. This reduces
accidental packaging risk; it is not a guarantee that every dependency or
historic artifact is free of vulnerabilities or identifying information.

## Optional pipeline files

The CLI/plugin pipeline stores ledger.jsonl, curriculum.md and pipeline.json in
your local Sori data folder, and briefs, critiques and handoffs under Trainings.
These can contain source text, filenames, notes and links; keep them private.
The Python handoff commands do not upload files or call a model. Using a chat
client or external slide tool shares data according to that tool's policies and
your authorizations. An environment API key is read only when SORI_KEY_FROM_ENV=1
is explicitly set. The cloud wrapper opts in; ordinary browser startup does not.
