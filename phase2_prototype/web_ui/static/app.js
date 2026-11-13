(() => {
  const form = document.querySelector("#analysis-form");
  if (!form) return;

  const presets = {
    signal: { line: 0.60, axis: "y", zone: [0.45, 0.05, 1.00, 1.00], title: "Signalized junction", note: "A fixed-camera clip with seven manually reviewed crossings.", badge: "REAL FOOTAGE", url: "https://commons.wikimedia.org/wiki/File:Temporary_traffic_signal_at_Colonel_By_Drive.webm", poster: "signal_poster.jpg" },
    overhead: { line: 0.55, axis: "y", zone: [0.02, 0.05, 0.98, 0.94], title: "Overhead road", note: "An elevated real clip with four manually reviewed crossings.", badge: "REAL FOOTAGE", url: "https://github.com/intel-iot-devkit/sample-videos", poster: "poster_overhead.jpg" },
    cuttack: { line: 0.50, axis: "x", zone: [0.05, 0.25, 0.95, 0.95], title: "Link Road, Cuttack", note: "30-second fixed-camera India scene. Model event totals are not manually audited.", badge: "INDIA / REAL FOOTAGE", url: "https://commons.wikimedia.org/wiki/File:Moving_vehicles_in_Link_road,_Cuttack,_Odisha.webm", poster: "poster_cuttack.jpg" },
    bengaluru: { line: 0.65, axis: "y", zone: [0.05, 0.40, 0.60, 0.95], title: "Bengaluru at night", note: "20-second fixed-camera congestion scene from 2025. Model event totals are not manually audited.", badge: "INDIA / REAL FOOTAGE", url: "https://commons.wikimedia.org/wiki/File:Ramana_Maharshi_Road,_Bangalore_(2025)_02.webm", poster: "poster_bengaluru.jpg" },
    pothole: { line: 0.65, axis: "y", zone: [0.10, 0.45, 0.72, 0.95], title: "Road defect reference", note: "Real public footage near Kumasi. Location is approximate; traffic counts are unvalidated.", badge: "PUBLIC REFERENCE", url: "https://commons.wikimedia.org/wiki/File:Cars_Moving_into_pothole.webm", poster: "poster_pothole.jpg" },
    stop: { line: 0.55, axis: "y", zone: [0.02, 0.05, 0.98, 0.94], title: "Synthetic stop test", note: "Frozen frame used only to exercise the stop rule.", badge: "SYNTHETIC TEST", url: "https://github.com/intel-iot-devkit/sample-videos", poster: "poster_stop.jpg" }
  };
  const sourceInputs = [...form.querySelectorAll('input[name="source"]')];
  const uploadWrap = document.querySelector("#upload-wrap");
  const preview = document.querySelector("#source-preview");
  const previewSource = preview.querySelector("source");
  const previewTitle = document.querySelector("#preview-title");
  const previewCaption = document.querySelector("#preview-caption");
  const previewSourceLink = document.querySelector("#preview-source-link");
  const badge = document.querySelector(".preview-panel .badge");
  const line = document.querySelector("#line-at");
  const lineValue = document.querySelector("#line-value");
  const progress = document.querySelector("#job-progress");
  const progressTitle = document.querySelector("#progress-title");
  const progressFill = document.querySelector("#progress-fill");
  const progressPercent = document.querySelector("#progress-percent");
  const progressDetail = document.querySelector("#progress-detail");
  const errorBox = document.querySelector("#analysis-error");
  const button = document.querySelector("#analyze-button");
  let uploadUrl;

  function selectedSource() {
    return sourceInputs.find(input => input.checked)?.value || "signal";
  }
  function setRangeLabel() {
    lineValue.textContent = Math.round(Number(line.value) * 100) + "%";
  }
  function updateSource() {
    const key = selectedSource();
    uploadWrap.hidden = key !== "upload";
    if (key === "upload") {
      previewTitle.textContent = "Your footage";
      previewCaption.textContent = "Choose a local file to preview it here. The model runs on this computer.";
      badge.textContent = "LOCAL UPLOAD";
      previewSourceLink.hidden = true;
      preview.removeAttribute("poster");
      if (!uploadUrl) {
        preview.removeAttribute("src");
        previewSource.removeAttribute("src");
        preview.load();
      }
      return;
    }
    if (uploadUrl) { URL.revokeObjectURL(uploadUrl); uploadUrl = null; }
    const preset = presets[key];
    if (!preset) return;
    previewTitle.textContent = preset.title;
    previewCaption.textContent = preset.note;
    badge.textContent = preset.badge;
    previewSourceLink.hidden = false;
    previewSourceLink.href = preset.url;
    preview.poster = "/static/" + preset.poster;
    previewSource.src = "/samples/" + encodeURIComponent(key);
    preview.load();
    line.value = preset.line.toFixed(2);
    form.elements.axis.value = preset.axis;
    ["zone_x1", "zone_y1", "zone_x2", "zone_y2"].forEach((name, i) => {
      form.elements[name].value = preset.zone[i].toFixed(2);
    });
    form.elements.confidence.value = key === "stop" ? "0.10" : "0.25";
    setRangeLabel();
  }
  sourceInputs.forEach(input => input.addEventListener("change", updateSource));
  line.addEventListener("input", setRangeLabel);
  document.querySelector("#video-upload").addEventListener("change", event => {
    if (uploadUrl) URL.revokeObjectURL(uploadUrl);
    const file = event.target.files?.[0];
    if (!file) return;
    uploadUrl = URL.createObjectURL(file);
    previewSource.src = uploadUrl;
    preview.load();
    previewCaption.textContent = file.name + " · local upload";
  });
  updateSource();

  function showError(message) {
    errorBox.hidden = false;
    errorBox.textContent = message;
    progress.hidden = true;
    button.disabled = false;
    button.textContent = "Run analysis ↗";
  }
  async function waitForJob(id) {
    try {
      const response = await fetch("/api/jobs/" + encodeURIComponent(id));
      if (!response.ok) throw new Error("Could not read analysis status.");
      const job = await response.json();
      if (job.status === "error") { showError(job.error || "Analysis failed."); return; }
      if (job.status === "complete") {
        progressTitle.textContent = "Analysis complete";
        progressPercent.textContent = "100%";
        progressFill.style.width = "100%";
        window.location.assign(job.result_url);
        return;
      }
      const percent = job.total ? Math.min(99, Math.round(job.done / job.total * 100)) : 0;
      progressTitle.textContent = job.status === "queued" ? "Waiting for the model…" : "Tracking vehicles…";
      progressPercent.textContent = percent + "%";
      progressFill.style.width = percent + "%";
      progressDetail.textContent = job.done ? job.done + " of " + (job.total || "?") + " frames processed" : "Loading model and tracker";
      window.setTimeout(() => waitForJob(id), 650);
    } catch (error) { showError(error.message || "Could not read analysis status."); }
  }
  form.addEventListener("submit", async event => {
    event.preventDefault();
    errorBox.hidden = true;
    progress.hidden = false;
    progressTitle.textContent = "Preparing analysis…";
    progressPercent.textContent = "0%";
    progressFill.style.width = "0%";
    progressDetail.textContent = "Saving source and loading the Python model";
    button.disabled = true;
    button.textContent = "Analyzing…";
    try {
      const response = await fetch("/api/jobs", { method: "POST", body: new FormData(form) });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || "Could not start analysis.");
      waitForJob(result.job_id);
    } catch (error) { showError(error.message || "Could not start analysis."); }
  });
})();
