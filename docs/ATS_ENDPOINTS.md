# ATS: endpoints y prioridades para el escáner

Documento adaptado para **career-ops** a partir de ideas y tablas de URL del proyecto
[career-ops-plugin](https://github.com/andrew-shwetzer/career-ops-plugin) (MIT, ver su `ATTRIBUTION.md`)
y del comportamiento real de `scan.mjs` / `scan-list.mjs`.

## Prioridad 1 — Integrados y comprobados (HTTP + JSON público)

Estos son los tipos que el escáner Node llama hoy para **listar vacantes**. **Sin API key** (solo job postings públicos, no ATS “core” de candidatos).

| ATS | Cómo se detecta en `careers_url` (o `api`) | Endpoint usado |
|-----|----------------------------------|----------------|
| **Greenhouse** | `job-boards*.greenhouse.io/{slug}`, `boards.greenhouse.io/{slug}`, `{slug}.greenhouse.io`, o campo `api` con URL boards-api | `GET https://boards-api.greenhouse.io/v1/boards/{slug}/jobs` (alternativa documentada por terceros: `api.greenhouse.io/v1/boards/{slug}/jobs`) |
| **Ashby** | `jobs.ashbyhq.com/{slug}` | `GET https://api.ashbyhq.com/posting-api/job-board/{slug}?includeCompensation=true` |
| **Lever** | `jobs.lever.co/{slug}` | `GET https://api.lever.co/v0/postings/{slug}` → si **404**, reintento en `https://api.eu.lever.co/v0/postings/{slug}` |
| **Recruitee** | `https://{client}.recruitee.com/...` o `api` apuntando a `.../api/offers` | `GET https://{client}.recruitee.com/api/offers` ([referencia](https://fantastic.jobs/article/ats-with-api)) |
| **Workable** | `https://apply.workable.com/{account}/` o `api` al widget | `GET https://apply.workable.com/api/v1/widget/accounts/{account}` ([referencia](https://fantastic.jobs/article/ats-with-api)) |

### Notas

- **Greenhouse:** muchas empresas usan `boards.greenhouse.io/nombre` o `nombre.greenhouse.io` (subdominio). El módulo `ats-detect.mjs` cubre esos patrones además de `job-boards.greenhouse.io`.
- **Lever EU:** el mismo slug en `jobs.lever.co` puede estar sólo en la API europea; el fallback evita añadir campos extra en `portals.yml`.
- **Recruitee:** solo ofertas con `status` publicable (`published` / `open` si viene informado).
- **Workable:** no usar como `careers_url` solo una URL de puesto `apply.workable.com/j/{code}`; hace falta la raíz de cuenta `apply.workable.com/{account}/` para resolver el widget.

## Prioridad 2 — No integrados en el escáner (documentación / uso manual)

| ATS / plataforma | Motivo |
|-----|--------|
| **SmartRecruiters** | Existe `GET https://api.smartrecruiters.com/v1/companies/{slug}/postings`, pero en pruebas recientes la API devolvió `content: []` para varios slugs públicos. Hasta tener respuestas estables **no** forma parte del pipeline automático. Detectar ofertas vía **WebSearch** + pegar URL en el flujo `oferta` sigue siendo válido. |
| **Workday** | Requiere `POST` a `*.myworkdayjobs.com` con `tenant` y sitio extraídos de la URL real; sin patrón único fiable. No implementado. |
| **ManpowerGroup (Talent Solutions)** | API tipo [directorio/partners](https://apitracker.io/a/manpowergroup-talent-solutions); no hay endpoint público de vacantes comparable a GH/Ashby/Lever/Recruitee/Workable. Omitido. |
| **Hireline** | Sin documentación pública verificable de API de listados en el mismo esquema; integración típica por convenio o conectores. |
| **Glassdoor** | [Política de no partnerships API](https://help.glassdoor.com/s/article/Glassdoor-API?language=en_US); páginas legacy de desarrollador sin garantía de acceso. |
| **Microsoft Dynamics 365 HR (ATS integration API)** | API de **integración** corporativa (autenticación, no job board público). Ver [Learn](https://learn.microsoft.com/en-us/dynamics365/human-resources/hr-admin-integration-ats-api-introduction). |
| **Apideck / Unified.to (unified ATS)** | Producto aparte (clave, mapping); no sustituye detección por URL en `portals.yml`. |

Referencias generales de listados públicos: [Fantastic.jobs — ATS with public job posting APIs](https://fantastic.jobs/article/ats-with-api), [PublicAPIs.dev — Jobs](https://publicapis.dev/category/jobs).

## Eliminado o no recomendado como “fuente automática”

- Cualquier endpoint que devuelva **401/403** de forma sistemática o listas **siempre vacías** sin documentación clara no se considera fuente para el scanner.
- **Cowork / proxies:** en entornos que bloqueen `boards-api.greenhouse.io`, `api.lever.co`, etc., el plugin original sugiere WebSearch; en tu máquina local el escáner Node **sí** hace HTTPS directo.

## Reglas de CV frente a ATS (parsers de documento)

El archivo `references/ats-rules.md` del plugin habla de **cómo formatear el PDF/HTML** para parsers de currículum (no de listados de empleo). Para plantillas PDF en career-ops sigue siendo relevante `templates/cv-template.html` y `generate-pdf.mjs`.

## Webapp: filtro por CV (además de `portals.yml`)

El endpoint `GET /api/jobs` ejecuta `scan-list.mjs` (filtro `title_filter` del YAML). Si el estado del usuario tiene un CV con texto suficiente, se derivan **palabras clave** desde el resumen (`cv_profile_keywords.py`, heurística local) y, si hay **≥ 6** términos, se **vuelve a filtrar**: la oferta debe contener al menos uno de esos términos en el **título** o en el **nombre de empresa**. Con `?use_cv_profile=false` solo se aplica el YAML.

## Mantenimiento del listado (`portals.yml`)

Tras cambiar muchas URLs, conviene auditar qué APIs responden:

```bash
npm run audit-portals          # informe
npm run audit-portals -- --apply   # desactiva empresas cuya API falle (404, etc.)
```

Los timeouts ocasionales en red pueden marcar un falso positivo; revise manualmente si una empresa sana quedó en `enabled: false`.

## Referencias

- [career-ops-plugin — references/ats-endpoints.md](https://github.com/andrew-shwetzer/career-ops-plugin/blob/main/references/ats-endpoints.md) (patrones originales; parte del contenido SmartRecruiters/Workday quedó fuera del escáner por lo anterior).
- Código: `ats-detect.mjs`, `scan.mjs`, `scan-list.mjs`, `audit-portals.mjs`.
