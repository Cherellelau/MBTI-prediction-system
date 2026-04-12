// static/js/voice.js
(() => {
  // ---------- Elements ----------
  const btnStart = document.getElementById("btnStart");
  const btnStop = document.getElementById("btnStop");
  const btnTranscribe = document.getElementById("btnTranscribe");
  const btnSubmit = document.getElementById("btnSubmit");

  const audioFile = document.getElementById("audioFile");
  const btnUploadFile = document.getElementById("btnUploadFile");
  const voiceLang = document.getElementById("voiceLang");
  const fileNameText = document.getElementById("fileNameText");

  const transcriptBox = document.getElementById("transcriptBox");
  const transcriptEnBox = document.getElementById("transcriptEnBox");
  const transcriptHidden = document.getElementById("transcriptHidden");
  const detectedLangHidden = document.getElementById("detectedLangHidden");

  const timerText = document.getElementById("timerText");
  const recordBadge = document.getElementById("statusText");
  const voiceHint = document.getElementById("voiceLangHint");
  const detectedLangEl = document.getElementById("detectedLang");
  const transcribeWarningEl = document.getElementById("transcribeWarning");

  const ALLOWED_LANGS = ["en", "ms", "zh"];

  // ---------- Guards ----------
  if (!btnStart || !btnStop || !btnTranscribe || !btnSubmit || !transcriptBox || !transcriptHidden) {
    console.warn("voice.js: missing required elements");
    return;
  }

  // ---------- State ----------
  let mode = null; // "record" | "upload"
  let mediaRecorder = null;
  let stream = null;
  let chunks = [];
  let timer = null;
  let seconds = 0;

  let lastAudioBlob = null;
  let uploadedFilename = null;
  let recordedFilename = null;

  let detectedLang = "";
  let translateDebounce = null;

  // ---------- Message packs ----------
  const VOICE_MESSAGES = {
    en: {
      choose_file_first: "Please choose an audio file first.",
      uploading: "Uploading audio file...",
      uploaded: "Uploaded. Click Transcribe.",
      upload_failed: "Upload failed. Try again.",
      upload_error: "Upload error. Check console/server logs.",
      recording_saved: "Recording saved. Click Transcribe.",
      recording_hint: "Recording... speak naturally for 10–20 seconds.",
      mic_blocked: "Microphone blocked. Please allow mic access.",
      transcribing: "Transcribing audio...",
      transcribed: "Transcription completed.",
      transcribe_failed: "Transcription failed. Please try again.",
      language_changed: "Language changed. Click Transcribe again.",
      select_lang_hint: "Select the spoken language before transcription. If the result looks wrong, switch language and retry.",
      valid_ready: "Done. The input is valid for MBTI prediction.",
      invalid_more: "Please provide more personality-related information.",
      empty: "Please provide audio input before prediction.",
      too_short: "The audio is too short for personality analysis. Please describe your interests, habits, or preferences.",
      identity_only: "Insufficient personality-related information. Please describe your interests, habits, or preferences.",
      greeting_only: "No personality suggestion can be generated because the audio content is not relevant for personality analysis.",
      background_only: "Please provide more information about your interests, behavior, or decision-making style.",
      insufficient: "Insufficient personality-related information. Please describe your interests, habits, preferences, social behavior, or decision-making style.",
      unsupported: (detected) =>
        `Only English, Malay, and Mandarin are supported. Detected language: ${detected || "UNKNOWN"}. Please select English, Malay, or Mandarin and transcribe again.`,

      idle_badge: "Idle",
      uploading_badge: "Uploading...",
      uploaded_badge: "Uploaded",
      recorded_badge: "Recorded",
      recording_badge: "Recording",
      transcribing_badge: "Transcribing...",
      validation_failed_badge: "Validation Failed",
      ready_badge: "Ready"
    },

    ms: {
      choose_file_first: "Sila pilih fail audio terlebih dahulu.",
      uploading: "Sedang memuat naik fail audio...",
      uploaded: "Muat naik berjaya. Klik Transkripsi.",
      upload_failed: "Muat naik gagal. Cuba lagi.",
      upload_error: "Ralat semasa memuat naik. Sila semak console atau log server.",
      recording_saved: "Rakaman disimpan. Klik Transkripsi.",
      recording_hint: "Sedang merakam... sila bercakap secara semula jadi selama 10–20 saat.",
      mic_blocked: "Mikrofon disekat. Sila benarkan akses mikrofon.",
      transcribing: "Sedang mentranskripsi audio...",
      transcribed: "Transkripsi selesai.",
      transcribe_failed: "Transkripsi gagal. Sila cuba lagi.",
      language_changed: "Bahasa telah ditukar. Sila klik Transkripsi semula.",
      select_lang_hint: "Pilih bahasa pertuturan sebelum transkripsi. Jika keputusan nampak salah, tukar bahasa dan cuba semula.",
      valid_ready: "Selesai. Input ini sah untuk ramalan MBTI.",
      invalid_more: "Sila berikan lebih banyak maklumat berkaitan personaliti.",
      empty: "Sila berikan input audio sebelum membuat ramalan.",
      too_short: "Audio terlalu pendek untuk analisis personaliti. Sila terangkan minat, tabiat, atau kecenderungan anda.",
      identity_only: "Maklumat berkaitan personaliti tidak mencukupi. Sila terangkan minat, tabiat, atau kecenderungan anda.",
      greeting_only: "Cadangan personaliti tidak dapat dijana kerana kandungan audio tidak berkaitan dengan analisis personaliti.",
      background_only: "Sila berikan lebih banyak maklumat tentang minat, tingkah laku, atau gaya membuat keputusan anda.",
      insufficient: "Maklumat berkaitan personaliti tidak mencukupi. Sila terangkan minat, tabiat, keutamaan, tingkah laku sosial, atau gaya membuat keputusan anda.",
      unsupported: (detected) =>
        `Hanya bahasa Inggeris, Bahasa Melayu, dan Mandarin disokong. Bahasa yang dikesan: ${detected || "TIDAK DIKETAHUI"}. Sila pilih English, Malay, atau Mandarin dan transkripsi semula.`,

      idle_badge: "Sedia",
      uploading_badge: "Memuat naik...",
      uploaded_badge: "Berjaya dimuat naik",
      recorded_badge: "Dirakam",
      recording_badge: "Sedang merakam",
      transcribing_badge: "Sedang transkripsi...",
      validation_failed_badge: "Pengesahan gagal",
      ready_badge: "Sedia"
    },

    zh: {
      choose_file_first: "请先选择音频文件。",
      uploading: "正在上传音频文件...",
      uploaded: "上传成功。请点击转写。",
      upload_failed: "上传失败，请再试一次。",
      upload_error: "上传时发生错误。请检查 console 或 server log。",
      recording_saved: "录音已保存。请点击转写。",
      recording_hint: "正在录音……请自然说话 10–20 秒。",
      mic_blocked: "麦克风已被阻止。请允许麦克风权限。",
      transcribing: "正在转写音频...",
      transcribed: "转写完成。",
      transcribe_failed: "转写失败，请再试一次。",
      language_changed: "语言已更改，请重新点击转写。",
      select_lang_hint: "请先选择语音语言再进行转写。如果结果不正确，请切换语言后重试。",
      valid_ready: "完成。此输入可用于 MBTI 预测。",
      invalid_more: "请提供更多与人格相关的信息。",
      empty: "请先提供语音内容再进行预测。",
      too_short: "语音内容太短，无法进行人格分析。请描述你的兴趣、习惯或偏好。",
      identity_only: "与人格相关的信息不足。请描述你的兴趣、习惯或偏好。",
      greeting_only: "由于音频内容与人格分析无关，因此无法生成性格建议。",
      background_only: "请提供更多关于你的兴趣、行为方式或决策风格的信息。",
      insufficient: "与人格相关的信息不足。请描述你的兴趣、习惯、偏好、社交行为或决策风格。",
      unsupported: (detected) =>
        `目前只支持英语、马来语和华语。检测到的语言：${detected || "未知"}。请选择 English、Malay 或 Mandarin 后重新转写。`,

      idle_badge: "待命",
      uploading_badge: "上传中...",
      uploaded_badge: "已上传",
      recorded_badge: "已录音",
      recording_badge: "录音中",
      transcribing_badge: "转写中...",
      validation_failed_badge: "验证失败",
      ready_badge: "可提交"
    }
  };

  // ---------- Language helpers ----------
  function getSelectedLang() {
    const val = (voiceLang?.value || "en").trim().toLowerCase();
    if (val === "bm" || val === "ms" || val === "malay") return "ms";
    if (val === "zh" || val === "cn" || val === "mandarin" || val === "chinese") return "zh";
    return "en";
  }

  function getPageLang() {
    const htmlLang = (document.documentElement.lang || "en").trim().toLowerCase();
    if (htmlLang.startsWith("zh")) return "zh";
    if (htmlLang === "ms" || htmlLang.startsWith("ms")) return "ms";
    return "en";
  }

  function msg(key, detected = "") {
    const lang = getPageLang();
    const pack = VOICE_MESSAGES[lang] || VOICE_MESSAGES.en;
    const value = pack[key];
    return typeof value === "function" ? value(detected) : (value || "");
  }

  function normalizeDetectedLang(code) {
    const lang = (code || "").trim().toLowerCase();
    if (lang === "english") return "en";
    if (lang === "malay" || lang === "bm" || lang === "bahasa melayu" || lang === "ms-my") return "ms";
    if (lang === "mandarin" || lang === "chinese" || lang === "zh-cn" || lang === "zh-tw" || lang === "zh-hans" || lang === "zh-hant") return "zh";
    return lang;
  }

  function isSupportedLang(code) {
    return ALLOWED_LANGS.includes(normalizeDetectedLang(code));
  }

  // ---------- Validation ----------
  function validatePersonalityContent(text) {
    const raw = (text || "").trim();
    const t = raw.toLowerCase();

    if (!t) {
      return { valid: false, type: "empty", message: msg("empty") };
    }

    const words = t.split(/\s+/).filter(Boolean);
    const wordCount = words.length;
    const charCount = raw.replace(/\s+/g, "").length;

    if (wordCount < 4 && charCount < 12) {
      return { valid: false, type: "too_short", message: msg("too_short") };
    }

    const identityOnlyPatterns = [
      /^my name is\s+[a-z\s]+\.?$/i,
      /^i am\s+[a-z\s]+\.?$/i,
      /^i'm\s+[a-z\s]+\.?$/i,

      /^nama saya\s+[a-z\s]+\.?$/i,
      /^saya\s+[a-z\s]+\.?$/i,

      /^我叫[\u4e00-\u9fffa-zA-Z\s]+[。.]?$/u,
      /^我是[\u4e00-\u9fffa-zA-Z\s]+[。.]?$/u,
      /^我的名字是[\u4e00-\u9fffa-zA-Z\s]+[。.]?$/u
    ];

    if (identityOnlyPatterns.some((p) => p.test(raw)) && (wordCount <= 5 || charCount <= 16)) {
      return { valid: false, type: "identity_only", message: msg("identity_only") };
    }

    const greetingOnlyPatterns = [
      /^hello[.!]?$/i,
      /^hi[.!]?$/i,
      /^hey[.!]?$/i,
      /^good morning[.!]?$/i,
      /^good afternoon[.!]?$/i,
      /^good evening[.!]?$/i,

      /^hai[.!]?$/i,
      /^helo[.!]?$/i,
      /^selamat pagi[.!]?$/i,
      /^selamat tengah hari[.!]?$/i,
      /^selamat petang[.!]?$/i,
      /^selamat malam[.!]?$/i,

      /^你好[。.!]?$/u,
      /^嗨[。.!]?$/u,
      /^哈咯[。.!]?$/u,
      /^早安[。.!]?$/u,
      /^早上好[。.!]?$/u,
      /^下午好[。.!]?$/u,
      /^晚上好[。.!]?$/u,
      /^午安[。.!]?$/u
    ];

    if (greetingOnlyPatterns.some((p) => p.test(raw))) {
      return { valid: false, type: "greeting_only", message: msg("greeting_only") };
    }

    const weakBackgroundPatterns = [
      /\bi am \d{1,2} years old\b/i,
      /\bi'm \d{1,2} years old\b/i,
      /\bi study\b/i,
      /\bi am studying\b/i,
      /\bmy degree\b/i,
      /\bmy course\b/i,
      /\bcomputer science\b/i,
      /\bengineering\b/i,
      /\bbusiness\b/i,
      /\bdata science\b/i,
      /\bi am a student\b/i,
      /\bi am currently studying\b/i,

      /\bumur saya \d{1,2} tahun\b/i,
      /\bsaya belajar\b/i,
      /\bsaya sedang belajar\b/i,
      /\bjurusan saya\b/i,
      /\bkursus saya\b/i,
      /\bsains komputer\b/i,
      /\bkejuruteraan\b/i,
      /\bperniagaan\b/i,
      /\bsains data\b/i,
      /\bsaya seorang pelajar\b/i,

      /我今年\d{1,2}岁/u,
      /我\d{1,2}岁/u,
      /我在读书/u,
      /我正在读书/u,
      /我是学生/u,
      /我的科系/u,
      /我的课程/u,
      /电脑科学/u,
      /工程系/u,
      /商业系/u,
      /数据科学/u
    ];

    const personalityKeywords = [
      "i like", "i enjoy", "i prefer", "usually", "often", "always",
      "alone", "by myself", "friends", "team", "teams", "group", "people",
      "social", "talking to people", "plan", "planned", "planning", "schedule",
      "organized", "organised", "structure", "structured", "logic", "facts",
      "efficient", "feelings", "care about", "creative", "ideas", "imagine",
      "possibilities", "future", "carefully", "decision", "decisions",
      "behaviour", "behavior", "habit", "habits",

      "saya suka", "saya lebih suka", "saya gemar", "biasanya", "selalunya",
      "sering", "selalu", "bersendirian", "sendiri", "kawan", "rakan",
      "pasukan", "kumpulan", "orang", "sosial", "bercakap dengan orang",
      "merancang", "rancang", "jadual", "tersusun", "teratur", "logik",
      "fakta", "perasaan", "ambil kira perasaan", "kreatif", "idea",
      "bayangkan", "kemungkinan", "masa depan", "buat keputusan",
      "keputusan", "tingkah laku", "tabiat",

      "我喜欢", "我比较喜欢", "我通常", "我常常", "我经常", "我总是",
      "一个人", "自己一个人", "朋友", "团队", "小组", "人群", "社交",
      "和别人说话", "计划", "规划", "时间表", "有条理", "有组织",
      "逻辑", "事实", "感受", "在意别人的感受", "创意", "想法",
      "想象", "可能性", "未来", "做决定", "决定", "行为", "习惯"
    ];

    const hasWeakBackground = weakBackgroundPatterns.some((p) => p.test(raw));
    const hasPersonalityClue = personalityKeywords.some((k) => t.includes(k.toLowerCase()) || raw.includes(k));

    if (hasWeakBackground && !hasPersonalityClue) {
      return { valid: false, type: "background_only", message: msg("background_only") };
    }

    if (hasPersonalityClue) {
      return { valid: true, type: "personality_related", message: "" };
    }

    return { valid: false, type: "insufficient", message: msg("insufficient") };
  }

  // ---------- UI helpers ----------
  function setBadge(text, isRecording = false) {
    if (!recordBadge) return;
    recordBadge.textContent = text || "";
    recordBadge.classList.toggle("recording", !!isRecording);
  }

  function setHint(text) {
    if (!voiceHint) return;
    voiceHint.textContent = text || "";
  }

  function setDetectedLang(code) {
    detectedLang = normalizeDetectedLang(code || "");
    if (detectedLangEl) {
      detectedLangEl.textContent = detectedLang ? detectedLang.toUpperCase() : "-";
    }
    if (detectedLangHidden) {
      detectedLangHidden.value = detectedLang;
    }
  }

  function setWarning(text) {
    if (!transcribeWarningEl) return;
    const message = (text || "").trim();

    if (message) {
      transcribeWarningEl.textContent = message;
      transcribeWarningEl.classList.add("show");
    } else {
      transcribeWarningEl.textContent = "";
      transcribeWarningEl.classList.remove("show");
    }
  }

  function setTranscriptLocked(locked) {
    if (transcriptBox) transcriptBox.readOnly = locked;
    if (transcriptEnBox) transcriptEnBox.readOnly = locked;
  }

  function formatTime(s) {
    const mm = String(Math.floor(s / 60)).padStart(2, "0");
    const ss = String(s % 60).padStart(2, "0");
    return `${mm}:${ss}`;
  }

  function startTimer() {
    seconds = 0;
    if (timerText) timerText.textContent = "00:00";
    timer = setInterval(() => {
      seconds += 1;
      if (timerText) timerText.textContent = formatTime(seconds);
    }, 1000);
  }

  function stopTimer() {
    if (timer) clearInterval(timer);
    timer = null;
  }

  // ---------- Enable/Disable logic ----------
  function lockAll() {
    btnStart.disabled = true;
    btnStop.disabled = true;
    if (btnUploadFile) btnUploadFile.disabled = true;
    if (audioFile) audioFile.disabled = true;
    if (voiceLang) voiceLang.disabled = true;
    btnTranscribe.disabled = true;
    btnSubmit.disabled = true;
  }

  function enableBaseControls() {
    btnStart.disabled = false;
    btnStop.disabled = true;
    btnTranscribe.disabled = true;

    if (voiceLang) voiceLang.disabled = false;
    if (btnUploadFile) btnUploadFile.disabled = false;
    if (audioFile) audioFile.disabled = false;
  }

  function setMode(newMode) {
    mode = newMode;

    if (mode === "record") {
      if (btnUploadFile) btnUploadFile.disabled = true;
      if (audioFile) audioFile.disabled = true;
      if (voiceLang) voiceLang.disabled = true;
    } else if (mode === "upload") {
      btnStart.disabled = true;
      btnStop.disabled = true;
      if (voiceLang) voiceLang.disabled = false;
    }
  }

  function resetAudioState(clearSelectedFile = false) {
    lastAudioBlob = null;
    uploadedFilename = null;
    recordedFilename = null;
    chunks = [];

    if (clearSelectedFile && audioFile) audioFile.value = "";
    if (clearSelectedFile && fileNameText) {
      fileNameText.textContent = window.I18N_NO_FILE_CHOSEN || "No file chosen";
    }
  }

  function resetTranscriptUI() {
    transcriptBox.value = "";
    if (transcriptEnBox) transcriptEnBox.value = "";
    transcriptHidden.value = "";
    setDetectedLang("");
    setWarning("");
    btnSubmit.disabled = true;
    setTranscriptLocked(false);
  }

  function applyValidation(finalText, serverWarning = "") {
    const validation = validatePersonalityContent(finalText);
    transcriptHidden.value = finalText || "";

    if (!validation.valid) {
      btnSubmit.disabled = true;
      setWarning(validation.message);
      setBadge(msg("validation_failed_badge"), false);
      setHint(msg("invalid_more"));
      setTranscriptLocked(false);
      return false;
    }

    btnSubmit.disabled = false;
    setWarning(serverWarning || "");
    setBadge(msg("ready_badge"), false);
    setHint(msg("valid_ready"));
    setTranscriptLocked(false);
    return true;
  }

  // ---------- Init ----------
  lockAll();
  enableBaseControls();
  setBadge(msg("idle_badge"), false);
  setHint(window.I18N_VOICE_SELECT_LANG_HINT || msg("select_lang_hint"));
  setDetectedLang("");
  setWarning("");
  setTranscriptLocked(false);

  if (audioFile) {
    audioFile.addEventListener("change", () => {
      if (audioFile.files && audioFile.files.length > 0) {
        if (fileNameText) fileNameText.textContent = audioFile.files[0].name;
      } else {
        if (fileNameText) fileNameText.textContent = window.I18N_NO_FILE_CHOSEN || "No file chosen";
      }
    });
  }

  // ---------- Upload file flow ----------
  if (btnUploadFile && audioFile) {
    btnUploadFile.addEventListener("click", async () => {
      setMode("upload");

      if (!audioFile.files || audioFile.files.length === 0) {
        alert(msg("choose_file_first"));
        return;
      }

      // clear recorded session when switching to upload mode
      stopTimer();
      if (timerText) timerText.textContent = "00:00";
      lastAudioBlob = null;
      recordedFilename = null;
      chunks = [];
      resetTranscriptUI();

      const file = audioFile.files[0];

      try {
        setBadge(msg("uploading_badge"), false);
        setHint(msg("uploading"));

        const fd = new FormData();
        fd.append("audio", file);

        const res = await fetch(window.VOICE_UPLOAD_URL, {
          method: "POST",
          body: fd
        });

        const data = await res.json();

        if (!res.ok) {
          alert(data.error || msg("upload_failed"));
          setBadge(msg("idle_badge"), false);
          setHint(msg("upload_failed"));
          enableBaseControls();
          return;
        }

        uploadedFilename = data.filename;
        btnTranscribe.disabled = false;

        setBadge(msg("uploaded_badge"), false);
        setHint(msg("uploaded"));
      } catch (err) {
        console.error(err);
        alert(msg("upload_error") + ": " + err.message);
        setBadge(msg("idle_badge"), false);
        setHint(msg("upload_error"));
        enableBaseControls();
      }
    });
  }

  // ---------- Record flow ----------
  btnStart.addEventListener("click", async () => {
    setMode("record");
    resetAudioState(true);
    resetTranscriptUI();

    if (btnUploadFile) btnUploadFile.disabled = true;
    if (audioFile) audioFile.disabled = true;

    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      mediaRecorder = new MediaRecorder(stream);
      chunks = [];

      mediaRecorder.ondataavailable = (e) => {
        if (e.data && e.data.size > 0) chunks.push(e.data);
      };

      mediaRecorder.onstop = () => {
        const type = mediaRecorder.mimeType || "audio/webm";
        lastAudioBlob = new Blob(chunks, { type });

        if (stream) {
          stream.getTracks().forEach((t) => t.stop());
          stream = null;
        }

        setBadge(msg("recorded_badge"), false);
        setHint(msg("recording_saved"));

        enableBaseControls();
        btnTranscribe.disabled = !(lastAudioBlob && lastAudioBlob.size > 0);
      };

      mediaRecorder.start();
      setBadge(msg("recording_badge"), true);
      setHint(msg("recording_hint"));
      startTimer();

      btnStart.disabled = true;
      btnStop.disabled = false;
      btnTranscribe.disabled = true;
      btnSubmit.disabled = true;
    } catch (err) {
      console.error(err);
      alert(msg("mic_blocked"));
      setBadge(msg("idle_badge"), false);
      setHint(msg("mic_blocked"));
      enableBaseControls();
    }
  });

  btnStop.addEventListener("click", () => {
    if (!mediaRecorder) return;

    try {
      mediaRecorder.stop();
    } catch (e) {
      console.error(e);
    }

    stopTimer();
    btnStop.disabled = true;
  });

  async function uploadRecordedBlob(blob) {
    const ext = blob.type && blob.type.includes("ogg") ? "ogg" : "webm";
    const filename = `recording_${Date.now()}.${ext}`;

    const fd = new FormData();
    fd.append("audio", blob, filename);

    const res = await fetch(window.VOICE_UPLOAD_URL, {
      method: "POST",
      body: fd
    });

    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "Upload failed");
    return data.filename;
  }

  // ---------- Transcribe flow ----------
  btnTranscribe.addEventListener("click", async () => {
    resetTranscriptUI();

    try {
      setBadge(msg("transcribing_badge"), false);
      setHint(msg("transcribing"));

      let filename = null;

      if (mode === "record") {
        if (!lastAudioBlob || lastAudioBlob.size === 0) {
          setBadge(msg("idle_badge"), false);
          enableBaseControls();
          return;
        }

        recordedFilename = await uploadRecordedBlob(lastAudioBlob);
        filename = recordedFilename;
      } else if (mode === "upload") {
        filename = uploadedFilename;
      }

      if (!filename) {
        throw new Error("No uploaded audio filename available");
      }

      const selectedLang = getSelectedLang();

      const res = await fetch(window.VOICE_TRANSCRIBE_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          filename,
          lang: selectedLang
        })
      });

      const data = await res.json();

      if (!res.ok) {
        const detected = normalizeDetectedLang(data.detected_lang || "");
        setDetectedLang(detected);

        transcriptBox.value = data.transcript || "";
        if (transcriptEnBox) transcriptEnBox.value = data.transcript_en || "";

        transcriptHidden.value = "";
        btnSubmit.disabled = true;

        setWarning(data.error || msg("transcribe_failed"));
        setBadge(msg("validation_failed_badge"), false);
        setHint("");

        if (data.mismatch) {
          setTranscriptLocked(true);
        } else {
          setTranscriptLocked(false);
        }

        enableBaseControls();
        btnTranscribe.disabled = false;
        return;
      }

      const originalText = (data.transcript || "").trim();
      const englishText = (data.transcript_en || "").trim();
      const rawDetected = data.detected_lang || selectedLang;
      const normalizedDetected = normalizeDetectedLang(rawDetected);

      setDetectedLang(normalizedDetected);
      transcriptBox.value = originalText;
      if (transcriptEnBox) transcriptEnBox.value = englishText || originalText || "";
      setTranscriptLocked(false);

      if (!originalText) {
        transcriptHidden.value = "";
        btnSubmit.disabled = true;
        setWarning(msg("empty"));
        setBadge(msg("validation_failed_badge"), false);
        setHint(msg("invalid_more"));
        setTranscriptLocked(false);
        enableBaseControls();
        btnTranscribe.disabled = false;
        return;
      }

      if (!isSupportedLang(normalizedDetected)) {
        transcriptHidden.value = "";
        btnSubmit.disabled = true;
        setWarning(msg("unsupported", rawDetected || "UNKNOWN"));
        setBadge(msg("validation_failed_badge"), false);
        setHint(msg("invalid_more"));
        setTranscriptLocked(false);
        enableBaseControls();
        btnTranscribe.disabled = false;
        return;
      }

      const finalText = (englishText || originalText || "").trim();
      applyValidation(finalText, (data.warning || "").trim());

      setBadge(msg("uploaded_badge"), false);
      setHint(msg("transcribed"));
      enableBaseControls();
      btnTranscribe.disabled = false;
    } catch (err) {
      console.error(err);
      alert(msg("transcribe_failed") + ": " + err.message);
      setBadge(msg("idle_badge"), false);
      setHint(msg("transcribe_failed"));
      enableBaseControls();
    }
  });

  // ---------- Live re-validate when original transcript is edited ----------
  transcriptBox.addEventListener("input", () => {
    const text = (transcriptBox.value || "").trim();

    if (translateDebounce) clearTimeout(translateDebounce);

    translateDebounce = setTimeout(async () => {
      setWarning("");

      if (!text) {
        if (transcriptEnBox) transcriptEnBox.value = "";
        transcriptHidden.value = "";
        btnSubmit.disabled = true;
        return;
      }

      if (transcriptBox.readOnly || (transcriptEnBox && transcriptEnBox.readOnly)) {
        return;
      }

      if (!isSupportedLang(detectedLang || getSelectedLang())) {
        if (transcriptEnBox) transcriptEnBox.value = "";
        transcriptHidden.value = "";
        btnSubmit.disabled = true;
        setWarning(msg("unsupported", detectedLang || "UNKNOWN"));
        return;
      }

      if (!window.VOICE_TRANSLATE_TEXT_URL) {
        if (transcriptEnBox) transcriptEnBox.value = text;
        applyValidation(text, "");
        return;
      }

      try {
        const res = await fetch(window.VOICE_TRANSLATE_TEXT_URL, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            text,
            source_lang: detectedLang || getSelectedLang() || null
          })
        });

        const data = await res.json();
        if (!res.ok) throw new Error(data.error || "Translate failed");

        const en = (data.translated_en || "").trim();
        if (transcriptEnBox) transcriptEnBox.value = en || text;

        const finalText = (en || text || "").trim();
        applyValidation(finalText, "");
      } catch (e) {
        console.warn("Translate endpoint failed, using original text.", e);
        if (transcriptEnBox) transcriptEnBox.value = text;
        applyValidation(text, "");
      }
    }, 500);
  });

  // ---------- Re-validate if English transcript is edited directly ----------
  if (transcriptEnBox) {
    transcriptEnBox.addEventListener("input", () => {
      if (transcriptEnBox.readOnly) return;
      const finalText = (transcriptEnBox.value || "").trim();
      applyValidation(finalText, "");
    });
  }

  voiceLang?.addEventListener("change", () => {
    resetTranscriptUI();
    setBadge(msg("idle_badge"), false);
    setHint(msg("language_changed"));
  });
})();