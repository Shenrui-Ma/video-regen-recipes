#!/usr/bin/env node
// Requires an existing Playwright+Chromium setup and ffmpeg. No model/API calls.
const fs=require('node:fs');
const path=require('node:path');
const {pathToFileURL}=require('node:url');
const {spawn,spawnSync}=require('node:child_process');
const {once}=require('node:events');
const os=require('node:os');
const {chromium}=require('playwright');

async function main(){
  const args=process.argv.slice(2);
  const get=(key,fallback)=>{const i=args.indexOf(key);return i<0?fallback:args[i+1];};
  const html=get('--html'), output=get('--output');
  const fps=Number(get('--fps',30));
  if(!html || !output || !Number.isInteger(fps) || fps<1 || fps>60 || !output.endsWith('.mp4'))throw Error('Use --html demo.html --output new.mp4 [--fps 30]');
  if(fs.existsSync(output))throw Error('Output already exists');
  const ffmpeg=get('--ffmpeg','ffmpeg');
  if(spawnSync(ffmpeg,['-version'],{stdio:'ignore'}).status!==0)throw Error('FFmpeg is required');
  const parent=path.dirname(path.resolve(output));fs.mkdirSync(parent,{recursive:true});
  const temp=fs.mkdtempSync(path.join(parent,'.svg-video-'));const target=path.join(temp,'render.mp4');
  let browser,encoder,stderr='';
  try{
    browser=await chromium.launch({headless:true,...(get('--browser')?{executablePath:get('--browser')}: {})});
    const page=await browser.newPage({deviceScaleFactor:1});
    await page.goto(pathToFileURL(path.resolve(html)).href);
    await page.waitForFunction(()=>document.body.dataset.ready==='true');
    const info=await page.evaluate(()=>({duration:window.replay.duration,width:window.replay.width,height:window.replay.height}));
    if(!Number.isFinite(info.duration)||info.duration<=0||info.duration>300||info.width%2||info.height%2)throw Error('Invalid player timeline or geometry');
    const count=Math.ceil(info.duration*fps);
    encoder=spawn(ffmpeg,['-nostdin','-v','error','-n','-f','image2pipe','-vcodec','png','-framerate',String(fps),'-i','pipe:0','-an','-c:v','libx264','-preset','fast','-crf','20','-pix_fmt','yuv420p','-movflags','+faststart',target],{stdio:['pipe','ignore','pipe']});
    const completion=new Promise((resolve,reject)=>{encoder.on('error',reject);encoder.on('close',code=>code===0?resolve():reject(Error('FFmpeg failed: '+stderr)));});
    completion.catch(()=>{});encoder.stderr.on('data',data=>{stderr=(stderr+data).slice(-2000);});encoder.stdin.on('error',()=>{});
    for(let frame=0;frame<count;frame++){
      const png=await page.evaluate(async t=>{await window.replay.renderAt(t);return document.querySelector('canvas').toDataURL('image/png').split(',')[1];},frame/fps);
      if(encoder.stdin.destroyed)throw Error('Encoder stopped');
      if(!encoder.stdin.write(Buffer.from(png,'base64')))await once(encoder.stdin,'drain');
      if(frame%fps===0)process.stdout.write(`Frames ${frame}/${count}\n`);
    }
    encoder.stdin.end();await completion;
    const probe=spawnSync(get('--ffprobe','ffprobe'),['-v','error','-count_frames','-select_streams','v:0','-show_entries','stream=width,height,nb_read_frames,avg_frame_rate','-of','json',target],{encoding:'utf8'});
    if(probe.status!==0)throw Error('ffprobe failed');
    const actual=JSON.parse(probe.stdout).streams[0];
    if(Number(actual.nb_read_frames)!==count||actual.width!==info.width||actual.height!==info.height||actual.avg_frame_rate!==`${fps}/1`)throw Error('Export does not match timeline');
    fs.copyFileSync(target,output,fs.constants.COPYFILE_EXCL);
    process.stdout.write(JSON.stringify({frames:count,fps,width:info.width,height:info.height,audio:false})+'\n');
  }finally{
    if(encoder && encoder.exitCode===null)encoder.kill();
    if(browser)await browser.close();
    fs.rmSync(temp,{recursive:true,force:true});
  }
}
main().catch(error=>{console.error(error.message);process.exitCode=1;});
