# Optional CLI and Claude plugin

Sori's browser launcher is the primary entry point. The optional `sori.py`
launcher offers CLI profiles and the training pipeline without requiring the
desktop window. Run it from the source directory with Python 3.11 or newer.

```text
python sori.py doctor
python sori.py setup
python sori.py shows list
python sori.py transcribe audio sample.mp3 --out sample.txt
python sori.py train --brief
python sori.py curate --list
```

This optional launcher keeps its environment in <SORI_HOME>/.venv. The browser
launcher uses the existing preflight environment, so the two environments are
separate while the library and engine lock are shared. Dependencies follow the
checkout's exact direct pins and shared constraints. `update` reinstalls those
pins; upgrade the source release to receive newer tested dependencies.

The claude profile excludes the paid API client and desktop window. Use
`python sori.py --profile app app` for the browser dependency profile, or
`python start_sori.py` for the primary browser setup. Optional arm64 macOS MLX
transcription is provided but has not been tested on physical Mac hardware here.
Its platform-specific transitive dependency closure is not covered by the
Windows lock. Use SORI_WHISPER_BACKEND=faster to keep the default CPU backend.

The plugin supplies curate, design and setup skills plus separate author/reviewer
roles. Role descriptions are instructions to the client, not an always-running
service. Scheduling transcription does not start a Claude conversation.
Client installation and live client execution require their own verification;
Cowork upload remains unverified. Your client's normal usage charges apply.

See [pipeline](PIPELINE.md), [privacy](../PRIVACY.md) and [CLI](CLI.md).
