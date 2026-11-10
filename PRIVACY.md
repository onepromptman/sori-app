# Privacy and data flow

Sori is a local browser app. Its server listens only on your own computer.
It has no hosted account, analytics, advertising, or telemetry service.

| Action | What leaves your computer |
|---|---|
| Follow a feed or fetch an episode | Requests to that publisher and its media host, including your IP address |
| Transcribe a local recording | No recording upload by Sori; the selected speech model downloads if needed |
| Generate Training or enable Auto-train | Transcript text and episode metadata go to Anthropic using your API key; API charges apply |
| Use Sori in an AI chat client | Content you give that client follows the client's own data policies and plan limits |
| Install or update dependencies | Requests to package and model download services |

Transcripts, decks, subscription URLs and settings stay in your Sori folder.
The API key is stored in `credentials.json` as local, unencrypted JSON. Protect
your operating system account. Backup or sync software you configure may copy
this folder; Sori itself does not sync it. Clear the key in Settings to remove it.

Closing the tab leaves the local app running. Use Settings > Stop to stop it.
Auto-train is optional and can spend API credits whenever new episodes finish.
Turn it off for each source to stop future automatic training requests.

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
