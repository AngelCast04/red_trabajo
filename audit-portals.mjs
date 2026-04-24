#!/usr/bin/env node
/**
 * audit-portals.mjs — Prueba APIs detectables en portals.yml y desactiva fallidas.
 *
 *   node audit-portals.mjs           # informe
 *   node audit-portals.mjs --apply   # enabled: false + comentario # audit:
 */

import { readFileSync, writeFileSync, existsSync } from 'fs';
import yaml from 'js-yaml';
import { detectApi, fetchBoardJson } from './ats-detect.mjs';

const PORTALS_PATH = 'portals.yml';
const CONCURRENCY = 10;

async function parallelMap(items, limit, fn) {
  const out = new Array(items.length);
  let i = 0;
  async function worker() {
    while (i < items.length) {
      const idx = i++;
      out[idx] = await fn(items[idx], idx);
    }
  }
  await Promise.all(Array.from({ length: Math.min(limit, items.length) }, () => worker()));
  return out;
}

/**
 * Parte tracked_companies en bloques que empiezan en columna con "  - name:"
 */
function splitTrackedBlocks(text) {
  const marker = '\ntracked_companies:';
  const ti = text.indexOf(marker);
  if (ti === -1) return { head: text, blocks: [] };

  const afterKey = text.indexOf('\n', ti + marker.length) + 1;
  const head = text.slice(0, afterKey);
  const body = text.slice(afterKey);

  const indices = [];
  const re = /^  - name:/gm;
  let m;
  while ((m = re.exec(body)) !== null) indices.push(m.index);

  const blocks = [];
  for (let i = 0; i < indices.length; i++) {
    const a = indices[i];
    const b = i + 1 < indices.length ? indices[i + 1] : body.length;
    blocks.push(body.slice(a, b));
  }
  return { head, blocks };
}

function joinTrackedBlocks(head, blocks) {
  return head + blocks.join('');
}

function parseNameFromBlock(block) {
  const m = block.match(/^  - name:\s*(.+)$/m);
  return m ? m[1].trim() : null;
}

function disableBlock(block, dateStr) {
  let b = block;
  if (!/^([ \t]*)enabled:\s*false/m.test(b)) {
    b = b.replace(/^([ \t]*)enabled:\s*true\s*$/m, '$1enabled: false');
  }
  if (/# audit: API/i.test(b)) return b;
  const lines = b.trimEnd().split('\n');
  const ins = `    # audit: desactivado ${dateStr} — la API del ATS no respondió (404/403/timeout)`;
  return lines.join('\n') + '\n' + ins + '\n';
}

async function main() {
  const apply = process.argv.includes('--apply');
  if (!existsSync(PORTALS_PATH)) {
    console.error('No se encuentra portals.yml');
    process.exit(1);
  }

  const raw = readFileSync(PORTALS_PATH, 'utf-8');
  const config = yaml.load(raw);
  const companies = config.tracked_companies || [];

  const active = companies.map((c, index) => ({ c, index })).filter(({ c }) => c.enabled !== false);

  const results = await parallelMap(active, CONCURRENCY, async ({ c }) => {
    const api = detectApi(c);
    if (!api) {
      return { name: c.name, ok: true, reason: 'sin_api' };
    }
    try {
      await fetchBoardJson(api);
      return { name: c.name, ok: true, reason: 'ok' };
    } catch (e) {
      return { name: c.name, ok: false, error: e.message };
    }
  });

  const failed = results.filter(r => !r.ok);
  const ok = results.filter(r => r.ok && r.reason === 'ok');
  const noApi = results.filter(r => r.ok && r.reason === 'sin_api');

  console.log(`\n━━━ Auditoría ATS ━━━`);
  console.log(`Empresas activas analizadas: ${active.length}`);
  console.log(`API OK:                    ${ok.length}`);
  console.log(`Sin API en escáner:        ${noApi.length}`);
  console.log(`API con error:             ${failed.length}`);

  if (failed.length) {
    console.log('\nFallos:');
    for (const f of failed) {
      console.log(`  · ${f.name}: ${f.error}`);
    }
  }

  if (!apply) {
    console.log('\n→ node audit-portals.mjs --apply  (desactiva las que fallen)\n');
    return;
  }

  if (!failed.length) {
    console.log('\nNada que desactivar.\n');
    return;
  }

  const failSet = new Set(failed.map(f => f.name));
  const dateStr = new Date().toISOString().slice(0, 10);
  const { head, blocks } = splitTrackedBlocks(raw);
  if (!blocks.length) {
    console.error('No se pudo partir tracked_companies');
    process.exit(1);
  }

  let changed = 0;
  const newBlocks = blocks.map(block => {
    const name = parseNameFromBlock(block);
    if (name && failSet.has(name)) {
      changed++;
      return disableBlock(block, dateStr);
    }
    return block;
  });

  if (changed !== failSet.size) {
    console.warn(
      `Aviso: bloques tocados (${changed}) ≠ empresas fallidas (${failSet.size}). Revise nombres exactos en YAML.`
    );
  }

  writeFileSync(PORTALS_PATH, joinTrackedBlocks(head, newBlocks), 'utf-8');
  console.log(`\n✓ ${PORTALS_PATH} actualizado: ${changed} empresa(s) con enabled: false.\n`);
}

main().catch(e => {
  console.error(e);
  process.exit(1);
});
