// Model and runtime requests are downloads. Audio enters this worker as PCM
// from the page and is passed directly to the local WASM pipeline.
const RUNTIME_BASE = "https://cdn.jsdelivr.net/npm/@huggingface/transformers@3.8.1/dist/";
const MODEL_ID = "Xenova/whisper-tiny";
const MODEL_REVISION = "5332fcc35e32a33b86612b9a57a89be7906102b1";
const SAMPLE_RATE = 16000;
const CHUNK_SECONDS = 30;
const STRIDE_SECONDS = 5;
const BATCH_SAMPLES = 5 * 60 * SAMPLE_RATE;
let engine;
let runtime;

function report(stage, progress) {
  self.postMessage({ type: "progress", value: progress === undefined ? { stage } : { stage, progress } });
}

async function loadEngine() {
  if (engine) return engine;
  report("model");
  runtime = await import(RUNTIME_BASE + "transformers.min.js");
  const { env, pipeline } = runtime;
  env.allowLocalModels = false;
  env.useBrowserCache = typeof caches !== "undefined";
  // A single WASM thread works without cross-origin isolation or a GPU.
  env.backends.onnx.wasm.numThreads = 1;
  env.backends.onnx.wasm.wasmPaths = RUNTIME_BASE;
  const downloads = new Map();
  let lastUpdate = 0;
  let lastProgress = 0;
  engine = await pipeline("automatic-speech-recognition", MODEL_ID, {
    revision: MODEL_REVISION,
    device: "wasm",
    dtype: "q8",
    progress_callback({ status, file, loaded, total }) {
      // Count the weights so the small configuration downloads cannot fill
      // the progress bar before the models have begun.
      if (status !== "progress" || !file?.endsWith(".onnx") || !Number.isFinite(total) || total <= 0) return;
      downloads.set(file, { loaded, total });
      if (downloads.size < 2 || performance.now() - lastUpdate < 200) return;
      const values = [...downloads.values()];
      const loadedBytes = values.reduce((sum, value) => sum + value.loaded, 0);
      const totalBytes = values.reduce((sum, value) => sum + value.total, 0);
      lastUpdate = performance.now();
      lastProgress = Math.min(0.99, Math.max(lastProgress, loadedBytes / totalBytes));
      report("model", lastProgress);
    },
  });
  report("model", 1);
  return engine;
}

function appendSegments(segments, output, offset, duration) {
  const chunks = output.chunks?.length ? output.chunks : [{ timestamp: [0, duration], text: output.text }];
  chunks.forEach((chunk, index) => {
    const text = chunk.text?.trim();
    if (!text) return;
    const start = Math.min(duration, Math.max(0, chunk.timestamp?.[0] ?? 0));
    const fallbackEnd = chunks[index + 1]?.timestamp?.[0] ?? duration;
    const end = Math.max(start, Math.min(duration, chunk.timestamp?.[1] ?? fallbackEnd));
    segments.push({ start: offset + start, end: offset + end, text });
  });
}

async function transcribe(transcriber, samples, language) {
  const segments = [];
  report("transcribing", 0);
  for (let start = 0; start < samples.length; start += BATCH_SAMPLES) {
    const batch = samples.subarray(start, start + BATCH_SAMPLES);
    const duration = batch.length / SAMPLE_RATE;
    const stride = CHUNK_SECONDS - 2 * STRIDE_SECONDS;
    const chunkCount = 1 + Math.max(0, Math.ceil((duration - CHUNK_SECONDS) / stride));
    let complete = 0;
    let preview = "";
    const streamer = new runtime.WhisperTextStreamer(transcriber.tokenizer, {
      skip_prompt: true,
      callback_function(text) {
        if (!text) return;
        preview += text;
        self.postMessage({ type: "preview", value: preview.trimStart() });
      },
      on_finalize() {
        // Overlapping chunks may repeat words. Preview only the latest chunk.
        preview = "";
        complete = Math.min(complete + 1, chunkCount);
        report("transcribing", (start + batch.length * (complete / chunkCount)) / samples.length);
      },
    });
    const output = await transcriber(batch, {
      chunk_length_s: CHUNK_SECONDS,
      stride_length_s: STRIDE_SECONDS,
      return_timestamps: true,
      task: "transcribe",
      ...(language && language !== "auto" ? { language } : {}),
      streamer,
    });
    appendSegments(segments, output, start / SAMPLE_RATE, duration);
  }
  return { text: segments.map(({ text }) => text).join(" "), segments };
}

self.addEventListener("message", async ({ data: { samples, language } }) => {
  let transcriber;
  try {
    transcriber = await loadEngine();
  } catch (error) {
    console.error("Whisper model load failed", error);
    self.postMessage({
      type: "error",
      message: "Sori couldn't load the speech model. Check your connection and try again.",
    });
    return;
  }
  try {
    const result = await transcribe(transcriber, samples, language);
    self.postMessage({ type: "result", value: result });
  } catch (error) {
    console.error("Whisper transcription failed", error);
    self.postMessage({
      type: "error",
      message: "Sori couldn't transcribe this audio on your device. Try a shorter file or another browser.",
    });
  }
});
