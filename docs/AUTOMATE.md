# Automating Sori: four ways to run the daily sweep

All four run the same engine, `app.py --sweep` (`python3 sori.py sweep`
through the launcher): check every subscribed show, transcribe new episodes
for shows marked Auto, generate a training for shows marked Auto-train
(paid), append a block to `sweep.log`. They differ in where the machine is,
what it can transcribe, and where the files land.

| | (a) Windows scheduled task | (b) Cowork schedule, on this computer | (c) Cloud routine | (d) launchd / cron (Mac, Linux) |
|---|---|---|---|---|
| How | `setup-auto-sweep.bat` registers a `schtasks` job that runs `Sori.exe --sweep` daily at 09:03 | A recurring Cowork task runs `/sori:sweep` on your Mac or PC | A Claude Code scheduled task runs `cloud/sweep_cloud.sh` on an Anthropic runner | A launchd agent or a cron line runs `python3 sori.py sweep` |
| Transcribes | Everything: YouTube captions and Whisper for audio/RSS | Everything (same engine, same machine; MLX on Apple Silicon) | YouTube captions only; no Whisper; needs a Custom network allowlist; YouTube bot-checks datacenter IPs | Everything |
| Needs | The unzipped exe; PC on at 09:03 | Claude Desktop + the Sori plugin; machine on when it fires | A private output repo, a GitHub token, an environment with Custom network access, optionally `ANTHROPIC_API_KEY`; PC can be off | A checkout or the plugin folder; machine on (launchd runs a missed job at next wake) |
| Output lands in | `%USERPROFILE%\Sori\Transcripts\` | `~/Sori/Transcripts/` (the folder every door reads) | `sori-output/state/Transcripts/`, one commit per run | `~/Sori/Transcripts/` |
| Tells you what happened | Nothing; read `sweep.log` | A message in Cowork after every run | A git commit message with the counts; details in `sweep.log` | Nothing; read `sweep.log` |
| Training (paid) | If a key is saved in Settings | If a key is saved in Settings | If `ANTHROPIC_API_KEY` is a routine secret (`SORI_KEY_FROM_ENV=1` is set by the script) | If a key is saved in Settings |
| Status | Shipped, used since v2 | Prompt below | Spec in `cloud/`; creating it is ask-first, owner-only | Shipped with 3.3 |

Pick (a) if you never open Claude on Windows. Pick (b) if you use Claude
Desktop on this machine: it is the same full-strength sweep with a readable
report instead of a log file, and it is the Mac default. Pick (d) if you want
the sweep to run without Claude at all on a Mac or Linux box. Pick (c) only
for YouTube shows you want swept even when the computer is off, and only if
you own the environment.

Never point two of these at the same `~/Sori`: both queue the same episodes.

## (a) Windows scheduled task

Double-click `setup-auto-sweep.bat` in the unzipped Sori folder once. It
creates the task `Sori Daily Sweep` (`schtasks /create ... /sc daily /st
09:03`) that runs `Sori.exe --sweep` with no window. Everything lands in
`%USERPROFILE%\Sori`: `Transcripts\<Show>\<date> - <title>.txt` and, for
Auto-train shows with a saved key, `Trainings\<Show>\...pptx` + `.md`. To
check it, open the app (the Library shows the new files) or read the last
block of `%USERPROFILE%\Sori\sweep.log`; each block ends with `Done in Ns:
N transcribed, N failed, N skipped, N trained, N training failed.` Remove
it with `schtasks /delete /tn "Sori Daily Sweep" /f`. The PC has to be on
and awake at 09:03; a missed run is not caught up.

## (b) Cowork schedule, on this computer (the Claude-native door)

Prerequisites, once:

1. The Sori plugin is on your account (**Customize > Plugins > Add
   marketplace** `onepromptman/sori-app`, add **sori**) and `/sori:setup`
   has been run once on this machine, so `~/Sori/.venv` exists.
2. The task runs **on this computer**, not in the cloud. A cloud Cowork
   task cannot reach YouTube or podcast hosts (see (c)) and would write
   files somewhere you cannot see.
3. `SORI_HOME` is left **unset**, so the sweep reads and writes the same
   `~/Sori` the other doors use. Set it only if you deliberately want a
   second, separate subscription list.
4. Do not also leave (a) or (d) registered on the same folder.

Create a recurring Cowork task, daily, 09:03, with this prompt verbatim:

```
Run the Sori sweep with /sori:sweep, then run /sori:curate on whatever landed. Tell me which transcripts landed, which the curator marked train / park / skip and why, and which briefs passed the critic and are ready for /sori:design; if a show or a stage failed, say why.
```

To also build the decks in the same run (your own viewing, your Claude
Design, private), set the backend once with `python3 sori.py design-config
design_backend claude-design` plus `design_system_url`, and append: "then
run /sori:design on every brief that passed." Leave that line out to keep
deck-building a step you trigger.

What lands where: `~/Sori/Transcripts/<Show>/` and `Trainings/<Show>/`, so
the desktop app's Library (on Windows) shows them the next time it opens.
How to check: the Cowork message after each run lists the saved paths and
per-show errors; `~/Sori/sweep.log` has the same block. Training runs only
for shows you marked Auto-train and only if a key is saved (`/sori:shows` →
`settings api-key set` with `ANTHROPIC_API_KEY` in the environment); it
costs money per new episode, so leave Auto-train off until you want that.

Before you schedule it, run `/sori:transcribe` once on a YouTube URL from a
Cowork task to confirm your Cowork setup reaches YouTube; the Cowork sandbox
has its own network rules.

## (c) Cloud routine (captions-only, owner-only)

A Claude Code scheduled task clones the repo into a cloud runner, installs
`requirements-captions.txt` (yt-dlp, anthropic, python-pptx, numpy,
matplotlib; no Whisper), and runs `cloud/sweep_cloud.sh`. The full spec,
the verbatim routine prompt, the secrets, the network allowlist the
environment must carry, and the dry-run-first procedure are in
[`cloud/ROUTINE.md`](../cloud/ROUTINE.md); the output layout is in
[`cloud/README.md`](../cloud/README.md).

Two facts decide its place in this table. Anthropic's cloud environments
default to **Trusted** network access, which reaches package registries and
GitHub and nothing else: probed from a cloud session on 2026-10-26,
`youtube.com`, a Simplecast feed and a podcast CDN all returned `403`. The
environment's owner can switch it to **Custom** and list the YouTube hosts.
And YouTube answers many datacenter IPs with "Sign in to confirm you're not
a bot", which yt-dlp cannot reliably clear any more. So this route is
best-effort for YouTube and useless for audio; it exists for the repo owner's
own channels, not as a way to hand Sori to someone else.

## (d) launchd (Mac) or cron (Linux)

No Claude involved. The sweep runs headless from Sori's own environment and
appends to `~/Sori/sweep.log`. `SORI` below is the folder holding `sori.py`:
a `git clone` of `onepromptman/sori-app`, or the installed plugin folder
(Claude Code keeps it under `~/.claude/plugins/`; `/sori:setup` can print
the exact path).

**Mac, launchd.** Save this as `~/Library/LaunchAgents/com.sori.sweep.plist`
with `SORI` replaced by the real path, then run
`launchctl load ~/Library/LaunchAgents/com.sori.sweep.plist`.

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.sori.sweep</string>
  <key>ProgramArguments</key>
  <array>
    <string>/usr/bin/python3</string>
    <string>SORI/sori.py</string>
    <string>sweep</string>
  </array>
  <key>StartCalendarInterval</key>
  <dict><key>Hour</key><integer>9</integer><key>Minute</key><integer>3</integer></dict>
  <key>StandardOutPath</key><string>/tmp/sori-sweep.out</string>
  <key>StandardErrorPath</key><string>/tmp/sori-sweep.err</string>
</dict>
</plist>
```

launchd runs a missed job the next time the Mac wakes, so a closed laptop at
09:03 still gets its sweep. Remove with `launchctl unload` on the same file
and delete it.

**Linux, cron.** `crontab -e`, then:

```
3 9 * * * /usr/bin/python3 SORI/sori.py sweep >> /tmp/sori-sweep.out 2>&1
```

Both call the launcher, so the environment is created on the first run if
it is missing (that run takes a minute longer and installs from PyPI).
Training on either happens only for Auto-train shows with a saved key.
