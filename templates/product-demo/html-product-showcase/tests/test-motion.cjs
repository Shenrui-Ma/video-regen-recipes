'use strict';
// Pure function and mocked DOM state tests; no browser, screenshot or media execution.
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const M=require('../scripts/motion.js');
assert.equal(M.phase(-1,0,2),0);assert.equal(M.phase(1,0,2),.5);assert.equal(M.phase(3,0,2),1);
assert.throws(()=>M.phase(0,1,1));assert.throws(()=>M.phase(NaN,0,1));
assert.equal(M.out(0),0);assert.equal(M.out(1),1);assert.equal(M.smooth(.5),.5);
assert.equal(M.stagger(0,2,0,1,.2),0);assert.equal(M.stagger(2,2,0,1,.2),1);
assert.throws(()=>M.stagger(1,-1,0,1,.2));
assert.equal(M.envelope(2,0,1,3,4),1);assert.equal(M.envelope(5,0,1,3,4),0);
assert(M.backOut(.7)>1);assert.equal(M.backOut(1),1);
const html=fs.readFileSync(path.join(__dirname,'../examples/film.html'),'utf8');
const inline=[...html.matchAll(/<script(?:\s[^>]*)?>([\s\S]*?)<\/script>/g)].map(m=>m[1]).filter(s=>s.trim());
for(const [width,height] of [[1920,1080],[1080,1440]]){
 const nodes=new Map();
 function node(id){
  if(!nodes.has(id))nodes.set(id,{style:{},dataset:{},attributes:{},textContent:'',value:0,
   setAttribute(k,v){this.attributes[k]=v;},getTotalLength(){return 100;},getPointAtLength(n){return {x:n,y:10};},
   getBoundingClientRect(){const i=Number(id.split('-')[1])||0;return {left:i*400,top:150,width:300,height:250,right:i*400+300,bottom:400};}});
  return nodes.get(id);
 }
 const context={Motion:M,URLSearchParams,location:{search:'?render=1'},innerWidth:width,innerHeight:height,
  document:{getElementById:node,documentElement:{dataset:{}}},addEventListener(){},
  requestAnimationFrame(){throw new Error('Preview clock must not start during export');},cancelAnimationFrame(){}};
 context.window=context;vm.createContext(context);
 for(const script of inline)vm.runInContext(script,context);
 const snapshot=()=>JSON.stringify([...nodes.entries()].map(([id,n])=>({id,style:n.style,attributes:n.attributes,text:n.textContent,value:n.value})));
 context.setShotTime(9.5);const a=snapshot();
 context.setShotTime(.2);assert.notEqual(snapshot(),a);
 context.setShotTime(9.5);assert.equal(snapshot(),a);
 context.setShotTime(0);assert.equal(node('result').textContent,'03');
 assert.equal(context.document.documentElement.dataset.render,'true');
 assert.throws(()=>context.setShotTime(Infinity));
}
console.log('Motion math and reversible HTML state checks passed (mock DOM; no browser).');
