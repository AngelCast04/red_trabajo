#!/usr/bin/env node
/**
 * scan-list.mjs — Lista todas las ofertas filtradas por título (JSON a stdout).
 * No escribe pipeline ni historial. Para consumo desde la UI web.
 *
 * Uso: node scan-list.mjs [--limit=N] [--profiles=management,tech,legal,education]
 */

import { readFileSync, existsSync } from 'fs';
import { createHash } from 'crypto';
import yaml from 'js-yaml';
import {
  detectApi,
  fetchBoardJson,
  PARSERS,
} from './ats-detect.mjs';

const parseYaml = yaml.load;
const PORTALS_PATH = 'portals.yml';
const PORTALS_FALLBACK = 'templates/portals.example.yml';
const CONCURRENCY = 10;

/**
 * Filtros por área (UI web). Claves: management, tech, legal, education.
 * Coincidencia por substring en el título normalizado (ATS: L&D → "and", guiones → espacio).
 * Palabras clave tipo "learning …" no cuentan si forman "machine learning …" / "deep learning …".
 * Evitar términos de 2–3 letras (ell, esl sueltos) que generan ruido en "fellows", "systems", etc.
 */
export const JOB_AREA_PROFILES = {
  management: {
    label: 'Gestión',
    positive: [
      // C-level / dirección general
      'chief',
      'chief of staff',
      'coo',
      'ceo',
      'cfo',
      'cmo',
      'cro',
      'cpo',
      'chro',
      'clo',
      'president',
      'presidente',
      'executive director',
      'executive vice',
      'chief executive',
      'chief executive officer',
      'managing director',
      'general manager',
      'managing partner',
      'partner in charge',
      // VP / SVP / EVP (ATS suelen usar coma o guion)
      'vice president',
      'vicepresident',
      'svp',
      'evp',
      'vp ',
      ' vp',
      ', vp',
      'v.p.',
      // Director / associate director
      'director',
      'director of',
      'director,',
      'associate director',
      'assistant director',
      'regional director',
      'global director',
      'country director',
      'area director',
      'group director',
      // Head / Lead (gestión de función; "lead" suelto evita pillar "lead engineer" en exceso con frases)
      'head of',
      'head,',
      'department head',
      'practice lead',
      'engagement manager',
      'delivery manager',
      'program lead',
      'team lead',
      'group lead',
      'chapter lead',
      'people lead',
      'business lead',
      'functional lead',
      'market lead',
      'lead,',
      ' lead ',
      // Manager (muy frecuente en ATS)
      'manager',
      'mgr',
      'senior manager',
      'group manager',
      'area manager',
      'regional manager',
      'district manager',
      'operations manager',
      'program manager',
      'project manager',
      'product manager',
      'office manager',
      'account manager',
      'client manager',
      'customer success manager',
      'partner manager',
      'channel manager',
      'sales manager',
      'marketing manager',
      'finance manager',
      'strategy manager',
      'transformation manager',
      'business manager',
      'people manager',
      'talent manager',
      'hr manager',
      'human resources manager',
      // Otros roles de gestión
      'management',
      'supervisor',
      'coordinator',
      'administrator',
      'officer',
      'strategist',
      'principal consultant',
      'management consultant',
      'board member',
      'gestión',
      'director general',
      'jefe de',
      'responsable de',
      'responsable del',
      'coordinador',
      'coordinadora',
    ],
  },
  tech: {
    label: 'Tecnología / corte tecnológico',
    positive: [
      'artificial intelligence',
      'machine learning',
      'deep learning',
      'llm',
      'genai',
      'generative',
      'nlp',
      'mlops',
      'llmops',
      'agentic',
      'software',
      'engineer',
      'engineering',
      'developer',
      'development',
      'architect',
      'devops',
      'sre',
      'platform',
      'backend',
      'frontend',
      'full stack',
      'fullstack',
      'data scientist',
      'data engineer',
      'cloud',
      'infrastructure',
      'security engineer',
      'solutions engineer',
      'forward deployed',
      'deployed engineer',
      'integration engineer',
      'technical',
      'automation',
      'scientist',
      'analytics engineer',
      'qa engineer',
      'test engineer',
      'embedded',
      'firmware',
    ],
  },
  legal: {
    label: 'Legal',
    positive: [
      'legal',
      'counsel',
      'attorney',
      'lawyer',
      'compliance',
      'regulatory',
      'privacy counsel',
      'paralegal',
      'abogado',
      'abogada',
      'jurídico',
      'jurídica',
      'contracts',
      'contracting',
      'litigation',
      'general counsel',
      'associate counsel',
    ],
  },
  education: {
    label: 'Educativo / tecnología educativa',
    positive: [
      // Sector y producto
      'education',
      'educational',
      'edtech',
      'education technology',
      'learning technology',
      'teaching technology',
      'academic technology',
      'digital learning',
      'online learning',
      'blended learning',
      'distance learning',
      'corporate learning',
      'enterprise learning',
      'workplace learning',
      'workforce learning',
      'learning experience',
      'learning platform',
      'learning management',
      'learning systems',
      'learning solutions',
      'learning services',
      'learning partner',
      'learning specialist',
      'learning consultant',
      'learning coordinator',
      'learning manager',
      'learning director',
      'learning officer',
      'learning lead',
      'learning designer',
      'learning architect',
      'learning analyst',
      'learning strategist',
      'learning program',
      'learning content',
      'learning operations',
      'learning enablement',
      'customer education',
      'partner education',
      'developer education',
      'user education',
      'field education',
      'product education',
      'sales education',
      // L&D / talent (frases típicas en ATS; "learning" solo en compuestos)
      'l&d',
      'learning and development',
      'talent development',
      'people development',
      'workforce development',
      'organizational development',
      'organisation development',
      'organization development',
      'employee development',
      'staff development',
      'professional development',
      'faculty development',
      'career development',
      'training and development',
      'training & development',
      'training manager',
      'training director',
      'training lead',
      'training specialist',
      'training coordinator',
      'training consultant',
      'corporate trainer',
      'technical trainer',
      'sales trainer',
      'enablement',
      'revenue enablement',
      'sales enablement',
      // Instructional / curriculum
      'instructional',
      'instructional design',
      'instructional designer',
      'instructional technologist',
      'curriculum',
      'curriculum design',
      'curriculum developer',
      'curriculum manager',
      'curriculum specialist',
      'course developer',
      'content developer',
      'educational content',
      'e-learning',
      'elearning',
      'elearn',
      'microlearning',
      'cohort',
      'bootcamp',
      'academy',
      'certification',
      'accreditation',
      // Roles académicos / escolares
      'professor',
      'lecturer',
      'instructor',
      'teacher',
      'teaching',
      'tutor',
      'tutoring',
      'adjunct',
      'faculty',
      'dean',
      'provost',
      'registrar',
      'superintendent',
      'school principal',
      'head of school',
      'headteacher',
      'academic',
      'academics',
      'pedagogy',
      'pedagogical',
      'andragogy',
      'literacy coach',
      'literacy specialist',
      'esl teacher',
      'esl instructor',
      'esl specialist',
      'ell teacher',
      'ell specialist',
      'special education',
      'student success',
      'student affairs',
      'student services',
      'admissions',
      'enrollment',
      'enrolment',
      'bilingual',
      'montessori',
      'stem education',
      'steam education',
      // Contextos K-12 / higher ed
      'k-12',
      'k12',
      'prek',
      'pre-k',
      'primary school',
      'secondary school',
      'middle school',
      'high school',
      'higher education',
      'postsecondary',
      'post secondary',
      'university',
      'college',
      'campus',
      'school',
      'kindergarten',
      'early childhood',
      'dozent',
      'lehrer',
      'weiterbildung',
      'ausbildung',
      'bildung',
      'formación',
      'formacion',
      'educativo',
      'educativa',
      'educador',
      'educadora',
      'docente',
      'scholastic',
      'biblioteca',
      'library media',
    ],
  },
};

function parseProfilesArg(argv) {
  for (const a of argv) {
    if (a.startsWith('--profiles=')) {
      return a
        .slice(11)
        .split(',')
        .map((s) => s.trim().toLowerCase())
        .filter(Boolean);
    }
  }
  return [];
}

function mergeProfilePositives(keys) {
  const seen = new Set();
  const out = [];
  const unknown = [];
  for (const k of keys) {
    const p = JOB_AREA_PROFILES[k];
    if (!p) {
      unknown.push(k);
      continue;
    }
    for (const kw of p.positive) {
      const low = kw.toLowerCase();
      if (!seen.has(low)) {
        seen.add(low);
        out.push(low);
      }
    }
  }
  return { positives: out, unknown };
}

/**
 * Normaliza títulos típicos de ATS (Greenhouse, Ashby, Lever) para mejorar acierto:
 * - L&D / L & D → "and"
 * - guiones/barras → espacio (k-12, full-time)
 * - colapsa espacios
 */
function normalizeAtsTitle(s) {
  if (!s || typeof s !== 'string') return '';
  return s
    .toLowerCase()
    .replace(/\s*&\s*/g, ' and ')
    .replace(/[\u2013\u2014–—]/g, ' ')
    .replace(/[-_/]/g, ' ')
    .replace(/[^a-z0-9áéíóúñü\s]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

/**
 * Evita falsos positivos en educación/L&D: "Machine Learning Specialist" contiene
 * la subcadena "learning specialist" (tras "machine "). Misma idea con "deep learning …".
 */
function positiveKeywordMatches(lower, kw) {
  if (!kw || !lower.includes(kw)) return false;
  if (kw.startsWith('learning ')) {
    if (lower.includes(`machine ${kw}`) || lower.includes(`deep ${kw}`)) return false;
  }
  return true;
}

function buildTitleFilter(titleFilter) {
  const positiveRaw = (titleFilter?.positive || []).map((k) => k.toLowerCase());
  const negativeRaw = (titleFilter?.negative || []).map((k) => k.toLowerCase());
  const positive = positiveRaw.map((k) => normalizeAtsTitle(k)).filter(Boolean);
  const negative = negativeRaw.map((k) => normalizeAtsTitle(k)).filter(Boolean);
  return (title) => {
    const lower = normalizeAtsTitle(title);
    const hasPositive =
      positive.length === 0 || positive.some((k) => k.length > 0 && positiveKeywordMatches(lower, k));
    const hasNegative = negative.some((k) => k.length > 0 && lower.includes(k));
    return hasPositive && !hasNegative;
  };
}

function jobId(url) {
  return createHash('sha256').update(url || '').digest('hex').slice(0, 16);
}

async function parallelFetch(tasks, limit) {
  const results = [];
  let i = 0;
  async function next() {
    while (i < tasks.length) {
      const task = tasks[i++];
      results.push(await task());
    }
  }
  const workers = Array.from({ length: Math.min(limit, tasks.length) }, () => next());
  await Promise.all(workers);
  return results;
}

async function main() {
  const args = process.argv.slice(2);
  let limit = Infinity;
  for (const a of args) {
    if (a.startsWith('--limit=')) limit = parseInt(a.slice(8), 10) || Infinity;
  }

  const profileKeys = parseProfilesArg(args);
  const { positives: profilePositives, unknown: unknownProfileKeys } =
    profileKeys.length > 0 ? mergeProfilePositives(profileKeys) : { positives: [], unknown: [] };

  const portalsPath = existsSync(PORTALS_PATH) ? PORTALS_PATH : PORTALS_FALLBACK;
  if (!existsSync(portalsPath)) {
    console.log(JSON.stringify({ ok: false, error: 'No portals.yml', jobs: [], errors: [] }));
    process.exit(0);
  }

  const config = parseYaml(readFileSync(portalsPath, 'utf-8'));
  const companies = config.tracked_companies || [];
  const yamlTf = config.title_filter || {};
  let filterSpec = yamlTf;
  let profileMode = null;
  if (profileKeys.length > 0) {
    if (profilePositives.length > 0) {
      filterSpec = {
        positive: profilePositives,
        negative: yamlTf.negative || [],
      };
      profileMode = 'area_union';
    } else {
      profileMode = 'fallback_yaml_all_keys_unknown';
    }
  }
  const titleFilter = buildTitleFilter(filterSpec);

  const targets = companies
    .filter(c => c.enabled !== false)
    .map(c => ({ ...c, _api: detectApi(c) }))
    .filter(c => c._api !== null);

  const jobs = [];
  const errors = [];

  const tasks = targets.map(company => async () => {
    const { type } = company._api;
    try {
      const json = await fetchBoardJson(company._api);
      const parsed = PARSERS[type](json, company.name);
      for (const job of parsed) {
        if (!job.url || !titleFilter(job.title)) continue;
        jobs.push({
          id: jobId(job.url),
          title: job.title,
          company: job.company,
          location: job.location || '',
          url: job.url,
          source: type,
        });
      }
    } catch (err) {
      errors.push({ company: company.name, error: err.message });
    }
  });

  await parallelFetch(tasks, CONCURRENCY);

  jobs.sort((a, b) => `${a.company} ${a.title}`.localeCompare(`${b.company} ${b.title}`));
  const limited = Number.isFinite(limit) ? jobs.slice(0, limit) : jobs;

  const errList = [...errors];
  if (unknownProfileKeys.length) {
    errList.push({
      type: 'unknown_profile',
      keys: unknownProfileKeys,
      allowed: Object.keys(JOB_AREA_PROFILES),
    });
  }
  if (profileMode === 'fallback_yaml_all_keys_unknown') {
    errList.push({
      type: 'profiles_invalid',
      message:
        'Ninguna clave de perfil válida; se aplicó el title_filter completo de portals.yml.',
      keys: profileKeys,
    });
  }

  const profileLabels = profileKeys
    .filter((k) => JOB_AREA_PROFILES[k])
    .map((k) => ({ key: k, label: JOB_AREA_PROFILES[k].label }));

  console.log(
    JSON.stringify({
      ok: true,
      portals_file: portalsPath,
      count: limited.length,
      jobs: limited,
      errors: errList,
      area_profiles:
        profileKeys.length && profileMode === 'area_union'
          ? {
              keys: profileKeys.filter((k) => JOB_AREA_PROFILES[k]),
              labels: profileLabels,
              mode: profileMode,
            }
          : profileKeys.length
            ? { keys: [], labels: [], mode: profileMode || 'none' }
            : null,
    })
  );
}

main().catch(err => {
  console.log(JSON.stringify({ ok: false, error: err.message, jobs: [], errors: [] }));
  process.exit(1);
});
