"""
Estructuración de CV en formato Harvard vía OpenAI.
La clave se lee solo de variables de entorno (OPENAI_API_KEY); nunca del código.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

# Carga opcional de .env (raíz del repo y webapp/; ambos si existen, sin parar en el primero)
try:
    from dotenv import load_dotenv

    _ROOT = Path(__file__).resolve().parent.parent
    _WEBAPP = Path(__file__).resolve().parent

    def _load_env_files() -> None:
        for _env in (_ROOT / ".env", _WEBAPP / ".env"):
            if _env.is_file():
                load_dotenv(_env, override=True)

    _load_env_files()
except ImportError:
    pass


def openai_configured() -> bool:
    return bool(os.environ.get("OPENAI_API_KEY", "").strip())


def _model() -> str:
    return os.environ.get("OPENAI_MODEL", "gpt-4o-mini").strip() or "gpt-4o-mini"


def openai_model_name() -> str:
    """Modelo efectivo (para /api/llm-status)."""
    return _model()


def _truncate(text: str, max_chars: int = 48_000) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n\n[… texto truncado para el modelo …]"


def _normalize_harvard_payload(data: dict[str, Any]) -> dict[str, Any]:
    """Asegura forma compatible con harvard_to_markdown / UI."""
    out: dict[str, Any] = {
        "format": "harvard",
        "description": data.get("description")
        or (
            "Estructura Harvard (OpenAI): contacto y resumen; educación y experiencia "
            "en orden cronológico inverso."
        ),
        "header": {"lines": [], "full_text": ""},
        "education": [],
        "experience": [],
        "skills": [],
        "projects": [],
        "additional": data.get("additional") or [],
    }

    h = data.get("header") or {}
    if isinstance(h, dict):
        lines = h.get("lines")
        if isinstance(lines, list):
            out["header"]["lines"] = [str(x) for x in lines if str(x).strip()]
        elif h.get("full_text"):
            out["header"]["lines"] = [ln.strip() for ln in str(h["full_text"]).split("\n") if ln.strip()]
        out["header"]["full_text"] = h.get("full_text") or "\n".join(out["header"]["lines"])

    for key in ("education", "experience"):
        for item in data.get(key) or []:
            if not isinstance(item, dict):
                continue
            if item.get("raw"):
                out[key].append({"raw": str(item["raw"])})
            elif item.get("lines"):
                out[key].append({"lines": [str(x) for x in item["lines"]]})
            elif key == "education" and item.get("institution"):
                parts = [
                    item.get("degree", ""),
                    item.get("institution", ""),
                    item.get("dates", ""),
                ]
                raw = " — ".join(p for p in parts if p)
                details = item.get("details") or []
                if isinstance(details, list) and details:
                    raw += "\n" + "\n".join(f"- {d}" for d in details)
                out[key].append({"raw": raw.strip()})
            elif key == "experience":
                lines: list[str] = []
                org = item.get("organization") or item.get("company") or ""
                role = item.get("role") or item.get("title") or ""
                dates = item.get("dates") or ""
                if org or role:
                    lines.append(f"### {org}" + (f" — {role}" if role else ""))
                if dates:
                    lines.append(str(dates))
                for bullet in item.get("highlights") or item.get("bullets") or []:
                    lines.append(f"- {bullet}" if not str(bullet).lstrip().startswith("-") else str(bullet))
                if lines:
                    out[key].append({"lines": lines})

    sk = data.get("skills")
    if isinstance(sk, list):
        flat: list[str] = []
        for s in sk:
            if isinstance(s, str):
                flat.append(s)
            elif isinstance(s, dict):
                cat = s.get("category")
                items = s.get("items") or []
                if cat and items:
                    flat.append(f"**{cat}:** " + ", ".join(str(x) for x in items))
                elif s.get("lines"):
                    flat.extend(str(x) for x in s["lines"])
        if flat:
            out["skills"] = [{"lines": flat}]

    pr = data.get("projects")
    if isinstance(pr, list):
        plines: list[str] = []
        for p in pr:
            if isinstance(p, str):
                plines.append(f"- {p}")
            elif isinstance(p, dict):
                name = p.get("name") or p.get("title") or ""
                desc = p.get("description") or ""
                if name:
                    plines.append(f"- **{name}**" + (f": {desc}" if desc else ""))
        if plines:
            out["projects"] = [{"lines": plines}]

    out["llm_meta"] = {"model": data.get("_model")}
    return out


def harvard_from_text_openai(raw_text: str) -> dict[str, Any]:
    """
    Llama a OpenAI y devuelve dict Harvard normalizado.
    Raises on error de API o JSON inválido.
    """
    from openai import OpenAI

    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise ValueError("OPENAI_API_KEY no está definida")

    kwargs: dict[str, Any] = {"api_key": api_key}
    base = os.environ.get("OPENAI_BASE_URL", "").strip()
    if base:
        kwargs["base_url"] = base

    client = OpenAI(**kwargs)
    text = _truncate(raw_text)

    system = (
        "Eres un asistente experto en currículums. Extraes y reorganizan contenido en "
        "formato Harvard: datos de contacto y resumen arriba; Educación e Experiencia "
        "en orden cronológico inverso (más reciente primero); habilidades y proyectos al final. "
        "Responde SOLO con un objeto JSON válido, sin markdown ni texto fuera del JSON."
    )
    user = f"""Analiza el siguiente texto (puede venir de PDF mal maquetado). Devuelve JSON con esta forma:
{{
  "header": {{ "lines": ["línea de contacto o resumen", "..."] }},
  "education": [
    {{ "institution": "...", "degree": "...", "dates": "...", "details": ["opcional"] }},
    o {{ "raw": "bloque libre de una entrada académica" }}
  ],
  "experience": [
    {{
      "organization": "empresa",
      "role": "puesto",
      "dates": "2020 – Presente",
      "highlights": ["logro con métrica si existe", "..."]
    }}
  ],
  "skills": [ {{ "category": "opcional", "items": ["Python", "..."] }} ],
  "projects": [ {{ "name": "...", "description": "..." }} ],
  "additional": ["certificaciones u otros"]
}}

Texto del CV:
---
{text}
---
"""

    resp = client.chat.completions.create(
        model=_model(),
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        response_format={"type": "json_object"},
        temperature=0.2,
    )
    content = resp.choices[0].message.content
    if not content:
        raise RuntimeError("Respuesta vacía del modelo")

    parsed = json.loads(content)
    parsed["_model"] = _model()
    return _normalize_harvard_payload(parsed)


def resolve_harvard(text: str, prefer_openai: bool = True) -> tuple[dict[str, Any], str]:
    """
    Devuelve (harvard_dict, fuente) con fuente 'openai' o 'heuristic'.
    Si prefer_openai y hay clave, intenta OpenAI; ante fallo, heurística.
    """
    from harvard_structure import text_to_harvard

    if prefer_openai and openai_configured():
        try:
            return harvard_from_text_openai(text), "openai"
        except Exception:
            pass
    return text_to_harvard(text), "heuristic"
