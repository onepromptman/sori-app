/* Sori — UI logic.
   Talks to app.py's Api class over the pywebview bridge. Every bridge call
   answers {ok, data|error}; call() unwraps that and turns failures into
   toasts, so view code never has to think about transport.

   Static chrome (inputs, tabs, buttons, containers) lives in index.html.
   This file only ever re-renders the dynamic list regions below it, so
   text inputs (add-source, library search, reader find) never lose focus. */
(function () {
  "use strict";

  var UNSORTED_ID = "unsorted";

  var MODELS = [
    { id: "tiny.en",  name: "tiny.en",  desc: "Rough draft quality. Good for skimming a two-hour stream.", speed: "~32× realtime" },
    { id: "base.en",  name: "base.en",  desc: "Readable. Misses names and jargon.", speed: "~16× realtime" },
    { id: "small.en", name: "small.en", desc: "The sweet spot for talk shows and lectures.", speed: "~6× realtime" },
    { id: "large-v3", name: "large-v3", desc: "Best accuracy on accents, crosstalk, technical terms.", speed: "~1.2× realtime" }
  ];
  var LANGS = [["auto", "Auto"], ["en", "English"], ["ko", "한국어"]];

  var STAGE_LABEL = {
    queued: "queued",
    captions: "captions",
    downloading: "downloading",
    "downloading model": "fetching model",
    transcribing: "transcribing",
    cancelling: "stopping…"
  };

  var state = {
    ready: false,
    railOpen: true,
    menuOpen: false,
    moveMenuFor: null,
    foldersCollapsed: {},

    shows: [],
    folders: [],
    episodes: [],
    jobs: {},           // id -> job dict from job_states()/events
    rateHistory: {},    // id -> {t0,p0}
    selected: {},        // episode id -> true
    addValue: "",
    adding: false,

    tab: "queue",
    reader: null,        // {path, meta, segments, legacy}
    readerQuery: "",

    transcripts: [],
    librarySearch: "",
    librarySearchResults: null, // null = not searching; array once fetched
    librarySearchTruncated: false,

    settings: { model: "small.en", lang: "auto", transcripts_dir: "" },
    trainingSettings: { deck_theme: "baek", themes: { baek: "light", dark: "dark", dancheong: "dancheong" },
                         has_api_key: false, api_key_last4: null },
    trainJobs: {},        // id -> trainjob dict from train_job_states()/events
    trainPollTimer: null,

    checkedAt: null,
    checking: false,
    checkErrorCount: 0,

    pollTimer: null,
    statusTimer: null
  };

  var $ = function (id) { return document.getElementById(id); };
  var esc = function (s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  };

  // ---------------------------------------------------------------- bridge

  function apiReady() {
    return new Promise(function (resolve, reject) {
      if (window.pywebview && window.pywebview.api) return resolve(window.pywebview.api);
      var settled = false;
      var t, timeout;
      var onReady = function () {
        if (settled) return;
        settled = true;
        clearInterval(t);
        clearTimeout(timeout);
        resolve(window.pywebview.api);
      };
      window.addEventListener("pywebviewready", onReady);
      t = setInterval(function () {
        if (window.pywebview && window.pywebview.api) onReady();
      }, 60);
      timeout = setTimeout(function () {
        if (settled) return;
        settled = true;
        clearInterval(t);
        window.removeEventListener("pywebviewready", onReady);
        reject(new Error("Desktop bridge not available."));
      }, 8000);
    });
  }

  function call(method) {
    var args = Array.prototype.slice.call(arguments, 1);
    return apiReady().then(function (api) {
      if (typeof api[method] !== "function") throw new Error("No such action: " + method);
      return api[method].apply(api, args);
    }).then(function (res) {
      if (!res) throw new Error("No response from the app.");
      if (res.ok === false) throw new Error(res.error || "Something went wrong.");
      return res.data;
    });
  }

  // ---------------------------------------------------------------- chrome

  function toast(msg, kind) {
    var el = document.createElement("div");
    el.className = "toast" + (kind ? " " + kind : "");
    el.textContent = msg;
    $("toasts").appendChild(el);
    setTimeout(function () {
      el.style.transition = "opacity .3s"; el.style.opacity = "0";
      setTimeout(function () { el.remove(); }, 320);
    }, 2600);
  }

  function fmtMinAgo(date) {
    if (!date) return null;
    var m = Math.round((Date.now() - date.getTime()) / 60000);
    if (m < 1) return "checked just now";
    return "checked " + m + " min ago";
  }

  // Feed/sidecar durations arrive as bare-seconds integers ("3720"), float
  // seconds ("3712.44"), or already-formatted clock strings. Normalize to
  // H:MM:SS / M:SS; anything else (non-numeric, unexpected shape) passes
  // through unchanged rather than mangling it.
  function fmtDuration(v) {
    if (v === null || v === undefined || v === "") return "";
    var s = String(v).trim();
    if (/^\d{1,2}:\d{2}(:\d{2})?$/.test(s)) return s;
    var n = Number(s);
    if (!isFinite(n)) return s;
    n = Math.max(0, Math.round(n));
    var h = Math.floor(n / 3600);
    var m = Math.floor((n % 3600) / 60);
    var sec = n % 60;
    var pad2 = function (x) { return (x < 10 ? "0" : "") + x; };
    if (h > 0) return h + ":" + pad2(m) + ":" + pad2(sec);
    return m + ":" + pad2(sec);
  }

  function truncate(s, n) {
    s = String(s == null ? "" : s);
    return s.length > n ? s.slice(0, n) + "…" : s;
  }

  function renderStatus() {
    var jobs = state.jobs;
    var working = 0, queued = 0;
    Object.keys(jobs).forEach(function (id) {
      var p = phaseOf(jobs[id]);
      if (p === "working") working++;
      else if (p === "queued") queued++;
    });
    var el = $("status-text");
    var text, kind = null;
    if (state.checking) { text = "Checking sources…"; kind = "busy"; }
    else if (working) { text = "Transcribing " + working + " · " + queued + " waiting"; kind = "busy"; }
    else if (queued) { text = queued + " waiting"; }
    else if (state.checkErrorCount) { text = "Last check had errors"; kind = "bad"; }
    else if (state.checkedAt) { text = "All caught up · " + fmtMinAgo(state.checkedAt); }
    else { text = state.shows.length ? "Ready" : "Add a source to begin"; }
    el.textContent = text;
    el.className = "status-text" + (kind ? " " + kind : "");
  }

  // ---------------------------------------------------------------- rail

  function detectSource(v) {
    if (!v) return { hint: "", ok: false, kind: null };
    if (/youtube\.com|youtu\.be/i.test(v)) return { hint: "YouTube channel detected", ok: true, kind: "youtube" };
    if (v.charAt(0) === "@") return { hint: "YouTube handle detected", ok: true, kind: "youtube" };
    if (/^https?:/i.test(v)) return { hint: "RSS feed detected", ok: true, kind: "rss" };
    return { hint: "Keep typing — paste a link or @handle", ok: false, kind: null };
  }

  function renderAddHint() {
    var v = state.addValue.trim();
    var d = detectSource(v);
    var hintEl = $("add-hint");
    if (!state.adding) {
      hintEl.textContent = v ? d.hint : "Press Enter to add";
      hintEl.className = "add-hint" + (d.ok ? " ok" : "");
    }
    $("add-field").classList.toggle("valid", d.ok);
  }

  function folderLabel(id) {
    if (id === UNSORTED_ID || !id) return "Unsorted";
    var f = state.folders.filter(function (x) { return x.id === id; })[0];
    return f ? f.name : "Unsorted";
  }

  function renderRail() {
    var list = $("rail-list");
    // Only the bare-minimum store (nothing subscribed, no folder made yet)
    // gets the pure first-run copy. The moment a folder exists — even an
    // empty one the user just created — it must be visible, so fall through
    // to the skeleton below instead of short-circuiting the whole rail.
    if (!state.shows.length && state.folders.length <= 1) {
      list.innerHTML = '<li class="rail-empty">Nothing subscribed yet. Paste a link above to start watching a show.</li>';
      return;
    }

    var buckets = {}; // folder id -> shows[]
    var order = [];
    state.folders.forEach(function (f) { buckets[f.id] = []; order.push(f.id); });
    if (!buckets[UNSORTED_ID]) { buckets[UNSORTED_ID] = []; order.push(UNSORTED_ID); }

    state.shows.forEach(function (s) {
      var fid = s.folder && buckets[s.folder] ? s.folder : UNSORTED_ID;
      buckets[fid].push(s);
    });

    var html = order.map(function (fid) {
      var items = buckets[fid];
      if (!items.length && fid === UNSORTED_ID && order.length > 1) return "";
      var name = fid === UNSORTED_ID ? "Unsorted" : folderLabel(fid);
      var collapsed = !!state.foldersCollapsed[fid];
      var itemsHtml = collapsed ? "" : items.map(function (s) {
        return sourceRowHtml(s);
      }).join("");
      return '<li class="folder" data-folder="' + esc(fid) + '">' +
        '<div class="folder-row">' +
          '<button class="folder-toggle" data-act="toggle-folder">' +
            '<span class="folder-caret' + (collapsed ? "" : " open") + '"></span>' +
            '<span class="folder-name">' + esc(name) + '</span>' +
            '<span class="folder-count">' + items.length + '</span>' +
          '</button>' +
          '<span class="folder-actions">' +
            '<button class="folder-mini rename" data-act="rename-folder" title="Rename folder">✎</button>' +
            (fid === UNSORTED_ID ? "" : '<button class="folder-mini remove" data-act="remove-folder" title="Remove folder">×</button>') +
          '</span>' +
        '</div>' +
        '<ul class="folder-items">' + itemsHtml + '</ul>' +
      '</li>';
    }).join("");

    if (!state.shows.length) {
      html += '<li class="rail-empty">Nothing subscribed yet. Paste a link above to start watching a show.</li>';
    }
    list.innerHTML = html;
  }

  function sourceRowHtml(s) {
    var kind = s.type === "youtube" ? "youtube" : "rss";
    var moveOpen = state.moveMenuFor === s.id;
    var moveMenu = moveOpen ? moveMenuHtml(s) : "";
    return '<li class="source" data-id="' + esc(s.id) + '">' +
      '<span class="source-dot ' + kind + '"></span>' +
      '<span class="source-name" title="' + esc(s.name) + '">' + esc(s.name) + '</span>' +
      '<span class="source-actions">' +
        '<button class="source-mini move" data-act="move" title="Move to folder">▾</button>' +
        '<button class="source-mini remove" data-act="remove" title="Remove show">×</button>' +
      '</span>' +
      '<button class="switch" data-act="auto" role="switch" aria-checked="' + (s.auto ? "true" : "false") + '" title="Check automatically">' +
        '<span class="switch-knob"></span>' +
      '</button>' +
      '<button class="switch switch-train" data-act="auto-train" role="switch" aria-checked="' + (s.auto_train ? "true" : "false") + '" title="Generate a training after every new transcript (uses your Claude API key)">' +
        '<span class="switch-knob"></span>' +
      '</button>' +
      moveMenu +
    '</li>';
  }

  function moveMenuHtml(s) {
    // state.folders already carries the store's permanent "unsorted" entry
    // (app.py guarantees it exists) — do not append a synthetic duplicate.
    var opts = state.folders.map(function (f) { return { id: f.id, name: f.name }; });
    return '<div class="move-menu">' + opts.map(function (f) {
      var cur = (s.folder || UNSORTED_ID) === f.id;
      return '<button class="move-menu-item' + (cur ? " current" : "") + '" data-act="move-to" data-folder="' + esc(f.id) + '">' + esc(f.name) + (cur ? " ✓" : "") + '</button>';
    }).join("") + '</div>';
  }

  function renderRailFoot() {
    var path = state.settings.transcripts_dir || "";
    var pathEl = $("transcripts-path");
    pathEl.textContent = path || "—";
    pathEl.title = path;
    $("settings-folder-path").textContent = path || "—";
    $("settings-folder-path").title = path;

    var working = 0;
    Object.keys(state.jobs).forEach(function (id) { if (phaseOf(state.jobs[id]) === "working") working++; });
    $("queue-note").textContent = state.shows.length + " source" + (state.shows.length === 1 ? "" : "s") + " · " + (working ? working + " running" : "idle");
  }

  // ------------------------------------------------------------- job model

  function phaseOf(job) {
    if (!job || job.status == null) return "new";
    switch (job.status) {
      case "queued": return "queued";
      case "captions": case "downloading": case "downloading model": case "transcribing": case "cancelling": return "working";
      case "done": return "done";
      case "failed": return "failed";
      case "cancelled": return "stopped";
      default: return "new";
    }
  }

  function etaFor(id, status, progress) {
    if (typeof progress !== "number") { delete state.rateHistory[id]; return null; }
    var now = Date.now();
    var h = state.rateHistory[id];
    // Progress resets to 0 on every stage change (downloading -> transcribing,
    // etc.); a baseline sampled in a previous stage produces a fabricated
    // rate, so re-arm it whenever the recorded stage doesn't match.
    if (!h || h.status !== status) { state.rateHistory[id] = { t0: now, p0: progress, status: status }; return null; }
    var dt = now - h.t0, dp = progress - h.p0;
    if (dt < 4000 || dp <= 0.005) return null;
    var rate = dp / dt;
    var remainingMs = (1 - progress) / rate;
    if (!isFinite(remainingMs) || remainingMs <= 0) return null;
    var min = Math.max(1, Math.round(remainingMs / 60000));
    return min + " min";
  }

  function ensurePolling() {
    var active = Object.keys(state.jobs).some(function (id) {
      var p = phaseOf(state.jobs[id]);
      return p === "queued" || p === "working";
    });
    if (active && !state.pollTimer) {
      state.pollTimer = setInterval(function () {
        call("job_states").then(function (res) {
          state.jobs = (res && res.jobs) || {};
          renderQueue(); renderStatus(); renderRailFoot(); ensurePolling();
        }).catch(function () { /* transient */ });
      }, 2000);
    } else if (!active && state.pollTimer) {
      clearInterval(state.pollTimer); state.pollTimer = null;
    }
  }

  // ------------------------------------------------------------- queue

  function queueRows() {
    var byId = {};
    state.episodes.forEach(function (e) { byId[e.id] = true; });
    var rows = state.episodes.map(function (e) { return { ep: e, job: state.jobs[e.id] }; });
    // orphan jobs (e.g. local file imports) that never came through check_shows
    Object.keys(state.jobs).forEach(function (id) {
      if (byId[id]) return;
      var j = state.jobs[id];
      if (j.show_id && state.removedShows && state.removedShows[j.show_id]) return;
      // The backend doesn't (yet) send url/kind/show_name on job snapshots —
      // read them defensively so this row upgrades for free once it does.
      rows.push({
        ep: {
          id: id, title: j.title || "Untitled", show_id: j.show_id || null,
          show_name: j.show_name || "Imported", date: "", duration: j.duration || null,
          url: j.url || null, kind: j.kind || null
        },
        job: j
      });
    });
    return rows;
  }

  function renderQueue() {
    var rows = queueRows();
    var working = 0, queued = 0;
    rows.forEach(function (r) {
      var p = phaseOf(r.job);
      if (p === "working") working++; else if (p === "queued") queued++;
    });

    $("queue-pill").textContent = String(working + queued);

    var headEl = $("queue-head");
    headEl.textContent = working ? "Working — " + working + " of " + (working + queued) + " · newest first" : "Newest first";

    // Same live-row set the click handler acts on, so the count on the
    // button can never drift from what a click would actually queue.
    var selCount = rows.filter(function (r) { return state.selected[r.ep.id]; }).length;
    var btn = $("transcribe-btn");
    btn.disabled = selCount === 0;
    btn.textContent = selCount ? "Transcribe " + selCount : "Transcribe selected";
    $("dismiss-all").disabled = rows.filter(isDismissable).length === 0;

    var list = $("episode-list");
    // Rows are computed above BEFORE any empty-state decision — orphan job
    // rows (e.g. file imports, which never live in state.shows) must still
    // render even when nothing has been subscribed to yet.
    if (!rows.length) {
      if (!state.shows.length) {
        list.innerHTML =
          '<div class="empty"><div class="dots"><i></i><i></i><i></i></div>' +
          "<h2>Add your first source</h2>" +
          "<p>Paste a podcast RSS feed, a YouTube channel, or an @handle into the box on the left. " +
          "Sori watches for new episodes and turns them into plain text transcripts on your machine.</p>" +
          "<ul><li>https://example.com/podcast/rss</li><li>youtube.com/@channelname</li><li>@channelname</li></ul></div>";
      } else {
        list.innerHTML = '<div class="queue-quiet">You are all caught up.</div>';
      }
      return;
    }

    list.innerHTML = rows.map(episodeRowHtml).join("");
  }

  function episodeRowHtml(row) {
    var e = row.ep, job = row.job;
    var phase = phaseOf(job);
    var checked = !!state.selected[e.id];
    var meta = esc(e.show_name || "") +
      (e.duration ? '<span> · </span>' + esc(fmtDuration(e.duration)) : "") +
      (e.date ? '<span> · </span>' + esc(e.date) : "");

    var chipCls = phase, chipText, btnCls, btnLabel, act, btnDisabled = false;
    var err = (job && job.error) || e.last_error || null;
    var cancelling = !!(job && (job.cancelling || job.status === "cancelling"));

    // Orphan rows (imports) synthesize an episode with no url/kind — sending
    // those through transcribe/retry is guaranteed to fail server-side, so
    // suppress the action rather than offer a button that can't work. The
    // one exception: a failed/cancelled job whose own snapshot still carries
    // a url can still be retried even if the episode lookup came up empty.
    var hasUrl = (!!e.url || !!(job && (job.status === "failed" || job.status === "cancelled") && job.url))
      && e.show_id !== "imported";

    if (cancelling) {
      chipCls = "working";
      chipText = "stopping…";
      btnCls = "quiet"; btnLabel = "Stopping…"; act = null; btnDisabled = true;
    } else if (phase === "working") {
      var progress = job && typeof job.progress === "number" ? job.progress : null;
      if (progress != null) {
        var pct = Math.round(progress * 100);
        var eta = etaFor(e.id, job.status, progress);
        chipText = pct + "%" + (eta ? " · " + eta : "");
      } else {
        chipText = STAGE_LABEL[job.status] || job.status || "working";
      }
      btnCls = "quiet"; btnLabel = "Stop"; act = "stop";
    } else if (phase === "queued") {
      chipText = "Queued"; btnCls = "primary"; btnLabel = "Transcribe"; act = "transcribe";
      if (!hasUrl) { act = null; }
    } else if (phase === "done") {
      chipText = "Transcribed"; btnCls = "open"; btnLabel = "Open"; act = "open";
    } else if (phase === "failed") {
      chipText = err ? truncate(err, 26) : "Failed"; btnCls = "danger"; btnLabel = "Retry"; act = "retry";
      if (!hasUrl) { act = null; }
    } else if (phase === "stopped") {
      chipText = "Stopped"; btnCls = "primary"; btnLabel = "Transcribe"; act = "transcribe";
      if (!hasUrl) { act = null; }
    } else {
      chipText = "New"; btnCls = "primary"; btnLabel = "Transcribe"; act = "transcribe";
      if (!hasUrl) { act = null; }
    }

    var progressBar = phase === "working" && !cancelling && job && typeof job.progress === "number"
      ? '<span class="ep-progress" style="width:' + Math.round(job.progress * 100) + '%"></span>' : "";
    var flag = phase === "failed" ? '<span class="ep-flag"></span>' : "";
    var warn = phase === "failed" ? '<span class="ep-warn"></span>' : "";
    var titleAttr = err ? ' title="' + esc(err) + '"' : "";

    var btnHtml = act
      ? '<button class="ep-action ' + btnCls + '" data-act="' + act + '">' + esc(btnLabel) + '</button>'
      : (btnDisabled
        ? '<button class="ep-action ' + btnCls + '" disabled>' + esc(btnLabel) + '</button>'
        : "");
    // Dismiss = "skip this one for good". Not offered mid-run (that's Stop)
    // and not for file imports, which have no feed to be re-offered from.
    var dismissHtml = isDismissable(row)
      ? '<button class="ep-dismiss" data-act="dismiss" title="Dismiss — skip this episode, don\'t offer it again">&times;</button>'
      : "";

    return '<li class="ep" data-id="' + esc(e.id) + '"' + titleAttr + '>' +
      '<button class="ep-check" role="checkbox" aria-checked="' + (checked ? "true" : "false") + '" data-act="toggle-select"><span class="ep-check-fill"></span></button>' +
      '<div class="ep-body" data-act="toggle-select">' +
        '<div class="ep-title">' + esc(e.title) + '</div>' +
        '<div class="ep-meta">' + meta + '</div>' +
      '</div>' +
      '<div class="ep-chip-cell">' + warn + '<span class="chip ' + chipCls + '">' + esc(chipText) + '</span></div>' +
      '<div class="ep-btn-cell">' + btnHtml + dismissHtml + '</div>' +
      progressBar + flag +
    '</li>';
  }

  function findRow(id) {
    return queueRows().filter(function (r) { return r.ep.id === id; })[0] || null;
  }

  function queueEpisode(ep, isRetry) {
    state.jobs[ep.id] = {
      id: ep.id, status: "queued", progress: null, title: ep.title,
      show_id: ep.show_id, show_name: ep.show_name, url: ep.url, kind: ep.kind
    };
    delete state.selected[ep.id];
    delete state.rateHistory[ep.id];
    renderQueue(); renderStatus(); ensurePolling();
    call(isRetry ? "retry_episode" : "transcribe_episode", ep.show_id, ep).catch(function (e) {
      state.jobs[ep.id] = { id: ep.id, status: "failed", error: e.message };
      renderQueue(); renderStatus();
      toast(e.message, "bad");
    });
  }

  function isDismissable(row) {
    var p = phaseOf(row.job);
    return (p === "new" || p === "queued" || p === "failed" || p === "stopped") &&
      !!row.ep.show_id && row.ep.show_id !== "imported";
  }

  // Drop every trace of an episode from the client. The backend marks it
  // seen, so the next check won't bring it back either.
  function forgetEpisode(id) {
    delete state.jobs[id];
    delete state.selected[id];
    delete state.rateHistory[id];
    state.episodes = state.episodes.filter(function (e) { return e.id !== id; });
  }

  function dismissEpisode(row) {
    var id = row.ep.id, showId = row.ep.show_id, title = row.ep.title || "episode";
    forgetEpisode(id);
    renderQueue(); renderStatus(); renderRailFoot(); ensurePolling();
    call("dismiss_episode", showId, id).then(function () {
      toast("Dismissed: " + title);
    }).catch(function (e) {
      toast(e.message, "bad");
      return checkShows();
    });
  }

  function stopEpisode(id) {
    // stop_episode's return value is a transient {id, status} status word
    // ("cancelling"/"not queued"/"finished") from the worker call, not a job
    // snapshot — writing it into state.jobs wipes the real job's
    // progress/title/path and stalls polling. The worker emits the actual
    // "cancelled" job over the studioEvent channel; just re-render here.
    call("stop_episode", id).then(function () {
      renderQueue(); renderStatus(); ensurePolling();
    }).catch(function (e) { toast(e.message, "bad"); });
  }

  $("episode-list").addEventListener("click", function (ev) {
    var row = ev.target.closest(".ep");
    if (!row) return;
    var id = row.dataset.id;
    var found = findRow(id);
    if (!found) return;
    var actBtn = ev.target.closest("[data-act]");
    var act = actBtn ? actBtn.dataset.act : null;

    if (act === "transcribe") { queueEpisode(found.ep, false); return; }
    if (act === "retry") { queueEpisode(found.ep, true); return; }
    if (act === "stop") { stopEpisode(id); return; }
    if (act === "dismiss") { dismissEpisode(found); return; }
    if (act === "open") {
      var path = found.job && found.job.path;
      if (!path) { toast("No transcript path for this job yet.", "bad"); return; }
      openReader(path);
      return;
    }
    if (act === "toggle-select") {
      var phase = phaseOf(found.job);
      if (phase !== "new" && phase !== "queued" && phase !== "stopped") return;
      state.selected[id] = !state.selected[id];
      renderQueue();
    }
  });

  $("select-all").addEventListener("click", function () {
    queueRows().forEach(function (r) {
      var p = phaseOf(r.job);
      if (p === "new" || p === "queued" || p === "stopped") state.selected[r.ep.id] = true;
    });
    renderQueue();
  });

  $("dismiss-all").addEventListener("click", function () {
    var picked = queueRows().filter(isDismissable);
    if (!picked.length) { toast("Nothing new to dismiss."); return; }
    picked.forEach(function (r) { forgetEpisode(r.ep.id); });
    renderQueue(); renderStatus(); renderRailFoot(); ensurePolling();
    var items = picked.map(function (r) { return { show_id: r.ep.show_id, id: r.ep.id }; });
    call("dismiss_episodes", items).then(function (res) {
      var n = (res && res.dismissed) || 0;
      toast("Dismissed " + n + " episode" + (n === 1 ? "" : "s") + ". They won't be offered again.");
    }).catch(function (e) {
      toast(e.message, "bad");
      return checkShows();
    });
  });

  $("transcribe-btn").addEventListener("click", function () {
    var picked = queueRows().filter(function (r) { return state.selected[r.ep.id]; });
    if (!picked.length) return;
    picked.forEach(function (r) { queueEpisode(r.ep, false); });
    toast("Queued " + picked.length + " episode" + (picked.length === 1 ? "" : "s"));
  });

  // -------------------------------------------------------------- add / rail

  function addShow() {
    var input = $("add-input");
    var v = input.value.trim();
    var d = detectSource(v);
    if (!d.ok) { toast("Paste a YouTube channel, an @handle, or an RSS feed URL.", "bad"); return; }
    state.adding = true;
    $("add-hint").textContent = "Reading the feed…";
    $("add-btn").disabled = true;
    call("add_show", v).then(function (show) {
      state.shows.push(show);
      state.addValue = "";
      input.value = "";
      renderRail(); renderRailFoot();
      toast("Now watching " + show.name + ". Checking for episodes…", "good");
      if (show.warning) toast(show.warning, "bad");
      return checkShows();
    }).catch(function (e) {
      toast(e.message, "bad");
    }).then(function () {
      state.adding = false;
      $("add-btn").disabled = false;
      renderAddHint();
    });
  }

  $("add-btn").addEventListener("click", addShow);
  $("add-input").addEventListener("input", function (ev) {
    state.addValue = ev.target.value;
    renderAddHint();
  });
  $("add-input").addEventListener("keydown", function (ev) {
    if (ev.key === "Enter") { ev.preventDefault(); addShow(); }
    else if (ev.key === "Escape") { closeMenus(); }
  });

  function openAddMenu() {
    state.menuOpen = true;
    $("add-menu").classList.remove("hidden");
    $("add-menu-overlay").classList.remove("hidden");
    $("add-menu-btn").classList.add("is-open");
  }
  function closeMenus() {
    state.menuOpen = false;
    state.moveMenuFor = null;
    $("add-menu").classList.add("hidden");
    $("add-menu-overlay").classList.add("hidden");
    $("add-menu-btn").classList.remove("is-open");
    renderRail();
  }

  $("add-menu-btn").addEventListener("click", function () {
    if (state.menuOpen) closeMenus(); else openAddMenu();
  });
  $("add-menu-overlay").addEventListener("click", closeMenus);
  $("add-menu").addEventListener("click", function (ev) {
    var btn = ev.target.closest("[data-act]");
    if (!btn) return;
    var act = btn.dataset.act;
    closeMenus();
    if (act === "focus-add") {
      $("add-input").focus();
    } else if (act === "new-folder") {
      var name = window.prompt("Name this folder:", "");
      if (name && name.trim()) {
        call("add_folder", name.trim()).then(function (folder) {
          if (folder && folder.id) { state.folders.push(folder); renderRail(); }
          else { return call("list_folders").then(function (fs) { state.folders = fs || []; renderRail(); }); }
        }).catch(function (e) { toast(e.message, "bad"); });
      }
    } else if (act === "add-files") {
      call("choose_files").then(function (res) {
        var n = res && res.queued ? res.queued.length : 0;
        if (n) { toast("Queued " + n + " file" + (n === 1 ? "" : "s") + " for transcription.", "good"); }
        ensurePolling();
        return call("job_states");
      }).then(function (res) {
        if (res) { state.jobs = res.jobs || {}; renderQueue(); renderStatus(); ensurePolling(); }
      }).catch(function (e) { toast(e.message, "bad"); });
    }
  });

  $("rail-list").addEventListener("click", function (ev) {
    var act = ev.target.closest("[data-act]");
    if (!act) return;

    if (act.dataset.act === "toggle-folder") {
      var li = act.closest(".folder");
      var fid = li.dataset.folder;
      state.foldersCollapsed[fid] = !state.foldersCollapsed[fid];
      renderRail();
      return;
    }

    if (act.dataset.act === "rename-folder") {
      var renameLi = act.closest(".folder");
      var renameId = renameLi.dataset.folder;
      var current = folderLabel(renameId);
      var name = window.prompt("Rename folder", current);
      if (name && name.trim() && name.trim() !== current) {
        call("rename_folder", renameId, name.trim()).then(function () {
          return call("list_folders");
        }).then(function (fs) {
          state.folders = fs || [];
          return call("list_shows");
        }).then(function (shows) {
          state.shows = shows || state.shows;
          renderRail();
        }).catch(function (e) { toast(e.message, "bad"); });
      }
      return;
    }

    if (act.dataset.act === "remove-folder") {
      var removeLi = act.closest(".folder");
      var removeId = removeLi.dataset.folder;
      if (removeId === UNSORTED_ID) return;
      var removeName = folderLabel(removeId);
      if (!window.confirm('Remove folder "' + removeName + '"? Its sources move to Unsorted.')) return;
      call("remove_folder", removeId).then(function () {
        return call("list_folders");
      }).then(function (fs) {
        state.folders = fs || [];
        return call("list_shows");
      }).then(function (shows) {
        state.shows = shows || state.shows;
        renderRail();
      }).catch(function (e) { toast(e.message, "bad"); });
      return;
    }

    var srcLi = act.closest(".source");
    if (!srcLi) return;
    var id = srcLi.dataset.id;
    var show = state.shows.filter(function (s) { return s.id === id; })[0];
    if (!show) return;

    if (act.dataset.act === "auto") {
      var next = act.getAttribute("aria-checked") !== "true";
      act.setAttribute("aria-checked", next ? "true" : "false");
      call("set_auto", id, next).then(function () {
        show.auto = next;
        toast(next ? "Auto-check on for " + show.name : "Auto-check off for " + show.name);
      }).catch(function (e) {
        act.setAttribute("aria-checked", next ? "false" : "true");
        toast(e.message, "bad");
      });
    } else if (act.dataset.act === "auto-train") {
      var nextTrain = act.getAttribute("aria-checked") !== "true";
      if (nextTrain && !state.trainingSettings.has_api_key) {
        toast("Add a Claude API key in Settings first.", "bad");
        return;
      }
      act.setAttribute("aria-checked", nextTrain ? "true" : "false");
      call("set_auto_train", id, nextTrain).then(function () {
        show.auto_train = nextTrain;
        toast(nextTrain ? "Auto-train on for " + show.name : "Auto-train off for " + show.name);
      }).catch(function (e) {
        act.setAttribute("aria-checked", nextTrain ? "false" : "true");
        toast(e.message, "bad");
      });
    } else if (act.dataset.act === "remove") {
      if (!window.confirm('Remove "' + show.name + '"? This can\'t be undone.')) return;
      call("remove_show", id).then(function () {
        state.shows = state.shows.filter(function (s) { return s.id !== id; });
        state.episodes = state.episodes.filter(function (e) { return e.show_id !== id; });
        (state.removedShows || (state.removedShows = {}))[id] = true;
        // Otherwise these jobs outlive the show as orphan rows in the queue,
        // relabeled "Imported" by queueRows()'s fallback.
        Object.keys(state.jobs).forEach(function (jid) {
          if (state.jobs[jid] && state.jobs[jid].show_id === id) delete state.jobs[jid];
        });
        renderRail(); renderRailFoot(); renderQueue();
        toast("Removed " + show.name);
      }).catch(function (e) { toast(e.message, "bad"); });
    } else if (act.dataset.act === "move") {
      state.moveMenuFor = state.moveMenuFor === id ? null : id;
      renderRail();
    } else if (act.dataset.act === "move-to") {
      var folderId = act.dataset.folder;
      state.moveMenuFor = null;
      call("set_show_folder", id, folderId).then(function () {
        show.folder = folderId;
        renderRail();
        toast("Moved " + show.name + " to " + folderLabel(folderId));
      }).catch(function (e) { toast(e.message, "bad"); renderRail(); });
    }
  });

  $("open-folder-btn").addEventListener("click", function () {
    call("open_folder").catch(function (e) { toast(e.message, "bad"); });
  });

  function changeFolder() {
    return call("choose_folder").then(function (res) {
      if (res && res.changed) {
        state.settings.transcripts_dir = res.transcripts_dir || state.settings.transcripts_dir;
        renderRailFoot(); renderSettings();
        toast("Transcripts now save to " + state.settings.transcripts_dir, "good");
        if (res.orphaned > 0) {
          toast(res.orphaned + " existing transcripts stay in the previous folder.");
        }
      }
    }).catch(function (e) { toast(e.message, "bad"); });
  }
  $("change-folder-btn").addEventListener("click", changeFolder);
  $("settings-change-folder").addEventListener("click", changeFolder);

  $("hamburger").addEventListener("click", function () {
    state.railOpen = !state.railOpen;
    $("hamburger").classList.toggle("is-open", state.railOpen);
    $("body-grid").classList.toggle("rail-closed", !state.railOpen);
  });

  // ------------------------------------------------------------------ tabs

  function switchTab(tab) {
    state.tab = tab;
    state.reader = null;
    Array.prototype.forEach.call(document.querySelectorAll(".tab"), function (t) {
      t.classList.toggle("active", t.dataset.tab === tab);
    });
    $("pane-queue").classList.toggle("hidden", tab !== "queue");
    $("pane-library").classList.toggle("hidden", tab !== "library");
    $("pane-settings").classList.toggle("hidden", tab !== "settings");
    $("pane-reader").classList.add("hidden");
    if (tab === "library") refreshLibrary();
  }

  Array.prototype.forEach.call(document.querySelectorAll(".tab"), function (tab) {
    tab.addEventListener("click", function () { switchTab(tab.dataset.tab); });
  });

  // -------------------------------------------------------------- library

  function totalKb() {
    return state.transcripts.reduce(function (n, t) { return n + (t.kb || 0); }, 0);
  }

  function groupByShow(items) {
    var groups = {}, order = [];
    items.forEach(function (t) {
      if (!groups[t.show]) { groups[t.show] = []; order.push(t.show); }
      groups[t.show].push(t);
    });
    return order.map(function (show) { return { name: show, files: groups[show] }; });
  }

  function renderLibrary() {
    var q = state.librarySearch.trim();
    var searching = q.length >= 2;
    var body = $("library-body");
    var countEl = $("lib-count");

    if (!searching) {
      var groups = groupByShow(state.transcripts);
      var gb = (totalKb() / 1048576).toFixed(2);
      countEl.textContent = state.transcripts.length ? state.transcripts.length + " transcripts · " + gb + " GB" : "";

      if (!state.transcripts.length) {
        body.innerHTML = '<div class="empty"><div class="dots"><i></i><i></i><i></i></div>' +
          "<h2>No transcripts yet</h2><p>Transcripts you make show up here, grouped by show, and are saved as plain " +
          ".txt files you can open with anything.</p></div>";
        return;
      }
      body.innerHTML = groups.map(function (g) { return groupHtml(g, false); }).join("");
      return;
    }

    var results = state.librarySearchResults;
    if (results == null) {
      countEl.textContent = "Searching…";
      body.innerHTML = "";
      return;
    }
    countEl.textContent = results.length + " matching";
    if (!results.length) {
      body.innerHTML = '<div class="lib-quiet">Nothing matches “' + esc(state.librarySearch) + '”.</div>' +
        (state.librarySearchTruncated ? '<div class="lib-quiet">Search capped — showing first matches.</div>' : "");
      return;
    }
    var searchGroups = groupByShow(results);
    body.innerHTML = searchGroups.map(function (g) { return groupHtml(g, true); }).join("") +
      (state.librarySearchTruncated ? '<div class="lib-quiet">Search capped — showing first matches.</div>' : "");
  }

  function groupHtml(g, withSnippet) {
    var rows = g.files.map(function (t) {
      var label = String(t.title).replace(/^\d{4}-\d{2}-\d{2}\s+-\s+/, "");
      var snippet = withSnippet && t.snippet ? '<div class="file-snippet">' + esc(t.snippet) + '</div>' : "";
      return '<li class="file" data-path="' + esc(t.path) + '">' +
        '<div class="file-body"><div class="file-name">' + esc(label) + '</div>' + snippet + '</div>' +
        '<span class="file-meta">' + esc(t.modified) + ' · ' + t.kb + ' KB</span></li>';
    }).join("");
    return '<div class="group"><div class="group-head">' +
      '<span class="group-title">' + esc(g.name) + '</span>' +
      '<span class="group-count">' + g.files.length + (g.files.length === 1 ? " transcript" : " transcripts") + '</span></div>' +
      '<ul class="files">' + rows + '</ul></div>';
  }

  $("library-body").addEventListener("click", function (ev) {
    var row = ev.target.closest(".file");
    if (!row) return;
    openReader(row.dataset.path);
  });

  var libSearchTimer = null;
  $("lib-search").addEventListener("input", function (ev) {
    state.librarySearch = ev.target.value;
    clearTimeout(libSearchTimer);
    var q = state.librarySearch.trim();
    if (q.length < 2) { state.librarySearchResults = null; renderLibrary(); return; }
    libSearchTimer = setTimeout(function () {
      state.librarySearchResults = null;
      renderLibrary();
      call("search_transcripts", q).then(function (res) {
        // Accept both the legacy bare-array shape and the current
        // {results, truncated} envelope.
        if (Array.isArray(res)) {
          state.librarySearchResults = res;
          state.librarySearchTruncated = false;
        } else {
          state.librarySearchResults = (res && res.results) || [];
          state.librarySearchTruncated = !!(res && res.truncated);
        }
        renderLibrary();
      }).catch(function (e) {
        toast(e.message, "bad");
        state.librarySearchResults = [];
        state.librarySearchTruncated = false;
        renderLibrary();
      });
    }, 220);
  });

  function refreshLibrary() {
    return call("list_transcripts").then(function (items) {
      state.transcripts = items || [];
      renderLibrary();
    }).catch(function (e) { toast(e.message, "bad"); });
  }

  // -------------------------------------------------------------- settings

  function renderSettings() {
    var modelList = $("model-list");
    modelList.innerHTML = MODELS.map(function (m) {
      var sel = state.settings.model === m.id;
      return '<button class="model-row' + (sel ? " selected" : "") + '" data-act="pick-model" data-model="' + esc(m.id) + '">' +
        '<span class="model-dot"></span>' +
        '<span class="model-text"><span class="model-name">' + esc(m.name) + '</span>' +
        '<span class="model-desc">' + esc(m.desc) + '</span></span>' +
        '<span class="model-speed">' + esc(m.speed) + '</span></button>';
    }).join("");

    var seg = $("lang-seg");
    seg.innerHTML = LANGS.map(function (pair) {
      var id = pair[0], label = pair[1];
      var active = state.settings.lang === id;
      return '<button class="seg-btn' + (active ? " active" : "") + '" data-act="pick-lang" data-lang="' + esc(id) + '">' + esc(label) + '</button>';
    }).join("");

    var ts = state.trainingSettings;
    var themeSeg = $("theme-seg");
    var themeNames = Object.keys(ts.themes || { baek: 1, dark: 1, dancheong: 1 });
    themeSeg.innerHTML = themeNames.map(function (id) {
      var active = ts.deck_theme === id;
      return '<button class="seg-btn' + (active ? " active" : "") + '" data-act="pick-theme" data-theme="' + esc(id) + '">' + esc(id) + '</button>';
    }).join("");

    $("training-key-desc").textContent = ts.has_api_key
      ? "Key ending in ····" + (ts.api_key_last4 || "") + " — training generation is on."
      : "Not set — training generation needs your own Anthropic API key. Unlike transcription, this step is not free: it calls the Claude API per training.";
    $("training-key-input").value = "";
    $("training-key-input").placeholder = ts.has_api_key ? "Replace key…" : "sk-ant-…";

    renderRailFoot();
  }

  $("model-list").addEventListener("click", function (ev) {
    var btn = ev.target.closest("[data-act='pick-model']");
    if (!btn) return;
    var id = btn.dataset.model;
    var prev = state.settings.model;
    state.settings.model = id;
    renderSettings();
    call("set_settings", { model: id }).catch(function (e) {
      state.settings.model = prev; renderSettings(); toast(e.message, "bad");
    });
  });
  $("lang-seg").addEventListener("click", function (ev) {
    var btn = ev.target.closest("[data-act='pick-lang']");
    if (!btn) return;
    var id = btn.dataset.lang;
    var prev = state.settings.lang;
    state.settings.lang = id;
    renderSettings();
    call("set_settings", { lang: id }).catch(function (e) {
      state.settings.lang = prev; renderSettings(); toast(e.message, "bad");
    });
  });

  // -------------------------------------------------------- training settings

  $("theme-seg").addEventListener("click", function (ev) {
    var btn = ev.target.closest("[data-act='pick-theme']");
    if (!btn) return;
    var id = btn.dataset.theme;
    var prev = state.trainingSettings.deck_theme;
    state.trainingSettings.deck_theme = id;
    renderSettings();
    call("set_training_settings", { deck_theme: id }).catch(function (e) {
      state.trainingSettings.deck_theme = prev; renderSettings(); toast(e.message, "bad");
    });
  });

  $("training-key-save").addEventListener("click", function () {
    var key = $("training-key-input").value.trim();
    if (!key) { toast("Paste your Claude API key first.", "bad"); return; }
    call("set_training_settings", { api_key: key }).then(function (res) {
      state.trainingSettings = res;
      renderSettings();
      toast("API key saved.", "good");
    }).catch(function (e) { toast(e.message, "bad"); });
  });

  $("training-key-clear").addEventListener("click", function () {
    if (!state.trainingSettings.has_api_key) return;
    if (!window.confirm("Remove your Claude API key? Training generation stops working until you add one again.")) return;
    call("set_training_settings", { api_key: "" }).then(function (res) {
      state.trainingSettings = res;
      renderSettings();
      toast("API key removed.");
    }).catch(function (e) { toast(e.message, "bad"); });
  });

  $("open-trainings-folder").addEventListener("click", function () {
    call("open_trainings_folder").catch(function (e) { toast(e.message, "bad"); });
  });

  // ---------------------------------------------------------------- reader

  function escapeRe(s) { return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"); }
  function fmtTime(sec) {
    if (typeof sec !== "number" || isNaN(sec)) return null;
    var m = Math.floor(sec / 60), s = Math.floor(sec % 60);
    return (m < 10 ? "0" : "") + m + ":" + (s < 10 ? "0" : "") + s;
  }

  function openReader(path) {
    call("read_transcript", path).then(function (res) {
      state.reader = { path: path, meta: (res && res.meta) || {}, segments: (res && res.segments) || [], legacy: !!(res && res.legacy) };
      state.readerQuery = "";
      $("reader-find").value = "";
      $("reader-train-status").innerHTML = "";
      showReaderPane();
    }).catch(function (e) { toast(e.message, "bad"); });
  }

  function showReaderPane() {
    Array.prototype.forEach.call(document.querySelectorAll(".tab"), function (t) { t.classList.remove("active"); });
    $("pane-queue").classList.add("hidden");
    $("pane-library").classList.add("hidden");
    $("pane-settings").classList.add("hidden");
    $("pane-reader").classList.remove("hidden");
    renderReader();
  }

  function closeReader() {
    state.reader = null;
    switchTab("library");
  }
  $("reader-back").addEventListener("click", closeReader);

  function renderReader() {
    var r = state.reader;
    if (!r) return;
    var meta = r.meta || {};
    $("reader-title").textContent = meta.title || "";

    var parts = [];
    if (meta.show) parts.push(meta.show);
    if (meta.duration) parts.push(fmtDuration(meta.duration)); else if (meta.date) parts.push(meta.date);
    if (meta.model) parts.push(meta.model);
    $("reader-meta").textContent = parts.join("  ·  ");

    var q = state.readerQuery.trim();
    var matches = 0;
    var segHtml;
    if (!r.segments.length) {
      segHtml = '<div class="reader-quiet">This transcript has no readable segments.</div>';
    } else {
      segHtml = r.segments.map(function (seg) {
        var time = fmtTime(seg.start);
        var text = seg.text || "";
        var body;
        if (q.length > 1) {
          var re = new RegExp("(" + escapeRe(q) + ")", "ig");
          var chunks = text.split(re);
          body = chunks.map(function (chunk) {
            if (!chunk) return "";
            if (chunk.toLowerCase() === q.toLowerCase()) { matches++; return "<mark>" + esc(chunk) + "</mark>"; }
            return esc(chunk);
          }).join("");
        } else {
          body = esc(text);
        }
        return '<div class="segment">' +
          '<div class="segment-time">' + (time ? esc(time) : "") + '</div>' +
          '<p class="segment-text">' + body + '</p>' +
        '</div>';
      }).join("");
    }

    $("reader-body").innerHTML = segHtml +
      (meta.duration ? '<div class="reader-end">End of transcript · ' + esc(fmtDuration(meta.duration)) + '</div>' : "");

    var matchEl = $("reader-match");
    if (q.length > 1) {
      matchEl.textContent = matches ? matches + " match" + (matches === 1 ? "" : "es") : "no matches";
      matchEl.className = "reader-match" + (matches ? " has-matches" : "");
    } else {
      matchEl.textContent = "";
      matchEl.className = "reader-match";
    }
  }

  var readerFindTimer = null;
  $("reader-find").addEventListener("input", function (ev) {
    state.readerQuery = ev.target.value;
    clearTimeout(readerFindTimer);
    readerFindTimer = setTimeout(renderReader, 80);
  });

  $("reader-copy").addEventListener("click", function () {
    if (!state.reader) return;
    var text = state.reader.segments.map(function (s) { return s.text || ""; }).join("\n\n");
    var done = false;
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(function () { toast("Copied", "good"); }).catch(fallbackCopy);
      done = true;
    }
    if (!done) fallbackCopy();
    function fallbackCopy() {
      var ta = $("clip-shim");
      ta.value = text;
      ta.style.display = "block";
      ta.focus(); ta.select();
      try { document.execCommand("copy"); toast("Copied", "good"); }
      catch (e) { toast("Could not copy.", "bad"); }
      ta.style.display = "none";
    }
  });

  function exportReader(fmt) {
    if (!state.reader) return;
    call("export_transcript", state.reader.path, fmt).then(function (res) {
      var path = res && res.path ? res.path : "";
      var name = path.split(/[\\/]/).pop();
      toast("Saved " + (name || fmt), "good");
    }).catch(function (e) { toast(e.message, "bad"); });
  }
  $("reader-md").addEventListener("click", function () { exportReader("md"); });
  $("reader-srt").addEventListener("click", function () { exportReader("srt"); });
  $("reader-txt").addEventListener("click", function () {
    if (!state.reader) return;
    call("open_transcript", state.reader.path).catch(function (e) { toast(e.message, "bad"); });
  });

  // ------------------------------------------------------------- training job

  var TRAIN_STAGE_LABEL = { queued: "queued…", writing: "writing content…", rendering: "rendering deck…" };

  function trainStatusHtml(job) {
    if (!job) return "";
    if (job.status === "failed") return '<span class="reader-train-bad">' + esc(job.error || "Training failed") + "</span>";
    if (job.status === "cancelled") return "Training cancelled";
    if (job.status === "done") {
      return 'Training ready — ' +
        '<button class="reader-train-link" data-act="open-deck">Open Deck</button> · ' +
        '<button class="reader-train-link" data-act="open-guide">Open Guide</button>';
    }
    return TRAIN_STAGE_LABEL[job.status] || (job.status || "working…");
  }

  function pollTrainJob(id) {
    if (state.trainPollTimer) clearInterval(state.trainPollTimer);
    state.trainPollTimer = setInterval(function () {
      call("train_job_states").then(function (res) {
        state.trainJobs = (res && res.jobs) || {};
        var job = state.trainJobs[id];
        // The reader may have moved on to a different transcript since this
        // poll started (or closed entirely) — never let a stale poll from
        // job A overwrite the status line for whatever's showing now.
        if (!job) return;
        if (state.reader && trainIdForPath(state.reader.path) === id) {
          $("reader-train-status").innerHTML = trainStatusHtml(job);
        }
        // Toasting on failure happens in the "trainjob" studioEvent handler
        // only (same convention as the transcribe queue) — polling here is
        // just the fallback render path, not a second toast source.
        if (job.status === "done" || job.status === "failed" || job.status === "cancelled") {
          clearInterval(state.trainPollTimer);
          state.trainPollTimer = null;
        }
      }).catch(function () { /* transient */ });
    }, 2000);
  }

  $("reader-train").addEventListener("click", function () {
    if (!state.reader) return;
    if (!state.trainingSettings.has_api_key) {
      toast("Add a Claude API key in Settings first.", "bad");
      return;
    }
    $("reader-train-status").textContent = "queued…";
    call("generate_training", state.reader.path).then(function (res) {
      pollTrainJob(res.id);
    }).catch(function (e) {
      $("reader-train-status").innerHTML = '<span class="reader-train-bad">' + esc(e.message) + "</span>";
      toast(e.message, "bad");
    });
  });

  $("reader-train-status").addEventListener("click", function (ev) {
    var act = ev.target.closest("[data-act]");
    if (!act || !state.reader) return;
    var job = state.trainJobs[trainIdForPath(state.reader.path)];
    if (!job) return;
    var path = act.dataset.act === "open-deck" ? job.pptx_path : job.md_path;
    if (!path) return;
    call("open_training", path).catch(function (e) { toast(e.message, "bad"); });
  });

  function trainIdForPath(path) {
    var name = (path || "").split(/[\\/]/).pop() || "";
    return name.replace(/\.[^.]+$/, "");
  }

  // ---------------------------------------------------------------- checks

  function applyCheck(res) {
    state.episodes = (res && res.episodes) || [];
    state.checkErrorCount = (res && res.errors && res.errors.length) || 0;
    var d = res && res.checked_at ? new Date(res.checked_at) : null;
    state.checkedAt = d && !isNaN(d) ? d : new Date();
    ((res && res.errors) || []).forEach(function (err) { toast(err.show + ": " + err.error, "bad"); });
    pruneSelected();
    renderQueue(); renderStatus(); renderRailFoot();
  }

  // applyCheck replaces state.episodes wholesale, so any selected id that
  // isn't in the new episode set (or an orphan job row) is stale and would
  // otherwise inflate the "Transcribe selected" count for a row that no
  // longer exists.
  function pruneSelected() {
    var liveIds = {};
    queueRows().forEach(function (r) { liveIds[r.ep.id] = true; });
    Object.keys(state.selected).forEach(function (id) {
      if (!liveIds[id]) delete state.selected[id];
    });
  }

  function checkShows() {
    state.checking = true;
    renderStatus();
    $("check-now").disabled = true;
    return call("check_shows").then(applyCheck).catch(function (e) {
      toast(e.message, "bad");
    }).then(function () {
      state.checking = false;
      $("check-now").disabled = false;
      renderStatus();
    });
  }
  $("check-now").addEventListener("click", checkShows);

  // ---------------------------------------------- events pushed from python

  window.studioEvent = function (name, payload) {
    if (name === "job" && payload.status === "dismissed") {
      forgetEpisode(payload.id);
      renderQueue(); renderStatus(); renderRailFoot(); ensurePolling();
      return;
    }
    if (name === "job") {
      state.jobs[payload.id] = payload;
      renderQueue(); renderStatus(); renderRailFoot(); ensurePolling();
      if (payload.status === "done") {
        toast("Transcript saved: " + (payload.title || "episode"), "good");
        if (state.tab === "library") refreshLibrary();
      } else if (payload.status === "failed") {
        toast((payload.title || "Episode") + " — " + (payload.error || "failed"), "bad");
      }
    } else if (name === "queue") {
      renderRailFoot(); renderStatus();
    } else if (name === "checked") {
      applyCheck(payload);
    } else if (name === "trainjob") {
      state.trainJobs[payload.id] = payload;
      if (state.reader && trainIdForPath(state.reader.path) === payload.id) {
        $("reader-train-status").innerHTML = trainStatusHtml(payload);
      }
      if (payload.status === "failed") {
        toast((payload.title || "Training") + " — " + (payload.error || "failed"), "bad");
      }
    }
  };

  // -------------------------------------------------------------- keyboard

  document.addEventListener("keydown", function (ev) {
    if (ev.key !== "Escape") return;
    if (state.menuOpen || state.moveMenuFor) closeMenus();
  });

  // The add-menu already dismisses via its full-viewport overlay; the
  // per-source move-menu has no such shield, so give it (and, incidentally,
  // any still-open add-menu) an outside-click dismissal too.
  document.addEventListener("click", function (ev) {
    if (!state.moveMenuFor) return;
    var t = ev.target;
    if (t.closest(".move-menu") || t.closest('[data-act="move"]')) return;
    closeMenus();
  });

  // ------------------------------------------------------------------ boot

  function boot() {
    // Render empty-state chrome immediately so a bridge-less preview never
    // shows a blank page or throws.
    renderRail(); renderRailFoot(); renderQueue(); renderStatus(); renderSettings();

    state.statusTimer = setInterval(renderStatus, 30000);

    Promise.all([
      call("list_shows").catch(function () { return []; }),
      call("list_folders").catch(function () { return []; }),
      call("get_settings").catch(function () { return null; }),
      call("job_states").catch(function () { return null; }),
      call("list_transcripts").catch(function () { return []; }),
      call("get_training_settings").catch(function () { return null; })
    ]).then(function (res) {
      state.shows = res[0] || [];
      state.folders = res[1] || [];
      if (res[2]) state.settings = res[2];
      if (res[3]) state.jobs = res[3].jobs || {};
      state.transcripts = res[4] || [];
      if (res[5]) state.trainingSettings = res[5];
      state.ready = true;

      renderRail(); renderRailFoot(); renderQueue(); renderStatus(); renderSettings(); renderLibrary();
      ensurePolling();

      if (state.shows.length) checkShows();
    }).catch(function (e) {
      toast(e.message, "bad");
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
