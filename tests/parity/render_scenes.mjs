/* Render scenes with the browser-side renderer.
 *
 * Usage: node render_scenes.mjs <input.json> <output.json>
 * input:  {"icons": {...}, "scenes": [...], "values": [...]}
 * output: {"svgs": ["..."], "formatted": ["..."]}
 *
 * The canvas in the browser draws from the same scene JSON as the Python
 * exporter. If the two drift apart, what you edit stops matching what you
 * export, so this runs both over the same input and the test diffs them.
 */

import { fileURLToPath, pathToFileURL } from 'node:url';
import { dirname, join } from 'node:path';
import { readFileSync, writeFileSync } from 'node:fs';

const here = dirname(fileURLToPath(import.meta.url));
// A bare absolute path is not importable on Windows ("d:\..." is read as a URL
// scheme), so the path becomes a file:// URL before it is imported.
const scene = await import(pathToFileURL(join(here, '..', '..', 'src', 'figwright', 'web', 'scene.js')).href);

const [, , inPath, outPath] = process.argv;
const data = JSON.parse(readFileSync(inPath, 'utf8'));
if (data.icons) scene.setIcons(data.icons);

writeFileSync(
  outPath,
  JSON.stringify({
    svgs: (data.scenes || []).map((s) => scene.renderSvg(s)),
    formatted: (data.values || []).map((v) => scene.fmt(v)),
  }),
);
