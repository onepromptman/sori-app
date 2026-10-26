# Where Sori should live: the hosting decision (2026-10-26)

The question: Sori today is a Windows exe plus a Claude plugin. Mac users
have no exe, a signed `.dmg` costs money (Apple Developer Program plus
notarisation), and the goal is one plug-and-play route for anyone on any
machine: download, transcribe, and generate a training from podcasts and
YouTube. This page records the options that were weighed, the facts that
decided it, and what was built.

## Decision

**The Claude plugin, run on the user's own computer, is the universal
door.** The Windows exe stays first-class for people who never open Claude.
Everything else (cloud routines, a ChatGPT app, a hosted web app) is either
a secondary option or ruled out, for the reasons below.

A Mac user's whole install is: Claude Desktop (or Claude Code) signed in on a
paid plan, **Customize > Plugins > Add marketplace > `onepromptman/sori-app`**,
then `/sori:setup`. No `.dmg`, no signing, no Homebrew, no terminal
knowledge. The plugin's `sori.py` creates Sori's own Python environment in
`~/Sori/.venv` on first use and the five skills drive it.

## The facts that decided it

| Fact | Checked how | Consequence |
|---|---|---|
| Claude plugins install from a public GitHub repo by `owner/repo` into a user's claude.ai account and sync to Cowork and Claude Code | [Plugins on claude.ai](https://claude.com/docs/plugins/overview), [Cowork: install plugins](https://claude.com/docs/cowork/guide/plugins) | GitHub is the free host. One repo, every OS. |
| Skills load everywhere; hooks and local processes load in Cowork and Claude Code, not in chat | [Platform support table](https://claude.com/docs/plugins/platform-support) | Sori's skills shell out to Python, so the Claude Desktop/Code tab and Cowork are the surfaces. Plain claude.ai chat cannot run it. |
| Anthropic's cloud sandbox (cloud sessions, scheduled routines, Cowork-in-the-cloud) ships with **Trusted** network access: package registries and GitHub only. From this session, `youtube.com`, `feeds.simplecast.com` and a podcast CDN all returned `403` from the egress proxy | Probed live from a cloud session; [cloud environments: access levels](https://code.claude.com/docs/en/cloud-environments#access-levels) | A cloud routine needs a **Custom** allowlist (or **Full**) that the owner configures. It is never plug-and-play for a stranger. |
| YouTube blocks caption fetches from datacenter IPs with "Sign in to confirm you're not a bot"; the proof-of-origin-token workaround no longer works in most cases | yt-dlp issue tracker, Render and Azure reports, `bgutil-ytdlp-pot-provider` notes | Even with the allowlist open, cloud transcription of YouTube is unreliable. The user's home IP is the reliable place to fetch. |
| ChatGPT apps need a **publicly hosted HTTPS MCP server**, a verified OpenAI organisation, per-tool annotations, privacy policy and terms URLs, and a directory review; ChatGPT's own code sandbox has no internet | [OpenAI Apps SDK: deploy](https://developers.openai.com/apps-sdk/deploy), [submission guide](https://help.openai.com/en/articles/20001040-submitting-apps-to-the-chatgpt-app-directory) | Hosting it means running and paying for a server that does the downloading and Whisper work, which is the cost being avoided, and the server would sit on a datacenter IP (see the row above). |
| `faster-whisper` runs on Apple Silicon but on the CPU only; `mlx-whisper` runs the same models on the Apple GPU | PyPI (`mlx-whisper` 0.4.3), MLX community model repos | Sori gains an MLX backend, auto-selected on Apple Silicon; the Mac is the fastest Sori machine, not the slowest. |
| macOS ships an old `python3` (3.9 behind the Xcode tools) and Homebrew's Python refuses `pip install` outside a venv | PEP 668; Apple developer docs | A launcher must own its own venv and must be able to fetch a current Python (`uv` does). |

## Options, scored

| Option | Works on a Mac today | Hosting cost | Plug-and-play for a stranger | Transcription reliability | Training (deck) | Verdict |
|---|---|---|---|---|---|---|
| **A. Claude plugin on the user's machine** (Claude Desktop Code tab, Claude Code, Cowork local) | Yes | $0 (GitHub) | Yes: add marketplace, `/sori:setup` | High: home IP, local Whisper, Apple GPU | Free (session writes the outline) or paid API route | **Chosen** |
| B. Cloud routine (Claude Code scheduled task) | Yes, PC can be off | $0 beyond the plan | No: owner must set a Custom allowlist and a GitHub token; captions only, no Whisper | Low for YouTube (bot check), fine for RSS text but no audio | Paid only (no session to write the outline) | Keep as documented, owner-only option (`cloud/`) |
| C. ChatGPT app / custom GPT | Yes | A server you run | No: OpenAI org verification, review, OAuth | Low: datacenter IP; the GPT itself cannot download | Would need a Python render service | Not pursued. A "paste a transcript, get a study guide" GPT is the only zero-hosting shape, and it drops the download/transcribe half. |
| D. Hosted web app (e.g. a Vercel front end plus a worker) | Yes | Compute for Whisper + a residential proxy | Yes | Low (bot check) | Yes | Rejected: pays for exactly the two things the local route gets free. |
| E. Native Mac app (`.dmg`) | Yes | ~$99/yr Apple Developer Program, notarisation, a second build pipeline | Yes | High | Yes | Rejected on cost and maintenance; the plugin reaches the same user with zero build. |
| F. Remote MCP server for Sori (one server, both Claude and ChatGPT connect to it) | Yes | A server you run | Yes | Low (datacenter IP) | Yes | Parked. Reasonable later if a hosted service is ever wanted; shares C and D's IP problem. |

## What "plug and play" means after this change

| Person | Path | First-run cost |
|---|---|---|
| Mac user on a paid Claude plan | Add the marketplace in Customize > Plugins, type `/sori:setup` in Claude Desktop (Code tab) or Cowork, then `/sori:transcribe <url>` | About a minute of installs, a 150 MB Whisper model on first audio |
| Linux user with Claude Code | `claude plugin marketplace add onepromptman/sori-app`, `claude plugin install sori@sori`, `/sori:setup` | Same |
| Windows user who never opens Claude | `Sori-win64.zip` from the release page, double-click `Sori.exe` | Unchanged |
| Windows user with Claude | Either; the plugin and the exe share `%USERPROFILE%\Sori` | Same as Mac |
| Anyone with a terminal and no Claude | `git clone`, `python3 sori.py transcribe youtube <url>` | Same |

## Security scope of the decision

The plugin route keeps Sori's existing boundary intact: nothing leaves the
machine but the feed and audio fetches, the key (if any) stays in
`~/Sori/credentials.json`, and the default training route spends nothing.
It adds one new thing, a launcher that creates a virtualenv and installs
from PyPI, and one new optional dependency on Apple Silicon. Both are
covered in [SECURITY.md](SECURITY.md).

The two routes that were not chosen would each have added a trust boundary
Sori does not have today: a server holding other people's transcripts and
keys (C, D, F), or a cloud identity with repo write access and an open
egress allowlist (B). Not adding those is part of the decision.

## Parked, with the reason

- **Native `.dmg`**: revisit only if a non-Claude Mac audience appears. The
  `app.py` window runs on macOS from source already (pywebview over WebKit),
  so the gap is signing and packaging, not code.
- **Remote MCP server**: revisit if Sori should be a shared service for a
  team rather than a personal tool. Needs a residential egress for YouTube
  or a captions-only promise.
- **ChatGPT**: revisit only as a thin client over the MCP server above.
