# Upgrading from Earshot or Podcast Studio

The app was called Podcast Studio, then Earshot, before settling on Sori.
Two things to know if you ran an earlier build.

**Your data moves itself.** State used to live in
`%USERPROFILE%\PodcastStudio` (that folder name outlived the Earshot
rebrand). On first launch Sori renames it to `%USERPROFILE%\Sori`; every
show, transcript, and training carries over. If the rename cannot happen,
Sori keeps using the old folder rather than starting empty.

**The old scheduled task lingers.** An earlier `setup-auto-sweep.bat`
registered a task under the previous name, and the new one does not replace
it, so you would end up with both. Remove the stale one once, in a Command
Prompt:

```
schtasks /delete /tn "Earshot Daily Sweep" /f
schtasks /delete /tn "Podcast Studio Daily Sweep" /f
```

Whichever does not exist just reports "task does not exist". Harmless.

## From 3.1 to 3.2

**`train.py --api-key` is gone.** A key on the command line lands in shell
history and process listings, and the new `settings.py api-key set` never
takes one that way either. Put the key in `ANTHROPIC_API_KEY` for one run,
or save it once with `settings.py api-key set` (it reads that variable). A
script that still passes `--api-key` exits 2 with a usage error and spends
nothing.

**Training no longer needs a key from a Claude session.** `train.py
--brief` prints the house rules and the outline schema; a Claude Code or
Cowork session writes `outline.json` and `train.py <transcript> --outline
outline.json` renders it through the same validator and renderer as the API
route. The exe still uses the API route. `transcribe.py` now writes the
same three-line header the sweep writes (title, `show — date`, source), so
`train.py` reads metadata from CLI transcripts too; `--title/--show/--date`
override it.

## From 3.2 to 3.3

**There is a launcher.** `python3 sori.py <verb>` replaces "install the
requirements, then run the script" on every OS. It keeps Sori's Python in
`~/Sori/.venv`, so a plugin update never breaks it and `SORI_HOME` still
isolates everything. The scripts themselves are unchanged and still run
directly if you manage your own environment.

**The plugin has a fifth skill, `/sori:setup`,** and the other four call
`sori.py`. Reinstall or update the plugin to get them; the old skills keep
working against the same files.

**Apple Silicon gets MLX.** `sori.py setup` installs `mlx-whisper` there and
`transcribe.py` picks it automatically. Nothing changes on Windows, Linux,
or Intel Macs. `SORI_WHISPER_BACKEND=faster` restores the CPU path.

**`SORI_KEY_FROM_ENV=1`** is the only way the engine reads
`ANTHROPIC_API_KEY` for the window, the sweep and Auto-train (train.py's own
lookup is unchanged). Only `cloud/sweep_cloud.sh` sets it. If you had a
script that relied on a shell key reaching the desktop sweep, it never did;
nothing to change.

**A store written by the exe (`deck_theme: baek`) now renders on a checkout
without `engine/`** by falling back to `studio` instead of failing.
