"""
Deriva palabras clave desde el texto del CV para filtrar ofertas (criterio base, sin LLM).
Si hay pocas señales, devuelve lista vacía y el caller no aplica filtro extra.
"""

from __future__ import annotations

import re
from collections import Counter

# Español + inglés comunes (no roles)
_STOP = frozenset(
    """
    the and for with from that this have been were will your you are was but not all can
    has had his her their our out any may its also than into only over such both few
    more most some what when where which while about after before between through under
    el la los las un una uno de del al en y o a por para con sin sobre entre como más
    muy todo todos todas cada cual quien mismo misma otros otras being each which their
    years year month months experience including university college school degree
    """.split()
)


def _summary_slice(text: str) -> str:
    """Prioriza resumen / perfil; si no hay, primeros caracteres del cuerpo."""
    for pat in (
        r"##\s*(Professional Summary|Summary|Profile|Resumen|Perfil profesional)\s*\n([\s\S]*?)(?=\n##\s|\Z)",
        r"^#\s[^\n]+\n+([\s\S]{0,4000}?)(?=\n##\s|\Z)",
    ):
        m = re.search(pat, text, re.I | re.MULTILINE)
        if m:
            g = m.lastindex if m.lastindex else 1
            chunk = m.group(g).strip()
            if len(chunk) > 80:
                return chunk
    return text[:6000]


def derive_profile_keywords(text: str, max_keywords: int = 28) -> list[str]:
    """
    Extrae términos relevantes (frecuencia en resumen + términos de rol típicos).
    Devuelve lista en minúsculas para matchear títulos de ofertas.
    """
    if not text or len(text.strip()) < 40:
        return []

    focus = _summary_slice(text)
    combined = focus + "\n" + text[:8000]

    # Palabras alfanuméricas 4+ caracteres
    words = re.findall(r"\b[a-záéíóúñü0-9][a-záéíóúñü0-9'-]{3,}\b", focus.lower())
    words = [w for w in words if w not in _STOP and not w.isdigit()]
    if not words:
        words = re.findall(
            r"\b[a-záéíóúñü0-9][a-záéíóúñü0-9'-]{3,}\b", combined.lower()
        )
        words = [w for w in words if w not in _STOP]

    cnt = Counter(words)
    top = [w for w, _ in cnt.most_common(max_keywords * 2)]

    # Bigramas en resumen (p. ej. "machine learning", "educational technology")
    raw = re.sub(r"[^\w\sáéíóúñüÁÉÍÓÚÑÜ]", " ", focus.lower())
    parts = [p for p in raw.split() if len(p) >= 3 and p not in _STOP]
    bigrams: list[str] = []
    for i in range(len(parts) - 1):
        bg = f"{parts[i]} {parts[i + 1]}"
        if len(bg) >= 8:
            bigrams.append(bg)

    for bg in Counter(bigrams).most_common(8):
        top.insert(0, bg[0])

    # Dedup preservando orden
    seen: set[str] = set()
    out: list[str] = []
    for w in top:
        w = w.strip().lower()[:60]
        if len(w) < 4 or w in seen:
            continue
        seen.add(w)
        out.append(w)
        if len(out) >= max_keywords:
            break

    return out


# Términos cortos que suelen enlazar CV académico con ofertas tech (solo si aparecen en el CV).
_BRIDGE_TERMS = (
    "engineer",
    "engineering",
    "research",
    "researcher",
    "scientist",
    "software",
    "data",
    "product",
    "platform",
    "learning",
    "machine",
    "artificial",
    "intelligence",
    "developer",
    "architect",
    "analytics",
    "cloud",
)


def augment_keywords_for_jobs(text: str, keywords: list[str]) -> list[str]:
    """Añade palabras puente si el CV las menciona (ayuda a no quedar en 0 coincidencias)."""
    low = text.lower()
    extra: list[str] = []
    for t in _BRIDGE_TERMS:
        if re.search(rf"\b{re.escape(t)}\b", low) and t not in keywords:
            extra.append(t)
    seen = set(keywords)
    out = list(keywords)
    for e in extra:
        if e not in seen:
            seen.add(e)
            out.append(e)
    return out[:36]


def _tokens_from_keywords(keywords: list[str]) -> list[str]:
    """Palabras sueltas ≥4 caracteres; el filtro por substring de frase sola suele dejar 0 resultados."""
    toks: set[str] = set()
    for k in keywords:
        for part in re.split(r"[^\wáéíóúñü]+", k.lower()):
            if len(part) >= 4 and part not in _STOP:
                toks.add(part)
    return list(toks)


def job_matches_profile(title: str, company: str, keywords: list[str]) -> bool:
    if not keywords:
        return True
    blob = f"{title} {company}".lower()
    if any(k in blob for k in keywords):
        return True
    for t in _tokens_from_keywords(keywords):
        if t in blob:
            return True
    return False
