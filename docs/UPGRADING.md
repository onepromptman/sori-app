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
