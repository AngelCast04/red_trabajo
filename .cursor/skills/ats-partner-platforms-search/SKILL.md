---
name: ats-partner-platforms-search
description: >-
  Busca vacantes alineadas al CV en fuentes sin API pública en el escáner career-ops
  (ManpowerGroup Talent Solutions, Hireline, Glassdoor, Dynamics 365 HR ATS,
  Apideck/Unified.to). Lee el CV y perfil del repo, extrae palabras clave relevantes,
  ejecuta búsqueda web dirigida y devuelve solo ofertas afines. Usar cuando el usuario
  pida empleos en esas plataformas, ATS “partner”, o fuentes fuera de Greenhouse/Ashby/Lever/Recruitee/Workable.
---

# Búsqueda de ofertas en fuentes ATS sin endpoint público (career-ops)

## Alcance y límites técnicos

Estas fuentes **no** están en `ats-detect.mjs` / `scan-list.mjs` porque no exponen un **JSON anónimo de vacantes** comparable al pipeline Node actual:

| Fuente | Realidad práctica |
|--------|-------------------|
| **ManpowerGroup Talent Solutions** | Staffing / talent solutions; API tipo partner ([apitracker](https://apitracker.io/a/manpowergroup-talent-solutions)), no listado público estable para agregadores. |
| **Hireline** | Sin API pública documentada en el mismo esquema que el escáner. |
| **Glassdoor** | [Sin API de partnerships](https://help.glassdoor.com/s/article/Glassdoor-API?language=en_US) según Help Center; documentación legacy no garantizada. |
| **Dynamics 365 HR (ATS integration API)** | API de **integración corporativa** (autenticación), no job board JSON anónimo. Las vacantes se publican en el **career site del empleador**. |
| **Apideck / Unified.to** | Productos **unificados B2B** (credenciales, múltiples ATS); no son portales de candidato ni sustituyen búsqueda por URL. |

**No inventar** llamadas a APIs REST de estas marcas como si fueran públicas. El flujo de esta skill es: **contexto del CV → consultas web / navegación → filtrado por afinidad**.

## Cuándo aplicar esta skill

- El usuario pide buscar trabajo en Manpower, Hireline, Glassdoor, “Dynamics ATS”, Apideck o Unified.to.
- Quiere **solo ofertas afines** a su CV, no listados crudos genéricos.

## Archivos a cargar (capa usuario, DATA_CONTRACT)

Antes de buscar, leer del proyecto (si existen):

- `cv.md` — CV canónico.
- `config/profile.yml` — roles objetivo, ubicación, comp, narrativa.
- `modes/_profile.md` — arquetipos, deal-breakers, pruebas de ajuste.
- Estado webapp si aplica: `data/webapp-state.json` (CV en markdown cache) **solo** si el usuario usa la webapp y no hay `cv.md` actualizado.

Si falta CV sustancial, pedir resumen o pegar el resumen profesional antes de buscar.

## Extracción de palabras clave (para consultas)

1. **Rol objetivo**: títulos que el usuario persigue (ej. “Learning & Development Manager”, “Data Engineer”, “Legal Counsel”).
2. **Skills duras**: stack, dominios (IA, educación, legal, SAP, etc.), idiomas exigibles.
3. **Ubicación / modalidad**: ciudad, país, remoto/híbrido (para acotar `site:` y términos en la query).
4. **Seniority**: senior, lead, principal — para excluir junior si el perfil no encaja.
5. **Exclusiones**: tecnologías o sectores que el usuario rechaza (tomar de `_profile.md` / `profile.yml`).

Reutilizar si existe lógica ya descrita en `webapp/cv_profile_keywords.py` como **inspiración** (palabras del resumen); no hace falta ejecutar Python para la skill.

## Estrategia por fuente

### ManpowerGroup / Manpower (Talent Solutions)

- Buscar portales de carreras por país: `Manpower careers [país]`, `ManpowerGroup jobs`, `Experis` / marcas del grupo si aplican al usuario.
- Queries WebSearch ejemplo: `site:manpower.com careers [rol] [ubicación]`, `Manpower Talent Solutions [ciudad] [keyword rol]`.
- Filtrar resultados: solo listados cuyo título/resumen **solape** con ≥2 ejes del CV (rol + skill o sector).

### Hireline

- `site:hireline.com` + términos de rol y ubicación; revisar páginas de listados y fichas.
- Sin API: cada URL de oferta debe evaluarse **manualmente** o con snapshot si hay herramientas de navegador.

### Glassdoor

- Búsquedas del tipo: `site:glassdoor.com [rol] [empresa o ciudad]`, o el buscador integrado vía WebSearch.
- Recordar **términos de uso**: uso razonable, sin scraping agresivo; preferir enlaces a fichas concretas.
- Verificar ofertas con **Playwright** (navegar + snapshot) cuando el usuario vaya a postular, según reglas globales de career-ops sobre verificación de URLs.

### Dynamics 365 HR / “ATS Microsoft”

- No buscar “API Dynamics ATS” como candidato.
- Buscar **empleos en empresas** que usan Microsoft stack o que publiquen en **career sites** estándar; si el usuario trabaja en ecosistema D365, priorizar queries: `"Dynamics 365" OR "D365" careers [rol]`.
- La integración ATS de Dynamics es **del empleador**, no un portal único de vacantes.

### Apideck / Unified.to

- Explicar brevemente: son **capas de integración para productos**, no sitios donde el candidato busque empleo.
- Si el usuario confunde con “un solo buscador”: redirigir a **búsqueda en los ATS subyacentes** (Greenhouse, Lever, etc.) o a la webapp career-ops con `scan-list` / portales YAML.

## Filtrado: “solo ofertas afines”

Para cada candidato a oferta (título + snippet o descripción corta):

1. **Debe** coincidir con al menos un **rol objetivo** o sinónimo del CV.
2. **Debe** alinear con **≥1 skill o dominio** fuerte del CV (o justificar excepción, p. ej. transición de carrera explícita en el perfil).
3. **Excluir** si choca con deal-breakers de `modes/_profile.md` o `profile.yml`.
4. Si la información es insuficiente en el snippet, marcar **“revisar ficha completa”** en lugar de incluirla como alta confianza.

## Formato de salida recomendado

1. **Palabras clave usadas** (lista corta, justificada por el CV).
2. **Tabla** (máx. 10–15 filas de alta relevancia): Empresa | Título | Ubicación/modalidad | URL | Afinidad (1–2 frases) | Confianza (alta/media/baja).
3. **Descartadas** (opcional): 2–3 ejemplos de listados genéricos excluidos y por qué.
4. **Siguiente paso**: añadir URLs prometedoras a `data/pipeline.md` para evaluación `/career-ops oferta` o modo pipeline.

## Ética (career-ops)

- Priorizar **calidad sobre cantidad**; no animar a aplicar masivamente a baja afinidad.
- No automatizar envíos a portales; el usuario revisa y envía.
- No garantizar que Glassdoor/Manpower muestren ofertas aún activas sin verificación en la ficha.

## Referencias internas del repo

- `docs/ATS_ENDPOINTS.md` — qué está integrado en Node vs qué no.
- `.claude/skills/career-ops/SKILL.md` — router principal career-ops.
