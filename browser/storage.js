const stores = ["sources", "transcripts", "files", "evidence"];
let opening;
const channel = typeof BroadcastChannel === "function" ? new BroadcastChannel("sori-library") : null;

function openLibrary() {
  opening ??= new Promise((resolve, reject) => {
    const request = indexedDB.open("sori-library", 1);
    request.onupgradeneeded = () => {
      for (const name of stores) {
        const store = request.result.createObjectStore(name, { keyPath: "id" });
        if (name === "files") store.createIndex("transcript", "transcriptId");
      }
    };
    request.onsuccess = () => {
      request.result.onversionchange = () => {
        request.result.close();
        opening = undefined;
      };
      resolve(request.result);
    };
    request.onerror = () => {
      opening = undefined;
      reject(request.error);
    };
  });
  return opening;
}

async function transact(names, mode, perform) {
  const db = await openLibrary();
  const tx = db.transaction(names, mode);
  return new Promise((resolve, reject) => {
    tx.oncomplete = () => {
      if (mode === "readwrite") channel?.postMessage("changed");
      resolve(readResult());
    };
    tx.onabort = () => reject(tx.error ?? new Error("The library update was cancelled."));
    let readResult = () => undefined;
    try {
      readResult = perform(tx) ?? readResult;
    } catch (error) {
      tx.abort();
      reject(error);
    }
  });
}

export function readLibrary() {
  return transact(stores, "readonly", tx => {
    const requests = Object.fromEntries(stores.map(name => [name, tx.objectStore(name).getAll()]));
    return () => Object.fromEntries(stores.map(name => [name, requests[name].result]));
  });
}

export function saveRecord(store, record) {
  return transact(store, "readwrite", tx => { tx.objectStore(store).put(record); });
}

export function addSource(source) {
  return transact("sources", "readwrite", tx => { tx.objectStore("sources").add(source); });
}

export function updateSource(source) {
  let exists;
  return transact("sources", "readwrite", tx => {
    const store = tx.objectStore("sources");
    const lookup = store.getKey(source.id);
    lookup.onsuccess = () => {
      exists = Boolean(lookup.result);
      if (exists) store.put(source);
    };
    return () => exists;
  });
}

export function saveSlideResults(transcriptId, files, evidence) {
  let exists;
  return transact(["transcripts", "files", "evidence"], "readwrite", tx => {
    const transcript = tx.objectStore("transcripts").getKey(transcriptId);
    transcript.onsuccess = () => {
      exists = Boolean(transcript.result);
      if (!exists) return;
      for (const file of files) tx.objectStore("files").put(file);
      if (evidence) tx.objectStore("evidence").put({ id: transcriptId, ...evidence });
    };
    return () => exists;
  });
}

export function removeRecord(store, id) {
  if (store !== "transcripts") {
    return transact(store, "readwrite", tx => { tx.objectStore(store).delete(id); });
  }
  return transact(["transcripts", "files", "evidence"], "readwrite", tx => {
    tx.objectStore("transcripts").delete(id);
    tx.objectStore("evidence").delete(id);
    const files = tx.objectStore("files").index("transcript").openCursor(id);
    files.onsuccess = () => {
      const cursor = files.result;
      if (!cursor) return;
      cursor.delete();
      cursor.continue();
    };
  });
}

export function watchLibrary(onChange) {
  channel?.addEventListener("message", onChange);
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible") onChange();
  });
}
