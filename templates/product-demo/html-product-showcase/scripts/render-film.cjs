'use strict';
// Standalone deterministic HTML -> silent MP4. No account/profile access.
// Usage: node render-film.cjs film.html out.mp4 width height seconds fps
// Adapted from html-motion-production 0.1.1 (MIT), Shenrui Ma.
const fs = require('node:fs');
const path = require('node:path');
const { pathToFileURL } = require('node:url');
const { execFileSync } = require('node:child_process');
const crypto = require('node:crypto');
const [input, output, sw='1920', sh='1080', sd='2', sf='30'] = process.argv.slice(2);
const width=Number(sw), height=Number(sh), duration=Number(sd), fps=Number(sf);
if (!input || !output || ![width,height,fps].every(Number.isInteger) ||
    width<64 || height<64 || width>4096 || height>4096 || width%2 || height%2 || fps<1 || fps>120 ||
    !Number.isFinite(duration) || duration<=0 || duration>600) {
  throw new Error('Usage: node render-film.cjs input.html out.mp4 evenWidth evenHeight seconds fps');
}
const frames=Math.round(duration*fps);
if(frames<1 || frames>18000)throw new Error('Frame count must be 1..18000');
const dest=path.resolve(output), source=path.resolve(input);
if(!fs.statSync(source).isFile() || !/\.html?$/i.test(source) || !/\.mp4$/i.test(dest))throw new Error('Need an HTML file and MP4 output');
const reportPath=dest+'.qc.json', lock=dest+'.lock';
if([dest,reportPath,lock].some(p=>fs.existsSync(p)))throw new Error('Output already exists; choose a fresh version');
fs.mkdirSync(path.dirname(dest),{recursive:true});
const errors=[], hashes=new Set();
let browser, temp, ownsLock=false;
(async()=>{
 try {
  const { chromium } = require('playwright');
  fs.writeFileSync(lock,String(process.pid),{flag:'wx'});ownsLock=true;
  if([dest,reportPath].some(p=>fs.existsSync(p)))throw new Error('Output became occupied');
  temp=fs.mkdtempSync(path.join(path.dirname(dest),'.html-motion-'));
  const part=path.join(temp,'film.part.mp4');
  const sourceSha256=crypto.createHash('sha256').update(fs.readFileSync(source)).digest('hex');
  browser=await chromium.launch({headless:true,...(process.env.CHROME_PATH?{executablePath:process.env.CHROME_PATH}:{})});
  const context=await browser.newContext({viewport:{width,height},deviceScaleFactor:1});
  await context.route(/^https?:\/\//,route=>route.abort());
  const page=await context.newPage();
  page.on('pageerror',e=>errors.push(String(e)));
  page.on('console',m=>{if(m.type()==='error')errors.push(m.text());});
  page.on('requestfailed',r=>errors.push('Resource failure: '+r.url()));
  const url=pathToFileURL(source);url.searchParams.set('render','1');
  await page.goto(url.href,{waitUntil:'load',timeout:30000});
  await page.evaluate(async()=>{
   await document.fonts.ready;
   await Promise.all([...document.images].map(img=>img.decode()));
   if(typeof window.setShotTime!=='function')throw new Error('Missing setShotTime(seconds)');
  });
  async function seek(t){await page.evaluate(async t=>{
   await window.setShotTime(t);
   await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));
  },t);}
  // Random/backward seeking must restore the same pixel state.
  await seek(duration*.75); const a=await page.screenshot({animations:'allow'});
  await seek(duration*.1); await seek(duration*.75);
  const b=await page.screenshot({animations:'allow'});
  if(!a.equals(b))throw new Error('Non-deterministic seek: independent CSS/timer/video clock?');
  let maxProtected=0;
  for(let i=0;i<frames;i++){
   await seek(i/fps);
   const qc=await page.evaluate(()=>{
    const stage=document.getElementById('stage');
    if(!stage)throw new Error('Missing #stage');
    const s=stage.getBoundingClientRect(), issues=[];
    if(Math.abs(s.left)>1||Math.abs(s.top)>1||Math.abs(s.width-innerWidth)>1||Math.abs(s.height-innerHeight)>1)
     issues.push('Stage must fill the export viewport');
    const visible=e=>{
     let opacity=1;
     for(let p=e;p;p=p.parentElement){const c=getComputedStyle(p);
      opacity*=Number(c.opacity);
      if(c.display==='none'||c.visibility==='hidden'||c.visibility==='collapse'||opacity<.01)return false;
     }const r=e.getBoundingClientRect();return r.width>0&&r.height>0;
    };
    const items=[...document.querySelectorAll('[data-protected]')].filter(visible);
    for(const e of items){const r=e.getBoundingClientRect();
     if(r.left<s.left-1||r.top<s.top-1||r.right>s.right+1||r.bottom>s.bottom+1)
      issues.push('Outside stage: '+(e.id||e.tagName));
     if(e.scrollWidth>e.clientWidth+2||e.scrollHeight>e.clientHeight+2)
      issues.push('Overflow: '+(e.id||e.tagName));
    }
    for(const m of document.querySelectorAll('[data-mascot]'))if(visible(m)){
     const a=m.getBoundingClientRect();
     for(const e of items){if(e.contains(m)||m.contains(e))continue;
      const b=e.getBoundingClientRect();
      if(Math.min(a.right,b.right)>Math.max(a.left,b.left)&&Math.min(a.bottom,b.bottom)>Math.max(a.top,b.top))
       issues.push('Mascot intersects: '+(e.id||e.tagName));
     }
    }
    return {count:items.length,issues};
   });
   maxProtected=Math.max(maxProtected,qc.count);
   if(qc.issues.length)throw new Error(`frame ${i}: ${qc.issues.join('; ')}`);
   const png=await page.screenshot({animations:'allow'});
   hashes.add(crypto.createHash('sha256').update(png).digest('hex'));
   fs.writeFileSync(path.join(temp,String(i).padStart(6,'0')+'.png'),png);
  }
  if(!maxProtected)throw new Error('No data-protected elements: layout QC would be empty');
  if(errors.length)throw new Error(errors.join('\n'));
  await browser.close();browser=null;
  execFileSync('ffmpeg',['-nostdin','-n','-hide_banner','-v','error','-framerate',String(fps),'-i',path.join(temp,'%06d.png'),'-frames:v',String(frames),'-vf','setsar=1','-c:v','libx264','-preset','medium','-crf','18','-pix_fmt','yuv420p','-an','-movflags','+faststart',part],{stdio:'inherit'});
  execFileSync('ffmpeg',['-v','error','-xerror','-i',part,'-f','null','-'],{stdio:'inherit'});
  const probe=JSON.parse(execFileSync('ffprobe',['-v','error','-select_streams','v:0','-count_frames','-show_entries','stream=width,height,r_frame_rate,sample_aspect_ratio,nb_read_frames:format=duration','-of','json',part],{encoding:'utf8'}));
  const v=probe.streams[0];
  const [rateNum,rateDen]=v.r_frame_rate.split('/').map(Number);
  if(v.width!==width||v.height!==height||Number(v.nb_read_frames)!==frames||v.sample_aspect_ratio!=='1:1'||rateNum/rateDen!==fps)throw new Error('Encoded media differs from requested geometry/frame count');
  const sha256=crypto.createHash('sha256').update(fs.readFileSync(part)).digest('hex');
  const report={source:path.basename(source),sourceSha256,output:path.basename(dest),width,height,fps,requestedDuration:duration,duration:frames/fps,frames,uniqueFrames:hashes.size,protectedElements:maxProtected,deterministicSeek:true,basicDomQC:true,fullDecode:true,visualReview:false,audio:false,sha256,probe};
  const stagedReport=path.join(temp,'report.json');
  fs.writeFileSync(stagedReport,JSON.stringify(report,null,2)+'\n',{flag:'wx'});
  fs.linkSync(part,dest);
  try {fs.linkSync(stagedReport,reportPath);} catch(error){fs.unlinkSync(dest);throw error;}
  console.log(JSON.stringify(report));
 }finally{
  try {if(browser)await browser.close();}
  finally {
   try {if(temp)fs.rmSync(temp,{recursive:true,force:true});}
   finally {if(ownsLock)fs.unlinkSync(lock);}
  }
 }
})().catch(e=>{console.error(e.stack||String(e));process.exitCode=1;});
