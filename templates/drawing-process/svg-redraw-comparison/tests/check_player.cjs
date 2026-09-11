const assert=require('node:assert/strict'),path=require('node:path'),crypto=require('node:crypto'),{pathToFileURL}=require('node:url'),fs=require('node:fs'),http=require('node:http');
const {chromium}=require('playwright');
(async()=>{const b=await chromium.launch({headless:true,...(process.env.CHROMIUM_EXECUTABLE?{executablePath:process.env.CHROMIUM_EXECUTABLE}:{})});try{
 const page=await b.newPage({viewport:{width:1536,height:1200},deviceScaleFactor:1}),external=[];page.on('request',r=>{if(!r.url().startsWith('file:'))external.push(r.url());});
 const demo=path.resolve(process.env.DEMO_HTML||path.join(__dirname,'../examples/demo.html'));
 await page.goto(pathToFileURL(demo).href);
 if(await page.locator('#svg-files').count())await page.locator('#svg-files').setInputFiles(['redraw.svg','foundations.svg'].map(name=>path.join(path.dirname(demo),name)));
 await page.waitForFunction(()=>window.replay,{},{timeout:120000});
 assert.equal(await page.locator('canvas,img,image,foreignObject,script[src]').count(),0);
 const captureStyle='svg{position:fixed!important;top:0!important;left:0!important;width:1536px!important;height:1024px!important;background:white!important;z-index:99!important}';
 const style=await page.addStyleTag({content:captureStyle});
 const hashes=[];
 for(const t of [0,6,12,24,40,6]){await page.evaluate(t=>window.replay.renderAt(t),t);const bytes=await page.locator('svg').screenshot({timeout:120000});hashes.push(crypto.createHash('sha256').update(bytes).digest('hex'));}
 assert.equal(hashes[1],hashes[5]);assert.equal(new Set(hashes.slice(0,5)).size,5);assert.deepEqual(external,[]);
 await style.evaluate(e=>e.remove());
 await page.locator('#reset').click();await page.locator('#play').click();await page.waitForFunction(()=>Number(document.querySelector('#slider').value)>.1);await page.locator('#play').click();assert.equal(await page.locator('#play').textContent(),'播放');
 if(fs.existsSync(path.join(path.dirname(demo),'foundations.svg'))){
  const server=http.createServer((req,res)=>{
   const name=req.url.slice(1);if(!['demo.html','redraw.svg','foundations.svg'].includes(name)){res.writeHead(404);return res.end();}
   res.setHeader('Content-Type',name.endsWith('.svg')?'image/svg+xml':'text/html; charset=utf-8');fs.createReadStream(path.join(path.dirname(demo),name)).pipe(res);
  });
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
  try{await page.goto(`http://127.0.0.1:${server.address().port}/demo.html`);await page.waitForFunction(()=>window.replay,{},{timeout:120000});assert.equal(await page.locator('#svg-files').isHidden(),true);}
  finally{await new Promise(resolve=>server.close(resolve));}
  await page.goto(pathToFileURL(demo).href);
  await page.locator('#svg-files').setInputFiles([{name:'redraw.svg',mimeType:'image/svg+xml',buffer:Buffer.from('wrong vector')},{name:'foundations.svg',mimeType:'image/svg+xml',buffer:fs.readFileSync(path.join(path.dirname(demo),'foundations.svg'))}]);
  await page.waitForFunction(()=>document.body.dataset.error==='true');assert.equal(await page.evaluate(()=>!!window.replay),false);
  console.log('PASS: HTTP automatic loading and mismatched-file rejection.');
 }
 if(process.env.OLD_DEMO_HTML){
  await page.goto(pathToFileURL(path.resolve(process.env.OLD_DEMO_HTML)).href);await page.waitForFunction(()=>window.replay);
  await page.addStyleTag({content:captureStyle});
  for(const [i,t] of [0,6,12,24,40].entries()){
   await page.evaluate(t=>window.replay.renderAt(t),t);
   const png=await page.locator('svg').screenshot({timeout:120000});
   assert.equal(crypto.createHash('sha256').update(png).digest('hex'),hashes[i],`Changed image at ${t}s`);
  }
  console.log('PASS: all five stages are pixel-identical to the previous inline demo.');
 }
 console.log('PASS: native SVG only, distinct painting stages, deterministic seek, offline playback and controls.');
}finally{await b.close();}})().catch(e=>{console.error(e.message);process.exitCode=1});
