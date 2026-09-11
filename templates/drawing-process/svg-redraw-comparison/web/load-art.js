// Load fixed local vector data, then reconstruct the original semantic batches.
async function loadArt(){
 const status=document.getElementById('load-status'),picker=document.getElementById('svg-files');
 const expected=JSON.parse(document.getElementById('art-manifest').textContent);
 const ns='http://www.w3.org/2000/svg';
 async function parse(bytes,name){
  const hash=[...new Uint8Array(await crypto.subtle.digest('SHA-256',bytes))].map(x=>x.toString(16).padStart(2,'0')).join('');
  if(hash!==expected[name])throw Error('SVG 文件与此 Demo 不匹配：'+name);
  const doc=new DOMParser().parseFromString(new TextDecoder().decode(bytes),'image/svg+xml');
  if(doc.querySelector('parsererror'))throw Error('SVG 无法解析');
  const tags=new Set(['svg','g','path','polygon']);
  const attrs=new Set(['id','class','xmlns','viewBox','width','height','role','aria-label','data-region','data-order','opacity','shape-rendering','fill-rule','fill','d','points','stroke','stroke-width']);
  for(const el of doc.querySelectorAll('*')){
   if(el.namespaceURI!==ns||!tags.has(el.localName))throw Error('SVG 含有不支持的元素');
   for(const a of el.attributes)if(!attrs.has(a.name)||/url\s*\(/i.test(a.value))throw Error('SVG 含有不支持的属性');
  }
  return doc.documentElement;
 }
 let files;
 if(location.protocol==='file:'){
  status.textContent='选择同目录的 redraw.svg 和 foundations.svg 后即可离线播放。';picker.hidden=false;
  files=await new Promise(resolve=>{picker.onchange=()=>resolve(new Map([...picker.files].map(f=>[f.name,f])));});
 }
 const roots={};
 for(const name of ['foundations.svg','redraw.svg']){
  let bytes;
  if(files){if(!files.has(name))throw Error('请同时选择两个 SVG 文件，刷新页面后重试。');bytes=await files.get(name).arrayBuffer();}
  else {const response=await fetch(name);if(!response.ok)throw Error('无法读取 '+name);bytes=await response.arrayBuffer();}
  roots[name]=await parse(bytes,name);
 }
 const art=roots['foundations.svg'],complete=roots['redraw.svg'];
 if(art.getAttribute('viewBox')!==complete.getAttribute('viewBox'))throw Error('SVG 画幅不一致');
 const final=document.createElementNS(ns,'g');final.id='final-contours';final.setAttribute('shape-rendering','crispEdges');final.setAttribute('fill-rule','evenodd');
 const regions=[...complete.querySelector('#complete-vector-art').children];
 for(const phase of ['shadow','highlight','detail']){
  for(const region of regions){
   const name=region.getAttribute('data-region');
   const labels=expected.stages[name];if(!labels||labels.length!==region.children.length)throw Error('区域阶段索引不匹配');
   const paths=[...region.children].filter((p,i)=>labels[i]===phase[0]);
   for(let offset=0;offset<paths.length;offset+=64){
    const group=document.createElementNS(ns,'g');group.id=phase+'-'+name+'-'+offset/64;group.setAttribute('class','paint-step');group.dataset.stage=phase;group.dataset.region=name;
    for(const p of paths.slice(offset,offset+64))group.appendChild(p.cloneNode(true));final.appendChild(group);
   }
  }
 }
 art.appendChild(final);document.querySelector('.frame').replaceChildren(document.importNode(art,true));
 picker.hidden=true;status.textContent='本地 SVG 已加载';
}
