const $ = (id) => document.getElementById(id);

/**
 * Origen del API FastAPI (puerto 8765).
 * Si la página no se sirve desde ese puerto (vista previa del IDE, otro host),
 * todas las peticiones deben ir explícitamente a http://127.0.0.1:8765.
 * El sondeo por fetch fallaba a veces y dejaba API_BASE vacío → 404 en el origen equivocado.
 */
let API_BASE = "";

const apiBaseReady = (async () => {
  const meta = document.querySelector('meta[name="career-ops-api"]');
  if (meta && meta.content && meta.content.trim()) {
    API_BASE = meta.content.trim().replace(/\/$/, "");
    return;
  }
  const { protocol, hostname, port } = window.location;
  if (protocol === "file:") {
    API_BASE = "http://127.0.0.1:8765";
    return;
  }
  const p = String(port || "");
  const mismoServidorCareerOps =
    (hostname === "127.0.0.1" || hostname === "localhost") && p === "8765";
  if (mismoServidorCareerOps) {
    API_BASE = "";
    return;
  }
  if (hostname === "127.0.0.1" || hostname === "localhost") {
    API_BASE = `http://${hostname}:8765`;
    return;
  }
  API_BASE = "http://127.0.0.1:8765";
})();

function apiUrl(path) {
  return API_BASE ? `${API_BASE}${path}` : path;
}

async function api(path, opts = {}) {
  await apiBaseReady;
  const headers = { ...opts.headers };
  if (opts.body != null && !(opts.body instanceof FormData)) {
    headers["Content-Type"] = headers["Content-Type"] || "application/json";
  }
  const r = await fetch(apiUrl(path), {
    ...opts,
    headers,
  });
  if (!r.ok) {
    const t = await r.text();
    throw new Error(t || r.statusText);
  }
  const ct = r.headers.get("content-type");
  if (ct && ct.includes("application/json")) return r.json();
  return r.text();
}

function setStatus(el, msg, ok = true) {
  el.textContent = msg;
  el.style.color = ok ? "var(--ok, #3fb950)" : "#f85149";
}

$("pdf-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const input = e.target.querySelector('input[type="file"]');
  const f = input.files[0];
  const st = $("upload-status");
  if (!f) {
    setStatus(st, "Elija un archivo PDF.", false);
    return;
  }
  const fd = new FormData();
  fd.append("file", f);
  try {
    setStatus(st, "Procesando…", true);
    const data = await api("/api/upload-pdf", { method: "POST", body: fd });
    setStatus(
      st,
      `PDF leído (${data.chars} caracteres). Harvard: ${data.harvard_source || "—"}.`,
      true
    );
    $("harvard-out").textContent = JSON.stringify(data.harvard, null, 2);
    if (data.preview) $("cv-md").value = data.preview.slice(0, 8000);
  } catch (err) {
    setStatus(st, err.message, false);
  }
});

$("save-md").addEventListener("click", async () => {
  const st = $("upload-status");
  try {
    const markdown = $("cv-md").value;
    const data = await api("/api/set-cv-markdown", {
      method: "POST",
      body: JSON.stringify({ markdown }),
    });
    $("harvard-out").textContent = JSON.stringify(data.harvard, null, 2);
    setStatus(st, `Markdown guardado (fuente Harvard: ${data.harvard_source || "—"}).`, true);
  } catch (err) {
    setStatus(st, err.message, false);
  }
});

let jobsCache = [];

async function loadCvIntoTextarea() {
  try {
    const cv = await api("/api/cv");
    if (cv.markdown && !$("cv-md").value.trim()) {
      $("cv-md").value = cv.markdown.slice(0, 120000);
    }
    if (cv.harvard) {
      $("harvard-out").textContent = JSON.stringify(cv.harvard, null, 2);
    }
  } catch (_) {
    /* sin cv.md */
  }
}

$("load-jobs").addEventListener("click", async () => {
  const st = $("jobs-status");
  const meta = $("jobs-meta");
  const list = $("jobs-list");
  try {
    setStatus(st, "Consultando portales…", true);
    meta.textContent = "";
    const ignoreCv = $("jobs-ignore-cv")?.checked;
    const params = new URLSearchParams();
    if (ignoreCv) params.set("use_cv_profile", "false");
    const areaKeys = [];
    if ($("job-profile-management")?.checked) areaKeys.push("management");
    if ($("job-profile-tech")?.checked) areaKeys.push("tech");
    if ($("job-profile-legal")?.checked) areaKeys.push("legal");
    if ($("job-profile-education")?.checked) areaKeys.push("education");
    if (areaKeys.length) params.set("profiles", areaKeys.join(","));
    const qs = params.toString();
    const data = await api(`/api/jobs${qs ? `?${qs}` : ""}`);
    jobsCache = data.jobs || [];
    let line = data.portals_file
      ? `Fuente: ${data.portals_file} · ${jobsCache.length} ofertas`
      : `${jobsCache.length} ofertas`;
    if (data.jobs_before_cv_filter != null && data.jobs_cv_filter === "applied") {
      line += ` (tras filtro CV: ${data.jobs_before_cv_filter} → ${jobsCache.length})`;
    }
    if (data.jobs_cv_filter === "rolled_back_no_overlap") {
      line += ` (filtro CV: ${data.jobs_before_cv_filter} → 0 coincidencias; mostrando ${jobsCache.length} ofertas del YAML)`;
    }
    if (data.jobs_cv_filter === "skipped_weak_cv_signals") {
      line += " · CV: pocas palabras clave; mostrando solo filtro YAML";
    }
    if (data.area_profiles && data.area_profiles.labels && data.area_profiles.labels.length) {
      const al = data.area_profiles.labels.map((x) => x.label).join("; ");
      line += ` · Ámbitos: ${al}`;
    }
    if (data.errors && data.errors.length) {
      line += ` · avisos API: ${data.errors.length}`;
    }
    meta.textContent = line;
    const hintEl = $("jobs-filter-hint");
    if (hintEl) {
      hintEl.textContent = data.filter_explanation
        ? data.filter_explanation.slice(0, 400)
        : "";
    }
    list.innerHTML = "";
    jobsCache.forEach((j) => {
      const row = document.createElement("div");
      row.className = "job-row";
      row.innerHTML = `
        <input type="checkbox" data-id="${j.id}" aria-label="Seleccionar ${j.title}" />
        <div>
          <div class="job-title">${escapeHtml(j.title)}</div>
          <div class="muted">${escapeHtml(j.company)} · ${escapeHtml(j.location || "")}</div>
          <a href="${escapeAttr(j.url)}" target="_blank" rel="noopener">Ver oferta</a>
        </div>
        <span class="badge">${escapeHtml(j.source || "")}</span>
      `;
      list.appendChild(row);
    });
    setStatus(st, "Listo.", true);
  } catch (err) {
    setStatus(st, err.message, false);
  }
});

function escapeHtml(s) {
  const d = document.createElement("div");
  d.textContent = s ?? "";
  return d.innerHTML;
}

function escapeAttr(s) {
  return String(s ?? "")
    .replace(/&/g, "&amp;")
    .replace(/"/g, "&quot;")
    .replace(/</g, "&lt;");
}

$("apply-selected").addEventListener("click", async () => {
  const st = $("jobs-status");
  const ids = [...document.querySelectorAll(".job-row input:checked")].map(
    (el) => el.getAttribute("data-id")
  );
  if (!ids.length) {
    setStatus(st, "Marque al menos una oferta.", false);
    return;
  }
  try {
    setStatus(st, "Generando CVs a medida…", true);
    const res = await api("/api/select-jobs", {
      method: "POST",
      body: JSON.stringify({ job_ids: ids }),
    });
    setStatus(
      st,
      `Generados: ${res.generated}. Total en seguimiento: ${res.applications.length}.`,
      true
    );
    renderApps(res.applications);
  } catch (err) {
    setStatus(st, err.message, false);
  }
});

function renderApps(apps) {
  const ul = $("apps-list");
  ul.innerHTML = "";
  (apps || []).forEach((a) => {
    const li = document.createElement("li");
    li.innerHTML = `
      <strong>${escapeHtml(a.title)}</strong>
      <span class="muted">${escapeHtml(a.company)}</span>
      <span class="badge">${escapeHtml(a.status)}</span>
      <a href="${escapeAttr(a.url)}" target="_blank" rel="noopener">Oferta</a>
      <code>${escapeHtml(a.tailored_cv_path || "")}</code>
      <button type="button" class="secondary mark-applied" data-id="${escapeAttr(a.id)}">Marcar enviada</button>
    `;
    ul.appendChild(li);
  });
  ul.querySelectorAll(".mark-applied").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const id = btn.getAttribute("data-id");
      try {
        await api("/api/mark-applied", {
          method: "POST",
          body: JSON.stringify({ job_id: id }),
        });
        const fresh = await api("/api/applications");
        renderApps(fresh);
      } catch (err) {
        alert(err.message);
      }
    });
  });
}

async function refreshLlmBanner() {
  const el = $("llm-banner");
  try {
    const s = await api("/api/llm-status");
    if (s.openai_configured) {
      el.textContent = `OpenAI listo (modelo: ${s.model}).`;
      el.classList.add("ok");
    } else {
      el.textContent =
        "OpenAI no configurado: defina OPENAI_API_KEY (véase webapp/.env.example). Se usa parseo heurístico.";
      el.classList.remove("ok");
    }
  } catch (_) {
    el.textContent = "";
  }
}

$("reparse-llm").addEventListener("click", async () => {
  const st = $("upload-status");
  try {
    setStatus(st, "Reparseando con OpenAI…", true);
    const data = await api("/api/reparse-harvard", {
      method: "POST",
      body: JSON.stringify({ use_openai: true }),
    });
    $("harvard-out").textContent = JSON.stringify(data.harvard, null, 2);
    setStatus(st, `Fuente: ${data.harvard_source}`, true);
  } catch (err) {
    setStatus(st, err.message, false);
  }
});

$("reparse-heur").addEventListener("click", async () => {
  const st = $("upload-status");
  try {
    setStatus(st, "Reparseando (heurística)…", true);
    const data = await api("/api/reparse-harvard", {
      method: "POST",
      body: JSON.stringify({ use_openai: false }),
    });
    $("harvard-out").textContent = JSON.stringify(data.harvard, null, 2);
    setStatus(st, `Fuente: ${data.harvard_source}`, true);
  } catch (err) {
    setStatus(st, err.message, false);
  }
});

(async function init() {
  try {
    await api("/api/health");
  } catch (_) {
    const el = $("llm-banner");
    if (el) {
      el.textContent =
        "No se alcanza el API. Ejecute «npm run webapp» y abra http://127.0.0.1:8765 (no solo la vista previa del editor).";
      el.classList.remove("ok");
    }
  }
  await refreshLlmBanner();
  await loadCvIntoTextarea();
  try {
    const apps = await api("/api/applications");
    renderApps(apps);
  } catch (_) {}
})();
