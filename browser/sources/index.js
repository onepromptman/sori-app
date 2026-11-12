const MAX_FEED_MIB = 16;
const MAX_FEED_BYTES = MAX_FEED_MIB * 1024 * 1024;
const MAX_AUDIO_BYTES = 100 * 1024 * 1024;
const MAX_EPISODES = 60;
const YOUTUBE_HOSTS = new Set([
  "youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com",
  "youtu.be", "www.youtu.be", "youtube-nocookie.com", "www.youtube-nocookie.com",
]);
const MEDIA_EXTENSIONS = /\.(aac|aif|aiff|flac|m4a|m4b|mp3|mp4|ogg|opus|wav|webm)$/i;
const VIDEO_ID = /^[\w-]{11}$/;

export class SourceError extends Error {
  constructor(code, message) {
    super(message);
    this.name = "SourceError";
    this.code = code;
  }
}

function webUrl(raw, base) {
  try {
    const url = new URL(raw, base);
    if (!["http:", "https:"].includes(url.protocol) || url.username || url.password) {
      return null;
    }
    return url;
  } catch {
    return null;
  }
}

function youtubeUrl(url) {
  const [section, id] = url.pathname.split("/").filter(Boolean);
  const video = url.hostname.endsWith("youtu.be") ? section :
    section === "watch" ? url.searchParams.get("v") :
    ["shorts", "live", "embed", "v"].includes(section) ? id : null;
  if (video && VIDEO_ID.test(video)) {
    return `https://www.youtube.com/watch?v=${video}`;
  }
  const list = url.searchParams.get("list");
  if (["watch", "playlist", "embed"].includes(section) && list && /^[\w-]+$/.test(list)) {
    return `https://www.youtube.com/playlist?list=${list}`;
  }
  if (section?.startsWith("@") && section.length > 1) {
    return `https://www.youtube.com/${section}`;
  }
  if (["channel", "c", "user"].includes(section) && id && id !== "..") {
    return `https://www.youtube.com/${section}/${id}`;
  }
  // Legacy vanity URLs and links that do not identify one playable video.
  url.hash = "";
  return url.href;
}

export function describeSource(raw) {
  let input = String(raw ?? "").trim();
  if (/^@[^/\s]+$/u.test(input)) {
    input = `https://www.youtube.com/@${encodeURIComponent(input.slice(1))}`;
  } else if (/^[\w-]+(?:\.[\w-]+)+(?:[:/?#]|$)/.test(input)) {
    input = `https://${input}`;
  }
  const url = webUrl(input);
  if (!url) {
    throw new SourceError("invalid-url", "Enter a podcast RSS feed or a YouTube link.");
  }
  const kind = YOUTUBE_HOSTS.has(url.hostname) ? "youtube" : "rss";
  url.hash = "";
  const href = kind === "youtube" ? youtubeUrl(url) : url.href;
  return { kind, url: href, key: href };
}

export function youtubeVideoId(raw) {
  const url = webUrl(raw);
  if (!url || !YOUTUBE_HOSTS.has(url.hostname)) return "";
  const normalized = new URL(youtubeUrl(url));
  const id = normalized.searchParams.get("v");
  return normalized.pathname === "/watch" && VIDEO_ID.test(id ?? "") ? id : "";
}

const children = (node, tag) => Array.from(node.children).filter((child) => child.localName === tag);
const first = (node, tag) => children(node, tag)[0];
const field = (node, tag) => first(node, tag)?.textContent.trim() || "";

function resolveXmlUrl(node, raw, fallback) {
  if (!raw?.trim()) return "";
  const bases = [];
  for (let current = node; current?.nodeType === 1; current = current.parentElement) {
    const declared = current.getAttributeNS("http://www.w3.org/XML/1998/namespace", "base");
    if (declared) bases.unshift(declared);
  }
  const base = bases.reduce((url, part) => webUrl(part, url)?.href ?? url, fallback);
  return webUrl(raw.trim(), base)?.href ?? "";
}

function audioLink(item, base) {
  const attachments = [
    ...children(item, "enclosure"),
    ...children(item, "link").filter((node) => node.getAttribute("rel")?.toLowerCase() === "enclosure"),
    ...children(item, "content").filter((node) => node.namespaceURI === "http://search.yahoo.com/mrss/"),
    ...children(item, "group")
      .filter((node) => node.namespaceURI === "http://search.yahoo.com/mrss/")
      .flatMap((group) => children(group, "content")),
  ];
  for (const node of attachments) {
    const href = resolveXmlUrl(node, node.getAttribute("url") || node.getAttribute("href"), base);
    if (!href || YOUTUBE_HOSTS.has(new URL(href).hostname)) continue;
    const type = (node.getAttribute("type") || "").toLowerCase();
    if (/^(audio\/|video\/|application\/ogg\b)/.test(type) ||
        node.getAttribute("medium") === "audio" ||
        MEDIA_EXTENSIONS.test(new URL(href).pathname)) {
      return href;
    }
  }
  return "";
}

export function parseFeedXml(xml, baseUrl) {
  if (typeof xml !== "string" || /<!doctype\b/i.test(xml)) {
    throw new SourceError("invalid-feed", "Choose a standard RSS or Atom feed XML file.");
  }
  if (xml.length > MAX_FEED_BYTES) {
    throw new SourceError("too-large", `Choose an RSS or Atom feed up to ${MAX_FEED_MIB} MB.`);
  }
  const document = new DOMParser().parseFromString(xml, "application/xml");
  if (document.getElementsByTagNameNS("*", "parsererror").length) {
    throw new SourceError("invalid-feed", "This link does not contain readable RSS or Atom XML.");
  }
  const root = document.documentElement;
  const channel = root.localName === "rss" || root.localName === "RDF" ? first(root, "channel") : root;
  if (!channel || !["channel", "feed"].includes(channel.localName)) {
    throw new SourceError("invalid-feed", "This link is not a podcast RSS or Atom feed.");
  }
  const items = root.localName === "RDF" ? children(root, "item") :
    channel.localName === "feed" ? children(channel, "entry") : children(channel, "item");
  const episodes = [];
  const seen = new Set();
  for (const item of items) {
    const audioUrl = audioLink(item, baseUrl);
    if (!audioUrl) continue;
    const id = field(item, "guid") || field(item, "id") || audioUrl;
    if (seen.has(id)) continue;
    seen.add(id);
    const link = children(item, "link").find((node) => ["alternate", null].includes(node.getAttribute("rel")));
    const url = link ? resolveXmlUrl(link, link.getAttribute("href") || link.textContent, baseUrl) : "";
    const timestamp = Date.parse(field(item, "pubDate") || field(item, "published") ||
      field(item, "updated") || field(item, "date"));
    episodes.push({
      id,
      title: field(item, "title") || "Untitled episode",
      date: Number.isFinite(timestamp) ? new Date(timestamp).toISOString() : "",
      audioUrl,
      url: url || audioUrl,
    });
    if (episodes.length >= MAX_EPISODES) break;
  }
  if (!episodes.length) {
    throw new SourceError("no-audio", "This feed has no audio episodes. Try the publisher's podcast RSS feed or add an audio file.");
  }
  return { title: field(channel, "title") || "Podcast", episodes };
}

export async function readFeedFile(file, baseUrl) {
  if (file.size > MAX_FEED_BYTES) {
    throw new SourceError("too-large", `Choose an RSS or Atom file up to ${MAX_FEED_MIB} MB.`);
  }
  return parseFeedXml(await file.text(), baseUrl);
}

function fetchError(status, name) {
  if (status === 429) {
    return new SourceError("rate-limit", `The publisher is limiting requests for this ${name}. Wait and try again, or add an audio file you have.`);
  }
  return new SourceError("http-error", `The publisher returned HTTP ${status} for this ${name}.`);
}

async function readResponse(url, { name, limit, timeout, signal, onProgress }) {
  const controller = new AbortController();
  const forwardAbort = () => controller.abort();
  if (signal?.aborted) forwardAbort();
  signal?.addEventListener("abort", forwardAbort, { once: true });
  const timer = setTimeout(() => controller.abort(), timeout);
  const tooLarge = () => new SourceError("too-large", `This ${name} exceeds the browser limit of ${limit / 1024 / 1024} MB.`);
  let reader;
  try {
    const response = await fetch(url, {
      signal: controller.signal,
      credentials: "omit",
      referrerPolicy: "no-referrer",
    });
    if (!response.ok) throw fetchError(response.status, name);
    const total = Number(response.headers.get("content-length")) || undefined;
    if (total > limit) throw tooLarge();
    const type = response.headers.get("content-type") || "";
    if (name === "episode audio" && /(?:text\/|application\/(?:json|xml))/i.test(type)) {
      throw new SourceError("invalid-audio", "The publisher returned a web page instead of audio. Add an audio file you have.");
    }
    if (!response.body) throw new SourceError("empty-response", `The publisher returned an empty ${name}.`);
    reader = response.body.getReader();
    const chunks = [];
    let loaded = 0;
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      loaded += value.byteLength;
      if (loaded > limit) throw tooLarge();
      chunks.push(value);
      onProgress?.({ loaded, total });
    }
    return { blob: new Blob(chunks, { type }), url: response.url || url };
  } catch (error) {
    if (signal?.aborted) throw new DOMException("The request was canceled.", "AbortError");
    if (controller.signal.aborted) {
      throw new SourceError("timeout", `The ${name} took too long to load. Try again or add an audio file you have.`);
    }
    if (error instanceof SourceError) throw error;
    throw new SourceError(
      "unreadable",
      `The browser could not read this ${name}. The publisher may block access from websites. Try the publisher's download or add an audio file you have.`,
    );
  } finally {
    clearTimeout(timer);
    signal?.removeEventListener("abort", forwardAbort);
    controller.abort();
    reader?.releaseLock();
  }
}

export async function loadFeed(source, { signal } = {}) {
  const resolved = describeSource(typeof source === "string" ? source : source?.url);
  if (resolved.kind === "youtube") {
    throw new SourceError(
      "youtube-restricted",
      "Open the link in YouTube. For transcription, try the show's podcast RSS feed or choose an audio file you have permission to use.",
    );
  }
  const { blob, url } = await readResponse(resolved.url, {
    name: "feed", limit: MAX_FEED_BYTES, timeout: 20_000, signal,
  });
  return parseFeedXml(await blob.text(), url);
}

export async function searchPodcastFeeds(name, { signal } = {}) {
  const query = name.trim();
  if (!query) throw new SourceError("empty-search", "Enter the name of the show.");
  const url = new URL("https://itunes.apple.com/search");
  url.search = new URLSearchParams({ term: query, media: "podcast", entity: "podcast", limit: "8" });
  let results;
  try {
    const { blob } = await readResponse(url.href, {
      name: "podcast search", limit: 1024 * 1024, timeout: 10_000, signal,
    });
    results = JSON.parse(await blob.text()).results;
    if (!Array.isArray(results)) throw new Error("Invalid podcast search results.");
  } catch (error) {
    if (error.name === "AbortError") throw error;
    throw new SourceError("search-failed", "Podcast search is unavailable. Try again or paste the RSS feed in Sources.");
  }
  const feeds = new Map();
  for (const result of results) {
    const feed = webUrl(result?.feedUrl);
    const title = typeof result?.collectionName === "string" ? result.collectionName.trim() : "";
    if (title && feed && !YOUTUBE_HOSTS.has(feed.hostname)) feeds.set(feed.href, { title, url: feed.href });
  }
  return [...feeds.values()];
}

export async function fetchEpisodeAudio(episode, { signal, onProgress } = {}) {
  const raw = typeof episode === "string" ? episode : episode?.audioUrl;
  const url = webUrl(raw);
  if (!url || YOUTUBE_HOSTS.has(url.hostname)) {
    throw new SourceError("invalid-audio", "Choose a podcast audio enclosure or an audio file you have.");
  }
  const { blob } = await readResponse(url.href, {
    name: "episode audio", limit: MAX_AUDIO_BYTES, timeout: 180_000, signal, onProgress,
  });
  if (!blob.size) throw new SourceError("empty-response", "The publisher returned an empty audio file.");
  return blob;
}
