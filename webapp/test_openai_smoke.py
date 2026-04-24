#!/usr/bin/env python3
"""Prueba rápida de OpenAI (opcional). Uso desde la raíz del repo:

  cd webapp && OPENAI_API_KEY=... python3 test_openai_smoke.py

No imprime la clave. Sin OPENAI_API_KEY termina con código 0 y mensaje skip.
"""

from __future__ import annotations

import os
import sys

# Carga .env antes de importar openai_enrich
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

try:
    from dotenv import load_dotenv

    root = Path(__file__).resolve().parent.parent
    for p in (root / ".env", Path(__file__).resolve().parent / ".env"):
        if p.exists():
            load_dotenv(p)
            break
except ImportError:
    pass


def main() -> int:
    from openai_enrich import harvard_from_text_openai, openai_configured

    if not openai_configured():
        print("SKIP: OPENAI_API_KEY no definida (configure .env o entorno).")
        return 0

    sample = """
    Jane Doe | jane@email.com | +1 555-0100
    SUMMARY
    Senior engineer with 8 years in distributed systems.

    EXPERIENCE
    Acme Corp — Staff Engineer, 2020–Present
    - Led migration to Kubernetes
    - Cut latency 40%

    EDUCATION
    MS Computer Science, State University, 2015
    """
    out = harvard_from_text_openai(sample)
    assert out.get("format") == "harvard"
    assert "header" in out
    print("OK: OpenAI devolvió estructura Harvard.")
    print("Keys:", list(out.keys()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
