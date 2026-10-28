# Maintaining Sori

Notes for whoever builds, tests or releases Sori. Each rule below was
learned the hard way: a broken build, a stuck queue or a wasted paid call.
Setup for users is in the [README](../README.md); the command-line tools
are in [CLI.md](CLI.md).

## Rules that bit us

- **Build with `package.py`, never raw PyInstaller.** PyInstaller emits only
  `Sori.exe` + `_internal/`; the sidecars beside the exe come from
  `package.py`, which fails loudly if one is missing.
- **Close every Sori window before building.** An exe running from
  `dist/Sori/` locks the folder; PyInstaller then fails (exit 1) or the
  background build stalls silently.
- **`SORI_HOME=<dir>` isolates state** (subscriptions, transcripts, key).
  Two app instances on one state dir both auto-queue and reproduce the
  "endless queue".
- **`add_show` seeds `seen` with all but the newest episode**, so a fresh
  subscription offers exactly one episode. Trim `seen` in `shows.json` to
  stage more.
- **UI work happens in a browser, not the WebView.** `py
  tools/ui-preview/preview.py` serves `ui/` with a fake bridge (`stub.js`
  must load before `app.js`; the bridge wait times out after 8 s; a Proxy
  stub must return `undefined` for `then`). `--shot out.png` renders a
  crisp PNG through headless Edge. PrintWindow on the real app returns
  stale paint; a background process cannot foreground it.
- **Check layouts at 1024 wide.** The page's minimum width is 1024 logical
  px; the window opens at 1360x820 so that a 125% or 150% display still
  shows the right-hand buttons.
- **Row grid:** `.ep` is `24px minmax(0,1fr) 156px 138px`; the last column
  must hold a 100 px action button plus the 26 px Dismiss control.
- **`gh release upload --clobber` prints nothing.** Verify by comparing the
  asset `digest` to a local sha256, not by timestamps.
- **Training costs money.** Nothing in tests may call Anthropic;
  `tests/conftest.py` installs a fake `anthropic` whose client raises.
  `train.py` reads `ANTHROPIC_API_KEY`, then the app's saved key; the sweep
  reads the saved key only. No CLI takes a key on argv (`settings.py
  api-key set` reads the env var). Never print a key; last 4 chars at most.
- Fonts in `ui/fonts/` are SIL OFL 1.1; `THIRD-PARTY-NOTICES.md` must
  ship in every zip (it is a `package.py` sidecar).

## Provenance

The optional deck engine (`engine/deckgen.py`, not part of this repository) was copied from a private design repository.
