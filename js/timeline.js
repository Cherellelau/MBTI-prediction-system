// static/js/timeline.js

(() => {
  // ---------- Helpers ----------
  function buildUrl(params) {
    const url = new URL(window.location.href);

    Object.keys(params).forEach((k) => {
      const v = params[k];
      if (v === "" || v === null || v === undefined) {
        url.searchParams.delete(k);
      } else {
        url.searchParams.set(k, v);
      }
    });

    return url.toString();
  }

  function isValidMBTI(code) {
    if (!code || code.length !== 4) return false;
    const c = code.toUpperCase();
    return (
      "EI".includes(c[0]) &&
      "SN".includes(c[1]) &&
      "TF".includes(c[2]) &&
      "JP".includes(c[3])
    );
  }

  // ---------- i18n text (fallback EN + override from page) ----------
  const I18N = {
    alert_invalid_range: "Start date cannot be after end date.",
    alert_invalid_mbti: "Please enter a valid MBTI code (e.g., INTJ, ENFP).",
    ...(window.TIMELINE_I18N || {})
  };

  const btnToggleGuide = document.getElementById("btnToggleGuide");
  const guideBody = document.getElementById("guideBody");
  const guideI18n =
    window.TIMELINE_I18N && window.TIMELINE_I18N.guide
      ? window.TIMELINE_I18N.guide
      : {
        hide: "Hide Guide",
        show: "Show Guide"
      };

  btnToggleGuide?.addEventListener("click", () => {
    if (!guideBody) return;

    const isHidden = guideBody.style.display === "none";

    if (isHidden) {
      guideBody.style.display = "";
      btnToggleGuide.textContent = guideI18n.hide;
    } else {
      guideBody.style.display = "none";
      btnToggleGuide.textContent = guideI18n.show;
    }
  });

  // ---------- Main DOM logic ----------
  document.addEventListener("DOMContentLoaded", () => {
    // 1) Activate preset chip
    const preset = window.TIMELINE_PRESET || "all";
    document.querySelectorAll(".tl-chip").forEach((btn) => {
      if (btn.dataset.preset === preset) btn.classList.add("active");
    });

    // 2) Preset chip click
    document.querySelectorAll(".tl-chip").forEach((btn) => {
      btn.addEventListener("click", () => {
        const p = btn.dataset.preset;
        window.location.href = buildUrl({ preset: p, start: "", end: "" });
      });
    });

    // 3) Custom range apply/clear
    const btnApply = document.getElementById("btnApplyRange");
    const btnClear = document.getElementById("btnClearRange");
    const startDate = document.getElementById("startDate");
    const endDate = document.getElementById("endDate");

    btnApply?.addEventListener("click", () => {
      const s = startDate?.value || "";
      const e = endDate?.value || "";

      if (!s && !e) return;
      if (s && e && s > e) {
        alert(I18N.alert_invalid_range);
        return;
      }

      window.location.href = buildUrl({ preset: "custom", start: s, end: e });
    });

    btnClear?.addEventListener("click", () => {
      if (startDate) startDate.value = "";
      if (endDate) endDate.value = "";
      window.location.href = buildUrl({ preset: "all", start: "", end: "" });
    });

    // 4) Search MBTI
    const qInput = document.getElementById("qInput");
    const btnSearch = document.getElementById("btnSearch");

    qInput?.addEventListener("input", () => {
      qInput.value = qInput.value
        .toUpperCase()
        .replace(/[^EISNTFJP]/g, "")
        .slice(0, 4);
    });

    btnSearch?.addEventListener("click", () => {
      const q = (qInput?.value || "").trim().toUpperCase();

      if (q && !isValidMBTI(q)) {
        alert(I18N.alert_invalid_mbti);
        qInput?.focus();
        return;
      }

      window.location.href = buildUrl({ q });
    });

    qInput?.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        btnSearch?.click();
      }
    });
  });
})();