const assert=require('node:assert/strict'),path=require('node:path'),crypto=require('node:crypto'),{pathToFileURL}=require('node:url');
const {chromium}=require('playwright');
(async()=>{const b=await chromium.launch({headless:true,...(process.env.CHROMIUM_EXECUTABLE?{executablePath:process.env.CHROMIUM_EXECUTABLE}:{})});try{
 const page=await b.newPage({viewport:{width:1536,height:1200},deviceScaleFactor:1}),external=[];page.on('request',r=>{if(!r.url().startsWith('file:'))external.push(r.url());});
 await page.goto(pathToFileURL(path.resolve(__dirname,'../examples/demo.html')).href);await page.waitForFunction(()=>window.replay);
 assert.equal(await page.locator('canvas,img,image,foreignObject,script[src]').count(),0);
 const hashes=[];
 for(const t of [0,6,12,24,40,6]){await page.evaluate(t=>window.replay.renderAt(t),t);const bytes=await page.locator('svg').screenshot({timeout:120000});hashes.push(crypto.createHash('sha256').update(bytes).digest('hex'));}
 assert.equal(hashes[1],hashes[5]);assert.equal(new Set(hashes.slice(0,5)).size,5);assert.deepEqual(external,[]);
 await page.locator('#reset').click();await page.locator('#play').click();await page.waitForFunction(()=>Number(document.querySelector('#slider').value)>.1);await page.locator('#play').click();assert.equal(await page.locator('#play').textContent(),'播放');
 console.log('PASS: native SVG only, distinct painting stages, deterministic seek, offline playback and controls.');
}finally{await b.close();}})().catch(e=>{console.error(e.message);process.exitCode=1});
