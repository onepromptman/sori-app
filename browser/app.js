import { addSource, readLibrary, removeRecord, saveRecord, saveSlideResults, updateSource, watchLibrary } from "./storage.js";
import { describeSource, fetchEpisodeAudio, loadFeed, readFeedFile, searchPodcastFeeds, youtubeVideoId } from "./sources/index.js";
import { createSlideRequest, prepareSlideImports } from "./slides/index.js";
import { transcribeAudio } from "./transcription/index.js";
import { canRecordTabAudio, recordTabAudio } from "./transcription/tab-audio.js";

const $ = id => document.getElementById(id);
let library = { sources: [], transcripts: [], files: [], evidence: [] };
let selected = null;
let running = null;
let feedSearch = null;
let refreshNumber = 0;
const expanded = new Set();

function element(tag, text, className) {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (className) node.className = className;
  return node;
}

function button(text, action, className) {
  const node = element("button", text, className);
  node.type = "button";
  node.addEventListener("click", action);
  return node;
}

function link(text, target) {
  const url = new URL(target);
  if (!["https:", "http:"].includes(url.protocol) || url.username || url.password) {
    throw new Error("This link is unavailable.");
  }
  const node = element("a", text);
  node.href = url.href;
  node.target = "_blank";
  node.rel = "noopener noreferrer";
  return node;
}

function report(text, error = false, target = $("notice")) {
  target.textContent = text;
  target.hidden = !text;
  target.classList.toggle("error", error);
}

function message(error) {
  return error?.name === "QuotaExceededError"
    ? "This browser is out of storage. Download or remove older items, then try again."
    : error?.message || "Something went wrong. Try again.";
}

async function refresh() {
  const current = ++refreshNumber;
  const snapshot = await readLibrary();
  if (current !== refreshNumber) return;
  library = snapshot;
  renderSources();
  renderLibrary();
  renderReader();
}

function refreshSafely() {
  refresh().catch(error => report(message(error), true));
}

function activeTranscript() {
  return library.transcripts.find(item => item.id === selected);
}

function confirmRemoval(text) {
  const dialog = $("confirm");
  $("confirm-text").textContent = text;
  dialog.returnValue = "cancel";
  dialog.showModal();
  return new Promise(resolve => dialog.addEventListener(
    "close", () => resolve(dialog.returnValue === "remove"), { once: true }
  ));
}

async function remove(store, id, text) {
  if (!await confirmRemoval(text)) return;
  try {
    await removeRecord(store, id);
    await refresh();
  } catch (error) {
    report(message(error), true);
  }
}

function renderSources() {
  const sources = [...library.sources].sort((a, b) => a.title.localeCompare(b.title));
  $("sources").replaceChildren();
  if (!sources.length) $("sources").append(element("p", "Your podcast feeds will appear here.", "small"));
  for (const source of sources) {
    const row = element("div", undefined, "entry");
    row.append(element("p", source.title, "entry-title"));
    const actions = element("div", undefined, "actions");
    if (source.kind === "youtube") {
      actions.append(link("Open YouTube", source.url));
      if (youtubeVideoId(source.url)) {
        actions.append(button("Paste transcript", () => openYouTubeImport(source.url)));
      }
    } else if (source.kind === "rss") {
      actions.append(button("Refresh episodes", () => updateFeed(source)));
    }
    actions.append(button("Remove source", () => remove("sources", source.id, "Remove this source from Sori?"), "subtle"));
    row.append(actions);
    if (source.episodes?.length) {
      const episodes = element("details");
      episodes.open = expanded.has(source.id);
      episodes.addEventListener("toggle", () => {
        if (episodes.open) expanded.add(source.id);
        else expanded.delete(source.id);
      });
      episodes.append(element("summary", `${source.episodes.length} episodes`));
      const list = element("ul", undefined, "episodes");
      for (const episode of source.episodes) {
        const item = element("li", episode.title);
        if (episode.date) item.append(element("span", ` (${episode.date})`, "small"));
        item.append(button("Transcribe", () => startTranscription(
          episode.title, (signal, progress) => fetchEpisodeAudio(episode, {
            signal,
            onProgress: ({ loaded, total }) => progress("Downloading episode audio…", total ? loaded / total : undefined)
          }), { sourceTitle: source.title }
        )));
        item.append(link("Open audio", episode.audioUrl));
        list.append(item);
      }
      episodes.append(list);
      row.append(episodes);
    }
    $("sources").append(row);
  }
}

async function updateFeed(source) {
  try {
    report("Reading the podcast feed…");
    const feed = await loadFeed(source);
    if (!await updateSource({ ...source, ...feed })) return;
    expanded.add(source.id);
    await refresh();
    report("Episodes updated.");
  } catch (error) {
    report(message(error), true);
  }
}

async function saveSource(source, feed) {
  if (library.sources.some(item => item.id === source.key)) {
    throw new Error("This source is already in Sori. Open it under Sources.");
  }
  try {
    await addSource({ ...source, id: source.key, ...feed });
  } catch (error) {
    if (error?.name === "ConstraintError") throw new Error("This source is already in Sori.");
    throw error;
  }
  expanded.add(source.key);
  await refresh();
}

$("source-form").addEventListener("submit", async event => {
  event.preventDefault();
  const submit = event.currentTarget.querySelector("button");
  submit.disabled = true;
  try {
    const input = $("source-url");
    const source = describeSource(input.value);
    if (source.kind === "youtube") {
      if (!youtubeVideoId(source.url)) throw new Error("Open a video on YouTube and paste its video link here.");
      report("");
      openYouTubeImport(source.url);
      return;
    }
    if (library.sources.some(item => item.id === source.key)) {
      throw new Error("This source is already in Sori. Open it under Sources.");
    }
    report("Reading the podcast feed…");
    const feed = await loadFeed(source);
    await saveSource(source, feed);
    input.value = "";
    report("Podcast added. Pick an episode under Sources.");
  } catch (error) {
    report(message(error), true);
  } finally {
    submit.disabled = false;
  }
});

function openYouTubeImport(url) {
  const dialog = $("youtube-import");
  feedSearch?.abort();
  $("youtube-transcript-form").reset();
  $("youtube-record-options").open = false;
  $("feed-search-form").reset();
  $("feed-search-options").open = false;
  $("feed-search-results").replaceChildren();
  $("youtube-video-link").replaceChildren(link("Open YouTube", url));
  report("", false, $("youtube-import-status"));
  report("", false, $("feed-search-status"));
  dialog.dataset.url = url;
  dialog.showModal();
}

$("close-youtube-import").addEventListener("click", () => $("youtube-import").close());
$("youtube-import").addEventListener("close", event => {
  if (!event.currentTarget.open) {
    feedSearch?.abort();
    feedSearch = null;
  }
});

$("youtube-transcript-form").addEventListener("submit", async event => {
  event.preventDefault();
  const submit = event.currentTarget.querySelector("button[type=submit]");
  const status = $("youtube-import-status");
  const dialog = $("youtube-import");
  const url = dialog.dataset.url;
  const text = $("youtube-transcript").value.trim();
  if (!text) return report("Paste the transcript before saving.", true, status);
  const title = youtubeTitle(url);
  const entry = { id: crypto.randomUUID(), title, sourceTitle: "YouTube transcript", sourceUrl: url, text, created: Date.now() };
  submit.disabled = true;
  try {
    await saveRecord("transcripts", entry);
    dialog.close();
    await openTranscript(entry.id);
    report("YouTube transcript saved in this browser.");
  } catch (error) {
    report(message(error), true, dialog.open ? status : $("notice"));
  } finally {
    submit.disabled = false;
  }
});

function youtubeTitle(url) {
  return $("youtube-title").value.trim() || `YouTube · ${youtubeVideoId(url)}`;
}

$("record-youtube").addEventListener("click", () => {
  const dialog = $("youtube-import");
  const sourceUrl = dialog.dataset.url;
  if (!canRecordTabAudio()) {
    return report("Tab audio sharing is unavailable here. Try desktop Chrome or paste the transcript.", true, $("youtube-import-status"));
  }
  if (running) return report("Wait for the current transcription to finish.", true, $("youtube-import-status"));
  dialog.close();
  return startTranscription(youtubeTitle(sourceUrl), captureAudio, { sourceTitle: "YouTube tab audio", sourceUrl });
});

$("record-tab").addEventListener("click", () => {
  if (!canRecordTabAudio()) return report("Tab audio sharing is unavailable here. Try desktop Chrome or choose an audio or video file.", true);
  return startTranscription("Browser tab recording", captureAudio, { sourceTitle: "Browser tab audio" });
});

async function captureAudio(signal, progress) {
  const finish = $("finish-recording");
  progress("Choose the tab you want to record. Turn on Also share tab audio and click Share.");
  $("task").scrollIntoView({ block: "nearest" });
  try {
    return await recordTabAudio({ signal, onRecording: stop => {
      progress("Recording tab audio. Press Play in the shared tab. When you have the part you want, return here and click Finish and transcribe.");
      finish.onclick = stop;
      finish.hidden = false;
    } });
  } finally {
    finish.hidden = true;
    finish.onclick = null;
  }
}

$("feed-search-form").addEventListener("submit", async event => {
  event.preventDefault();
  feedSearch?.abort();
  const controller = new AbortController();
  feedSearch = controller;
  const status = $("feed-search-status");
  const results = $("feed-search-results");
  results.replaceChildren();
  report("Searching for podcast feeds…", false, status);
  try {
    const feeds = await searchPodcastFeeds($("feed-query").value, { signal: controller.signal });
    if (controller.signal.aborted) return;
    for (const feed of feeds) {
      const item = element("li", feed.title);
      item.append(button("Add feed", () => {
        $("youtube-import").close();
        $("source-url").value = feed.url;
        $("source-form").requestSubmit();
      }));
      results.append(item);
    }
    report(feeds.length ? "" : "No podcast feeds found. Try the show’s exact name.", false, status);
  } catch (error) {
    if (!controller.signal.aborted) report(message(error), true, status);
  } finally {
    if (feedSearch === controller) feedSearch = null;
  }
});

$("feed-file").addEventListener("change", async event => {
  const file = event.target.files[0];
  if (!file) return;
  try {
    const input = $("source-url").value.trim();
    const source = input ? describeSource(input) : null;
    if (source?.kind === "youtube") throw new Error("Use a podcast RSS URL with this feed file.");
    const feed = await readFeedFile(file, source?.url);
    await saveSource(source || { kind: "imported", key: `imported:${feed.title.toLowerCase()}` }, feed);
    report("Podcast added from file. Pick an episode under Sources.");
  } catch (error) {
    report(message(error), true);
  } finally {
    event.target.value = "";
  }
});

async function startTranscription(title, loadAudio, { sourceTitle = "Audio file", sourceUrl } = {}) {
  if (running) {
    report("A transcription is already running in this tab.");
    return;
  }
  const controller = new AbortController();
  const taskProgress = $("task-progress");
  const preview = $("task-preview");
  const previewText = $("task-preview-text");
  running = controller;
  $("task").hidden = false;
  $("cancel").disabled = false;
  $("transcribe-file").disabled = true;
  report("");
  function progress(label, ratio) {
    $("task-text").textContent = label;
    taskProgress.hidden = !Number.isFinite(ratio);
    if (!taskProgress.hidden) taskProgress.value = ratio;
  }
  try {
    progress("Opening audio…");
    const audio = await loadAudio(controller.signal, progress);
    const result = await transcribeAudio(audio, {
      signal: controller.signal,
      onProgress: event => progress({
        decoding: "Reading audio…",
        model: "Getting Whisper ready. The first download can take a few minutes.",
        transcribing: "Transcribing in this browser…"
      }[event.stage] || "Working…", event.progress),
      onPreview: text => {
        previewText.textContent = text;
        preview.hidden = false;
        previewText.scrollTop = previewText.scrollHeight;
      }
    });
    if (controller.signal.aborted) return;
    if (!result.text.trim()) throw new Error("Whisper didn’t find any speech in this audio.");
    const entry = { id: crypto.randomUUID(), title, sourceTitle, sourceUrl, ...result, created: Date.now() };
    await saveRecord("transcripts", entry);
    await openTranscript(entry.id);
    report("Transcript saved in this browser.");
  } catch (error) {
    if (controller.signal.aborted) report("Transcription cancelled.");
    else report(message(error) + (error?.code === "unreadable"
      ? " Try Open audio, then choose the file if you can download it." : ""), true);
  } finally {
    running = null;
    $("task").hidden = true;
    preview.hidden = true;
    previewText.textContent = "";
    $("transcribe-file").disabled = false;
  }
}

$("transcribe-file").addEventListener("click", () => {
  const file = $("audio-file").files[0];
  if (!file) return report("Choose an audio or video file first.", true);
  return startTranscription(file.name.replace(/\.[^.]+$/, "") || file.name, async () => file);
});
$("cancel").addEventListener("click", () => {
  $("cancel").disabled = true;
  running?.abort();
});

$("sample").addEventListener("click", async () => {
  try {
    if (!library.transcripts.some(item => item.id === "sample")) {
      await saveRecord("transcripts", {
        id: "sample", title: "Explain an idea in your own words", sourceTitle: "Fictional sample", created: Date.now(),
        text: "Before you teach an idea, put it into your own words. For example, take a short podcast segment and write one sentence explaining its main point. Then ask someone what they understood. Revise your sentence using their feedback. In our practice session, three readers tried the exercise."
      });
    }
    await openTranscript("sample");
  } catch (error) {
    report(message(error), true);
  }
});

function renderLibrary() {
  const query = $("search").value.trim().toLowerCase();
  const list = [...library.transcripts].sort((a, b) => b.created - a.created);
  const trainingByTranscript = new Map();
  for (const file of library.files) {
    if (!trainingByTranscript.has(file.transcriptId)) trainingByTranscript.set(file.transcriptId, []);
    trainingByTranscript.get(file.transcriptId).push(file);
  }
  $("transcripts").replaceChildren();
  const visible = list.filter(item => {
    const names = (trainingByTranscript.get(item.id) || []).map(file => file.name).join(" ");
    return `${item.title} ${item.text} ${names}`.toLowerCase().includes(query);
  });
  if (!visible.length) {
    $("transcripts").append(element("p", query
      ? "No matching transcripts or training files."
      : "Transcribe an episode or open the sample to see a transcript and lesson together.", "small library-empty"));
  }
  for (const item of visible) {
    const open = () => openTranscript(item.id).catch(error => report(message(error), true));
    const row = element("div", undefined, "library-row");
    const transcript = element("div");
    const title = button(item.title, open, "library-title");
    if (item.id === selected) title.setAttribute("aria-current", "true");
    transcript.append(title, element("p", item.sourceTitle, "small"));
    const training = element("div", undefined, "training-summary");
    const files = trainingByTranscript.get(item.id) || [];
    if (files.length) {
      const actions = element("div", undefined, "actions");
      for (const file of files.slice(0, 2)) {
        const action = button(file.name, () => downloadTraining(file), "training-file");
        action.setAttribute("aria-label", `Download ${file.name}`);
        actions.append(action);
      }
      if (files.length > 2) actions.append(button("View all", open));
      training.append(actions, element("p", `${files.length} returned file${files.length === 1 ? "" : "s"}`, "small"));
    } else if (item.id === "sample") {
      training.append(button("Preview sample lesson", open, "training-file"));
    } else {
      training.append(button("Add training", open, "training-file subtle"));
    }
    row.append(transcript, training);
    $("transcripts").append(row);
  }
}

async function openTranscript(id) {
  selected = id;
  report("", false, $("import-status"));
  await refresh();
  $("reader").scrollIntoView({ block: "start" });
  $("reader-title").focus({ preventScroll: true });
}

function renderReader() {
  const item = activeTranscript();
  $("reader").hidden = !item;
  if (!item) return;
  $("reader-title").textContent = item.title;
  $("reader-meta").textContent = item.sourceTitle;
  if (item.sourceUrl) $("reader-meta").append(" · ", link("Open YouTube", item.sourceUrl));
  $("reader-text").textContent = item.text;
  $("sample-training").hidden = item.id !== "sample";
  const panel = $("slide-results");
  panel.replaceChildren();
  const evidence = library.evidence.find(record => record.id === item.id);
  const files = library.files.filter(file => file.transcriptId === item.id);
  if (files.length) {
    const status = !evidence
      ? "Files saved. No source check was submitted."
      : evidence.status !== "passed"
        ? "Some submitted evidence did not match the transcript."
        : evidence.checked
          ? `${evidence.checked} evidence entries matched the transcript. Sori did not check the full deck.`
          : "No quotations or figures were listed for checking.";
    panel.append(element("p", status, "small"));
  }
  if (evidence?.issues?.length) {
    const issues = element("ul");
    for (const issue of evidence.issues) issues.append(element("li", String(issue)));
    panel.append(issues);
  }
  for (const file of files) {
    const row = element("div", undefined, "entry actions");
    row.append(element("span", file.name));
    row.append(button("Download", () => downloadTraining(file)));
    row.append(button("Remove file", () => remove("files", file.id, "Remove this file from Sori?"), "subtle"));
    panel.append(row);
  }
}

function downloadTraining(file) {
  download(file.blob ?? new Blob([file.bytes], { type: file.type }), file.name);
}

function download(blob, name) {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = name.replace(/[\\/:*?"<>|]/g, "_");
  document.body.append(anchor);
  anchor.click();
  anchor.remove();
  setTimeout(() => URL.revokeObjectURL(url), 30000);
}

$("search").addEventListener("input", renderLibrary);
$("save-transcript").addEventListener("click", () => {
  const item = activeTranscript();
  if (item) download(new Blob([item.text], { type: "text/plain" }), `${item.title}.txt`);
});
$("remove-transcript").addEventListener("click", () => {
  const item = activeTranscript();
  if (item) return remove("transcripts", item.id, "Remove this transcript and its returned files from Sori?");
});
$("copy-slide-request").addEventListener("click", async () => {
  const item = activeTranscript();
  if (!item) return;
  try {
    await navigator.clipboard.writeText(createSlideRequest(item));
    report("Slide request copied. Paste it into your chat.", false, $("import-status"));
  } catch {
    report("Clipboard access is unavailable. Download the request and attach it in your chat.", true, $("import-status"));
  }
});
$("save-slide-request").addEventListener("click", () => {
  const item = activeTranscript();
  if (item) download(new Blob([createSlideRequest(item)], { type: "text/plain" }), "sori-slide-request.txt");
});

async function importSlides(files) {
  const item = activeTranscript();
  if (!item || !files.length) return;
  try {
    const result = await prepareSlideImports(files, item);
    if (result.files.length || result.evidence) {
      if (!await saveSlideResults(item.id, result.files, result.evidence)) {
        throw new Error("This transcript was removed before the files could be saved.");
      }
      await refresh();
    }
    if (selected !== item.id) return;
    const saved = result.files.length ? `Saved ${result.files.length} file(s). ` : "";
    report((saved + result.errors.join(" ")).trim() || "Evidence saved.", Boolean(result.errors.length), $("import-status"));
  } catch (error) {
    if (selected === item.id) report(message(error), true, $("import-status"));
  }
}

$("slide-files").addEventListener("change", event => {
  const files = [...event.target.files];
  event.target.value = "";
  importSlides(files);
});
$("slide-drop").addEventListener("dragover", event => event.preventDefault());
$("slide-drop").addEventListener("drop", event => {
  event.preventDefault();
  importSlides([...event.dataTransfer.files]);
});
watchLibrary(refreshSafely);
refreshSafely();
