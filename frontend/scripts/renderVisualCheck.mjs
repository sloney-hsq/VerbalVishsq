// Render trusted local smoke results to six SVGs and a contact sheet.
import { readFile, writeFile, mkdir } from 'node:fs/promises';
import path from 'node:path';
import { compile } from 'vega-lite';
import * as vega from 'vega';
import { createSpec } from '../src/specFactory.js';

const [manifestPath, outputPath] = process.argv.slice(2);
if (!manifestPath || !outputPath) throw new Error('Usage: node renderVisualCheck.mjs views.json output-dir');
const views = JSON.parse(await readFile(manifestPath, 'utf8'));
await mkdir(outputPath, {recursive:true});
const examples = [
  ['bar','delivery_rank'], ['line','delivery_monthly'], ['scatter','freight_scatter'],
  ['heatmap','delivery_heatmap'], ['histogram','freight_histogram'], ['boxplot','delivery_box'],
];
for (const [type,key] of examples) {
  const source = views[key];
  if (!source || source.visual?.type !== type) throw new Error(`Missing ${type} result: ${key}`);
  const spec = createSpec(source);
  const compiled = compile({...spec,width:560}).spec;
  const svg = await new vega.View(vega.parse(compiled), {renderer:'svg'}).toSVG();
  if (!svg.includes('<svg')) throw new Error(`SVG render failed: ${key}`);
  await writeFile(path.join(outputPath,`${type}.svg`),svg,'utf8');
}
const cards = examples.map(([type,key]) => `<section><h2>${type} — ${key}</h2><img src="${type}.svg" alt="${type} rendered from actual Olist data"></section>`).join('\n');
await writeFile(path.join(outputPath,'index.html'),`<!doctype html><html lang="en"><meta charset="utf-8"><title>Visual analysis check</title><style>body{font:14px system-ui;background:#f4f6fa;color:#172133;padding:24px}main{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px}section{background:white;padding:12px;border-radius:8px;overflow:hidden}img{width:100%;height:auto}h2{font-size:16px}@media(max-width:900px){main{grid-template-columns:1fr}}</style><h1>Olist visual analysis — six chart families</h1><main>${cards}</main></html>`,'utf8');
console.log(`Rendered ${examples.length} SVGs to ${outputPath}`);
