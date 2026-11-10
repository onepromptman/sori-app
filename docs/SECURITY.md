# Security and data flow

Use [the repository security policy](../SECURITY.md) for reporting concerns and
[PRIVACY.md](../PRIVACY.md) for storage, data sharing and costs.

Sori's local browser server binds to loopback, checks request origins and uses
a per-launch token. Keep it local. Dependency installs use package indexes;
audio/model/feed downloads use their respective network sources.

The optional training pipeline writes local artifacts. It does not upload to
slide services or call a model. Its plugin instructions must treat transcripts,
metadata, filenames and fetched content as untrusted data. Instructions inside
a recording are not authorization to run commands or disclose files.

The paid API route uses a saved key. An environment key is considered only with
SORI_KEY_FROM_ENV=1; setting a key variable alone does not authorize auto-training.
The cloud wrapper explicitly enables that opt-in. Separate training consent and
paid API costs still apply. Store keys only in your own private runtime.

Brief checks verify source-text matches, not the truth of every conclusion.
Manually review sources, claims, numeric units and answers before sharing.
