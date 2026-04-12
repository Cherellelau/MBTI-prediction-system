// ---------- UI helpers ----------
const statusText = document.getElementById("statusText");
const statusDot = document.getElementById("statusDot");
const recordBadge = document.getElementById("recordBadge");
const guideText = document.getElementById("guideText");
const progressFill = document.getElementById("progressFill");
const steps = [
  document.getElementById("step1"),
  document.getElementById("step2"),
  document.getElementById("step3"),
  document.getElementById("step4"),
];

function setStatus(label, color) {
  statusText.textContent = label;
  statusDot.style.background = color;
}

function setStep(n) {
  steps.forEach((s, i) => s.classList.toggle("active", i === n));
  progressFill.style.width = (n + 1) * 25 + "%";
}

// ---------- collapsible ----------
const scenarioInfoBtn = document.getElementById("scenarioInfoBtn");
const scenarioInfo = document.getElementById("scenarioInfo");
scenarioInfoBtn?.addEventListener("click", () => {
  scenarioInfo.classList.toggle("open");
});

// ---------- Voice Recording ----------
const btnStart = document.getElementById("btnStart");
const btnStop = document.getElementById("btnStop");
const btnTranscribe = document.getElementById("btnTranscribe");
const btnSubmitVoice = document.getElementById("btnSubmitVoice");

const transcriptBox = document.getElementById("transcriptBox");
const transcriptInput = document.getElementById("transcriptInput");
const timerText = document.getElementById("timerText");

let mediaRecorder = null;
let chunks = [];
let blob = null;
let timer = null;
let seconds = 0;

function resetTimer() {
  seconds = 0;
  timerText.textContent = "00:00";
  if (timer) clearInterval(timer);
  timer = null;
}

function startTimer() {
  resetTimer();
  timer = setInterval(() => {
    seconds += 1;
    const mm = String(Math.floor(seconds / 60)).padStart(2, "0");
    const ss = String(seconds % 60).padStart(2, "0");
    timerText.textContent = `${mm}:${ss}`;
  }, 1000);
}

function setRecordingUI(isRecording) {
  btnStart.disabled = isRecording;
  btnStop.disabled = !isRecording;
  btnTranscribe.disabled = isRecording || !blob;

  recordBadge.textContent = isRecording ? "Recording..." : (blob ? "Recorded" : "Idle");

  setStatus(isRecording ? "Recording" : (blob ? "Recorded" : "Ready"),
           isRecording ? "#f59e0b" : "#10b981");

  guideText.textContent = isRecording ? "Speak now..." : (blob ? "Click Transcribe" : "Pick a method to start");
  setStep(isRecording ? 1 : (blob ? 2 : 0));
}

btnStart?.addEventListener("click", async () => {
  try {
    setStep(1);
    setStatus("Recording", "#f59e0b");

    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    chunks = [];
    blob = null;

    mediaRecorder = new MediaRecorder(stream);
    mediaRecorder.ondataavailable = (e) => chunks.push(e.data);

    mediaRecorder.onstop = () => {
      blob = new Blob(chunks, { type: "audio/webm" });
      setRecordingUI(false);
      btnTranscribe.disabled = false;

      // stop mic tracks
      stream.getTracks().forEach((t) => t.stop());
    };

    mediaRecorder.start();
    startTimer();
    setRecordingUI(true);

  } catch (err) {
    alert("Microphone permission denied or not available.");
    setStatus("Mic error", "#ef4444");
  }
});

btnStop?.addEventListener("click", () => {
  if (mediaRecorder && mediaRecorder.state !== "inactive") {
    mediaRecorder.stop();
    if (timer) clearInterval(timer);
    timer = null;
  }
});

btnTranscribe?.addEventListener("click", async () => {
  if (!blob) return;

  setStatus("Transcribing...", "#3b82f6");
  guideText.textContent = "Uploading audio to transcribe...";
  setStep(2);

  const fd = new FormData();
  fd.append("audio", blob, "recording.webm");

  const res = await fetch(window.VOICE_TRANSCRIBE_URL, {
    method: "POST",
    body: fd,
  });

  const data = await res.json();

  if (!data.ok) {
    transcriptBox.textContent = data.error || "Failed to transcribe.";
    setStatus("Transcribe failed", "#ef4444");
    return;
  }

  transcriptBox.textContent = data.transcript || "";
  transcriptInput.value = data.transcript || "";
  btnSubmitVoice.disabled = !(data.transcript && data.transcript.trim().length > 0);

  setStatus("Transcribed", "#10b981");
  guideText.textContent = "Now submit for prediction";
  setStep(2);
});

// init
resetTimer();
setRecordingUI(false);
setStep(0);
