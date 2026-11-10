# Changelog

## 3.2.2 (release candidate)

- Build public artifacts from tracked source in a fresh folder; exclude the
  private renderer and refuse to re-zip old binaries. Include checksums.
- Explain local browser operation, data flow, costs and release status.
- Request self-study objectives, exercises, quiz answers and review activities.
- Confirm transcript sharing before manual training or enabling Auto-train.
- Add browser origin checks and a content security policy. Keep rejected
  transcript excerpts and provider error bodies out of training diagnostics.

- Every skill runs `preflight.py` first. It checks for Python 3.11 or newer,
  keeps Sori's packages in its own environment, installs only what that skill
  needs, and says before a Whisper model download. Nobody runs pip by hand.
- One engine per Sori folder: the browser app, the desktop window and the
  sweep share one lock file, so two of them can no longer queue the same
  episodes. A second sweep, or `--window` beside the browser app, stands down.
- `transcribe.py` prints one plain line instead of a traceback when a feed or
  file cannot be read, and the `audio` verb writes the same three-line header
  as the other verbs.
- A `data` slide shows its heading, and a missing study guide is no longer
  reported as something Claude returned on the free route.
- The README covers installing the plugin by upload.
- Installing from source holds every package to `requirements.lock`, so a
  newer release of a dependency can no longer break transcription.
- Clarified installation routes and added contribution guidance.
- Preserve corrupt store backups, reject malformed folder and seen identities,
  and avoid transcript filename collisions.
- Report sweep failures, retain rolling caption updates, and protect pasted URLs
  and mistaken key arguments in command-line diagnostics.
- Capture preview screenshots safely and document local and blocked acceptance cases.
- `Sori.exe` now runs as a local web app and opens in your browser. It keeps
  working after the tab closes, and Settings has a Stop button. `--window` opens
  the older desktop window.
- A deck is refused when a quote is not word for word in the transcript, or a
  stat or chart figure is not a number the transcript states. An earlier good
  deck is left untouched.

## 3.2.1

- See the repository history and releases for earlier changes.
