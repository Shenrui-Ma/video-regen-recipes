// Run with an existing Playwright setup; optionally set CHROMIUM_EXECUTABLE.
const assert=require('node:assert/strict'), path=require('node:path'),{pathToFileURL}=require('node:url'),crypto=require('node:crypto');
const {chromium}=require('playwright');
(async()=>{
 const browser=await chromium.launch({headless:true,...(process.env.CHROMIUM_EXECUTABLE?{executablePath:process.env.CHROMIUM_EXECUTABLE}:{})});
 try{
  const page=await browser.newPage();
  await page.goto(pathToFileURL(path.resolve(__dirname,'../examples/demo.html')).href);
  await page.waitForFunction(()=>document.body.dataset.ready==='true');
  const samples=[];
  for(const t of [0,5,9,13,16,5]){
   const data=await page.evaluate(async t=>{
    const state=await window.replay.renderAt(t),c=document.querySelector('canvas'),ctx=c.getContext('2d');
    const pixels=ctx.getImageData(0,32,768,512).data;let hash=2166136261;for(const v of pixels)hash=Math.imul(hash^v,16777619)>>>0;
    const lower=ctx.getImageData(0,576,768,512).data;let blank=true;for(let i=0;i<lower.length;i++)if(lower[i]!==255){blank=false;break;}
    return {time:t,referenceHash:hash,blankDrawing:blank,png:c.toDataURL(),progress:state.progress};
   },t);
   samples.push({...data,png:undefined,frame_sha256:crypto.createHash('sha256').update(data.png).digest('hex')});
  }
  assert.equal(samples[0].blankDrawing,true);
  assert.equal(new Set(samples.map(s=>s.referenceHash)).size,1);
  assert.equal(samples[1].frame_sha256,samples[5].frame_sha256);
  assert.equal(samples[3].frame_sha256,samples[4].frame_sha256);
  assert.ok(new Set(samples.slice(0,4).map(s=>s.frame_sha256)).size===4);
  await page.locator('#restart').click();await page.waitForFunction(()=>document.querySelector('#time').value==='0');
  await page.locator('#play').click();await page.waitForFunction(()=>Number(document.querySelector('#time').value)>.05);await page.locator('#play').click();
  assert.equal(await page.locator('#play').textContent(),'播放');
  console.log(JSON.stringify({blank_start:true,reference_static:true,seek_deterministic:true,final_hold_stable:true,stages_differ:true,controls_checked:true}));
 }finally{await browser.close();}
})().catch(error=>{console.error(error.message);process.exitCode=1;});
