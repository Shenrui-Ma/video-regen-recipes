(() => {
  const cfg = window.REPLAY_CONFIG;
  const canvas = document.querySelector('canvas');
  const ctx = canvas.getContext('2d', {willReadFrequently:true});
  let referencePixels = null;
  const status = document.querySelector('#status');
  const slider = document.querySelector('#time');
  const source = document.querySelector('#source');
  const svg = document.querySelector('#vector svg');
  const title = {sketch: '起稿', ink: '线稿', color: '铺色', shadow: '明暗', detail: '细节'};
  const bands = {sketch:[0,.13], ink:[.10,.34], color:[.34,.66], shadow:[.66,.84], detail:[.84,1]};
  const clamp = n => Math.max(0, Math.min(1,n));
  const items = [];
  for (const group of svg.querySelectorAll('g[data-phase]')) {
    const phase = group.dataset.phase;
    for (const [i, element] of [...group.children].entries()) {
      const length = phase === 'ink' || phase === 'sketch' ? element.getTotalLength?.() : null;
      items.push({element,phase,i,count:group.children.length,length,opacity:element.getAttribute('opacity') || '1'});
    }
  }
  const panelW = cfg.panelWidth;
  const panelH = Math.round(panelW*cfg.height/cfg.width);
  const bar = 32;
  const stacked = cfg.layout === 'stacked';
  canvas.width = stacked ? panelW : panelW*2;
  canvas.height = stacked ? 2*(panelH+bar) : panelH+bar;
  slider.max = cfg.duration;
  let current = 0, playing = false, origin = 0, busy = false, renderVersion = 0;
  const ready = new Promise((resolve,reject) => {source.onload=resolve;source.onerror=reject;source.src=cfg.reference;});

  function paintProgress(seconds) {
    const p = clamp((seconds-cfg.lead)/cfg.draw);
    for (const item of items) {
      const [a,b] = bands[item.phase];
      const groupP = clamp((p-a)/(b-a));
      const start = item.i/item.count*.86;
      const local = clamp((groupP-start)/.14);
      const fade = item.phase === 'sketch' ? 1-clamp((p-.25)/.09) : item.phase === 'ink' ? 1-clamp((p-.34)/.12) : 1;
      item.element.style.opacity = String(Number(item.opacity)*(item.length != null ? (local>0?1:0) : local)*fade);
      if (item.length != null) {
        item.element.style.strokeDasharray = String(item.length);
        item.element.style.strokeDashoffset = String(item.length*(1-local));
      }
    }
    return p;
  }
  function drawPanel(image,x,y,label,detail='') {
    ctx.fillStyle='#172135';ctx.fillRect(x,y,panelW,bar);
    ctx.font='14px sans-serif';ctx.fillStyle='#f2f5fb';ctx.textAlign='left';ctx.fillText(label,x+12,y+21);
    ctx.fillStyle='#adbfda';ctx.textAlign='right';ctx.fillText(detail,x+panelW-12,y+21);
    ctx.fillStyle='#fff';ctx.fillRect(x,y+bar,panelW,panelH);
    if(image===source && referencePixels)ctx.putImageData(referencePixels,x,y+bar);
    else ctx.drawImage(image,x,y+bar,panelW,panelH);
  }
  async function renderAt(seconds) {
    await ready;
    if(!referencePixels){
      const fixed=document.createElement('canvas');fixed.width=panelW;fixed.height=panelH;
      const paint=fixed.getContext('2d',{willReadFrequently:true});
      paint.fillStyle='#fff';paint.fillRect(0,0,panelW,panelH);paint.drawImage(source,0,0,panelW,panelH);
      referencePixels=paint.getImageData(0,0,panelW,panelH);
    }
    const version=++renderVersion;
    const targetTime=Math.max(0,Math.min(cfg.duration,Number(seconds)));
    const progress=paintProgress(targetTime);
    const blob = new Blob([new XMLSerializer().serializeToString(svg)],{type:'image/svg+xml'});
    const url=URL.createObjectURL(blob);
    const frame=new Image();
    try {
      await new Promise((resolve,reject)=>{frame.onload=resolve;frame.onerror=reject;frame.src=url;});
      if(version!==renderVersion)return {stale:true};
      current=targetTime;
      const stage = Object.keys(bands).find(key => progress < bands[key][1]) || 'detail';
      const detail=progress===1?'完成 · 100%':`${title[stage]} · ${Math.round(progress*100)}%`;
      drawPanel(source,0,0,'参考原图');
      drawPanel(frame,stacked?0:panelW,stacked?panelH+bar:0,'SVG 临摹重绘',detail);
      slider.value=String(current);status.textContent=`${current.toFixed(1)} / ${cfg.duration.toFixed(1)} 秒`;
      return {time:current,progress,width:canvas.width,height:canvas.height};
    } finally {URL.revokeObjectURL(url);}
  }
  async function tick(now) {
    if (!playing) return;
    if (!busy) {
      busy=true;
      try {await renderAt((now-origin)/1000);} finally {busy=false;}
      if (current >= cfg.duration) {playing=false;document.querySelector('#play').textContent='播放';return;}
    }
    requestAnimationFrame(tick);
  }
  document.querySelector('#play').onclick=()=>{
    playing=!playing;
    document.querySelector('#play').textContent=playing?'暂停':'播放';
    if(playing){origin=performance.now()-(current>=cfg.duration?0:current)*1000;requestAnimationFrame(tick);}
  };
  document.querySelector('#restart').onclick=async()=>{playing=false;document.querySelector('#play').textContent='播放';await renderAt(0);};
  slider.oninput=async()=>{playing=false;document.querySelector('#play').textContent='播放';await renderAt(Number(slider.value));};
  window.replay = {renderAt,ready,duration:cfg.duration,width:canvas.width,height:canvas.height};
  renderAt(0).then(()=>document.body.dataset.ready='true');
})();
