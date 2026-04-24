"""
Servidor web career-ops: PDF → estructura Harvard, listado de ofertas, selección y CVs a medida.

Las solicitudes reales en portales externos no se envían automáticamente (ética career-ops).
Se generan archivos y se registran como "preparadas"; el envío es manual en el portal.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from pypdf import PdfReader

from cv_profile_keywords import (
    augment_keywords_for_jobs,
    derive_profile_keywords,
    job_matches_profile,
)
from harvard_structure import harvard_to_markdown, text_to_harvard

from openai_enrich import (
    harvard_from_text_openai,
    openai_configured,
    openai_model_name,
    resolve_harvard,
)

ROOT = Path(__file__).resolve().parent.parent
DATA_ROOT = Path(os.getenv("DATA_ROOT", str(ROOT))).resolve()
STATE_PATH = DATA_ROOT / "data" / "webapp-state.json"
OUTPUT_DIR = DATA_ROOT / "output" / "webapp-cvs"
STATIC_DIR = Path(__file__).resolve().parent / "static"


def _load_dotenv_at_startup() -> None:
    """Asegura OPENAI_* desde .env. override=True: el archivo gana sobre variables vacías en el shell."""
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    for path in (ROOT / ".env", Path(__file__).resolve().parent / ".env"):
        if path.is_file():
            load_dotenv(path, override=True)


_load_dotenv_at_startup()

app = FastAPI(title="Career-Ops Web", version="0.1.0")

# La UI puede abrirse desde otro puerto (vista previa, Live Server). Sin CORS, /api/* devuelve 404 vía otro host.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _ensure_dirs() -> None:
    (DATA_ROOT / "data").mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def _load_state() -> dict:
    _ensure_dirs()
    if not STATE_PATH.exists():
        return {
            "cv_markdown": "",
            "harvard": None,
            "harvard_source": None,
            "last_pdf_text": "",
            "applications": [],
        }
    with open(STATE_PATH, encoding="utf-8") as f:
        return json.load(f)


def _save_state(state: dict) -> None:
    _ensure_dirs()
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


# Mínimo de términos extraídos del CV para cruzar con el título de la oferta (criterio base).
MIN_PROFILE_KEYWORDS_TO_FILTER = 6


def _sync_profile_keywords(state: dict) -> None:
    """Actualiza profile_keywords desde cv_markdown / last_pdf_text (heurística local, sin LLM)."""
    text = (state.get("cv_markdown") or state.get("last_pdf_text") or "").strip()
    if len(text) < 40:
        state["profile_keywords"] = []
        state["profile_keywords_meta"] = {
            "reason": "cv_muy_corto_o_vacío",
            "ready_to_filter": False,
        }
        return
    raw_kws = derive_profile_keywords(text)
    kws = augment_keywords_for_jobs(text, raw_kws)
    state["profile_keywords"] = kws
    state["profile_keywords_meta"] = {
        "count": len(kws),
        "derived_count": len(raw_kws),
        "ready_to_filter": len(raw_kws) >= MIN_PROFILE_KEYWORDS_TO_FILTER,
        "sample": kws[:15],
    }


def _extract_pdf_text(data: bytes) -> str:
    from io import BytesIO

    reader = PdfReader(BytesIO(data))
    parts: list[str] = []
    for page in reader.pages:
        t = page.extract_text() or ""
        parts.append(t)
    return "\n\n".join(parts).strip()


def _tailor_cv_markdown(base_md: str, job_title: str, company: str) -> str:
    """Ajusta el CV con un bloque objetivo y refuerzo de palabras clave del puesto."""
    header = (
        f"> **Candidatura:** {job_title} — {company}  \n"
        f"> Generado el {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}. "
        f"Revise y edite antes de enviar.\n\n"
    )
    # Refuerzo breve al inicio del documento si hay un resumen
    reinforced = base_md
    summary_match = re.search(
        r"(##\s*Professional Summary|##\s*Resumen|##\s*Summary)\s*\n+",
        reinforced,
        re.IGNORECASE,
    )
    if summary_match:
        insert_at = summary_match.end()
        extra = (
            f"*Alineación con el puesto:* interés explícito en **{job_title}** "
            f"en **{company}** (ajuste automático; personalice según la oferta).\n\n"
        )
        reinforced = reinforced[:insert_at] + extra + reinforced[insert_at:]
    return header + reinforced


class SelectJobsBody(BaseModel):
    job_ids: list[str] = Field(default_factory=list)


@app.get("/api/health")
def health():
    return {
        "ok": True,
        "root": str(ROOT),
        "data_root": str(DATA_ROOT),
        "openai_configured": openai_configured(),
        "openai_model": openai_model_name() if openai_configured() else None,
    }


@app.get("/api/llm-status")
def llm_status():
    """Estado de la integración OpenAI (sin exponer secretos)."""
    env_paths = [
        {"path": str(ROOT / ".env"), "exists": (ROOT / ".env").is_file()},
        {"path": str(Path(__file__).resolve().parent / ".env"), "exists": (Path(__file__).resolve().parent / ".env").is_file()},
    ]
    configured = openai_configured()
    if configured:
        hint = "OpenAI listo. Tras editar .env, reinicie el servidor (npm run webapp)."
    elif not any(p["exists"] for p in env_paths):
        hint = (
            "No existe ningún archivo .env. Ejecute: cp webapp/.env.example .env "
            "y edite .env con su clave; luego reinicie npm run webapp."
        )
    else:
        hint = (
            ".env existe pero OPENAI_API_KEY está vacía o no es válida. "
            "Revise el archivo y reinicie el servidor."
        )
    return {
        "openai_configured": configured,
        "model": openai_model_name() if configured else None,
        "env_files_checked": env_paths,
        "env_hint": hint,
    }


@app.get("/api/cv")
def get_cv():
    state = _load_state()
    md = state.get("cv_markdown") or ""
    cv_path = ROOT / "cv.md"
    if not md.strip() and cv_path.exists():
        md = cv_path.read_text(encoding="utf-8")
        state["cv_markdown"] = md
        harvard, src = resolve_harvard(md)
        state["harvard"] = harvard
        state["harvard_source"] = src
        _sync_profile_keywords(state)
        _save_state(state)
    return {
        "markdown": md,
        "harvard": state.get("harvard"),
        "harvard_source": state.get("harvard_source"),
        "profile_keywords_meta": state.get("profile_keywords_meta"),
    }


@app.post("/api/upload-pdf")
async def upload_pdf(file: UploadFile = File(...)):
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "Se requiere un archivo .pdf")
    data = await file.read()
    if len(data) > 15 * 1024 * 1024:
        raise HTTPException(400, "PDF demasiado grande (máx. 15 MB)")
    try:
        text = _extract_pdf_text(data)
    except Exception as e:
        raise HTTPException(400, f"No se pudo leer el PDF: {e}") from e
    state = _load_state()
    state["last_pdf_text"] = text
    # Usar texto extraído como base de cv_markdown si aún no hay MD manual
    if not state.get("cv_markdown"):
        state["cv_markdown"] = text
    harvard, harvard_source = resolve_harvard(text)
    state["harvard"] = harvard
    state["harvard_source"] = harvard_source
    _sync_profile_keywords(state)
    _save_state(state)
    return {
        "ok": True,
        "chars": len(text),
        "preview": text[:2000],
        "harvard": harvard,
        "harvard_source": harvard_source,
        "harvard_markdown": harvard_to_markdown(harvard),
        "profile_keywords_meta": state.get("profile_keywords_meta"),
    }


@app.post("/api/set-cv-markdown")
async def set_cv_markdown(body: dict):
    md = body.get("markdown") or ""
    if isinstance(md, str) and len(md) > 500_000:
        raise HTTPException(400, "Markdown demasiado largo")
    state = _load_state()
    state["cv_markdown"] = md
    harvard, src = resolve_harvard(md)
    state["harvard"] = harvard
    state["harvard_source"] = src
    _sync_profile_keywords(state)
    _save_state(state)
    return {
        "ok": True,
        "harvard": harvard,
        "harvard_source": src,
        "profile_keywords_meta": state.get("profile_keywords_meta"),
    }


@app.get("/api/harvard")
def get_harvard():
    state = _load_state()
    h = state.get("harvard")
    if not h:
        return {"ok": False, "message": "Suba un PDF o pegue markdown primero."}
    return {
        "ok": True,
        "harvard": h,
        "harvard_source": state.get("harvard_source"),
        "markdown": harvard_to_markdown(h),
    }


class ReparseBody(BaseModel):
    use_openai: bool = True


@app.post("/api/reparse-harvard")
def reparse_harvard(body: ReparseBody):
    """
    Vuelve a generar la estructura Harvard desde el CV guardado.
    Con OPENAI_API_KEY y use_openai=true usa el modelo; si no, heurística.
    """
    state = _load_state()
    text = (state.get("cv_markdown") or state.get("last_pdf_text") or "").strip()
    if not text:
        raise HTTPException(400, "No hay texto de CV. Suba un PDF o guarde markdown.")

    if body.use_openai:
        if not openai_configured():
            raise HTTPException(
                400,
                "OPENAI_API_KEY no configurada. Cree el archivo "
                f"{ROOT / '.env'} o {STATIC_DIR.parent / '.env'} con una línea "
                "OPENAI_API_KEY=sk-... (sin comillas), guarde y reinicie el servidor "
                '("npm run webapp"). Alternativa: botón «Solo heurística».',
            )
        try:
            harvard = harvard_from_text_openai(text)
            src = "openai"
        except Exception as e:
            raise HTTPException(502, f"Error OpenAI: {e!s}") from e
    else:
        harvard = text_to_harvard(text)
        src = "heuristic"

    state["harvard"] = harvard
    state["harvard_source"] = src
    _sync_profile_keywords(state)
    _save_state(state)
    return {
        "ok": True,
        "harvard": harvard,
        "harvard_source": src,
        "harvard_markdown": harvard_to_markdown(harvard),
        "profile_keywords_meta": state.get("profile_keywords_meta"),
    }


def _node_bin() -> str:
    return shutil.which("node") or "node"


def _run_scan_list(limit: int, profiles: Optional[str]) -> dict:
    """Ejecuta scan-list.mjs y devuelve el dict JSON (ofertas + metadatos)."""
    script = ROOT / "scan-list.mjs"
    if not script.exists():
        return {"ok": False, "jobs": [], "errors": [{"error": "scan-list.mjs no encontrado"}]}
    cmd = [_node_bin(), str(script), f"--limit={limit}"]
    ps = (profiles or "").strip()
    if ps:
        cmd.append(f"--profiles={ps}")
    proc = subprocess.run(
        cmd,
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=120,
    )
    out = proc.stdout.strip() or proc.stderr.strip()
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        return {
            "ok": False,
            "jobs": [],
            "errors": [{"error": "Salida inválida del scanner", "raw": out[:500]}],
        }


def _get_jobs_impl(
    limit: int,
    use_cv_profile: bool,
    profiles: Optional[str],
) -> dict:
    """
    Ofertas desde scan-list. Opcionalmente --profiles une áreas (management, tech, legal, education).
    Si hay CV y bastantes palabras clave derivadas, se filtra de nuevo por título/empresa.
    """
    data = _run_scan_list(limit, profiles)
    if data.get("ok") is False and not data.get("jobs"):
        return data

    state = _load_state()
    state["last_jobs_profiles"] = (profiles or "").strip()
    _save_state(state)
    if not state.get("profile_keywords") and (
        state.get("cv_markdown") or state.get("last_pdf_text")
    ):
        _sync_profile_keywords(state)
        _save_state(state)

    meta = state.get("profile_keywords_meta") or {}
    kws = list(state.get("profile_keywords") or [])
    jobs_in = data.get("jobs") or []
    ap = data.get("area_profiles")
    ps_clean = (profiles or "").strip()
    if ps_clean and ap and ap.get("mode") == "area_union" and ap.get("labels"):
        lbs = ", ".join(lbl["label"] for lbl in ap["labels"])
        yaml_part = (
            f"Áreas de empleo seleccionadas: {lbs}. "
            "Unión de palabras clave por área; las exclusiones negativas del YAML siguen activas."
        )
    elif ps_clean and ap and ap.get("mode") == "fallback_yaml_all_keys_unknown":
        yaml_part = (
            "Claves de área no reconocidas; se usó el filtro de títulos completo de portals.yml."
        )
    else:
        yaml_part = "Primero se aplica el title_filter de portals.yml (sin filtro por área adicional)."
    cv_note = (
        yaml_part
        + f" Luego, si el CV aporta ≥{MIN_PROFILE_KEYWORDS_TO_FILTER} términos, se muestran solo "
        "ofertas cuyo título o empresa coinciden con alguno de esos términos."
    )

    if not use_cv_profile:
        data["jobs_cv_filter"] = "disabled_by_query"
        data["profile_keywords_meta"] = meta
        data["filter_explanation"] = cv_note
        return data

    if not meta.get("ready_to_filter") or not kws:
        data["jobs_cv_filter"] = "skipped_weak_cv_signals"
        data["profile_keywords_meta"] = meta
        data["filter_explanation"] = (
            cv_note
            + " Ahora: señales insuficientes en el CV para filtrar; se listan todas las "
            "ofertas que ya pasaron el filtro del escáner (YAML y, si aplica, ámbitos)."
        )
        return data

    before = len(jobs_in)
    filtered = [
        j
        for j in jobs_in
        if job_matches_profile(
            j.get("title") or "",
            j.get("company") or "",
            kws,
        )
    ]
    rolled_back = before > 0 and len(filtered) == 0
    if rolled_back:
        data["jobs"] = jobs_in
        data["jobs_cv_filter"] = "rolled_back_no_overlap"
        data["jobs_after_cv_filter_attempt"] = 0
    else:
        data["jobs"] = filtered
        data["jobs_cv_filter"] = "applied"
        data["jobs_after_cv_filter_attempt"] = len(filtered)
    data["jobs_before_cv_filter"] = before
    data["profile_keywords_meta"] = meta
    if rolled_back:
        data["filter_explanation"] = (
            cv_note
            + f" Tras cruzar con el CV, 0 coincidencias de {before} ofertas "
            "(títulos/empresas sin solape con los términos extraídos). "
            "Se muestra el listado completo tras portals.yml para que elija manualmente; "
            "puede marcar «Ignorar perfil del CV» en la próxima búsqueda o enriquecer el resumen del CV con términos alineados a los puestos."
        )
    else:
        data["filter_explanation"] = (
            cv_note
            + f" Filtradas {before} → {len(filtered)} por coincidencia con el perfil del CV."
        )
    return data


@app.get("/api/jobs")
def get_jobs(
    limit: int = 200,
    use_cv_profile: bool = True,
    profiles: Optional[str] = Query(
        default=None,
        description="Áreas separadas por coma: management, tech, legal, education",
    ),
):
    return _get_jobs_impl(limit, use_cv_profile, profiles)


@app.post("/api/select-jobs")
def select_jobs(body: SelectJobsBody):
    state = _load_state()
    base = state.get("cv_markdown") or state.get("last_pdf_text") or ""
    if not base.strip():
        raise HTTPException(400, "No hay CV cargado. Suba un PDF o pegue el markdown.")

    last_p = (state.get("last_jobs_profiles") or "").strip()
    jobs_resp = _get_jobs_impl(500, True, last_p if last_p else None)
    jobs_list = jobs_resp.get("jobs") or []
    by_id = {j["id"]: j for j in jobs_list if j.get("id")}
    new_apps: list[dict] = []
    for jid in body.job_ids:
        job = by_id.get(jid)
        if not job:
            continue
        tailored = _tailor_cv_markdown(base, job["title"], job["company"])
        safe_company = re.sub(r"[^\w\-]+", "-", job["company"])[:40].strip("-") or "company"
        safe_title = re.sub(r"[^\w\-]+", "-", job["title"])[:50].strip("-") or "role"
        fname = f"{job['id']}-{safe_company}-{safe_title}.md"
        out_path = OUTPUT_DIR / fname
        out_path.write_text(tailored, encoding="utf-8")
        entry = {
            "id": job["id"],
            "company": job["company"],
            "title": job["title"],
            "url": job["url"],
            "location": job.get("location") or "",
            "tailored_cv_path": str(out_path.relative_to(DATA_ROOT)),
            "status": "preparada",
            "note": (
                "CV generado. Abra la URL de la oferta y envíe manualmente; "
                "career-ops no envía formularios automáticamente."
            ),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        new_apps.append(entry)

    existing = state.get("applications") or []
    merged = {a["id"]: a for a in existing}
    for a in new_apps:
        merged[a["id"]] = a
    state["applications"] = sorted(merged.values(), key=lambda x: (x["company"], x["title"]))
    _save_state(state)
    return {"ok": True, "applications": state["applications"], "generated": len(new_apps)}


@app.get("/api/applications")
def list_applications():
    return _load_state().get("applications") or []


@app.post("/api/mark-applied")
def mark_applied(body: dict):
    jid = body.get("job_id")
    if not jid:
        raise HTTPException(400, "job_id requerido")
    state = _load_state()
    apps = state.get("applications") or []
    for a in apps:
        if a.get("id") == jid:
            a["status"] = "marcada_enviada_por_usuario"
            a["applied_marked_at"] = datetime.now(timezone.utc).isoformat()
            break
    else:
        raise HTTPException(404, "Solicitud no encontrada")
    state["applications"] = apps
    _save_state(state)
    return {"ok": True}


# UI estática en /static para no tapar /docs ni /openapi.json
@app.get("/")
def spa_index():
    index = STATIC_DIR / "index.html"
    if not index.exists():
        return {
            "message": "Career-Ops API activa. Añada webapp/static/index.html para la interfaz.",
            "docs": "/docs",
        }
    return FileResponse(index)


app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


def main():
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=int(sys.argv[1]) if len(sys.argv) > 1 else 8765, reload=False)


if __name__ == "__main__":
    main()
