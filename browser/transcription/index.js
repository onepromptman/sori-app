const SAMPLE_RATE = 16000;
const MAX_FILE_BYTES = 150 * 1024 * 1024;
export const MAX_DURATION_SECONDS = 2 * 60 * 60;
let worker;
let busy = false;

function cancelError() {
  return new DOMException("Transcription canceled.", "AbortError");
}

function abortable(promise, signal) {
  if (!signal) return promise;
  return new Promise((resolve, reject) => {
    const abort = () => reject(cancelError());
    signal.addEventListener("abort", abort, { once: true });
    if (signal.aborted) abort();
    promise.then(resolve, reject).finally(() => signal.removeEventListener("abort", abort));
  });
}

async function decodeAudio(blob, signal) {
  const AudioContext = globalThis.OfflineAudioContext ?? globalThis.webkitOfflineAudioContext;
  if (!AudioContext) throw new Error("This browser cannot decode audio for local transcription.");

  let decoded;
  try {
    const data = await abortable(blob.arrayBuffer(), signal);
    const context = new AudioContext(1, 1, SAMPLE_RATE);
    decoded = await abortable(context.decodeAudioData(data), signal);
  } catch (error) {
    if (error?.name === "AbortError") throw error;
    throw new Error("Sori couldn't read that audio. Try an MP3, WAV, or M4A file.", { cause: error });
  }
  if (!decoded.length) throw new Error("This file has no audio to transcribe.");
  if (decoded.duration > MAX_DURATION_SECONDS) {
    throw new Error("This audio is over two hours. Split it into shorter files and try again.");
  }

  const samples = new Float32Array(decoded.length);
  if (decoded.numberOfChannels === 1) {
    samples.set(decoded.getChannelData(0));
    return samples;
  }
  for (let channel = 0; channel < decoded.numberOfChannels; channel += 1) {
    const input = decoded.getChannelData(channel);
    for (let index = 0; index < samples.length; index += 1) {
      samples[index] += input[index] / decoded.numberOfChannels;
    }
  }
  return samples;
}

function runWorker(samples, { signal, onProgress, onPreview, language }) {
  if (!globalThis.Worker || !globalThis.WebAssembly) {
    throw new Error("This browser cannot run local speech recognition.");
  }
  const activeWorker = worker ??= new Worker(new URL("./worker.js", import.meta.url), { type: "module" });
  return new Promise((resolve, reject) => {
    function cleanup() {
      activeWorker.removeEventListener("message", receive);
      activeWorker.removeEventListener("error", crash);
      activeWorker.removeEventListener("messageerror", crash);
      signal?.removeEventListener("abort", abort);
    }
    function discard() {
      cleanup();
      activeWorker.terminate();
      if (worker === activeWorker) worker = undefined;
    }
    function abort() {
      discard();
      reject(cancelError());
    }
    function crash() {
      discard();
      reject(new Error("Local transcription stopped. Try again with a shorter file."));
    }
    function receive({ data }) {
      if (data.type === "progress") {
        onProgress?.(data.value);
      } else if (data.type === "preview") {
        onPreview?.(data.value);
      } else if (data.type === "error") {
        discard();
        reject(new Error(data.message));
      } else if (data.type === "result") {
        cleanup();
        resolve(data.value);
      }
    }
    activeWorker.addEventListener("message", receive);
    activeWorker.addEventListener("error", crash);
    activeWorker.addEventListener("messageerror", crash);
    signal?.addEventListener("abort", abort, { once: true });
    if (signal?.aborted) {
      abort();
      return;
    }
    try {
      activeWorker.postMessage({ samples, language }, [samples.buffer]);
    } catch (error) {
      discard();
      reject(error);
    }
  });
}

/** Transcribe a browser-readable audio file on this device using local Whisper. */
export async function transcribeAudio(blob, { signal, onProgress, onPreview, language } = {}) {
  if (!(blob instanceof Blob) || !blob.size) throw new Error("Choose an audio file to transcribe.");
  if (blob.size > MAX_FILE_BYTES) {
    throw new Error("This file is over 150 MB. Split it into smaller files and try again.");
  }
  if (signal?.aborted) throw cancelError();
  if (busy) throw new Error("A transcription is already in progress.");
  busy = true;
  try {
    onProgress?.({ stage: "decoding" });
    const samples = await decodeAudio(blob, signal);
    return await runWorker(samples, { signal, onProgress, onPreview, language });
  } finally {
    busy = false;
  }
}
