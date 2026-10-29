# Security

Please report a security problem privately, not in a public issue.

1. Open the repository's **Security** tab and choose **Report a vulnerability**. GitHub
   keeps the report private between you and the maintainer.
2. Say what you found, how to reproduce it, and which version you ran (the number in
   `pyproject.toml`, or the release zip's name). Use a made-up key and made-up shows.
3. If that button is missing, open an issue that says only "security contact, please"
   and the maintainer will reach out privately.

You can expect a first reply within seven days. Sori is maintained by one person: there
is no SLA and no bounty.

## What counts

First, what the app's log is allowed to hold: `sori.log` may contain host names, file
names, error classes and short error messages, and never your API key, transcript text,
a full URL (feed links can carry private tokens) or a full folder path (paths carry your
user name). Anything beyond that in `sori.log` is a bug worth reporting.

- Your Claude API key reaching anything other than the Claude API: a log line,
  `sweep.log` or `sori.log`, `shows.json`, a transcript, a deck, or the screen past its
  last four characters.
- A training call (which costs money) that runs without your say-so: a show you did not
  mark Auto-train, or a key you never entered in Settings.
- A feed, caption file or transcript that can make the app run code, open a file outside
  your Sori folder, or load a remote page into the window.
- A secret or personal data committed to this repository.

## Supported versions

Only the latest release and the latest commit on `main` get fixes.
