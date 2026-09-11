/* Pure seekable motion primitives; usable in a browser or Node, no dependencies. */
(function(root){
  'use strict';
  const clamp = x => Math.min(1, Math.max(0, x));
  function phase(t, start, end) {
    if (![t,start,end].every(Number.isFinite) || end<=start) throw new Error('Invalid time interval');
    return clamp((t-start)/(end-start));
  }
  const out = x => 1-Math.pow(1-clamp(x),3);
  const smooth = x => {x=clamp(x);return x*x*(3-2*x);};
  const lerp = (a,b,p) => a+(b-a)*p;
  const backOut = x => {x=clamp(x)-1;return 1+2.70158*x*x*x+1.70158*x*x;};
  function stagger(t,index,start,duration,gap){
    if(!Number.isInteger(index)||index<0||!Number.isFinite(gap)||gap<0)throw new Error('Invalid stagger');
    return out(phase(t,start+index*gap,start+index*gap+duration));
  }
  function envelope(t,start,enterEnd,exitStart,end){
    if(!(start<enterEnd&&enterEnd<=exitStart&&exitStart<end))throw new Error('Invalid envelope');
    return out(phase(t,start,enterEnd))*(1-out(phase(t,exitStart,end)));
  }
  const api={clamp,phase,out,smooth,lerp,backOut,stagger,envelope};
  if(typeof module==='object'&&module.exports)module.exports=api;else root.Motion=api;
})(typeof globalThis==='object'?globalThis:this);
