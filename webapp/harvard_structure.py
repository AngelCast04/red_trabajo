"""
Estructura tipo CV Harvard (reverse chronological en educación y experiencia).
Parseo heurístico desde texto plano extraído de PDF/Markdown.
"""

from __future__ import annotations

import re
from typing import Any, Optional


SECTION_KEYS = (
    "header",
    "education",
    "experience",
    "skills",
    "projects",
    "additional",
)


def _clean_lines(text: str) -> list[str]:
    lines = [ln.rstrip() for ln in text.replace("\r\n", "\n").split("\n")]
    out: list[str] = []
    for ln in lines:
        s = ln.strip()
        if s:
            out.append(s)
    return out


def _guess_section(line: str) -> Optional[str]:
    u = line.upper()
    patterns = [
        (r"^(EDUCATION|FORMACI[ÓO]N|ACADEMIC)", "education"),
        (r"^(EXPERIENCE|WORK EXPERIENCE|EMPLOYMENT|EXPERIENCIA|PROFESSIONAL EXPERIENCE)", "experience"),
        (r"^(SKILLS|COMPETENCIES|TECHNICAL SKILLS|HABILIDADES)", "skills"),
        (r"^(PROJECTS|PERSONAL PROJECTS|PROYECTOS)", "projects"),
        (r"^(SUMMARY|PROFESSIONAL SUMMARY|PROFILE|OBJECTIVE|RESUMEN)", "header"),
    ]
    for pat, key in patterns:
        if re.match(pat, u):
            return key
    return None


def text_to_harvard(text: str) -> dict[str, Any]:
    """
    Convierte texto libre en un objeto con secciones estilo Harvard.
    El bloque inicial antes de la primera sección reconocida se trata como header (contacto + resumen corto).
    """
    lines = _clean_lines(text)
    if not lines:
        return {
            "format": "harvard",
            "header": {"lines": [], "note": "Sin contenido extraído."},
            "education": [],
            "experience": [],
            "skills": [],
            "projects": [],
            "additional": [],
        }

    sections: dict[str, list[str]] = {k: [] for k in SECTION_KEYS}
    current = "header"
    for ln in lines:
        sec = _guess_section(ln)
        if sec and sec != current:
            current = sec
            if sec != "header":
                continue
        sections[current].append(ln)

    def block_to_entries(block: list[str], mode: str) -> list[dict[str, Any]]:
        if mode == "education":
            return [{"raw": " ".join(block)}] if block else []
        if mode == "experience":
            chunks: list[list[str]] = []
            cur: list[str] = []
            for line in block:
                if re.match(r"^#{1,3}\s+", line) or (
                    len(line) < 80
                    and re.search(r"(19|20)\d{2}\s*[—–-]\s*(19|20)\d{2}|Present|Actualidad", line)
                ):
                    if cur:
                        chunks.append(cur)
                    cur = [line]
                else:
                    cur.append(line)
            if cur:
                chunks.append(cur)
            return [{"lines": c} for c in chunks] if chunks else [{"lines": block}]
        return [{"lines": block}] if block else []

    header_text = sections["header"]
    education = sections["education"]
    experience = sections["experience"]

    return {
        "format": "harvard",
        "description": (
            "Estructura Harvard: contacto y resumen arriba; Educación y Experiencia "
            "en orden cronológico inverso; Skills y proyectos al final."
        ),
        "header": {
            "lines": header_text[:40],
            "full_text": "\n".join(header_text),
        },
        "education": block_to_entries(education, "education"),
        "experience": block_to_entries(experience, "experience"),
        "skills": [{"lines": sections["skills"]}] if sections["skills"] else [],
        "projects": [{"lines": sections["projects"]}] if sections["projects"] else [],
        "additional": sections["additional"],
    }


def harvard_to_markdown(h: dict[str, Any]) -> str:
    """Serializa el objeto Harvard a Markdown legible."""
    lines: list[str] = ["# CV (formato Harvard)", ""]
    head = h.get("header") or {}
    if isinstance(head, dict) and head.get("lines"):
        lines.append("## Contacto y resumen")
        lines.extend(head["lines"])
        lines.append("")
    lines.append("## Educación")
    for e in h.get("education") or []:
        if isinstance(e, dict) and e.get("raw"):
            lines.append(f"- {e['raw']}")
        elif isinstance(e, dict) and e.get("lines"):
            lines.append("\n".join(e["lines"]))
        lines.append("")
    lines.append("## Experiencia")
    for ex in h.get("experience") or []:
        if isinstance(ex, dict) and ex.get("lines"):
            lines.append("\n".join(ex["lines"]))
            lines.append("")
    lines.append("## Habilidades")
    for s in h.get("skills") or []:
        if isinstance(s, dict) and s.get("lines"):
            lines.extend(f"- {x}" if not x.startswith("-") else x for x in s["lines"])
    lines.append("")
    proj = h.get("projects") or []
    if proj:
        lines.append("## Proyectos")
        for p in proj:
            if isinstance(p, dict) and p.get("lines"):
                lines.extend(p["lines"])
        lines.append("")
    return "\n".join(lines).strip() + "\n"
