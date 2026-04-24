# Career-Ops (Cursor, Codex, Copilot, u otros agentes)

No hace falta **Claude Code** ni **OpenCode**. Lee `CLAUDE.md` para instrucciones, enrutamiento y reglas de comportamiento; aplican a cualquier asistente que trabaje en este repo (p. ej. **Cursor**, **ChatGPT/Codex en el IDE**, **GitHub Copilot**).

Key points:
- Reuse the existing modes, scripts, templates, and tracker flow — do not create parallel logic.
- Store user-specific customization in `config/profile.yml`, `modes/_profile.md`, or `article-digest.md` — never in `modes/_shared.md`.
- Never submit an application on the user's behalf.

For Codex-specific setup, see `docs/CODEX.md`.

## Cursor (opcional)

En este repo hay una skill de proyecto para buscar ofertas **alineadas al CV** en fuentes sin API pública en el escáner Node (ManpowerGroup Talent Solutions, Hireline, Glassdoor, Dynamics 365 HR ATS, Apideck / Unified.to): `.cursor/skills/ats-partner-platforms-search/SKILL.md`.
