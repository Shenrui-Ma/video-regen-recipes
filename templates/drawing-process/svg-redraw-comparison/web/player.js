const total=40,drawEnd=36;
const clamp=n=>Math.max(0,Math.min(1,n));
const sketch=document.getElementById('construction');
const flats=[...document.querySelectorAll('.flat-step')],ink=[...document.querySelectorAll('.ink-step')],groups=[...document.querySelectorAll('.paint-step')];
const phases={shadow:[14,23],highlight:[23,28],detail:[28,36]};
for(const [phase,band] of Object.entries(phases)){
 const items=groups.filter(e=>e.dataset.stage===phase);items.forEach((e,i)=>{e.dataset.start=band[0]+(band[1]-band[0])*.90*i/items.length;e.dataset.span=.1*(band[1]-band[0]);});
}
let time=0,playing=false,origin=0;
function opacity(e,n){const value=String(n);if(e.style.opacity!==value)e.style.opacity=value;}
function renderAt(t){time=Math.max(0,Math.min(total,t));
 opacity(sketch,clamp(time/2)*(1-clamp((time-5)/3)));
 ink.forEach((e,i)=>opacity(e,clamp((time-(2+i*.48))/.75)*(1-clamp((time-33)/3))));
 flats.forEach((e,i)=>opacity(e,clamp((time-(8+i*.38))/.8)*(1-clamp((time-35)/1))));
 groups.forEach(e=>opacity(e,clamp((time-Number(e.dataset.start))/Number(e.dataset.span))));
 document.getElementById('slider').value=time;document.getElementById('stamp').textContent=time.toFixed(1)+' / '+total+' 秒';
 document.getElementById('phase').textContent=time<2?'构图定位':time<8?'线稿':time<14?'固有色':time<23?'阴影':time<28?'高光':'细节与完成';
 return {time,total,complete:time>=drawEnd};
}
function tick(now){if(!playing)return;renderAt((now-origin)/1000);if(time>=total){playing=false;document.getElementById('play').textContent='播放';return;}requestAnimationFrame(tick);}
document.getElementById('play').onclick=()=>{playing=!playing;if(playing){origin=performance.now()-(time>=total?0:time)*1000;requestAnimationFrame(tick);}document.getElementById('play').textContent=playing?'暂停':'播放';};
document.getElementById('reset').onclick=()=>{playing=false;document.getElementById('play').textContent='播放';renderAt(0);};
document.getElementById('final').onclick=()=>{playing=false;document.getElementById('play').textContent='播放';renderAt(total);};
document.getElementById('slider').oninput=e=>{playing=false;document.getElementById('play').textContent='播放';renderAt(Number(e.target.value));};
window.replay={renderAt,duration:total};renderAt(total);document.body.dataset.ready='true';
