import { MAX_DURATION_SECONDS } from "./index.js";

const FORMAT = "audio/webm;codecs=opus";

export function canRecordTabAudio() {
  return Boolean(navigator.mediaDevices?.getDisplayMedia && globalThis.MediaRecorder?.isTypeSupported(FORMAT));
}

export async function recordTabAudio({ signal, onRecording }) {
  let stream;
  try {
    stream = await navigator.mediaDevices.getDisplayMedia({
      video: { displaySurface: "browser" },
      audio: true,
      selfBrowserSurface: "exclude",
      systemAudio: "exclude",
      windowAudio: "exclude",
      surfaceSwitching: "exclude",
      monitorTypeSurfaces: "exclude"
    });
  } catch (error) {
    if (error.name === "NotAllowedError") {
      throw new Error("Tab sharing was closed or blocked. Try sharing the tab again.");
    }
    throw error;
  }

  try {
    signal.throwIfAborted();
    const [video] = stream.getVideoTracks();
    const [audio] = stream.getAudioTracks();
    if (video?.getSettings().displaySurface !== "browser" || !audio || audio.readyState === "ended") {
      throw new Error("Choose a browser tab and turn on Also share tab audio. If that option is missing, try desktop Chrome.");
    }
    const recorder = new MediaRecorder(new MediaStream([audio]), { mimeType: FORMAT, audioBitsPerSecond: 64000 });
    const chunks = [];
    function stop() {
      if (recorder.state !== "inactive") recorder.stop();
    }
    try {
      return await new Promise((resolve, reject) => {
        recorder.addEventListener("dataavailable", event => {
          if (event.data.size) chunks.push(event.data);
          if (event.timecode >= (MAX_DURATION_SECONDS - 5) * 1000) stop();
        });
        recorder.addEventListener("error", () => reject(new Error("The tab audio recording stopped unexpectedly.")), { once: true });
        recorder.addEventListener("stop", () => {
          if (signal.aborted) reject(signal.reason);
          else if (!chunks.length) reject(new Error("No tab audio was recorded. Play the video while sharing and try again."));
          else resolve(new Blob(chunks, { type: recorder.mimeType }));
        }, { once: true });
        video.addEventListener("ended", stop, { once: true });
        audio.addEventListener("ended", stop, { once: true });
        signal.addEventListener("abort", stop, { once: true });
        recorder.start(1000);
        onRecording(stop);
      });
    } finally {
      signal.removeEventListener("abort", stop);
      video.removeEventListener("ended", stop);
      audio.removeEventListener("ended", stop);
    }
  } finally {
    stream.getTracks().forEach(track => track.stop());
  }
}
