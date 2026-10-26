# Third-party notices

Sori itself is MIT licensed (see `LICENSE`). It redistributes the following
third-party components, which keep their own licences.

## Bundled fonts

Sori ships the same two families in two places, for two different jobs. Both
are licensed under the **SIL Open Font License, Version 1.1**, which permits
redistribution — including bundled inside an application — provided the
licence travels with the fonts and they are not sold on their own. Neither
family is sold, renamed, or modified here.

**`ui/fonts/`** — four `.woff2` files the app window loads for its own
interface. Present in every checkout. Licence: `ui/fonts/OFL.txt`.

**`engine/fonts/`** — eight `.ttf` files the optional private deck engine
names when it renders (`engine/install_fonts.py` installs them into the
Windows user font directory first, because PowerPoint substitutes a default
for any font it cannot find). Absent from public checkouts, which do not ship
`engine/`; the default `themes/studio.py` names stock system faces instead and
installs nothing. Licence: `engine/fonts/OFL.txt`.

| Font files | Family | Licence | Upstream |
|---|---|---|---|
| `ui/fonts/gowun-batang.woff2` · `engine/fonts/GowunBatang-{Regular,Bold}.ttf` | Gowun Batang | SIL OFL 1.1 | https://fonts.google.com/specimen/Gowun+Batang |
| `ui/fonts/ibm-plex-{sans,sans-semibold,mono}.woff2` · `engine/fonts/IBMPlex{Sans-Regular,Sans-SemiBold,Sans-Bold,Sans-VF,Mono-Regular,Mono-Medium}.ttf` | IBM Plex Sans / IBM Plex Mono | SIL OFL 1.1 | https://github.com/IBM/plex |

Full licence text: https://openfontlicense.org/open-font-license-official-text/

## Python dependencies

Installed from PyPI at build time and bundled into the release archive by
PyInstaller. Each keeps its own licence; these are the direct dependencies
declared in `requirements.txt`, `requirements-app.txt`, `requirements-claude.txt`
and `requirements-mac.txt`. The Claude-native door (`sori.py`) installs them
into `~/Sori/.venv` on the user's machine at first run rather than bundling
them; `uv`, when present, is used as the installer and is not redistributed.

| Package | Licence | Used for |
|---|---|---|
| `yt-dlp` | Unlicense | YouTube caption fetching |
| `faster-whisper` | MIT | local speech-to-text |
| `mlx-whisper` | MIT | local speech-to-text on Apple Silicon (installed by `sori.py` from `requirements-mac.txt`; not in the Windows archive) |
| `ctranslate2` | MIT | Whisper inference runtime |
| `av` (PyAV) | BSD-3-Clause | audio decoding |
| `onnxruntime` | MIT | voice-activity filter |
| `pywebview` | BSD-3-Clause | desktop window |
| `anthropic` | MIT | training generation (optional, needs your own API key) |
| `python-pptx` | MIT | `.pptx` deck writing |
| `numpy` | BSD-3-Clause | imported by the optional deck engine only |
| `matplotlib` | PSF-based (matplotlib licence) | imported by the optional deck engine only |
| `pyinstaller` | GPL-2.0-or-later **with a bootloader exception** | build tool only |

PyInstaller's licence carries an explicit exception permitting the resulting
frozen application to be distributed under any terms, so packaging Sori with
it does not make Sori GPL. PyInstaller is a build-time tool and none of its
own source ships in the release beyond that bootloader.

## Vendored deck engine (not in public checkouts)

`engine/deckgen.py` is Bryan Hong's own BH·SEOUL deck renderer, vendored
verbatim from a private repository and redistributed here under this
project's MIT licence. It is not distributed in public checkouts or in
the released archive.
