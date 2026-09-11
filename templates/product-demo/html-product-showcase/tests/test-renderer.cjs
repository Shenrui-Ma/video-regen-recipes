'use strict';
// Exercise output publication with fake browser/encoder; never render real media.
const assert=require('node:assert/strict');
const fs=require('node:fs'),os=require('node:os'),path=require('node:path'),vm=require('node:vm');
const code=fs.readFileSync(path.join(__dirname,'../scripts/render-film.cjs'),'utf8');
async function scenario(failure){
 const folder=fs.mkdtempSync(path.join(os.tmpdir(),'html-render-contract-'));
 try{
  const source=path.join(folder,'film.html'),output=path.join(folder,'out.mp4');
  fs.writeFileSync(source,'<html>test fixture only</html>');
  const state={closed:0,errors:[],exitCode:0};
  const page={on(){},async goto(){},async evaluate(fn){
   if(String(fn).includes('maxProtected'))throw new Error('Unexpected test branch');
   if(String(fn).includes('const stage='))return {count:1,issues:[]};
  },async screenshot(){return Buffer.from('fake-frame');}};
  const browser={async newContext(){return {async route(){},async newPage(){return page;}};},async close(){state.closed++;}};
  let links=0;
  const filesystem={...fs,linkSync(a,b){links++;if(failure==='publish'&&links===2)throw new Error('report publication failed');return fs.linkSync(a,b);}};
  const requireMock=name=>{
   if(name==='playwright')return {chromium:{async launch(){return browser;}}};
   if(name==='node:fs')return filesystem;
   if(name==='node:child_process')return {execFileSync(binary,args){
    if(failure==='encode')throw new Error('encoder failed');
    if(binary==='ffprobe')return JSON.stringify({streams:[{width:100,height:100,nb_read_frames:'1',sample_aspect_ratio:'1:1',r_frame_rate:'10/1'}],format:{duration:'0.1'}});
    if(args.includes('-framerate'))fs.writeFileSync(args.at(-1),'fake encoded bytes');
   }};
   return require(name);
  };
  const processMock={argv:['node','render-film.cjs',source,output,'100','100','0.1','10'],env:{},pid:process.pid};
  const context={require:requireMock,process:processMock,console:{log(){},error(e){state.errors.push(String(e));}},Buffer};
  await vm.runInNewContext(code,context,{filename:'render-film.cjs'});
  assert.equal(fs.existsSync(output+'.lock'),false);
  assert.equal(fs.readdirSync(folder).some(n=>n.startsWith('.html-motion-')),false);
  if(failure){
   assert.equal(processMock.exitCode,1);assert.equal(fs.existsSync(output),false);assert.equal(fs.existsSync(output+'.qc.json'),false);
  }else{
   assert.equal(processMock.exitCode,undefined);assert(fs.existsSync(output));
   const report=JSON.parse(fs.readFileSync(output+'.qc.json','utf8'));
   assert.equal(report.frames,1);assert.equal(report.source,'film.html');assert.equal(report.visualReview,false);
   assert.equal(report.sourceSha256.length,64);
  }
  assert.equal(state.closed,1);
 }finally{fs.rmSync(folder,{recursive:true,force:true});}
}
(async()=>{await scenario(null);await scenario('encode');await scenario('publish');console.log('Mock renderer publication checks passed; no browser or encoder executed.');})().catch(e=>{console.error(e);process.exitCode=1;});
