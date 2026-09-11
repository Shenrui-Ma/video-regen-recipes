#!/usr/bin/env node
// Capture native SVG DOM frames; compose the reference separately with FFmpeg.
const fs=require('node:fs'),path=require('node:path'),{pathToFileURL}=require('node:url');
const {spawn,spawnSync}=require('node:child_process'),{once}=require('node:events');
const {chromium}=require('playwright');
async function main(){
 const args=process.argv.slice(2),get=(k,d)=>{const i=args.indexOf(k);return i<0?d:args[i+1];};
 const html=get('--html'),reference=get('--reference'),output=get('--output'),fps=Number(get('--fps',24)),panel=Number(get('--panel-width',768));
 if(!html||!reference||!output||!output.endsWith('.mp4')||!Number.isInteger(fps)||fps<1||fps>60||!Number.isInteger(panel)||panel<128||panel>1920||panel%2)throw Error('Use --html demo.html --reference reference.png --output new.mp4 [--fps 24 --panel-width 768]');
 if(fs.existsSync(output))throw Error('Output already exists');
 const ffmpeg=get('--ffmpeg','ffmpeg'),ffprobe=get('--ffprobe','ffprobe');
 const probe=spawnSync(ffprobe,['-v','error','-show_entries','stream=width,height','-select_streams','v:0','-of','json',reference],{encoding:'utf8'});
 if(probe.status!==0)throw Error('Cannot inspect the reference image');
 const dimensions=JSON.parse(probe.stdout).streams[0],width=dimensions.width,height=dimensions.height,panelH=Math.round(panel*height/width);
 if(!width||!height||width>8192||height>8192||panelH%2)throw Error('Invalid source or odd video dimensions');
 const layout=get('--layout','auto')==='auto'?(width>=height?'stacked':'side-by-side'):get('--layout');
 if(!['stacked','side-by-side'].includes(layout))throw Error('Unknown layout');
 const parent=path.dirname(path.resolve(output));fs.mkdirSync(parent,{recursive:true});const temp=fs.mkdtempSync(path.join(parent,'.svg-export-')),target=path.join(temp,'render.mp4');
 let browser,encoder,stderr='';
 try{
  browser=await chromium.launch({headless:true,...(get('--browser')?{executablePath:get('--browser')}: {})});
  const page=await browser.newPage({viewport:{width,height},deviceScaleFactor:1});const external=[];
  await page.route('**/*',route=>{if(route.request().url().startsWith('file:'))return route.continue();external.push(route.request().url());return route.abort();});
  await page.goto(pathToFileURL(path.resolve(html)).href,{timeout:120000});
  await page.waitForFunction(()=>window.replay&&typeof window.replay.renderAt==='function',{},{timeout:120000});
  const info=await page.evaluate(()=>{
   if(document.querySelector('canvas,img,image,foreignObject,iframe,script[src],link[rel="stylesheet"]'))throw Error('The Demo must be native SVG without raster or external resources');
   const svg=document.querySelector('svg');if(!svg)throw Error('No SVG found');
   return {duration:window.replay.duration,viewBox:svg.getAttribute('viewBox')};
  });
  if(external.length)throw Error('Demo attempted external requests');
  const box=info.viewBox.trim().split(/[ ,]+/).map(Number);
  if(box.length!==4||box[0]!==0||box[1]!==0||box[2]!==width||box[3]!==height||!Number.isFinite(info.duration)||info.duration<=0||info.duration>300)throw Error('Demo geometry or timeline differs from the reference');
  await page.addStyleTag({content:`html,body{margin:0!important;padding:0!important;overflow:hidden!important;background:white!important}body>*{visibility:hidden!important}svg{position:fixed!important;left:0!important;top:0!important;width:${width}px!important;height:${height}px!important;visibility:visible!important}svg *{visibility:visible!important}`});
  const count=Math.ceil(info.duration*fps),outW=layout==='stacked'?panel:panel*2,outH=layout==='stacked'?panelH*2:panelH;
  const filter=`[0:v]scale=${panel}:${panelH}:flags=lanczos,setsar=1[draw];[1:v]scale=${panel}:${panelH}:flags=lanczos,setsar=1[ref];[ref][draw]${layout==='stacked'?'vstack':'hstack'}=inputs=2[out]`;
  encoder=spawn(ffmpeg,['-nostdin','-v','error','-n','-f','image2pipe','-vcodec','png','-framerate',String(fps),'-i','pipe:0','-loop','1','-framerate',String(fps),'-i',reference,'-filter_complex',filter,'-map','[out]','-frames:v',String(count),'-an','-c:v','libx264','-preset','fast','-crf','18','-pix_fmt','yuv420p','-map_metadata','-1','-movflags','+faststart',target],{stdio:['pipe','ignore','pipe']});
  const completion=new Promise((resolve,reject)=>{encoder.on('error',reject);encoder.on('close',code=>code===0?resolve():reject(Error('FFmpeg failed: '+stderr)));});completion.catch(()=>{});
  encoder.stderr.on('data',d=>stderr=(stderr+d).slice(-1500));encoder.stdin.on('error',()=>{});
  for(let frame=0;frame<count;frame++){
   await page.evaluate(t=>window.replay.renderAt(t),frame/fps);
   const png=await page.screenshot({type:'png',clip:{x:0,y:0,width,height},timeout:120000});
   if(encoder.stdin.destroyed)throw Error('Encoder stopped');
   if(!encoder.stdin.write(png))await once(encoder.stdin,'drain');
   if(frame%(fps*2)===0)process.stdout.write(`Frames ${frame}/${count}\n`);
  }
  encoder.stdin.end();await completion;
  const checked=spawnSync(ffprobe,['-v','error','-count_frames','-select_streams','v:0','-show_entries','stream=width,height,nb_read_frames,avg_frame_rate','-of','json',target],{encoding:'utf8'});
  if(checked.status!==0)throw Error('Output probe failed');const v=JSON.parse(checked.stdout).streams[0];
  if(Number(v.nb_read_frames)!==count||v.width!==outW||v.height!==outH||v.avg_frame_rate!==`${fps}/1`)throw Error('Video does not match requested dimensions or frame count');
  if(spawnSync(ffmpeg,['-v','error','-xerror','-i',target,'-map','0:v:0','-f','null','-'],{stdio:'ignore'}).status!==0)throw Error('Full video decode failed');
  fs.copyFileSync(target,output,fs.constants.COPYFILE_EXCL);
  console.log(JSON.stringify({frames:count,fps,width:outW,height:outH,duration:count/fps,layout,audio:false,canvas:false}));
 }finally{if(encoder&&encoder.exitCode===null)encoder.kill();if(browser)await browser.close();fs.rmSync(temp,{recursive:true,force:true});}
}
main().catch(e=>{console.error(e.message);process.exitCode=1});
