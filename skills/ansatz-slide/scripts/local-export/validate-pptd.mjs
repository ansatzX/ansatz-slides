#!/usr/bin/env node
/**
 * Strict PPTD v2 validator.
 *
 * This is deliberately separate from the renderer/WASM writer.  The writer is
 * permissive in a number of places (for example, an unknown chart encoding can
 * become an empty chart), while a PPTD author needs a deterministic failure
 * before any PPTX or image artifact is written.
 *
 * The module can be imported by the local exporter, or run as a small JSON
 * protocol helper from the Python browser/image exporters:
 *
 *   echo '{"manifest": {...}, "pages": [{"path":"...","data":{...}}]}' |
 *     node validate-pptd.mjs --stdin
 */

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

const ELEMENT_TYPES = new Set([
  'text', 'shape', 'line', 'image', 'icon', 'table', 'chart',
]);
const LINE_STYLES = new Set(['solid', 'dash', 'dot']);
const H_ALIGN = new Set(['left', 'center', 'right', 'justify', 'distributed']);
const V_ALIGN = new Set(['top', 'middle', 'bottom']);
const SHAPE_NAMES_FALLBACK = new Set([
  'rect', 'roundRect', 'ellipse', 'triangle', 'rtTriangle', 'parallelogram',
  'trapezoid', 'nonIsoscelesTrapezoid', 'diamond', 'pentagon', 'hexagon',
  'heptagon', 'octagon', 'decagon', 'dodecagon', 'plus', 'homePlate',
  'chevron', 'pie', 'pieWedge', 'arc', 'chord', 'blockArc', 'teardrop',
  'frame', 'halfFrame', 'corner', 'diagStripe', 'foldedCorner', 'donut',
  'noSmoking', 'heart', 'lightningBolt', 'sun', 'moon', 'cloud',
  'smileyFace', 'bevel', 'can', 'cube', 'funnel', 'gear6', 'gear9', 'plaque',
  'doubleWave', 'wave', 'lineInv', 'round1Rect', 'round2DiagRect',
  'round2SameRect', 'snip1Rect', 'snip2DiagRect', 'snip2SameRect',
  'snipRoundRect', 'star4', 'star5',
]);
const ANIMATION_EFFECTS = new Set([
  'appear', 'fade-in', 'fly-in', 'zoom-in', 'wipe-in', 'float-in', 'peek-in',
  'rise-in', 'pulse', 'grow-shrink', 'spin', 'teeter', 'fill-color',
  'transparency', 'color-pulse', 'disappear', 'fade-out', 'fly-out',
  'zoom-out', 'wipe-out', 'float-out', 'motion-path',
]);
const ANIMATION_TRIGGERS = new Set(['onClick', 'withPrevious', 'afterPrevious']);
const ANIMATION_DIRECTIONS = new Set(['up', 'down', 'left', 'right']);
const ANIMATION_EASINGS = new Set(['linear', 'ease-in', 'ease-out', 'ease-in-out']);
const ARROWS = new Set(['arrow', 'stealth', 'diamond', 'oval']);
const CHART_TYPES = new Set([
  'bar', 'line', 'area', 'scatter', 'bubble', 'candlestick', 'pie', 'radar',
  'waterfall', 'heatmap', 'treemap', 'sunburst', 'sankey',
]);
// These inputs are accepted by the upstream schema, but the bundled local
// writer was observed to emit missing marks or empty fallback charts. Reject
// them instead of silently producing a semantically different PPTX.
const UNSUPPORTED_LOCAL_CHART_TYPES = new Set([
  'candlestick', 'heatmap', 'treemap', 'sunburst', 'sankey',
]);
const CARTESIAN_TYPES = new Set([
  'bar', 'line', 'area', 'scatter', 'bubble', 'candlestick', 'waterfall', 'heatmap',
]);
const SIMPLE_MIX_TYPES = new Set(['bar', 'line', 'area', 'scatter', 'bubble']);
const EXCLUSIVE_TYPES = new Set([
  'pie', 'radar', 'waterfall', 'heatmap', 'treemap', 'sunburst', 'sankey',
]);
const NUMBER_FORMATS = new Set(['0', '0.0', '0%', '0.0%', '#,##0', '0.0E+00']);
const RICH_TAGS = new Set(['p', 'span', 'strong', 'em', 'u', 's', 'sup', 'sub', 'a', 'ul', 'ol', 'li', 'br']);

let cachedShapeNames;

function loadShapeNames() {
  if (cachedShapeNames) return cachedShapeNames;
  cachedShapeNames = new Set(SHAPE_NAMES_FALLBACK);
  // The reference is shipped with the skill.  Reading it here keeps the
  // validator aligned with the actual 177-shape library without duplicating a
  // 177-item list in executable code.  The fallback keeps common shapes usable
  // in a minimal copied installation.
  const candidates = [
    path.resolve(__dirname, '../../reference/shapes.md'),
    path.resolve(__dirname, '../reference/shapes.md'),
  ];
  for (const candidate of candidates) {
    try {
      const text = fs.readFileSync(candidate, 'utf8');
      for (const match of text.matchAll(/^\|\s*([A-Za-z][A-Za-z0-9]*)\s*\|/gm)) {
        if (match[1] !== 'shapeName') cachedShapeNames.add(match[1]);
      }
      if (cachedShapeNames.size > SHAPE_NAMES_FALLBACK.size) break;
    } catch {
      // A skill install can be intentionally minimal.  The fallback is still
      // stricter than accepting arbitrary names.
    }
  }
  cachedShapeNames.add('custom');
  return cachedShapeNames;
}

function isObject(value) {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}

function isFiniteNumber(value) {
  return typeof value === 'number' && Number.isFinite(value);
}

function isInteger(value) {
  return isFiniteNumber(value) && Number.isInteger(value);
}

function own(value, key) {
  return Object.prototype.hasOwnProperty.call(value, key);
}

function pathLabel(value) {
  return value || '$';
}

function safeRelativePath(value) {
  if (typeof value !== 'string' || !value.trim()) return false;
  if (path.isAbsolute(value) || /^[A-Za-z]:[\\/]/.test(value)) return false;
  const pieces = value.replaceAll('\\', '/').split('/');
  return !pieces.includes('..') && !value.includes('\0');
}

function valueType(value) {
  if (value === null) return 'null';
  if (Array.isArray(value)) return 'array';
  return typeof value;
}

function makeContext(options = {}) {
  return {
    errors: [],
    root: options.projectRoot ? path.resolve(options.projectRoot) : null,
    checkFiles: options.checkFiles !== false,
    themeColors: new Set(options.themeColors || []),
    textStyles: new Set(options.textStyles || []),
    tableStyles: new Set(options.tableStyles || []),
    pageSize: options.pageSize || null,
  };
}

function error(ctx, at, message) {
  if (ctx.errors.length < 200) ctx.errors.push(`${pathLabel(at)}: ${message}`);
}

function unknownKeys(value, allowed, at, ctx) {
  if (!isObject(value)) return;
  for (const key of Object.keys(value)) {
    if (!allowed.has(key)) error(ctx, at, `unknown field ${JSON.stringify(key)}`);
  }
}

function required(ctx, value, key, at) {
  if (!own(value, key)) {
    error(ctx, at, `missing required field ${JSON.stringify(key)}`);
    return false;
  }
  return true;
}

function expectObject(value, at, ctx) {
  if (!isObject(value)) {
    error(ctx, at, `expected object, got ${valueType(value)}`);
    return false;
  }
  return true;
}

function expectArray(value, at, ctx, min = null) {
  if (!Array.isArray(value)) {
    error(ctx, at, `expected array, got ${valueType(value)}`);
    return false;
  }
  if (min !== null && value.length < min) {
    error(ctx, at, `expected at least ${min} item(s), got ${value.length}`);
  }
  return true;
}

function expectString(value, at, ctx, nonEmpty = false) {
  if (typeof value !== 'string' || (nonEmpty && !value.trim())) {
    error(ctx, at, nonEmpty ? 'expected a non-empty string' : 'expected a string');
    return false;
  }
  return true;
}

function expectBoolean(value, at, ctx) {
  if (typeof value !== 'boolean') {
    error(ctx, at, 'expected a boolean');
    return false;
  }
  return true;
}

function expectNumber(value, at, ctx, { min = null, max = null, exclusiveMin = false, exclusiveMax = false } = {}) {
  if (!isFiniteNumber(value)) {
    error(ctx, at, 'expected a finite number');
    return false;
  }
  if (min !== null && (exclusiveMin ? value <= min : value < min)) {
    error(ctx, at, `must be ${exclusiveMin ? '>' : '>='} ${min}`);
  }
  if (max !== null && (exclusiveMax ? value >= max : value > max)) {
    error(ctx, at, `must be ${exclusiveMax ? '<' : '<='} ${max}`);
  }
  return true;
}

function expectEnum(value, values, at, ctx) {
  if (!values.has(value)) {
    error(ctx, at, `invalid value ${JSON.stringify(value)}; expected one of ${[...values].join(', ')}`);
    return false;
  }
  return true;
}

function checkColor(value, at, ctx) {
  if (typeof value !== 'string') {
    error(ctx, at, 'color must be a HEX6/HEX8 string or a theme reference');
    return;
  }
  if (/^#[0-9a-f]{6}(?:[0-9a-f]{2})?$/i.test(value)) return;
  const theme = /^\$([A-Za-z_][A-Za-z0-9_-]*)$/.exec(value);
  if (theme) {
    if (!ctx.themeColors.has(theme[1])) {
      error(ctx, at, `unknown theme color ${JSON.stringify(value)}`);
    }
    return;
  }
  error(ctx, at, 'color must be HEX6 (#RRGGBB), HEX8 (#RRGGBBAA), or $themeKey');
}

function checkAnimationColor(value, at, ctx) {
  if (typeof value !== 'string' || !/^#?[0-9a-f]{6}$/i.test(value)) {
    error(ctx, at, 'animation color must be a 6-digit HEX value, with optional #');
  }
}

function checkFontFamily(value, at, ctx) {
  if (typeof value === 'string') {
    expectString(value, at, ctx, true);
    return;
  }
  if (!expectObject(value, at, ctx)) return;
  unknownKeys(value, new Set(['latin', 'ea']), at, ctx);
  required(ctx, value, 'latin', at);
  required(ctx, value, 'ea', at);
  expectString(value.latin, `${at}.latin`, ctx, true);
  expectString(value.ea, `${at}.ea`, ctx, true);
}

function checkAlign(value, at, ctx) {
  if (!expectArray(value, at, ctx)) return;
  if (value.length !== 2) error(ctx, at, 'alignment must contain [horizontal, vertical]');
  if (value.length > 0) expectEnum(value[0], H_ALIGN, `${at}[0]`, ctx);
  if (value.length > 1) expectEnum(value[1], V_ALIGN, `${at}[1]`, ctx);
}

function checkBorder(value, at, ctx) {
  if (!expectObject(value, at, ctx)) return;
  unknownKeys(value, new Set(['style', 'width', 'color']), at, ctx);
  if (own(value, 'style')) expectEnum(value.style, LINE_STYLES, `${at}.style`, ctx);
  if (own(value, 'width')) expectNumber(value.width, `${at}.width`, ctx, { min: 0, exclusiveMin: true });
  if (own(value, 'color')) checkColor(value.color, `${at}.color`, ctx);
}

function checkBorderSpec(value, at, ctx) {
  if (value === null) return;
  if (Array.isArray(value)) {
    if (value.length !== 2 && value.length !== 4) {
      error(ctx, at, 'border array must contain 2 or 4 entries');
    }
    value.forEach((item, index) => {
      if (item !== null) checkBorder(item, `${at}[${index}]`, ctx);
    });
    return;
  }
  checkBorder(value, at, ctx);
}

function checkShadow(value, at, ctx) {
  if (!expectObject(value, at, ctx)) return;
  unknownKeys(value, new Set(['blur', 'color', 'offset']), at, ctx);
  required(ctx, value, 'blur', at);
  required(ctx, value, 'color', at);
  if (own(value, 'blur')) expectNumber(value.blur, `${at}.blur`, ctx, { min: 0 });
  if (own(value, 'color')) checkColor(value.color, `${at}.color`, ctx);
  if (own(value, 'offset')) {
    if (expectArray(value.offset, `${at}.offset`, ctx) && value.offset.length === 2) {
      value.offset.forEach((item, index) => expectNumber(item, `${at}.offset[${index}]`, ctx));
    }
  }
}

function checkCrop(value, at, ctx) {
  if (!expectObject(value, at, ctx)) return;
  const keys = new Set(['left', 'top', 'right', 'bottom']);
  unknownKeys(value, keys, at, ctx);
  for (const key of keys) {
    if (own(value, key)) expectNumber(value[key], `${at}.${key}`, ctx);
  }
  const left = Number(value.left || 0);
  const right = Number(value.right || 0);
  const top = Number(value.top || 0);
  const bottom = Number(value.bottom || 0);
  if (left + right >= 1) error(ctx, at, 'left + right must be < 1');
  if (top + bottom >= 1) error(ctx, at, 'top + bottom must be < 1');
}

function checkGradient(value, at, ctx) {
  if (!expectObject(value, at, ctx)) return;
  unknownKeys(value, new Set(['type', 'gradientType', 'stops', 'angle']), at, ctx);
  if (value.type !== 'gradient') error(ctx, `${at}.type`, 'gradient fill must have type "gradient"');
  if (own(value, 'gradientType')) expectEnum(value.gradientType, new Set(['linear', 'radial']), `${at}.gradientType`, ctx);
  else error(ctx, at, 'missing required field "gradientType"');
  if (!expectArray(value.stops, `${at}.stops`, ctx, 2)) return;
  let previous = -Infinity;
  value.stops.forEach((stop, index) => {
    const stopAt = `${at}.stops[${index}]`;
    if (!expectObject(stop, stopAt, ctx)) return;
    unknownKeys(stop, new Set(['position', 'color']), stopAt, ctx);
    required(ctx, stop, 'position', stopAt);
    required(ctx, stop, 'color', stopAt);
    if (own(stop, 'position')) {
      expectNumber(stop.position, `${stopAt}.position`, ctx, { min: 0, max: 1 });
      if (isFiniteNumber(stop.position) && stop.position < previous) {
        error(ctx, `${stopAt}.position`, 'gradient stop positions must be non-decreasing');
      }
      if (isFiniteNumber(stop.position)) previous = stop.position;
    }
    if (own(stop, 'color')) checkColor(stop.color, `${stopAt}.color`, ctx);
  });
  if (own(value, 'angle')) expectNumber(value.angle, `${at}.angle`, ctx, { min: 0, max: 360, exclusiveMax: true });
}

function checkImageSrc(value, at, ctx) {
  if (!expectString(value, at, ctx, true)) return;
  if (/^data:[^,]+,/i.test(value) || /^https?:\/\//i.test(value)) return;
  if (!safeRelativePath(value)) {
    error(ctx, at, 'local image source must be a relative path inside the PPTD project');
    return;
  }
  if (ctx.root && ctx.checkFiles) {
    const resolved = path.resolve(ctx.root, value);
    try {
      if (!resolved.startsWith(`${ctx.root}${path.sep}`) || !fs.statSync(resolved).isFile()) {
        error(ctx, at, `local image file does not exist: ${value}`);
      }
    } catch {
      error(ctx, at, `local image file does not exist: ${value}`);
    }
  }
}

function checkFit(value, at, ctx) {
  if (!expectObject(value, at, ctx)) return;
  unknownKeys(value, new Set(['mode']), at, ctx);
  required(ctx, value, 'mode', at);
  if (own(value, 'mode')) expectEnum(value.mode, new Set(['fill', 'contain', 'cover']), `${at}.mode`, ctx);
}

function checkFill(value, at, ctx) {
  if (!expectObject(value, at, ctx)) return;
  if (value.type === 'solid') {
    unknownKeys(value, new Set(['type', 'color']), at, ctx);
    required(ctx, value, 'color', at);
    if (own(value, 'color')) checkColor(value.color, `${at}.color`, ctx);
    return;
  }
  if (value.type === 'gradient') {
    checkGradient(value, at, ctx);
    return;
  }
  if (value.type === 'image') {
    unknownKeys(value, new Set(['type', 'src', 'fit', 'crop', 'opacity']), at, ctx);
    required(ctx, value, 'src', at);
    if (own(value, 'src')) checkImageSrc(value.src, `${at}.src`, ctx);
    if (own(value, 'fit')) checkFit(value.fit, `${at}.fit`, ctx);
    if (own(value, 'crop')) checkCrop(value.crop, `${at}.crop`, ctx);
    if (own(value, 'opacity')) expectNumber(value.opacity, `${at}.opacity`, ctx, { min: 0, max: 1 });
    return;
  }
  error(ctx, `${at}.type`, 'fill type must be solid, gradient, or image');
}

function checkColorOrGradient(value, at, ctx) {
  if (typeof value === 'string') checkColor(value, at, ctx);
  else checkGradient(value, at, ctx);
}

function checkSeriesFill(value, at, ctx, { collection = false, nested = false, record = false } = {}) {
  if (typeof value === 'string' || (isObject(value) && value.type === 'gradient')) {
    checkColorOrGradient(value, at, ctx);
    return;
  }
  if (collection && Array.isArray(value)) {
    if (!value.length) error(ctx, at, 'fill collection must not be empty');
    value.forEach((item, index) => {
      if (nested && Array.isArray(item)) {
        if (!item.length) error(ctx, `${at}[${index}]`, 'fill level collection must not be empty');
        item.forEach((inner, innerIndex) => checkColorOrGradient(inner, `${at}[${index}][${innerIndex}]`, ctx));
      } else {
        checkColorOrGradient(item, `${at}[${index}]`, ctx);
      }
    });
    return;
  }
  if (record && isObject(value)) {
    for (const [key, item] of Object.entries(value)) {
      if (!key.trim()) error(ctx, at, 'fill record keys must be non-empty');
      checkColorOrGradient(item, `${at}.${key}`, ctx);
    }
    return;
  }
  error(ctx, at, 'series fill must be a color or gradient (image fills are not supported)');
}

function checkTextStyle(value, at, ctx, { cell = false, allowExtra = false } = {}) {
  if (!expectObject(value, at, ctx)) return;
  const keys = new Set([
    'color', 'fontSize', 'fontFamily', 'bold', 'italic', 'backgroundColor',
    'lineHeight', 'lineHeightPx', 'letterSpacing', 'marginTop',
  ]);
  if (cell) keys.add('fill');
  if (cell) keys.add('border');
  if (cell) keys.add('align');
  if (!allowExtra) unknownKeys(value, keys, at, ctx);
  if (own(value, 'color')) checkColor(value.color, `${at}.color`, ctx);
  if (own(value, 'fontSize')) expectNumber(value.fontSize, `${at}.fontSize`, ctx, { min: 0, exclusiveMin: true });
  if (own(value, 'fontFamily')) checkFontFamily(value.fontFamily, `${at}.fontFamily`, ctx);
  for (const key of ['bold', 'italic']) if (own(value, key)) expectBoolean(value[key], `${at}.${key}`, ctx);
  if (own(value, 'backgroundColor')) checkColor(value.backgroundColor, `${at}.backgroundColor`, ctx);
  if (own(value, 'lineHeight')) expectNumber(value.lineHeight, `${at}.lineHeight`, ctx, { min: 0, exclusiveMin: true });
  if (own(value, 'lineHeightPx')) expectNumber(value.lineHeightPx, `${at}.lineHeightPx`, ctx, { min: 0, exclusiveMin: true });
  if (own(value, 'letterSpacing')) expectNumber(value.letterSpacing, `${at}.letterSpacing`, ctx);
  if (own(value, 'marginTop')) expectNumber(value.marginTop, `${at}.marginTop`, ctx);
  if (cell) {
    if (own(value, 'fill')) checkFill(value.fill, `${at}.fill`, ctx);
    if (own(value, 'border')) checkBorderSpec(value.border, `${at}.border`, ctx);
    if (own(value, 'align')) checkAlign(value.align, `${at}.align`, ctx);
  }
}

function checkStyleRef(value, at, ctx, available, kind) {
  if (!expectString(value, at, ctx, true)) return;
  const match = /^\$([A-Za-z_][A-Za-z0-9_-]*)$/.exec(value);
  if (!match) {
    error(ctx, at, `${kind} reference must use $key syntax`);
  } else if (!available.has(match[1])) {
    error(ctx, at, `unknown ${kind} reference ${JSON.stringify(value)}`);
  }
}

function validateRichStyle(style, at, ctx, tag) {
  if (typeof style !== 'string') {
    error(ctx, at, 'style attribute must be a string');
    return;
  }
  const allowed = {
    p: new Set(['text-align', 'line-height', 'margin-top', 'margin-left', 'margin-right']),
    li: new Set(['text-align', 'line-height', 'letter-spacing', 'margin-top', 'margin-left', 'list-style', 'list-style-type', 'list-style-position', 'list-style-image']),
    span: new Set(['color', 'font-size', 'font-family', 'background-color', 'font-weight', 'font-style', 'text-decoration']),
  }[tag] || new Set();
  for (const declaration of style.split(';')) {
    if (!declaration.trim()) continue;
    const colon = declaration.indexOf(':');
    if (colon <= 0) {
      error(ctx, at, `invalid CSS declaration ${JSON.stringify(declaration)}`);
      continue;
    }
    const key = declaration.slice(0, colon).trim().toLowerCase();
    const value = declaration.slice(colon + 1).trim();
    if (!allowed.has(key)) {
      error(ctx, at, `${key} is not supported on <${tag}>`);
      continue;
    }
    if (!value) error(ctx, at, `${key} must not be empty`);
    if (key === 'color' || key === 'background-color') checkColor(value, `${at}.${key}`, ctx);
    if (key === 'font-size') {
      if (!/^[-+]?(?:\d+\.?\d*|\.\d+)px$/.test(value) || Number.parseFloat(value) <= 0) {
        error(ctx, at, 'font-size must be a positive px value');
      }
    }
    if (key === 'font-weight' && !/^(?:normal|bold|[1-9]00)$/.test(value)) {
      error(ctx, at, 'font-weight must be normal, bold, or a 100-900 value');
    }
    if (key === 'font-style' && !/^(?:normal|italic|oblique)$/.test(value)) {
      error(ctx, at, 'font-style must be normal, italic, or oblique');
    }
    if (key === 'text-decoration' && !value) error(ctx, at, 'text-decoration must not be empty');
    if (key === 'line-height') {
      if (!/^(?:[-+]?(?:\d+\.?\d*|\.\d+)(?:px)?)$/.test(value) || Number.parseFloat(value) <= 0) {
        error(ctx, at, 'line-height must be a positive number or px value');
      }
    }
    if (key.startsWith('margin-') || key === 'letter-spacing') {
      if (!/^[-+]?(?:\d+\.?\d*|\.\d+)px$/.test(value)) error(ctx, at, `${key} must be a px value`);
    }
    if (key === 'text-align' && !H_ALIGN.has(value)) error(ctx, at, `invalid text-align ${JSON.stringify(value)}`);
  }
}

function parseTagAttributes(text, at, ctx) {
  const attrs = {};
  let rest = text.trim();
  if (rest.endsWith('/')) rest = rest.slice(0, -1).trim();
  const attrRe = /^([A-Za-z_:][A-Za-z0-9_.:-]*)\s*=\s*(?:"([^"]*)"|'([^']*)')/;
  while (rest) {
    const match = attrRe.exec(rest);
    if (!match) {
      error(ctx, at, `invalid tag attribute syntax near ${JSON.stringify(rest)}`);
      break;
    }
    attrs[match[1]] = match[2] ?? match[3] ?? '';
    rest = rest.slice(match[0].length).trim();
  }
  return attrs;
}

function checkRichText(value, at, ctx) {
  if (!expectString(value, at, ctx)) return;
  let match;
  const stack = [];
  const tagRe = /<\/?([A-Za-z][A-Za-z0-9]*)\b([^>]*)>/g;
  let cursor = 0;
  while ((match = tagRe.exec(value))) {
    const rawBefore = value.slice(cursor, match.index);
    if (rawBefore.includes('<') || rawBefore.includes('>')) error(ctx, at, 'raw < or > must be escaped outside rich-text tags');
    cursor = tagRe.lastIndex;
    const tag = match[1].toLowerCase();
    const closing = match[0].startsWith('</');
    const selfClosing = /\/\s*>$/.test(match[0]);
    if (!RICH_TAGS.has(tag)) {
      error(ctx, at, `unsupported rich-text tag <${tag}>`);
      continue;
    }
    if (closing) {
      if (selfClosing) error(ctx, at, `closing tag </${tag}> cannot be self-closing`);
      const previous = stack.pop();
      if (previous !== tag) error(ctx, at, `mismatched closing tag </${tag}>`);
      continue;
    }
    const attrAt = `${at}<${tag}>`;
    const attrs = parseTagAttributes(match[2], attrAt, ctx);
    const allowedAttrs = {
      p: new Set(['style']),
      li: new Set(['style']),
      span: new Set(['style']),
      a: new Set(['href']),
      br: new Set(),
      strong: new Set(), em: new Set(), u: new Set(), s: new Set(), sup: new Set(), sub: new Set(),
      ul: new Set(), ol: new Set(),
    }[tag];
    for (const key of Object.keys(attrs)) {
      if (!allowedAttrs.has(key)) error(ctx, attrAt, `attribute ${JSON.stringify(key)} is not allowed`);
    }
    if (own(attrs, 'style')) validateRichStyle(attrs.style, `${attrAt}.style`, ctx, tag);
    if (tag === 'a' && own(attrs, 'href') && !/^(?:https?:\/\/|mailto:)/i.test(attrs.href)) {
      error(ctx, attrAt, 'href must use https://, http://, or mailto:');
    }
    if (tag === 'a' && !own(attrs, 'href')) error(ctx, attrAt, '<a> requires href');
    if (tag === 'li' && !stack.includes('ul') && !stack.includes('ol')) error(ctx, attrAt, '<li> must be inside <ul> or <ol>');
    if ((tag === 'ul' || tag === 'ol') && stack.at(-1) === 'ul' || (tag === 'ul' || tag === 'ol') && stack.at(-1) === 'ol') {
      // Nested lists are legal only inside a list item.
      if (stack.at(-1) !== 'li') error(ctx, attrAt, 'nested list must be inside <li>');
    }
    if (tag === 'br' && !selfClosing && match[2].trim()) error(ctx, attrAt, '<br> may not have attributes');
    if (!selfClosing && tag !== 'br') stack.push(tag);
  }
  const tail = value.slice(cursor);
  if (tail.includes('<') || tail.includes('>')) error(ctx, at, 'raw < or > must be escaped outside rich-text tags');
  if (stack.length) error(ctx, at, `unclosed rich-text tag(s): ${stack.join(', ')}`);
  for (const formula of value.matchAll(/\\\((.*?)\\\)/gs)) {
    if (formula[1].includes('<') || formula[1].includes('>')) error(ctx, at, 'rich-text tags are not allowed inside a LaTeX formula');
  }
}

function checkTextContent(value, at, ctx) {
  if (!expectObject(value, at, ctx)) return;
  unknownKeys(value, new Set([
    'text', 'style', 'color', 'fontSize', 'fontFamily', 'bold', 'italic',
    'backgroundColor', 'lineHeight', 'lineHeightPx', 'letterSpacing', 'marginTop',
    'textDirection', 'wrap', 'align', 'gradient', 'shadow',
  ]), at, ctx);
  required(ctx, value, 'text', at);
  if (own(value, 'text')) checkRichText(value.text, `${at}.text`, ctx);
  if (own(value, 'style')) checkStyleRef(value.style, `${at}.style`, ctx, ctx.textStyles, 'text style');
  checkTextStyle(value, at, ctx, { allowExtra: true });
  if (own(value, 'textDirection')) expectEnum(value.textDirection, new Set(['horizontal', 'vertical']), `${at}.textDirection`, ctx);
  if (own(value, 'wrap')) expectBoolean(value.wrap, `${at}.wrap`, ctx);
  if (own(value, 'align')) checkAlign(value.align, `${at}.align`, ctx);
  if (own(value, 'gradient')) {
    if (!isObject(value.gradient) || value.gradient.type !== 'gradient') error(ctx, `${at}.gradient`, 'text gradient must be a GradientFill');
    else checkGradient(value.gradient, `${at}.gradient`, ctx);
  }
  if (own(value, 'shadow')) checkShadow(value.shadow, `${at}.shadow`, ctx);
}

function checkBounds(value, at, ctx, { allowZero = false } = {}) {
  if (!expectArray(value, at, ctx)) return;
  if (value.length !== 4) error(ctx, at, 'bounds must contain [x, y, width, height]');
  value.forEach((item, index) => expectNumber(item, `${at}[${index}]`, ctx));
  if (isFiniteNumber(value[2])) expectNumber(value[2], `${at}[2]`, ctx, { min: 0, exclusiveMin: !allowZero });
  if (isFiniteNumber(value[3])) expectNumber(value[3], `${at}[3]`, ctx, { min: 0, exclusiveMin: !allowZero });
  if (allowZero && isFiniteNumber(value[2]) && isFiniteNumber(value[3]) && value[2] === 0 && value[3] === 0) {
    error(ctx, at, 'line bounds cannot have both width and height equal to zero');
  }
}

function checkTransforms(value, at, ctx) {
  if (own(value, 'rotation')) expectNumber(value.rotation, `${at}.rotation`, ctx);
  if (own(value, 'opacity')) expectNumber(value.opacity, `${at}.opacity`, ctx, { min: 0, max: 1 });
  if (own(value, 'flip')) {
    if (expectArray(value.flip, `${at}.flip`, ctx) && value.flip.length === 2) {
      value.flip.forEach((item, index) => expectBoolean(item, `${at}.flip[${index}]`, ctx));
    }
  }
}

function pathTokens(value, at, ctx) {
  if (typeof value !== 'string' || !value.trim()) {
    error(ctx, at, 'path must be a non-empty SVG path string');
    return [];
  }
  const tokenRe = /[MmLlHhVvCcSsQqTtAaZz]|[-+]?(?:(?:\d+\.?\d*)|(?:\.\d+))(?:[eE][-+]?\d+)?/g;
  const tokens = [];
  let cursor = 0;
  let match;
  while ((match = tokenRe.exec(value))) {
    const gap = value.slice(cursor, match.index);
    if (gap && !/^[\s,]+$/.test(gap)) error(ctx, at, `invalid SVG path token near ${JSON.stringify(gap)}`);
    tokens.push(match[0]);
    cursor = tokenRe.lastIndex;
  }
  if (value.slice(cursor) && !/^[\s,]+$/.test(value.slice(cursor))) error(ctx, at, 'invalid trailing SVG path token');
  return tokens;
}

function checkSvgPath(value, at, ctx, { motion = false } = {}) {
  const tokens = pathTokens(value, at, ctx);
  if (!tokens.length) return;
  const counts = { M: 2, L: 2, H: 1, V: 1, C: 6, S: 4, Q: 4, T: 2, A: 7, Z: 0 };
  let command = null;
  let sawMove = false;
  let sawSubpath = 0;
  let index = 0;
  while (index < tokens.length) {
    if (/^[A-Za-z]$/.test(tokens[index])) {
      command = tokens[index++];
      const upper = command.toUpperCase();
      if (!(upper in counts)) {
        error(ctx, at, `unsupported SVG path command ${command}`);
        command = null;
        continue;
      }
      if (upper === 'M') {
        sawMove = true;
        sawSubpath += 1;
      }
      if (upper === 'Z') {
        command = null;
        continue;
      }
    }
    if (!command) {
      error(ctx, at, 'SVG path data must begin each segment with a command');
      break;
    }
    const count = counts[command.toUpperCase()];
    if (count === 0) continue;
    let numbers = 0;
    while (index < tokens.length && !/^[A-Za-z]$/.test(tokens[index])) {
      if (isFiniteNumber(Number(tokens[index]))) numbers += 1;
      index += 1;
    }
    if (numbers < count || numbers % count !== 0) {
      error(ctx, at, `SVG ${command} command requires groups of ${count} numbers`);
    }
    if (command.toUpperCase() === 'M') command = command === 'M' ? 'L' : 'l';
  }
  if (!sawMove) error(ctx, at, 'SVG path must contain a move command M');
  if (motion) {
    if (sawSubpath !== 1) error(ctx, at, 'motion-path must contain exactly one subpath');
    if (!/^\s*M\s*[-+]?0(?:\.0*)?\s*[, ]\s*[-+]?0(?:\.0*)?/i.test(value)) {
      error(ctx, at, 'motion-path must start with M 0 0');
    }
    if (/[AaTtHhVvSsZz]/.test(value)) error(ctx, at, 'motion-path supports only M/L/Q/C (and optional Z) commands');
  }
}

function checkShapeDefinition(value, at, ctx, { element = false } = {}) {
  if (!expectObject(value, at, ctx)) return;
  const keys = new Set(['shapeName', 'adjustments', 'viewBox', 'path']);
  if (element) keys.add('fill');
  if (element) keys.add('border');
  if (element) keys.add('shadow');
  unknownKeys(value, keys, at, ctx);
  required(ctx, value, 'shapeName', at);
  if (own(value, 'shapeName')) {
    expectString(value.shapeName, `${at}.shapeName`, ctx, true);
    if (typeof value.shapeName === 'string' && !loadShapeNames().has(value.shapeName)) error(ctx, `${at}.shapeName`, `unsupported shape name ${JSON.stringify(value.shapeName)}`);
  }
  if (own(value, 'adjustments')) {
    if (expectArray(value.adjustments, `${at}.adjustments`, ctx)) value.adjustments.forEach((item, index) => expectNumber(item, `${at}.adjustments[${index}]`, ctx));
  }
  const custom = value.shapeName === 'custom';
  if (custom) {
    required(ctx, value, 'viewBox', at);
    required(ctx, value, 'path', at);
    if (own(value, 'viewBox')) {
      if (expectArray(value.viewBox, `${at}.viewBox`, ctx) && value.viewBox.length === 2) value.viewBox.forEach((item, index) => expectNumber(item, `${at}.viewBox[${index}]`, ctx, { min: 0, exclusiveMin: true }));
    }
    if (own(value, 'path')) checkSvgPath(value.path, `${at}.path`, ctx);
  } else {
    if (own(value, 'path')) error(ctx, `${at}.path`, 'path is only valid when shapeName is custom');
    if (own(value, 'viewBox')) error(ctx, `${at}.viewBox`, 'viewBox is only valid when shapeName is custom');
  }
  if (element) {
    if (own(value, 'fill')) checkFill(value.fill, `${at}.fill`, ctx);
    if (own(value, 'border')) checkBorder(value.border, `${at}.border`, ctx);
    if (own(value, 'shadow')) checkShadow(value.shadow, `${at}.shadow`, ctx);
  }
}

function checkElementBase(value, at, ctx) {
  if (!expectObject(value, at, ctx)) return false;
  required(ctx, value, 'elementId', at);
  required(ctx, value, 'elementType', at);
  required(ctx, value, 'bounds', at);
  if (own(value, 'elementId')) expectString(value.elementId, `${at}.elementId`, ctx, true);
  if (own(value, 'elementType')) expectEnum(value.elementType, ELEMENT_TYPES, `${at}.elementType`, ctx);
  if (own(value, 'bounds')) checkBounds(value.bounds, `${at}.bounds`, ctx, { allowZero: value.elementType === 'line' });
  return true;
}

function checkElementTransformsAndCommon(value, at, ctx) {
  checkTransforms(value, at, ctx);
}

function checkTextElement(value, at, ctx) {
  unknownKeys(value, new Set(['elementId', 'elementType', 'bounds', 'rotation', 'opacity', 'flip', 'content']), at, ctx);
  checkElementTransformsAndCommon(value, at, ctx);
  for (const key of ['rotation', 'opacity', 'flip']) {
    if (own(value, key)) error(ctx, `${at}.${key}`, `text ${key} is not preserved by the local PPTX writer; use a shape/image composition instead`);
  }
  required(ctx, value, 'content', at);
  if (own(value, 'content')) checkTextContent(value.content, `${at}.content`, ctx);
}

function checkShapeElement(value, at, ctx) {
  unknownKeys(value, new Set(['elementId', 'elementType', 'bounds', 'rotation', 'opacity', 'flip', 'shapeName', 'adjustments', 'viewBox', 'path', 'fill', 'border', 'shadow']), at, ctx);
  checkElementTransformsAndCommon(value, at, ctx);
  const definition = {};
  for (const key of ['shapeName', 'adjustments', 'viewBox', 'path', 'fill', 'border', 'shadow']) {
    if (own(value, key)) definition[key] = value[key];
  }
  checkShapeDefinition(definition, at, ctx, { element: true });
}

function checkLineElement(value, at, ctx) {
  unknownKeys(value, new Set(['elementId', 'elementType', 'bounds', 'rotation', 'opacity', 'flip', 'viewBox', 'points', 'curve', 'arrow', 'border', 'shadow']), at, ctx);
  checkElementTransformsAndCommon(value, at, ctx);
  required(ctx, value, 'viewBox', at);
  required(ctx, value, 'points', at);
  if (own(value, 'viewBox')) {
    if (expectArray(value.viewBox, `${at}.viewBox`, ctx) && value.viewBox.length === 2) value.viewBox.forEach((item, index) => expectNumber(item, `${at}.viewBox[${index}]`, ctx, { min: 0, exclusiveMin: true }));
  }
  if (own(value, 'points')) {
    if (typeof value.points !== 'string') error(ctx, `${at}.points`, 'points must be a string');
    else {
      const pieces = value.points.trim() ? value.points.trim().split(/\s+/) : [];
      if (pieces.length < 2) error(ctx, `${at}.points`, 'points must contain at least two x,y points');
      pieces.forEach((piece, index) => {
        const pair = piece.split(',');
        if (pair.length !== 2 || !pair.every((item) => item.trim() && Number.isFinite(Number(item)))) error(ctx, `${at}.points[${index}]`, 'point must be finite x,y');
        if (pair.length === 2 && Array.isArray(value.viewBox) && value.viewBox.length === 2) {
          const x = Number(pair[0]);
          const y = Number(pair[1]);
          if (Number.isFinite(x) && (x < 0 || x > value.viewBox[0])) error(ctx, `${at}.points[${index}]`, 'x must be inside viewBox');
          if (Number.isFinite(y) && (y < 0 || y > value.viewBox[1])) error(ctx, `${at}.points[${index}]`, 'y must be inside viewBox');
        }
      });
    }
  }
  if (own(value, 'curve')) expectEnum(value.curve, new Set(['sharp', 'round', 'smooth']), `${at}.curve`, ctx);
  if (own(value, 'arrow')) {
    if (expectArray(value.arrow, `${at}.arrow`, ctx) && value.arrow.length === 2) value.arrow.forEach((item, index) => { if (item !== null) expectEnum(item, ARROWS, `${at}.arrow[${index}]`, ctx); });
  }
  if (own(value, 'border')) checkBorder(value.border, `${at}.border`, ctx);
  if (own(value, 'shadow')) checkShadow(value.shadow, `${at}.shadow`, ctx);
}

function checkImageElement(value, at, ctx) {
  unknownKeys(value, new Set(['elementId', 'elementType', 'bounds', 'rotation', 'opacity', 'flip', 'src', 'cropShape', 'fit', 'crop', 'border', 'shadow']), at, ctx);
  checkElementTransformsAndCommon(value, at, ctx);
  required(ctx, value, 'src', at);
  if (own(value, 'src')) checkImageSrc(value.src, `${at}.src`, ctx);
  if (own(value, 'cropShape')) checkShapeDefinition(value.cropShape, `${at}.cropShape`, ctx);
  if (own(value, 'fit')) checkFit(value.fit, `${at}.fit`, ctx);
  if (own(value, 'crop')) checkCrop(value.crop, `${at}.crop`, ctx);
  if (own(value, 'border')) checkBorder(value.border, `${at}.border`, ctx);
  if (own(value, 'shadow')) checkShadow(value.shadow, `${at}.shadow`, ctx);
}

function checkIconElement(value, at, ctx) {
  unknownKeys(value, new Set(['elementId', 'elementType', 'bounds', 'rotation', 'opacity', 'flip', 'iconName', 'fill', 'border', 'shadow']), at, ctx);
  checkElementTransformsAndCommon(value, at, ctx);
  required(ctx, value, 'iconName', at);
  if (own(value, 'iconName')) {
    expectString(value.iconName, `${at}.iconName`, ctx, true);
    if (typeof value.iconName === 'string' && !/^(?:fas|far|fab):[^:]+$/.test(value.iconName)) error(ctx, `${at}.iconName`, 'iconName must use fas:name, far:name, or fab:name');
  }
  if (own(value, 'fill')) checkFill(value.fill, `${at}.fill`, ctx);
  if (own(value, 'border')) checkBorder(value.border, `${at}.border`, ctx);
  if (own(value, 'shadow')) checkShadow(value.shadow, `${at}.shadow`, ctx);
}

function checkCell(value, at, ctx) {
  if (!expectObject(value, at, ctx)) return;
  unknownKeys(value, new Set([
    'text', 'textStyle', 'color', 'fontSize', 'fontFamily', 'bold', 'italic',
    'backgroundColor', 'lineHeight', 'lineHeightPx', 'letterSpacing', 'marginTop',
    'fill', 'border', 'align', 'rowSpan', 'colSpan',
  ]), at, ctx);
  if (own(value, 'text')) checkRichText(value.text, `${at}.text`, ctx);
  if (own(value, 'textStyle')) checkStyleRef(value.textStyle, `${at}.textStyle`, ctx, ctx.textStyles, 'text style');
  checkTextStyle(value, at, ctx, { cell: true, allowExtra: true });
  for (const key of ['rowSpan', 'colSpan']) if (own(value, key)) expectNumber(value[key], `${at}.${key}`, ctx, { min: 1 });
  for (const key of ['rowSpan', 'colSpan']) if (own(value, key) && !isInteger(value[key])) error(ctx, `${at}.${key}`, 'span must be an integer');
}

function checkTableStyle(value, at, ctx) {
  if (!expectObject(value, at, ctx)) return;
  unknownKeys(value, new Set(['cellStyle', 'firstRowStyle', 'lastRowStyle', 'firstColumnStyle', 'lastColumnStyle', 'bodyStyles', 'rowOverColumn']), at, ctx);
  for (const key of ['cellStyle', 'firstRowStyle', 'lastRowStyle', 'firstColumnStyle', 'lastColumnStyle']) if (own(value, key)) checkTextStyle(value[key], `${at}.${key}`, ctx, { cell: true });
  if (own(value, 'bodyStyles')) {
    if (expectArray(value.bodyStyles, `${at}.bodyStyles`, ctx)) value.bodyStyles.forEach((item, index) => checkTextStyle(item, `${at}.bodyStyles[${index}]`, ctx, { cell: true }));
  }
  if (own(value, 'rowOverColumn')) expectBoolean(value.rowOverColumn, `${at}.rowOverColumn`, ctx);
}

function checkTableElement(value, at, ctx) {
  unknownKeys(value, new Set(['elementId', 'elementType', 'bounds', 'columnWidths', 'rowHeights', 'rows', 'style', 'fill', 'shadow']), at, ctx);
  required(ctx, value, 'columnWidths', at);
  required(ctx, value, 'rowHeights', at);
  required(ctx, value, 'rows', at);
  const widths = value.columnWidths;
  const heights = value.rowHeights;
  if (expectArray(widths, `${at}.columnWidths`, ctx, 1)) {
    widths.forEach((item, index) => expectNumber(item, `${at}.columnWidths[${index}]`, ctx, { min: 0, max: 1, exclusiveMin: true }));
    if (widths.every(isFiniteNumber) && Math.abs(widths.reduce((a, b) => a + b, 0) - 1) > 1e-6) error(ctx, `${at}.columnWidths`, 'column widths must sum to 1');
  }
  if (expectArray(heights, `${at}.rowHeights`, ctx, 1)) {
    heights.forEach((item, index) => expectNumber(item, `${at}.rowHeights[${index}]`, ctx, { min: 0, max: 1, exclusiveMin: true }));
    if (heights.every(isFiniteNumber) && Math.abs(heights.reduce((a, b) => a + b, 0) - 1) > 1e-6) error(ctx, `${at}.rowHeights`, 'row heights must sum to 1');
  }
  if (own(value, 'style')) {
    if (typeof value.style === 'string') checkStyleRef(value.style, `${at}.style`, ctx, ctx.tableStyles, 'table style');
    else checkTableStyle(value.style, `${at}.style`, ctx);
  }
  if (own(value, 'fill')) checkFill(value.fill, `${at}.fill`, ctx);
  if (own(value, 'shadow')) checkShadow(value.shadow, `${at}.shadow`, ctx);
  if (!Array.isArray(widths) || !Array.isArray(heights) || !Array.isArray(value.rows)) return;
  const rowCount = heights.length;
  const colCount = widths.length;
  if (value.rows.length !== rowCount) error(ctx, `${at}.rows`, `must contain exactly ${rowCount} rows`);
  const occupied = Array.from({ length: rowCount }, () => Array(colCount).fill(false));
  for (let r = 0; r < rowCount; r += 1) {
    const row = value.rows[r];
    if (!Array.isArray(row)) {
      error(ctx, `${at}.rows[${r}]`, 'row must be an array');
      continue;
    }
    let cursor = 0;
    for (let index = 0; index < row.length; index += 1) {
      while (cursor < colCount && occupied[r][cursor]) cursor += 1;
      const cellAt = `${at}.rows[${r}][${index}]`;
      checkCell(row[index], cellAt, ctx);
      if (!isObject(row[index])) continue;
      const rowSpan = isInteger(row[index].rowSpan) ? row[index].rowSpan : 1;
      const colSpan = isInteger(row[index].colSpan) ? row[index].colSpan : 1;
      if (cursor >= colCount) {
        error(ctx, cellAt, 'too many cells for this row');
        continue;
      }
      if (cursor + colSpan > colCount || r + rowSpan > rowCount) error(ctx, cellAt, 'rowSpan/colSpan exceeds table dimensions');
      for (let rr = r; rr < Math.min(rowCount, r + rowSpan); rr += 1) {
        for (let cc = cursor; cc < Math.min(colCount, cursor + colSpan); cc += 1) {
          if (occupied[rr][cc]) error(ctx, cellAt, `merge overlaps cell at row ${rr}, column ${cc}`);
          occupied[rr][cc] = true;
        }
      }
      cursor += colSpan;
    }
    while (cursor < colCount && occupied[r][cursor]) cursor += 1;
    if (cursor !== colCount) error(ctx, `${at}.rows[${r}]`, 'row does not provide every unmerged cell');
  }
  for (let r = 0; r < rowCount; r += 1) for (let c = 0; c < colCount; c += 1) if (!occupied[r][c]) error(ctx, `${at}.rows`, `cell at row ${r}, column ${c} is missing`);
}

function checkTitle(value, at, ctx) {
  if (typeof value === 'string') {
    expectString(value, at, ctx, true);
    return;
  }
  if (!expectObject(value, at, ctx)) return;
  unknownKeys(value, new Set(['text', 'color', 'fontSize', 'fontFamily']), at, ctx);
  required(ctx, value, 'text', at);
  if (own(value, 'text')) expectString(value.text, `${at}.text`, ctx, true);
  if (own(value, 'color')) checkColor(value.color, `${at}.color`, ctx);
  if (own(value, 'fontSize')) expectNumber(value.fontSize, `${at}.fontSize`, ctx, { min: 0, exclusiveMin: true });
  if (own(value, 'fontFamily')) checkFontFamily(value.fontFamily, `${at}.fontFamily`, ctx);
}

function checkLegend(value, at, ctx) {
  if (typeof value === 'boolean') return;
  if (!expectObject(value, at, ctx)) return;
  unknownKeys(value, new Set(['show', 'position', 'color', 'fontSize', 'fontFamily']), at, ctx);
  if (own(value, 'show')) expectBoolean(value.show, `${at}.show`, ctx);
  if (own(value, 'position')) expectEnum(value.position, new Set(['top', 'bottom', 'left', 'right']), `${at}.position`, ctx);
  if (own(value, 'color')) checkColor(value.color, `${at}.color`, ctx);
  if (own(value, 'fontSize')) expectNumber(value.fontSize, `${at}.fontSize`, ctx, { min: 0, exclusiveMin: true });
  if (own(value, 'fontFamily')) checkFontFamily(value.fontFamily, `${at}.fontFamily`, ctx);
}

function checkLineStyleConfig(value, at, ctx, { arrow = false } = {}) {
  if (!expectObject(value, at, ctx)) return;
  const keys = new Set(['style', 'color', 'width']);
  if (arrow) keys.add('arrow');
  unknownKeys(value, keys, at, ctx);
  if (own(value, 'style')) expectEnum(value.style, LINE_STYLES, `${at}.style`, ctx);
  if (own(value, 'color')) checkColor(value.color, `${at}.color`, ctx);
  if (own(value, 'width')) expectNumber(value.width, `${at}.width`, ctx, { min: 0, exclusiveMin: true });
  if (arrow && own(value, 'arrow')) {
    if (typeof value.arrow === 'boolean') return;
    expectEnum(value.arrow, new Set(['start', 'end', 'both']), `${at}.arrow`, ctx);
  }
}

function checkAxis(value, at, ctx) {
  if (!expectObject(value, at, ctx)) return;
  unknownKeys(value, new Set(['show', 'type', 'min', 'max', 'reverse', 'title', 'label', 'axisLine', 'gridLine']), at, ctx);
  if (own(value, 'show')) expectBoolean(value.show, `${at}.show`, ctx);
  if (own(value, 'type')) expectEnum(value.type, new Set(['category', 'value']), `${at}.type`, ctx);
  if (own(value, 'min')) expectNumber(value.min, `${at}.min`, ctx);
  if (own(value, 'max')) expectNumber(value.max, `${at}.max`, ctx);
  if (isFiniteNumber(value.min) && isFiniteNumber(value.max) && value.min >= value.max) error(ctx, at, 'axis min must be less than max');
  if (own(value, 'reverse')) expectBoolean(value.reverse, `${at}.reverse`, ctx);
  if (own(value, 'title')) checkTitle(value.title, `${at}.title`, ctx);
  if (own(value, 'label')) {
    if (typeof value.label === 'boolean') { /* valid */ }
    else if (expectObject(value.label, `${at}.label`, ctx)) {
      unknownKeys(value.label, new Set(['color', 'fontSize', 'fontFamily', 'numberFormat']), `${at}.label`, ctx);
      if (own(value.label, 'color')) checkColor(value.label.color, `${at}.label.color`, ctx);
      if (own(value.label, 'fontSize')) expectNumber(value.label.fontSize, `${at}.label.fontSize`, ctx, { min: 0, exclusiveMin: true });
      if (own(value.label, 'fontFamily')) checkFontFamily(value.label.fontFamily, `${at}.label.fontFamily`, ctx);
      if (own(value.label, 'numberFormat') && !NUMBER_FORMATS.has(value.label.numberFormat)) error(ctx, `${at}.label.numberFormat`, 'unsupported number format');
    }
  }
  for (const key of ['axisLine', 'gridLine']) {
    if (!own(value, key)) continue;
    if (typeof value[key] === 'boolean') continue;
    checkLineStyleConfig(value[key], `${at}.${key}`, ctx, { arrow: key === 'axisLine' });
  }
}

function checkSpokeAxis(value, at, ctx) {
  if (!expectObject(value, at, ctx)) return;
  unknownKeys(value, new Set(['show', 'min', 'max', 'label', 'axisLine', 'gridLine']), at, ctx);
  if (own(value, 'show')) expectBoolean(value.show, `${at}.show`, ctx);
  if (own(value, 'min')) expectNumber(value.min, `${at}.min`, ctx);
  if (own(value, 'max')) expectNumber(value.max, `${at}.max`, ctx);
  if (isFiniteNumber(value.min) && isFiniteNumber(value.max) && value.min >= value.max) error(ctx, at, 'spoke axis min must be less than max');
  if (own(value, 'label')) {
    if (typeof value.label === 'boolean') { /* valid */ }
    else if (expectObject(value.label, `${at}.label`, ctx)) {
      unknownKeys(value.label, new Set(['color', 'fontSize', 'fontFamily', 'numberFormat']), `${at}.label`, ctx);
      if (own(value.label, 'color')) checkColor(value.label.color, `${at}.label.color`, ctx);
      if (own(value.label, 'fontSize')) expectNumber(value.label.fontSize, `${at}.label.fontSize`, ctx, { min: 0, exclusiveMin: true });
      if (own(value.label, 'fontFamily')) checkFontFamily(value.label.fontFamily, `${at}.label.fontFamily`, ctx);
      if (own(value.label, 'numberFormat') && !NUMBER_FORMATS.has(value.label.numberFormat)) error(ctx, `${at}.label.numberFormat`, 'unsupported number format');
    }
  }
  for (const key of ['axisLine', 'gridLine']) if (own(value, key)) {
    if (typeof value[key] !== 'boolean') checkLineStyleConfig(value[key], `${at}.${key}`, ctx);
  }
}

function checkDataLabels(value, at, ctx, allowedContents) {
  if (!expectObject(value, at, ctx)) return;
  unknownKeys(value, new Set(['show', 'content', 'numberFormat', 'color', 'fontSize', 'fontFamily']), at, ctx);
  if (own(value, 'show')) expectBoolean(value.show, `${at}.show`, ctx);
  if (own(value, 'content') && !allowedContents.has(value.content)) error(ctx, `${at}.content`, `invalid content; expected one of ${[...allowedContents].join(', ')}`);
  if (own(value, 'numberFormat') && !NUMBER_FORMATS.has(value.numberFormat)) error(ctx, `${at}.numberFormat`, 'unsupported number format');
  if (own(value, 'color')) checkColor(value.color, `${at}.color`, ctx);
  if (own(value, 'fontSize')) expectNumber(value.fontSize, `${at}.fontSize`, ctx, { min: 0, exclusiveMin: true });
  if (own(value, 'fontFamily')) checkFontFamily(value.fontFamily, `${at}.fontFamily`, ctx);
}

function checkMarker(value, at, ctx, allowFalse = false) {
  if (value === false) {
    if (!allowFalse) error(ctx, at, 'marker cannot be false for this series type');
    return;
  }
  if (!expectObject(value, at, ctx)) return;
  unknownKeys(value, new Set(['shape', 'fill', 'border', 'size']), at, ctx);
  if (own(value, 'shape')) expectEnum(value.shape, new Set(['circle', 'rect', 'diamond', 'triangle']), `${at}.shape`, ctx);
  if (own(value, 'fill')) checkSeriesFill(value.fill, `${at}.fill`, ctx);
  if (own(value, 'border')) checkBorder(value.border, `${at}.border`, ctx);
  if (own(value, 'size')) expectNumber(value.size, `${at}.size`, ctx, { min: 0, exclusiveMin: true });
}

function checkEncode(value, at, ctx, requiredKeys, optionalKeys = new Set()) {
  if (!expectObject(value, at, ctx)) return;
  unknownKeys(value, new Set([...requiredKeys, ...optionalKeys]), at, ctx);
  for (const key of requiredKeys) required(ctx, value, key, at);
  for (const key of [...requiredKeys, ...optionalKeys]) if (own(value, key)) expectString(value[key], `${at}.${key}`, ctx, true);
}

function checkIndex(value, at, ctx) {
  expectNumber(value, at, ctx, { min: 0 });
  if (!isInteger(value)) error(ctx, at, 'axis index must be a non-negative integer');
}

function checkDataFilter(value, at, ctx, cols) {
  if (!expectObject(value, at, ctx)) return;
  unknownKeys(value, new Set(['col', 'value']), at, ctx);
  required(ctx, value, 'col', at);
  required(ctx, value, 'value', at);
  if (own(value, 'col')) {
    expectString(value.col, `${at}.col`, ctx, true);
    if (typeof value.col === 'string' && !cols.has(value.col)) error(ctx, `${at}.col`, `unknown data column ${JSON.stringify(value.col)}`);
  }
  if (own(value, 'value') && !(typeof value.value === 'string' || isFiniteNumber(value.value))) error(ctx, `${at}.value`, 'filter value must be a string or number');
}

function checkSeriesStyle(value, at, ctx, key = 'fill') {
  if (own(value, key)) checkSeriesFill(value[key], `${at}.${key}`, ctx);
}

function checkSeries(value, at, ctx, type, dataCols, defaults = false) {
  if (!expectObject(value, at, ctx)) return;
  const common = new Set(['type', 'encode', 'name', 'xAxisIndex', 'yAxisIndex', 'dataLabels']);
  const allowedByType = {
    bar: new Set([...common, 'stack', 'symbol', 'fill', 'border']),
    line: new Set([...common, 'smooth', 'lineStyle', 'width', 'marker', 'nullHandling', 'lineColor']),
    area: new Set([...common, 'smooth', 'lineStyle', 'width', 'marker', 'nullHandling', 'lineColor', 'stack', 'areaColor']),
    scatter: new Set([...common, 'dataFilter', 'marker', 'fill', 'border']),
    bubble: new Set([...common, 'dataFilter', 'sizeScale', 'sizeRange', 'fill', 'border']),
    candlestick: new Set(['type', 'encode', 'xAxisIndex', 'yAxisIndex', 'upBars', 'downBars', 'wickStyle']),
    pie: new Set(['type', 'encode', 'innerRadius', 'startAngle', 'fill', 'border', 'dataLabels']),
    radar: new Set([...common, 'smooth', 'lineStyle', 'width', 'marker', 'nullHandling', 'lineColor', 'areaColor']),
    waterfall: new Set(['type', 'encode', 'totalBars', 'increaseBars', 'decreaseBars', 'dataLabels']),
    heatmap: new Set(['type', 'encode', 'colorScheme', 'colorScale', 'colorbar', 'dataLabels']),
    treemap: new Set(['type', 'encode', 'levels', 'fill', 'border', 'dataLabels']),
    sunburst: new Set(['type', 'encode', 'levels', 'fill', 'border', 'dataLabels']),
    sankey: new Set(['type', 'encode', 'nodeAlign', 'fill', 'border', 'dataLabels']),
  }[type];
  const allowed = allowedByType || new Set(['type', 'encode']);
  unknownKeys(value, allowed, at, ctx);
  if (!defaults) {
    if (value.type !== type) error(ctx, `${at}.type`, `expected series type ${type}`);
    if (!own(value, 'encode')) error(ctx, at, 'series must contain encode');
  } else if (own(value, 'type') || own(value, 'encode')) {
    error(ctx, at, 'seriesDefaults entries may not contain type or encode');
  }
  const requiredChannels = {
    bar: ['x', 'y'], line: ['x', 'y'], area: ['x', 'y'], scatter: ['x', 'y'],
    bubble: ['x', 'y', 'size'], candlestick: ['x', 'high', 'low', 'close'],
    pie: ['category', 'value'], radar: ['category', 'y'], waterfall: ['x', 'y'],
    heatmap: ['x', 'y', 'value'], treemap: ['category', 'value'], sunburst: ['category', 'value'],
    sankey: ['source', 'target', 'flow'],
  }[type] || [];
  const optionalChannels = {
    candlestick: new Set(['open']), waterfall: new Set(['isTotal']), treemap: new Set(['parent']), sunburst: new Set(['parent']),
  }[type] || new Set();
  if (!defaults && own(value, 'encode')) {
    checkEncode(value.encode, `${at}.encode`, ctx, new Set(requiredChannels), optionalChannels);
    for (const [channel, column] of Object.entries(value.encode || {})) {
      if (typeof column === 'string' && !dataCols.names.has(column)) {
        error(ctx, `${at}.encode.${channel}`, `unknown data column ${JSON.stringify(column)}`);
      }
    }
    const numeric = {
      bar: ['y'], line: ['y'], area: ['y'], scatter: ['x', 'y'], bubble: ['x', 'y', 'size'],
      candlestick: ['high', 'low', 'close', 'open'], pie: ['value'], radar: ['y'], waterfall: ['y'],
      heatmap: ['value'], treemap: ['value'], sunburst: ['value'], sankey: ['flow'],
    }[type] || [];
    for (const channel of numeric) if (typeof value.encode[channel] === 'string') checkNumericColumn(dataCols.rows, dataCols.index, value.encode[channel], `${at}.encode.${channel}`, ctx);
    if (type === 'waterfall' && value.encode.isTotal) checkBooleanColumn(dataCols.rows, dataCols.index, value.encode.isTotal, `${at}.encode.isTotal`, ctx);
    if (type === 'heatmap') {
      for (const channel of ['x', 'y']) if (typeof value.encode[channel] === 'string') checkCategoryColumn(dataCols.rows, dataCols.index, value.encode[channel], `${at}.encode.${channel}`, ctx);
    }
    if (type === 'radar' || type === 'pie' || type === 'treemap' || type === 'sunburst') if (typeof value.encode.category === 'string') checkCategoryColumn(dataCols.rows, dataCols.index, value.encode.category, `${at}.encode.category`, ctx);
    if (type === 'sankey') {
      for (const channel of ['source', 'target']) if (typeof value.encode[channel] === 'string') checkNonEmptyStringColumn(dataCols.rows, dataCols.index, value.encode[channel], `${at}.encode.${channel}`, ctx);
    }
    if ((type === 'treemap' || type === 'sunburst') && value.encode.parent) checkNullableStringColumn(dataCols.rows, dataCols.index, value.encode.parent, `${at}.encode.parent`, ctx);
  }
  if (own(value, 'name')) expectString(value.name, `${at}.name`, ctx, true);
  for (const key of ['xAxisIndex', 'yAxisIndex']) if (own(value, key)) checkIndex(value[key], `${at}.${key}`, ctx);
  if (own(value, 'dataLabels')) {
    const allowedLabels = {
      pie: new Set(['value', 'percentage', 'category']), waterfall: new Set(['value', 'category']),
      treemap: new Set(['value', 'category']), sunburst: new Set(['value', 'category']), sankey: new Set(['value', 'category']),
    }[type] || new Set(['value']);
    checkDataLabels(value.dataLabels, `${at}.dataLabels`, ctx, allowedLabels);
  }
  if (['line', 'area', 'radar'].includes(type)) {
    if (own(value, 'smooth')) expectBoolean(value.smooth, `${at}.smooth`, ctx);
    if (own(value, 'lineStyle')) expectEnum(value.lineStyle, LINE_STYLES, `${at}.lineStyle`, ctx);
    if (own(value, 'width')) expectNumber(value.width, `${at}.width`, ctx, { min: 0, exclusiveMin: true });
    if (own(value, 'marker')) checkMarker(value.marker, `${at}.marker`, ctx, true);
    if (own(value, 'nullHandling')) expectEnum(value.nullHandling, new Set(['zero', 'gap', 'connect']), `${at}.nullHandling`, ctx);
    if (own(value, 'lineColor')) checkSeriesFill(value.lineColor, `${at}.lineColor`, ctx);
  }
  if (type === 'radar' && own(value, 'areaColor')) checkSeriesFill(value.areaColor, `${at}.areaColor`, ctx);
  if (type === 'area' && own(value, 'areaColor')) checkSeriesFill(value.areaColor, `${at}.areaColor`, ctx);
  if (type === 'bar') {
    if (own(value, 'stack')) expectEnum(value.stack, new Set(['value', 'percent']), `${at}.stack`, ctx);
    if (own(value, 'symbol')) checkShapeDefinition(value.symbol, `${at}.symbol`, ctx);
    checkSeriesStyle(value, at, ctx, 'fill');
    if (own(value, 'border')) checkBorder(value.border, `${at}.border`, ctx);
  }
  if (type === 'line' || type === 'area' || type === 'radar') { /* fields checked above */ }
  if (type === 'scatter') {
    if (own(value, 'dataFilter')) checkDataFilter(value.dataFilter, `${at}.dataFilter`, ctx, dataCols.names);
    if (own(value, 'marker')) checkMarker(value.marker, `${at}.marker`, ctx, false);
    checkSeriesStyle(value, at, ctx, 'fill');
    if (own(value, 'border')) checkBorder(value.border, `${at}.border`, ctx);
  }
  if (type === 'bubble') {
    if (own(value, 'dataFilter')) checkDataFilter(value.dataFilter, `${at}.dataFilter`, ctx, dataCols.names);
    if (own(value, 'sizeScale')) expectEnum(value.sizeScale, new Set(['linear', 'sqrt', 'log']), `${at}.sizeScale`, ctx);
    if (own(value, 'sizeRange')) {
      if (expectArray(value.sizeRange, `${at}.sizeRange`, ctx) && value.sizeRange.length === 2) {
        value.sizeRange.forEach((item, index) => expectNumber(item, `${at}.sizeRange[${index}]`, ctx, { min: 0, exclusiveMin: true }));
        if (value.sizeRange.every(isFiniteNumber) && value.sizeRange[0] >= value.sizeRange[1]) error(ctx, `${at}.sizeRange`, 'minimum must be less than maximum');
      }
    }
    checkSeriesStyle(value, at, ctx, 'fill');
    if (own(value, 'border')) checkBorder(value.border, `${at}.border`, ctx);
  }
  if (type === 'candlestick') {
    for (const key of ['upBars', 'downBars']) if (own(value, key)) checkBarRoleStyle(value[key], `${at}.${key}`, ctx);
    if (own(value, 'wickStyle')) checkBorder(value.wickStyle, `${at}.wickStyle`, ctx);
  }
  if (type === 'pie') {
    if (own(value, 'innerRadius')) expectNumber(value.innerRadius, `${at}.innerRadius`, ctx, { min: 0, max: 1 });
    if (own(value, 'startAngle')) expectNumber(value.startAngle, `${at}.startAngle`, ctx, { min: 0, max: 360, exclusiveMax: true });
    if (own(value, 'fill')) checkSeriesFill(value.fill, `${at}.fill`, ctx, { collection: true });
    if (own(value, 'border')) checkBorder(value.border, `${at}.border`, ctx);
  }
  if (type === 'waterfall') {
    for (const key of ['totalBars', 'increaseBars', 'decreaseBars']) if (own(value, key)) checkBarRoleStyle(value[key], `${at}.${key}`, ctx);
  }
  if (type === 'heatmap') {
    if (own(value, 'colorScheme')) {
      if (expectArray(value.colorScheme, `${at}.colorScheme`, ctx, 2)) value.colorScheme.forEach((item, index) => checkColor(item, `${at}.colorScheme[${index}]`, ctx));
    }
    if (own(value, 'colorScale')) {
      if (expectObject(value.colorScale, `${at}.colorScale`, ctx)) {
        unknownKeys(value.colorScale, new Set(['type', 'domain']), `${at}.colorScale`, ctx);
        if (own(value.colorScale, 'type')) expectEnum(value.colorScale.type, new Set(['linear', 'diverging']), `${at}.colorScale.type`, ctx);
        if (own(value.colorScale, 'domain')) checkNumberRange(value.colorScale.domain, `${at}.colorScale.domain`, ctx);
        if (value.colorScale.type === 'diverging' && Array.isArray(value.colorScheme) && value.colorScheme.length !== 3) error(ctx, `${at}.colorScheme`, 'diverging heatmap requires exactly three colors');
      }
    }
    if (own(value, 'colorbar')) checkLegend(value.colorbar, `${at}.colorbar`, ctx);
  }
  if (type === 'treemap' || type === 'sunburst') {
    if (own(value, 'levels')) {
      expectNumber(value.levels, `${at}.levels`, ctx, { min: 1 });
      if (!isInteger(value.levels)) error(ctx, `${at}.levels`, 'levels must be a positive integer');
    }
    if (own(value, 'fill')) checkSeriesFill(value.fill, `${at}.fill`, ctx, { collection: true, nested: type === 'treemap' });
    if (own(value, 'border')) checkBorder(value.border, `${at}.border`, ctx);
  }
  if (type === 'sankey') {
    if (own(value, 'nodeAlign')) expectEnum(value.nodeAlign, new Set(['left', 'right', 'justify']), `${at}.nodeAlign`, ctx);
    if (own(value, 'fill')) checkSeriesFill(value.fill, `${at}.fill`, ctx, { collection: true, record: true });
    if (own(value, 'border')) checkBorder(value.border, `${at}.border`, ctx);
  }
  if (defaults) {
    // Defaults use the same field validators, but they do not carry data
    // encodings.  `requiredChannels` is intentionally skipped above.
  }
}

function checkBarRoleStyle(value, at, ctx) {
  if (!expectObject(value, at, ctx)) return;
  unknownKeys(value, new Set(['fill', 'border']), at, ctx);
  if (own(value, 'fill')) checkSeriesFill(value.fill, `${at}.fill`, ctx);
  if (own(value, 'border')) checkBorder(value.border, `${at}.border`, ctx);
}

function checkNumberRange(value, at, ctx) {
  if (expectArray(value, at, ctx) && value.length === 2) {
    value.forEach((item, index) => expectNumber(item, `${at}[${index}]`, ctx));
    if (value.every(isFiniteNumber) && value[0] >= value[1]) error(ctx, at, 'range minimum must be less than maximum');
  }
}

function checkNumericColumn(rows, index, column, at, ctx) {
  if (!index.has(column)) return;
  for (const [rowIndex, row] of rows.entries()) {
    const value = row[index.get(column)];
    if (value === null) continue;
    if (isFiniteNumber(value)) continue;
    if (typeof value === 'string' && value.trim() !== '' && Number.isFinite(Number(value))) continue;
    error(ctx, `${at} (row ${rowIndex})`, 'numeric channel contains a non-numeric value');
  }
}

function checkBooleanColumn(rows, index, column, at, ctx) {
  if (!index.has(column)) return;
  for (const [rowIndex, row] of rows.entries()) {
    const value = row[index.get(column)];
    if (value !== null && typeof value !== 'boolean') error(ctx, `${at} (row ${rowIndex})`, 'isTotal channel accepts only boolean or null');
  }
}

function checkCategoryColumn(rows, index, column, at, ctx) {
  if (!index.has(column)) return;
  for (const [rowIndex, row] of rows.entries()) {
    const value = row[index.get(column)];
    if (value !== null && typeof value !== 'string' && !isFiniteNumber(value)) error(ctx, `${at} (row ${rowIndex})`, 'category channel must contain strings or numbers');
  }
}

function checkNonEmptyStringColumn(rows, index, column, at, ctx) {
  if (!index.has(column)) return;
  for (const [rowIndex, row] of rows.entries()) {
    const value = row[index.get(column)];
    if (typeof value !== 'string' || !value.trim()) error(ctx, `${at} (row ${rowIndex})`, 'graph node must be a non-empty string');
  }
}

function checkNullableStringColumn(rows, index, column, at, ctx) {
  if (!index.has(column)) return;
  for (const [rowIndex, row] of rows.entries()) {
    const value = row[index.get(column)];
    if (value !== null && typeof value !== 'string') error(ctx, `${at} (row ${rowIndex})`, 'parent must be a string or null');
  }
}

function checkChartData(value, at, ctx) {
  if (!expectObject(value, at, ctx)) return { names: new Set(), rows: [], index: new Map() };
  unknownKeys(value, new Set(['cols', 'rows']), at, ctx);
  required(ctx, value, 'cols', at);
  required(ctx, value, 'rows', at);
  const cols = value.cols;
  const rows = value.rows;
  const names = new Set();
  const index = new Map();
  if (expectArray(cols, `${at}.cols`, ctx, 1)) cols.forEach((column, i) => {
    if (typeof column !== 'string' || !column.trim()) error(ctx, `${at}.cols[${i}]`, 'column names must be non-empty strings');
    else if (names.has(column)) error(ctx, `${at}.cols[${i}]`, `duplicate column ${JSON.stringify(column)}`);
    else { names.add(column); index.set(column, i); }
  });
  if (expectArray(rows, `${at}.rows`, ctx)) rows.forEach((row, r) => {
    if (!Array.isArray(row)) {
      error(ctx, `${at}.rows[${r}]`, 'row must be an array');
      return;
    }
    if (Array.isArray(cols) && row.length !== cols.length) error(ctx, `${at}.rows[${r}]`, `row length ${row.length} does not match cols length ${cols.length}`);
    row.forEach((cell, c) => {
      // Boolean cells are needed by waterfall's optional isTotal channel.
      // Channel-specific validators below still reject booleans for numeric
      // and category channels.
      if (cell !== null && typeof cell !== 'string' && typeof cell !== 'boolean' && !isFiniteNumber(cell)) error(ctx, `${at}.rows[${r}][${c}]`, 'cell must be number, string, boolean, or null');
    });
  });
  return { names, rows: Array.isArray(rows) ? rows : [], index };
}

function checkSankeyAcyclic(data, encode, at, ctx) {
  if (!encode || !data.index.has(encode.source) || !data.index.has(encode.target)) return;
  const sourceIndex = data.index.get(encode.source);
  const targetIndex = data.index.get(encode.target);
  const graph = new Map();
  const indegree = new Map();
  for (const row of data.rows) {
    const source = row[sourceIndex];
    const target = row[targetIndex];
    if (typeof source !== 'string' || typeof target !== 'string' || !source || !target) continue;
    if (!graph.has(source)) graph.set(source, new Set());
    if (!graph.has(target)) graph.set(target, new Set());
    if (!graph.get(source).has(target)) {
      graph.get(source).add(target);
      indegree.set(target, (indegree.get(target) || 0) + 1);
    }
    if (!indegree.has(source)) indegree.set(source, indegree.get(source) || 0);
  }
  const queue = [...graph.keys()].filter((node) => (indegree.get(node) || 0) === 0);
  let seen = 0;
  while (queue.length) {
    const node = queue.shift();
    seen += 1;
    for (const next of graph.get(node) || []) {
      indegree.set(next, indegree.get(next) - 1);
      if (indegree.get(next) === 0) queue.push(next);
    }
  }
  if (seen !== graph.size) error(ctx, at, 'sankey source/target graph contains a cycle');
}

function checkChartElement(value, at, ctx) {
  unknownKeys(value, new Set([
    'elementId', 'elementType', 'bounds', 'data', 'series', 'seriesDefaults',
    'xAxis', 'yAxis', 'barWidth', 'barGap', 'categoryGap', 'spokeAxis', 'title',
    'legend', 'dataLabels', 'fontFamily', 'fill', 'border', 'shadow',
  ]), at, ctx);
  required(ctx, value, 'data', at);
  required(ctx, value, 'series', at);
  const data = checkChartData(value.data, `${at}.data`, ctx);
  const series = value.series;
  if (!expectArray(series, `${at}.series`, ctx, 1)) return;
  const types = [];
  series.forEach((item, index) => {
    if (!isObject(item)) return;
    if (typeof item.type !== 'string' || !CHART_TYPES.has(item.type)) {
      error(ctx, `${at}.series[${index}].type`, `unsupported series type ${JSON.stringify(item.type)}`);
      return;
    }
    if (UNSUPPORTED_LOCAL_CHART_TYPES.has(item.type)) {
      error(ctx, `${at}.series[${index}].type`, `${item.type} is not preserved by the local PPTX writer; use an externally rendered PNG/SVG or a labeled placeholder`);
    }
    types.push(item.type);
    checkSeries(item, `${at}.series[${index}]`, ctx, item.type, data);
  });
  const typeSet = new Set(types);
  const nonRadarExclusive = [...typeSet].filter((type) => EXCLUSIVE_TYPES.has(type) && type !== 'radar');
  if (nonRadarExclusive.length && (typeSet.size !== 1 || types.length !== 1)) error(ctx, `${at}.series`, 'exclusive chart series types cannot be mixed or repeated');
  if (typeSet.has('candlestick') && [...typeSet].some((type) => !['candlestick', 'bar', 'line', 'area'].includes(type))) error(ctx, `${at}.series`, 'candlestick may mix only with bar, line, or area');
  if (typeSet.has('radar') && [...typeSet].some((type) => type !== 'radar')) error(ctx, `${at}.series`, 'radar cannot be mixed with other series types');
  for (const type of ['bar', 'area']) {
    const modes = types.filter((item) => item === type).map((_, index) => series.filter((s) => s?.type === type)[index]?.stack).filter(Boolean);
    if (new Set(modes).size > 1) error(ctx, `${at}.series`, `${type} stacked series must use one stack mode`);
  }
  const radarCategories = series.filter((s) => s?.type === 'radar' && s.encode?.category).map((s) => s.encode.category);
  if (new Set(radarCategories).size > 1) error(ctx, `${at}.series`, 'all radar series must share one category column');
  if (own(value, 'seriesDefaults')) {
    if (expectObject(value.seriesDefaults, `${at}.seriesDefaults`, ctx)) {
      const supported = new Set(['bar', 'line', 'area', 'scatter', 'bubble', 'candlestick', 'radar']);
      unknownKeys(value.seriesDefaults, supported, `${at}.seriesDefaults`, ctx);
      for (const [type, defaults] of Object.entries(value.seriesDefaults)) checkSeries(defaults, `${at}.seriesDefaults.${type}`, ctx, type, data, true);
    }
  }
  for (const axisKey of ['xAxis', 'yAxis']) if (own(value, axisKey)) {
    const axisValue = value[axisKey];
    if (Array.isArray(axisValue)) axisValue.forEach((axis, index) => checkAxis(axis, `${at}.${axisKey}[${index}]`, ctx));
    else checkAxis(axisValue, `${at}.${axisKey}`, ctx);
  }
  const axisIndexTypes = {
    xAxis: series.map((s) => s?.xAxisIndex || 0),
    yAxis: series.map((s) => s?.yAxisIndex || 0),
  };
  for (const [axisKey, indexes] of Object.entries(axisIndexTypes)) {
    const maxIndex = Math.max(...indexes, 0);
    if (maxIndex > 0 && (!Array.isArray(value[axisKey]) || value[axisKey].length <= maxIndex)) error(ctx, at, `${axisKey} must be an array long enough for series index ${maxIndex}`);
  }
  if (own(value, 'barWidth')) expectNumber(value.barWidth, `${at}.barWidth`, ctx, { min: 0, max: 1, exclusiveMin: true });
  if (own(value, 'barGap')) expectNumber(value.barGap, `${at}.barGap`, ctx, { min: 0, max: 1, exclusiveMax: true });
  if (own(value, 'categoryGap')) expectNumber(value.categoryGap, `${at}.categoryGap`, ctx, { min: 0, max: 1, exclusiveMax: true });
  if (own(value, 'spokeAxis')) checkSpokeAxis(value.spokeAxis, `${at}.spokeAxis`, ctx);
  if (own(value, 'title')) checkTitle(value.title, `${at}.title`, ctx);
  if (own(value, 'legend')) checkLegend(value.legend, `${at}.legend`, ctx);
  if (own(value, 'dataLabels')) checkDataLabels(value.dataLabels, `${at}.dataLabels`, ctx, new Set(['value', 'percentage', 'category']));
  if (own(value, 'fontFamily')) checkFontFamily(value.fontFamily, `${at}.fontFamily`, ctx);
  if (own(value, 'fill')) checkFill(value.fill, `${at}.fill`, ctx);
  if (own(value, 'border')) checkBorder(value.border, `${at}.border`, ctx);
  if (own(value, 'shadow')) checkShadow(value.shadow, `${at}.shadow`, ctx);
  const axisApplicable = {
    xAxis: CARTESIAN_TYPES, yAxis: CARTESIAN_TYPES,
    barWidth: new Set(['bar', 'waterfall']), barGap: new Set(['bar', 'waterfall']),
    categoryGap: new Set(['bar', 'candlestick', 'waterfall']), spokeAxis: new Set(['radar']),
  };
  for (const [field, applicable] of Object.entries(axisApplicable)) if (own(value, field) && !types.some((type) => applicable.has(type))) error(ctx, `${at}.${field}`, `field is not applicable to series type(s) ${types.join(', ')}`);
  if (types[0] === 'sankey' && series[0]?.encode) checkSankeyAcyclic(data, series[0].encode, `${at}.series[0].encode`, ctx);
}

function checkElement(value, at, ctx) {
  if (!checkElementBase(value, at, ctx)) return;
  switch (value.elementType) {
    case 'text': checkTextElement(value, at, ctx); break;
    case 'shape': checkShapeElement(value, at, ctx); break;
    case 'line': checkLineElement(value, at, ctx); break;
    case 'image': checkImageElement(value, at, ctx); break;
    case 'icon': checkIconElement(value, at, ctx); break;
    case 'table': checkTableElement(value, at, ctx); break;
    case 'chart': checkChartElement(value, at, ctx); break;
    default: break;
  }
}

function checkMotionPath(value, at, ctx) {
  checkSvgPath(value, at, ctx, { motion: true });
}

function checkAnimation(value, at, ctx, ids) {
  if (!expectObject(value, at, ctx)) return;
  unknownKeys(value, new Set(['elementId', 'effect', 'trigger', 'direction', 'durationMs', 'delayMs', 'easing', 'repeat', 'path', 'color', 'amount']), at, ctx);
  required(ctx, value, 'elementId', at);
  required(ctx, value, 'effect', at);
  if (own(value, 'elementId')) {
    expectString(value.elementId, `${at}.elementId`, ctx, true);
    if (typeof value.elementId === 'string' && !ids.has(value.elementId)) error(ctx, `${at}.elementId`, `animation target does not exist: ${JSON.stringify(value.elementId)}`);
  }
  if (own(value, 'effect')) expectEnum(value.effect, ANIMATION_EFFECTS, `${at}.effect`, ctx);
  if (own(value, 'trigger')) expectEnum(value.trigger, ANIMATION_TRIGGERS, `${at}.trigger`, ctx);
  if (own(value, 'direction')) expectEnum(value.direction, ANIMATION_DIRECTIONS, `${at}.direction`, ctx);
  if (own(value, 'durationMs')) expectNumber(value.durationMs, `${at}.durationMs`, ctx, { min: 0, exclusiveMin: true });
  if (own(value, 'delayMs')) expectNumber(value.delayMs, `${at}.delayMs`, ctx, { min: 0 });
  if (own(value, 'easing')) expectEnum(value.easing, ANIMATION_EASINGS, `${at}.easing`, ctx);
  if (own(value, 'repeat')) {
    expectNumber(value.repeat, `${at}.repeat`, ctx, { min: 1 });
    if (!isInteger(value.repeat)) error(ctx, `${at}.repeat`, 'repeat must be a positive integer');
  }
  const effect = value.effect;
  const directionEffects = new Set(['fly-in', 'fly-out', 'wipe-in', 'wipe-out', 'float-in', 'float-out', 'peek-in']);
  if (['float-in', 'float-out'].includes(effect) && own(value, 'direction') && !['up', 'down'].includes(value.direction)) error(ctx, `${at}.direction`, 'float effects support only up or down');
  if (effect === 'motion-path') {
    required(ctx, value, 'path', at);
    if (own(value, 'path')) checkMotionPath(value.path, `${at}.path`, ctx);
  } else if (own(value, 'path')) error(ctx, `${at}.path`, 'path is only valid for motion-path');
  const needsColor = effect === 'fill-color' || effect === 'color-pulse';
  if (needsColor) {
    required(ctx, value, 'color', at);
    if (own(value, 'color')) checkAnimationColor(value.color, `${at}.color`, ctx);
  } else if (own(value, 'color')) error(ctx, `${at}.color`, 'color is only valid for fill-color or color-pulse');
  if (effect === 'transparency') {
    required(ctx, value, 'amount', at);
    if (own(value, 'amount')) expectNumber(value.amount, `${at}.amount`, ctx, { min: 0, max: 1 });
  } else if (own(value, 'amount')) error(ctx, `${at}.amount`, 'amount is only valid for transparency');
}

function checkPage(value, at, ctx) {
  if (!expectObject(value, at, ctx)) return;
  unknownKeys(value, new Set(['pageType', 'background', 'notes', 'elements', 'animations']), at, ctx);
  if (own(value, 'pageType')) expectString(value.pageType, `${at}.pageType`, ctx, true);
  if (own(value, 'background')) checkFill(value.background, `${at}.background`, ctx);
  if (own(value, 'notes')) expectString(value.notes, `${at}.notes`, ctx);
  required(ctx, value, 'elements', at);
  const elements = value.elements;
  const ids = new Set();
  if (expectArray(elements, `${at}.elements`, ctx)) elements.forEach((element, index) => {
    const elementAt = `${at}.elements[${index}]`;
    checkElement(element, elementAt, ctx);
    if (isObject(element) && typeof element.elementId === 'string') {
      if (ids.has(element.elementId)) error(ctx, `${elementAt}.elementId`, `duplicate elementId ${JSON.stringify(element.elementId)}`);
      ids.add(element.elementId);
    }
  });
  if (own(value, 'animations')) {
    if (expectArray(value.animations, `${at}.animations`, ctx)) value.animations.forEach((animation, index) => checkAnimation(animation, `${at}.animations[${index}]`, ctx, ids));
  }
}

function checkTheme(value, at, ctx) {
  if (!expectObject(value, at, ctx)) return;
  unknownKeys(value, new Set(['colors', 'textStyles', 'tableStyles']), at, ctx);
  for (const key of ['colors', 'textStyles', 'tableStyles']) if (own(value, key) && !isObject(value[key])) error(ctx, `${at}.${key}`, 'must be an object map');
  if (isObject(value.colors)) for (const [key, color] of Object.entries(value.colors)) { if (!key.trim()) error(ctx, `${at}.colors`, 'color keys must be non-empty'); checkColor(color, `${at}.colors.${key}`, ctx); }
  if (isObject(value.textStyles)) for (const [key, style] of Object.entries(value.textStyles)) checkTextStyle(style, `${at}.textStyles.${key}`, ctx);
  if (isObject(value.tableStyles)) for (const [key, style] of Object.entries(value.tableStyles)) checkTableStyle(style, `${at}.tableStyles.${key}`, ctx);
}

function normalizeInput(input) {
  if (!isObject(input)) return { manifest: null, pageEntries: [] };
  const manifest = isObject(input.manifest) ? input.manifest : input;
  const pageEntries = Array.isArray(input.pages) ? input.pages : [];
  return { manifest, pageEntries };
}

export function validatePptdProject(input, options = {}) {
  const { manifest, pageEntries } = normalizeInput(input);
  const provisionalTheme = isObject(manifest?.theme) ? manifest.theme : {};
  const ctx = makeContext({
    ...options,
    themeColors: isObject(provisionalTheme.colors) ? Object.keys(provisionalTheme.colors) : [],
    textStyles: isObject(provisionalTheme.textStyles) ? Object.keys(provisionalTheme.textStyles) : [],
    tableStyles: isObject(provisionalTheme.tableStyles) ? Object.keys(provisionalTheme.tableStyles) : [],
    pageSize: Array.isArray(manifest?.size) ? manifest.size : null,
  });
  if (!expectObject(manifest, '$.manifest', ctx)) throwValidation(ctx);
  unknownKeys(manifest, new Set(['version', 'title', 'customFonts', 'size', 'theme', 'pages']), '$.manifest', ctx);
  required(ctx, manifest, 'version', '$.manifest');
  required(ctx, manifest, 'size', '$.manifest');
  required(ctx, manifest, 'pages', '$.manifest');
  if (manifest.version !== 'v2') error(ctx, '$.manifest.version', 'only PPTD version "v2" is supported');
  if (own(manifest, 'title')) expectString(manifest.title, '$.manifest.title', ctx);
  if (own(manifest, 'size')) {
    if (expectArray(manifest.size, '$.manifest.size', ctx) && manifest.size.length === 2) manifest.size.forEach((item, index) => expectNumber(item, `$.manifest.size[${index}]`, ctx, { min: 0, exclusiveMin: true }));
  }
  if (own(manifest, 'customFonts')) {
    if (expectArray(manifest.customFonts, '$.manifest.customFonts', ctx)) manifest.customFonts.forEach((font, index) => {
      const at = `$.manifest.customFonts[${index}]`;
      if (!expectObject(font, at, ctx)) return;
      unknownKeys(font, new Set(['family', 'src']), at, ctx);
      required(ctx, font, 'family', at); required(ctx, font, 'src', at);
      if (own(font, 'family')) expectString(font.family, `${at}.family`, ctx, true);
      if (own(font, 'src')) expectString(font.src, `${at}.src`, ctx, true);
    });
  }
  if (own(manifest, 'theme')) checkTheme(manifest.theme, '$.manifest.theme', ctx);
  if (isObject(manifest.theme)) {
    // Keep theme reference validation active even when a theme map is empty.
    ctx.themeColors = new Set(isObject(manifest.theme.colors) ? Object.keys(manifest.theme.colors) : []);
    ctx.textStyles = new Set(isObject(manifest.theme.textStyles) ? Object.keys(manifest.theme.textStyles) : []);
    ctx.tableStyles = new Set(isObject(manifest.theme.tableStyles) ? Object.keys(manifest.theme.tableStyles) : []);
  }
  const manifestPages = manifest.pages;
  const pagePaths = new Set();
  if (expectArray(manifestPages, '$.manifest.pages', ctx, 1)) manifestPages.forEach((entry, index) => {
    const at = `$.manifest.pages[${index}]`;
    if (!expectString(entry, at, ctx, true)) return;
    if (!safeRelativePath(entry)) error(ctx, at, 'page path must be relative and must not escape the project');
    if (pagePaths.has(entry)) error(ctx, at, `duplicate page path ${JSON.stringify(entry)}`);
    pagePaths.add(entry);
    if (ctx.root && ctx.checkFiles) {
      const resolved = path.resolve(ctx.root, entry);
      try {
        if (!resolved.startsWith(`${ctx.root}${path.sep}`) || !fs.statSync(resolved).isFile()) error(ctx, at, `page file does not exist: ${entry}`);
      } catch { error(ctx, at, `page file does not exist: ${entry}`); }
    }
  });
  if (pageEntries.length !== (Array.isArray(manifestPages) ? manifestPages.length : 0)) error(ctx, '$.pages', `loaded ${pageEntries.length} page(s), manifest lists ${Array.isArray(manifestPages) ? manifestPages.length : 0}`);
  pageEntries.forEach((entry, index) => {
    const page = isObject(entry) && own(entry, 'data') ? entry.data : entry;
    const rel = isObject(entry) && (entry.path || entry.pagePath) ? (entry.path || entry.pagePath) : manifestPages?.[index];
    checkPage(page, `$.pages[${index}]${rel ? `(${rel})` : ''}`, ctx);
  });
  if (ctx.errors.length) throwValidation(ctx);
  return { ok: true, pageCount: pageEntries.length };
}

function throwValidation(ctx) {
  const suffix = ctx.errors.length > 200 ? `\n... ${ctx.errors.length - 200} more error(s)` : '';
  const errorObject = new Error(`PPTD validation failed with ${ctx.errors.length} error(s):\n- ${ctx.errors.join('\n- ')}${suffix}`);
  errorObject.name = 'PptdValidationError';
  errorObject.validationErrors = [...ctx.errors];
  throw errorObject;
}

async function readStdin() {
  const chunks = [];
  for await (const chunk of process.stdin) chunks.push(chunk);
  return Buffer.concat(chunks).toString('utf8');
}

if (process.argv.includes('--stdin')) {
  try {
    const raw = await readStdin();
    const input = JSON.parse(raw);
    validatePptdProject(input, {
      projectRoot: input.projectRoot || undefined,
      checkFiles: input.checkFiles !== false,
    });
    process.stdout.write(JSON.stringify({ ok: true }));
  } catch (cause) {
    process.stderr.write(`${cause?.message || String(cause)}\n`);
    process.exitCode = 1;
  }
}
