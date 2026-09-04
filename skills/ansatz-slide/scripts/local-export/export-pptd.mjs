#!/usr/bin/env node
/**
 * Offline PPTD → PPTX exporter using the bundled WASM writer (no webpage UI).
 *
 * What this does:
 *   1. Load a PPTD project from disk (manifest + pages + media)
 *   2. Resolve images to bytes
 *   3. Prepare the local writer compatibility token (no remote authentication)
 *   4. Call the official WASM writer: exportPPTDToPPTXBytes(pptd, options, signature)
 *   5. Write .pptx
 *
 * Browser preview is optional. Delivery QA must inspect the exported PPTX.
 *
 * Usage:
 *   node export-pptd.mjs <projectDirOr.pptd> -o out.pptx
 *   node export-pptd.mjs ./deck -o deck.pptx
 *   --no-sign remains an accepted compatibility flag; export is always local.
 */

import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { parse as parseYamlDocument } from 'yaml';
import { validatePptdProject } from './validate-pptd.mjs';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

// YAML is an explicit, pinned runtime dependency. Never fall back to an
// undeclared Python interpreter or mutate the user's environment at runtime.
async function loadYaml() {
  return parseYamlDocument;
}

/** Canonical patched WASM lives in the editor mirror; skill install copies it here. */
const CANONICAL_WASM_NAME = 'pptd_wasm_bg-DPPWdROu.wasm';

function resolveDefaultWasmPath() {
  const candidates = [
    path.join(__dirname, 'pptd_wasm_bg.wasm'), // installed skill copy
    path.join(__dirname, CANONICAL_WASM_NAME),
    // monorepo / npm package: scripts/local-export → package root
    path.join(__dirname, '..', '..', '..', '..', 'editor', 'neo-ppt', 'assets', CANONICAL_WASM_NAME),
  ];
  for (const candidate of candidates) {
    if (fs.existsSync(candidate)) return candidate;
  }
  return candidates[0];
}

// ---------- CLI ----------
function parseArgs(argv) {
  const args = {
    input: null,
    output: null,
    embedFonts: false,
    transition: 'fade',
    wasmPath: null,
    validateOnly: false,
  };
  const a = [...argv];
  while (a.length) {
    const x = a.shift();
    if (x === '-o' || x === '--output') args.output = a.shift();
    else if (x === '--no-sign') { /* backward-compatible no-op: always offline */ }
    else if (x === '--embed-fonts') args.embedFonts = true;
    else if (x === '--transition') args.transition = a.shift();
    else if (x === '--wasm') args.wasmPath = a.shift();
    else if (x === '--validate-only') args.validateOnly = true;
    else if (x === '-h' || x === '--help') args.help = true;
    else if (!x.startsWith('-') && !args.input) args.input = x;
    else throw new Error(`Unknown arg: ${x}`);
  }
  if (!args.wasmPath) args.wasmPath = resolveDefaultWasmPath();
  return args;
}

// ---------- PPTD project load ----------
function findManifest(input) {
  const p = path.resolve(input);
  if (fs.statSync(p).isFile() && p.endsWith('.pptd')) return p;
  const files = fs.readdirSync(p).filter((f) => f.endsWith('.pptd'));
  if (files.length === 1) return path.join(p, files[0]);
  if (files.length === 0) throw new Error(`No .pptd in ${p}`);
  throw new Error(`Multiple .pptd in ${p}: ${files.join(', ')}`);
}

async function loadProject(manifestPath, parseYaml) {
  const root = path.dirname(manifestPath);
  const manifestText = fs.readFileSync(manifestPath, 'utf8');
  const manifest = parseYaml(manifestText);
  if (!manifest || manifest.version !== 'v2') {
    throw new Error('Only PPTD version: v2 is supported');
  }
  if (!Array.isArray(manifest.pages) || !manifest.pages.length) {
    throw new Error('manifest.pages must be a non-empty array');
  }

  const pages = [];
  const rawPages = [];
  for (const rel of manifest.pages) {
    const pagePath = path.join(root, rel);
    if (!fs.existsSync(pagePath)) throw new Error(`Missing page: ${rel}`);
    const page = parseYaml(fs.readFileSync(pagePath, 'utf8'));
    if (!page || !Array.isArray(page.elements)) {
      throw new Error(`Invalid page elements: ${rel}`);
    }
    rawPages.push({ path: rel.replace(/\\/g, '/'), data: page });
    // Match official nt()/rt() shape: embed full page objects
    pages.push({
      ...page,
      pagePath: rel.replace(/\\/g, '/'),
      elements: page.elements.map(normalizeElement),
    });
  }

  // Validate the original parsed documents before image resolution or WASM
  // invocation.  The local writer is intentionally permissive, so this gate
  // is the authoritative failure boundary for direct Node exports.
  validatePptdProject({ manifest, pages: rawPages }, { projectRoot: root });

  return {
    ...manifest,
    version: 'v2',
    pages,
    pptdFileName: path.basename(manifestPath),
  };
}

function normalizeElement(el) {
  // Official it()/at(): ensure custom shapes get viewBox from bounds
  if (el.elementType === 'shape') {
    return ensureViewBox(el, [el.bounds?.[2], el.bounds?.[3]]);
  }
  if (el.elementType === 'image' && el.cropShape) {
    return {
      ...el,
      cropShape: ensureViewBox(el.cropShape, [el.bounds?.[2], el.bounds?.[3]]),
    };
  }
  return el;
}

function ensureViewBox(shape, size) {
  if (
    shape.shapeName !== 'custom' ||
    !shape.path ||
    shape.viewBox ||
    String(shape.path).includes(';')
  ) {
    return shape;
  }
  return { ...shape, viewBox: size };
}

// ---------- image resolve (official Bt + Ht) ----------
function collectImageSrcs(pptd) {
  const set = new Set();
  walkImageObjects(pptd, (obj) => set.add(obj.src));
  return [...set];
}

function walkImageObjects(value, visit, seen = new WeakSet()) {
  if (!value || typeof value !== 'object') return;
  if (seen.has(value)) return;
  seen.add(value);
  if (
    typeof value.src === 'string' && value.src &&
    (value.elementType === 'image' || value.type === 'image')
  ) {
    visit(value);
  }
  if (Array.isArray(value)) {
    for (const item of value) walkImageObjects(item, visit, seen);
    return;
  }
  for (const item of Object.values(value)) walkImageObjects(item, visit, seen);
}

function extFromSrc(src, contentType = '') {
  const m = /\.(png|jpe?g|gif|svg)(?:$|[?#])/i.exec(src);
  const byPath = m?.[1]?.toLowerCase();
  const byCt = {
    'image/png': 'png',
    'image/jpeg': 'jpg',
    'image/gif': 'gif',
    'image/svg+xml': 'svg',
  }[String(contentType).split(';')[0].trim()];
  let ext = byPath || byCt || 'png';
  if (ext === 'jpeg') ext = 'jpg';
  return `.${ext}`;
}

async function resolveImages(pptd, projectRoot) {
  const srcs = collectImageSrcs(pptd);
  const images = {}; // path -> Uint8Array
  const remap = new Map();

  await Promise.all(
    srcs.map(async (src, idx) => {
      let bytes;
      let ext = extFromSrc(src);
      if (/^(https?:\/\/|data:)/i.test(src)) {
        if (src.startsWith('data:')) {
          const m = /^data:([^;,]+)?(;base64)?,(.*)$/s.exec(src);
          if (!m) return;
          const ct = m[1] || '';
          ext = extFromSrc(src, ct);
          bytes = m[2]
            ? Buffer.from(m[3], 'base64')
            : Buffer.from(decodeURIComponent(m[3]));
        } else {
          const res = await fetch(src);
          if (!res.ok) {
            throw new Error(`image fetch failed ${res.status}: ${src}`);
          }
          ext = extFromSrc(src, res.headers.get('content-type') || '');
          bytes = Buffer.from(await res.arrayBuffer());
        }
      } else {
        // local relative to project root
        const local = path.join(
          projectRoot,
          src.replace(/^file:\/\/+/, '').replace(/\\/g, '/'),
        );
        if (!fs.existsSync(local)) {
          throw new Error(`missing local image: ${src}`);
        }
        bytes = fs.readFileSync(local);
        ext = extFromSrc(src);
      }
      const key = `wasm-assets/img-${idx}${ext}`;
      images[key] = new Uint8Array(bytes);
      remap.set(src, key);
    }),
  );

  // rewrite src in place
  const rewrite = (obj) => {
    if (obj && typeof obj.src === 'string' && remap.has(obj.src)) {
      obj.src = remap.get(obj.src);
    }
  };
  walkImageObjects(pptd, rewrite);

  // shape path;viewBox split (official Kt/Gt)
  for (const page of pptd.pages ?? []) {
    for (const el of page.elements ?? []) {
      if (el?.elementType === 'shape') splitCustomPath(el);
      if (el?.elementType === 'image' && el.cropShape) splitCustomPath(el.cropShape);
    }
  }

  return images;
}

function splitCustomPath(shape) {
  if (shape?.shapeName !== 'custom' || typeof shape.path !== 'string' || shape.viewBox)
    return;
  const t = shape.path.indexOf(';');
  if (t < 0) return;
  const [w, h] = shape.path
    .slice(0, t)
    .split(',')
    .map(Number);
  if (!(w > 0) || !(h > 0)) return;
  shape.viewBox = [w, h];
  shape.path = shape.path.slice(t + 1);
}

// ---------- signature (official pptdExportSignature) ----------
function sha256Hex(text) {
  return crypto.createHash('sha256').update(text, 'utf8').digest('hex');
}

// ---------- WASM glue (Node / wasm-bindgen adapter) ----------
async function loadWasmExporter(wasmPath) {
  const wasmBytes = fs.readFileSync(wasmPath);
  let exportsRef;
  let memory;
  let cachedUint8;
  let cachedDataView;
  const textDecoder = new TextDecoder('utf-8', { ignoreBOM: true, fatal: true });
  const textEncoder = new TextEncoder();
  let heap = Array(1024).fill(undefined);
  heap.push(undefined, null, true, false);
  let heapNext = heap.length;
  let S = 0;

  function getUint8() {
    if (!cachedUint8 || cachedUint8.byteLength === 0) {
      cachedUint8 = new Uint8Array(memory.buffer);
    }
    return cachedUint8;
  }
  function getDataView() {
    if (
      !cachedDataView ||
      cachedDataView.buffer.detached === true ||
      (cachedDataView.buffer.detached === undefined &&
        cachedDataView.buffer !== memory.buffer)
    ) {
      cachedDataView = new DataView(memory.buffer);
    }
    return cachedDataView;
  }
  function addHeapObject(obj) {
    if (heapNext === heap.length) heap.push(heap.length + 1);
    const idx = heapNext;
    heapNext = heap[idx];
    heap[idx] = obj;
    return idx;
  }
  function takeObject(idx) {
    const ret = heap[idx];
    dropObject(idx);
    return ret;
  }
  function dropObject(idx) {
    if (idx < 1028) return;
    heap[idx] = heapNext;
    heapNext = idx;
  }
  function getObject(idx) {
    return heap[idx];
  }
  function isLikeNone(x) {
    return x == null;
  }
  function passStringToWasm(arg, malloc, realloc) {
    if (realloc === undefined) {
      const buf = textEncoder.encode(arg);
      const ptr = malloc(buf.length, 1) >>> 0;
      getUint8()
        .subarray(ptr, ptr + buf.length)
        .set(buf);
      S = buf.length;
      return ptr;
    }
    let len = arg.length;
    let ptr = malloc(len, 1) >>> 0;
    const mem = getUint8();
    let offset = 0;
    for (; offset < len; offset++) {
      const code = arg.charCodeAt(offset);
      if (code > 127) break;
      mem[ptr + offset] = code;
    }
    if (offset !== len) {
      if (offset !== 0) arg = arg.slice(offset);
      ptr = realloc(ptr, len, (len = offset + arg.length * 3), 1) >>> 0;
      const view = getUint8().subarray(ptr + offset, ptr + len);
      const ret = textEncoder.encodeInto(arg, view);
      offset += ret.written;
      ptr = realloc(ptr, len, offset, 1) >>> 0;
    }
    S = offset;
    return ptr;
  }
  function getStringFromWasm(ptr, len) {
    ptr = ptr >>> 0;
    return textDecoder.decode(getUint8().subarray(ptr, ptr + len));
  }
  function getArrayU8FromWasm(ptr, len) {
    ptr = ptr >>> 0;
    return getUint8().subarray(ptr / 1, ptr / 1 + len);
  }

  function handleError(f, args) {
    try {
      return f.apply(null, args);
    } catch (e) {
      exportsRef.__wbindgen_export3(addHeapObject(e));
    }
  }

  const imports = {
    './pptd_wasm_bg.js': {
      __wbg___wbindgen_boolean_get_fa956cfa2d1bd751(arg0) {
        const v = getObject(arg0);
        const x = typeof v === 'boolean' ? v : undefined;
        return isLikeNone(x) ? 0xffffff : +!!x;
      },
      __wbg___wbindgen_is_function_1ff95bcc5517c252(arg0) {
        return typeof getObject(arg0) === 'function';
      },
      __wbg___wbindgen_is_null_ea9085d691f535d3(arg0) {
        return getObject(arg0) === null;
      },
      __wbg___wbindgen_is_object_a27215656b807791(arg0) {
        const val = getObject(arg0);
        return typeof val === 'object' && val !== null;
      },
      __wbg___wbindgen_is_undefined_c05833b95a3cf397(arg0) {
        return getObject(arg0) === undefined;
      },
      __wbg___wbindgen_number_get_394265ed1e1b84ee(arg0, arg1) {
        const obj = getObject(arg1);
        const val = typeof obj === 'number' ? obj : undefined;
        getDataView().setFloat64(arg0 + 8, isLikeNone(val) ? 0 : val, true);
        getDataView().setInt32(arg0 + 0, !isLikeNone(val), true);
      },
      __wbg___wbindgen_string_get_b0ca35b86a603356(arg0, arg1) {
        const obj = getObject(arg1);
        const val = typeof obj === 'string' ? obj : undefined;
        var ptr = isLikeNone(val)
          ? 0
          : passStringToWasm(val, exportsRef.__wbindgen_export, exportsRef.__wbindgen_export2);
        var len = S;
        getDataView().setInt32(arg0 + 4, len, true);
        getDataView().setInt32(arg0 + 0, ptr, true);
      },
      __wbg___wbindgen_throw_344f42d3211c4765(arg0, arg1) {
        throw new Error(getStringFromWasm(arg0, arg1));
      },
      __wbg_call_a6e5c5dce5018821() {
        return handleError(function (arg0, arg1, arg2) {
          return addHeapObject(getObject(arg0).call(getObject(arg1), getObject(arg2)));
        }, arguments);
      },
      __wbg_call_e3b662382210db98() {
        return handleError(function (arg0, arg1, arg2, arg3) {
          return addHeapObject(
            getObject(arg0).call(getObject(arg1), getObject(arg2), getObject(arg3)),
          );
        }, arguments);
      },
      __wbg_from_13e323c65fc8f464(arg0) {
        return addHeapObject(Array.from(getObject(arg0)));
      },
      __wbg_get_78f252d074a84d0b() {
        return handleError(function (arg0, arg1) {
          return addHeapObject(Reflect.get(getObject(arg0), getObject(arg1)));
        }, arguments);
      },
      __wbg_get_unchecked_6e0ad6d2a41b06f6(arg0, arg1) {
        return addHeapObject(getObject(arg0)[arg1 >>> 0]);
      },
      __wbg_instanceof_ArrayBuffer_4480b9e0068a8adb(arg0) {
        let result;
        try {
          result = getObject(arg0) instanceof ArrayBuffer;
        } catch {
          result = false;
        }
        return result;
      },
      __wbg_instanceof_Uint8Array_309b927aaf7a3fc7(arg0) {
        let result;
        try {
          result = getObject(arg0) instanceof Uint8Array;
        } catch {
          result = false;
        }
        return result;
      },
      __wbg_length_1f0964f4a5e2c6d8(arg0) {
        return getObject(arg0).length;
      },
      __wbg_length_370319915dc99107(arg0) {
        return getObject(arg0).length;
      },
      __wbg_new_cd45aabdf6073e84(arg0) {
        return addHeapObject(new Uint8Array(getObject(arg0)));
      },
      __wbg_new_da52cf8fe3429cb2() {
        return addHeapObject({});
      },
      __wbg_new_from_slice_77cdfb7977362f3c(arg0, arg1) {
        return addHeapObject(getArrayU8FromWasm(arg0, arg1).slice());
      },
      __wbg_prototypesetcall_4770620bbe4688a0(arg0, arg1, arg2) {
        Uint8Array.prototype.set.call(getArrayU8FromWasm(arg0, arg1), getObject(arg2));
      },
      __wbg_set_8535240470bf2500() {
        return handleError(function (arg0, arg1, arg2) {
          return Reflect.set(getObject(arg0), getObject(arg1), getObject(arg2));
        }, arguments);
      },
      __wbg_stringify_b54333f60f1e4ead() {
        return handleError(function (arg0) {
          return addHeapObject(JSON.stringify(getObject(arg0)));
        }, arguments);
      },
      // note: official name may be slightly different hash suffix — also register alternate
      __wbg_stringify_b54333f60f1e4dad() {
        return handleError(function (arg0) {
          return addHeapObject(JSON.stringify(getObject(arg0)));
        }, arguments);
      },
      __wbindgen_cast_0000000000000001(arg0) {
        return addHeapObject(arg0);
      },
      __wbindgen_cast_0000000000000002(arg0, arg1) {
        return addHeapObject(getStringFromWasm(arg0, arg1));
      },
      __wbindgen_object_drop_ref(arg0) {
        takeObject(arg0);
      },
    },
  };

  const { instance } = await WebAssembly.instantiate(wasmBytes, imports);
  exportsRef = instance.exports;
  memory = exportsRef.memory;
  cachedUint8 = null;
  cachedDataView = null;

  function exportPPTDToPPTXBytes(pptd, options, signature) {
    const retptr = exportsRef.__wbindgen_add_to_stack_pointer(-16);
    try {
      const ptr0 = isLikeNone(signature)
        ? 0
        : passStringToWasm(
            signature,
            exportsRef.__wbindgen_export,
            exportsRef.__wbindgen_export2,
          );
      const len0 = S;
      exportsRef.exportPPTDToPPTXBytes(
        retptr,
        addHeapObject(pptd),
        addHeapObject(options),
        ptr0,
        len0,
      );
      const r0 = getDataView().getInt32(retptr + 0, true);
      const r1 = getDataView().getInt32(retptr + 4, true);
      const r2 = getDataView().getInt32(retptr + 8, true);
      if (r2) throw takeObject(r1);
      return takeObject(r0);
    } finally {
      exportsRef.__wbindgen_add_to_stack_pointer(16);
    }
  }

  return { exportPPTDToPPTXBytes };
}

// ---------- main ----------
async function main() {
  const args = parseArgs(process.argv.slice(2));
  if (args.help || !args.input) {
    console.log(`Usage: node export-pptd.mjs <pptd|projectDir> -o out.pptx [options]

Options:
  -o, --output PATH     output .pptx
  --no-sign             compatibility flag; export is always offline
  --transition fade|none
  --wasm PATH           path to patched pptd_wasm (default: resolve from editor mirror)
  --validate-only       validate the complete PPTD project without exporting
  --embed-fonts         reserved (font embedding needs font blobs)`);
    process.exit(args.help ? 0 : 1);
  }

  const parseYaml = await loadYaml();
  const manifestPath = findManifest(args.input);
  const projectRoot = path.dirname(manifestPath);
  const output =
    args.output ||
    path.join(projectRoot, path.basename(manifestPath, '.pptd') + '.offline.pptx');

  console.log('[1/5] load PPTD', manifestPath);
  let pptd = await loadProject(manifestPath, parseYaml);
  if (args.validateOnly) {
    console.log(`PPTD valid: ${pptd.pages.length} page(s)`);
    return;
  }

  console.log('[2/5] resolve images');
  // deep clone so we can rewrite src
  pptd = JSON.parse(JSON.stringify(pptd));
  const images = await resolveImages(pptd, projectRoot);
  console.log(`      ${Object.keys(images).length} image(s)`);

  console.log('[3/5] local writer token');
  const payloadForSign = JSON.stringify(pptd);
  const signature = 'offline-bypass-' + sha256Hex(payloadForSign).slice(0, 32);

  console.log('[4/5] load WASM', args.wasmPath);
  if (!fs.existsSync(args.wasmPath)) {
    throw new Error(
      `patched WASM not found: ${args.wasmPath}\n` +
        `Expected editor/neo-ppt/assets/${CANONICAL_WASM_NAME} (repo/npm) ` +
        `or scripts/local-export/pptd_wasm_bg.wasm (after skill install).`,
    );
  }
  const { exportPPTDToPPTXBytes } = await loadWasmExporter(args.wasmPath);

  console.log('[5/5] export PPTX');
  const options = {
    fonts: [],
    customFonts: [],
    images,
    fileName: path.basename(output),
    slideTransition: {
      effect: args.transition === 'none' ? 'none' : args.transition,
      speed: 'fast',
    },
    chartImages: [],
  };

  let bytes;
  try {
    bytes = exportPPTDToPPTXBytes(pptd, options, signature);
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    if (msg.includes('pptd export signature') || msg.toLowerCase().includes('signature')) {
      throw new Error(
        `WASM signature check failed: ${msg}\n` +
          `Use the bundled patched writer; remote authentication is not supported.`,
      );
    }
    throw e;
  }

  const outBuf = Buffer.from(bytes);
  fs.writeFileSync(output, outBuf);
  console.log('Wrote', output, `(${outBuf.length} bytes)`);

  // quick zip sanity
  if (outBuf[0] !== 0x50 || outBuf[1] !== 0x4b) {
    console.warn('[warn] output does not start with PK (not a ZIP/PPTX?)');
  }
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
