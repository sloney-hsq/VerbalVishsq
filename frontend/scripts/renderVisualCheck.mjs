// Render trusted local smoke results to six SVGs and a contact sheet.
import { readFile, writeFile, mkdir } from 'node:fs/promises';
import path from 'node:path';
import { compile } from 'vega-lite';
import * as vega from 'vega';
import { createSpec } from '../src/specFactory.js';
import { chartLayoutForView, heatmapPresentation } from '../src/chartLayout.js';

const [manifestPath, outputPath] = process.argv.slice(2);
if (!manifestPath || !outputPath) throw new Error('Usage: node renderVisualCheck.mjs views.json output-dir');
const views = JSON.parse(await readFile(manifestPath, 'utf8'));
await mkdir(outputPath, {recursive:true});
await writeFile(path.join(outputPath,'views.json'),JSON.stringify(views),'utf8');
const examples = [
  ['bar','delivery_rank'], ['line','delivery_monthly'], ['scatter','freight_scatter'],
  ['heatmap','delivery_heatmap'], ['histogram','freight_histogram'], ['boxplot','delivery_box'],
];
for (const [type,key] of examples) {
  const source = views[key];
  if (!source || source.visual?.type !== type) throw new Error(`Missing ${type} result: ${key}`);
  const presentation = type === 'heatmap' ? heatmapPresentation(source,{pageIndex:0,mode:'paged'},920) : null;
  const spec = createSpec(source,null,presentation);
  const compiled = compile({...spec,width:type === 'heatmap' ? 1180 : 560}).spec;
  const svg = await new vega.View(vega.parse(compiled), {renderer:'svg'}).toSVG();
  if (!svg.includes('<svg')) throw new Error(`SVG render failed: ${key}`);
  await writeFile(path.join(outputPath,`${type}.svg`),svg,'utf8');
}
const heatmapView = views.delivery_heatmap;
const heatmapLayout = chartLayoutForView(heatmapView,920);
for (let pageIndex=0; pageIndex<heatmapLayout.heatmap.pageCount; pageIndex+=1) {
  const page = heatmapPresentation(heatmapView,{pageIndex,mode:'paged'},920);
  const svg = await new vega.View(vega.parse(compile({...createSpec(heatmapView,null,page),width:1180}).spec),{renderer:'svg'}).toSVG();
  await writeFile(path.join(outputPath,`heatmap-page-${pageIndex + 1}.svg`),svg,'utf8');
}
const full = heatmapPresentation(heatmapView,{pageIndex:0,mode:'all'},920);
const fullSvg = await new vega.View(vega.parse(compile({...createSpec(heatmapView,null,full),width:1180}).spec),{renderer:'svg'}).toSVG();
await writeFile(path.join(outputPath,'heatmap-full.svg'),fullSvg,'utf8');
const displayExamples = [['bar','delivery_rank'],['histogram','freight_histogram'],['line','delivery_monthly'],
  ['scatter','freight_scatter'],['boxplot','delivery_box'],['heatmap','delivery_heatmap']];
const cards = displayExamples.map(([type,key]) => type === 'heatmap'
  ? `<section class="wide-card heatmap-card"><h2>${type} — ${key}</h2><nav aria-label="Heatmap pages"><button data-step="-1">Previous</button><span id="page-label">Page 1 of ${heatmapLayout.heatmap.pageCount}</span><button data-step="1">Next</button><button id="view-all">View all</button><span id="range-label">1–${Math.min(20,heatmapLayout.heatmap.domain.length)} of ${heatmapLayout.heatmap.domain.length} categories</span></nav><div class="heatmap-frame"><img id="heatmap-image" src="heatmap.svg" alt="heatmap rendered from actual Olist data"></div></section>`
  : `<section class="${type === 'line' ? 'wide-card' : ''}"><h2>${type} — ${key}</h2><img src="${type}.svg" alt="${type} rendered from actual Olist data"></section>`).join('\n');
await writeFile(path.join(outputPath,'index.html'),`<!doctype html><html lang="en"><meta charset="utf-8"><title>Visual analysis check</title><style>*{box-sizing:border-box}body{font:14px system-ui;background:#f4f6fa;color:#172133;padding:24px;margin:0}main{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px;max-width:1440px;margin:auto}section{background:white;padding:12px;border:1px solid #d9e1ec;border-radius:12px;overflow:hidden}section>img{width:100%;height:auto}.wide-card{grid-column:1/-1}.heatmap-card nav{display:flex;align-items:center;flex-wrap:wrap;gap:8px;margin-bottom:8px}.heatmap-card button{padding:5px 9px;border:1px solid #cbd5e1;border-radius:6px;background:#f8fafc}.heatmap-frame{max-height:620px;overflow:auto}.heatmap-frame img{display:block;width:100%;height:auto;min-width:900px}h1{max-width:1440px;margin:0 auto 18px}h2{font-size:16px}@media(max-width:879px){main{grid-template-columns:1fr}.wide-card{grid-column:span 1}body{padding:12px}}</style><h1>Olist visual analysis — six chart families</h1><main>${cards}</main><script>let page=1,all=false;const total=${heatmapLayout.heatmap.pageCount},count=${heatmapLayout.heatmap.domain.length},size=20,img=document.querySelector('#heatmap-image'),label=document.querySelector('#page-label'),range=document.querySelector('#range-label');function draw(){img.src=all?'heatmap-full.svg':page===1?'heatmap.svg':'heatmap-page-'+page+'.svg';label.textContent=all?'All categories':'Page '+page+' of '+total;range.textContent=all?'All '+count+' categories':((page-1)*size+1)+'–'+Math.min(count,page*size)+' of '+count+' categories';document.querySelector('#view-all').textContent=all?'Paged view':'View all'}document.querySelectorAll('[data-step]').forEach(button=>button.onclick=()=>{all=false;page=Math.max(1,Math.min(total,page+Number(button.dataset.step)));draw()});document.querySelector('#view-all').onclick=()=>{all=!all;draw()}</script>`,'utf8');
console.log(`Rendered ${examples.length} SVGs to ${outputPath}`);
