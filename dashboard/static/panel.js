/* Mobile HUD uses the desktop mesh and authenticated live state, without external assets. */
(() => {
  const labels={LISTENING:'Ouvindo',THINKING:'Pensando',SPEAKING:'Falando',MUTED:'Microfone mudo',SLEEPING:'Em repouso',OFFLINE:'Desconectado'};
  let state={connected:false,state:'OFFLINE',hud_style:'core',muted:false,level:0},mesh=null,polling=false,meshLoading=false;
  const $=id=>document.getElementById(id);
  const canvas=$('avatar'),ctx=canvas.getContext('2d');
  const reduced=matchMedia('(prefers-reduced-motion: reduce)').matches;
  function renderState(next){
    state=next;
    canvas.setAttribute('aria-label',next.hud_style==='face'?'Rosto animado do Jarvis':'Reator do Jarvis');
    if(next.hud_style==='face'&&!mesh&&!meshLoading){
      meshLoading=true;
      _authFetch('/api/avatar').then(r=>r.ok?r.json():null).then(data=>{mesh=data;}).catch(()=>{}).finally(()=>{meshLoading=false;});
    }
    const label=next.connected?(labels[next.state]||next.state):'Reconectando';
    $('hud-state').textContent=label;
    $('st').textContent=label;
    $('pill').className=next.connected?'pill on':'pill';
    $('assistant-name').textContent=next.name||'JARVIS';
    document.title=(next.name||'JARVIS')+' · Controle remoto';
    for(const key of ['cpu','memory']){
      const n=Number(next[key]);
      $(key+'-value').textContent=Number.isFinite(n)?Math.round(n)+'%':'—';
      $(key+'-bar').value=Number.isFinite(n)?n:0;
    }
    $('pc-mute').textContent=next.muted?'ATIVAR MICROFONE':'SILENCIAR MICROFONE';
    $('pc-mute').setAttribute('aria-pressed',String(!!next.muted));
    $('interrupt').disabled=!next.connected;
  }
  async function poll(){
    if(polling||document.hidden)return;
    polling=true;
    try{
      const response=await _authFetch('/api/panel');
      if(response.status===401){_reconnectPanel();return;}
      if(!response.ok)throw Error('state');
      renderState(await response.json());
      const tasks=await _authFetch('/api/tasks');
      if(tasks.ok)renderTask(await tasks.json());
    }catch{renderState({...state,connected:false});}
    finally{polling=false;}
  }
  async function control(action,value){
    try{
      const response=await _authFetch('/api/control',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({action,value})});
      if(!response.ok)throw Error('control');
      if(action==='interrupt')stopScheduledAudio();
      toast(action==='interrupt'?'Interrupção enviada':action==='mute'?'Comando do microfone enviado':'Sinal para despertar enviado');
      setTimeout(poll,200);
    }catch{toast('Não foi possível enviar o controle. Confira a conexão.');}
  }
  let task=null;
  function renderTask(data){
    task=data.plan;
    const states={active:'Em andamento',paused:'Pausada',blocked:'Bloqueada',completed:'Concluída',cancelled:'Cancelada'};
    $('task-title').textContent=task?`${task.objective} — ${task.completed}/${task.total} (${states[task.state]||task.state})`:'Nenhuma tarefa registrada';
    $('task-steps').textContent=task?task.steps.map(s=>`${s.state==='done'?'✓':'○'} ${s.title}`).join('\n')+'\n'+task.reason:'';
  }
  window.taskControl=async action=>{
    if(!task){toast('Nenhuma tarefa registrada');return;}
    try{
      const response=await _authFetch('/api/tasks',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({action,plan_id:task.id,revision:task.revision})});
      const data=await response.json();
      if(!response.ok)throw Error(data.error||'Controle recusado');
      renderTask(data);
    }catch(e){toast(e.message);}
  };
  window.panelView=view=>{
    if(view==='actions'){ $('actions-sheet').hidden=false;$('close-actions').focus();return; }
    document.body.dataset.view=view;
    document.querySelectorAll('.nav-button').forEach(button=>button.classList.toggle('active',button.dataset.view===view));
  };
  window.closePanelActions=()=>{$('actions-sheet').hidden=true;};
  window.downloadAndroidApp=async()=>{
    try{
      const response=await _authFetch('/api/android/apk');
      if(!response.ok)throw Error('download');
      const url=URL.createObjectURL(await response.blob());
      const link=document.createElement('a');link.href=url;link.download='JARVIS-Android-debug.apk';
      document.body.appendChild(link);link.click();link.remove();
      setTimeout(()=>URL.revokeObjectURL(url),60000);
      toast('APK baixado. Abra o arquivo no Android para instalar.');
    }catch{toast('APK indisponível. Confira a conexão e se o app foi compilado no PC.');}
  };
  window.panelCommand=text=>{
    closePanelActions();$('inp').value=text;panelView('conversation');$('inp').focus();
  };
  $('interrupt').addEventListener('click',()=>control('interrupt'));
  $('pc-mute').addEventListener('click',()=>control('mute',!state.muted));
  $('remote-wake').addEventListener('click',()=>control('wake'));
  $('inp').addEventListener('focus',()=>{
    if(matchMedia('(max-width:700px)').matches)panelView('conversation');
  });
  let speakerContext=null,listen=false,nextAudioAt=0;
  const scheduledAudio=new Set();
  function stopScheduledAudio(){
    for(const source of scheduledAudio){try{source.stop();}catch{}}
    scheduledAudio.clear();nextAudioAt=0;
  }
  const speaker=$('phone-speaker');
  function resetSpeaker(){
    stopScheduledAudio();
    listen=false;nextAudioAt=0;
    if(speakerContext)speakerContext.close().catch(()=>{});
    speakerContext=null;speaker.setAttribute('aria-pressed','false');
    speaker.innerHTML='Ouvir no celular<small>Ativar o áudio das respostas</small>';
  }
  speaker.addEventListener('click',async()=>{
    if(ws.readyState!==WebSocket.OPEN){toast('Conecte o painel antes de ativar o áudio.');return;}
    if(listen){ws.send(JSON.stringify({type:'listen_audio',enabled:false}));resetSpeaker();return;}
    try{
      const AudioEngine=window.AudioContext||window.webkitAudioContext;
      speakerContext=new AudioEngine();await speakerContext.resume();
      listen=true;nextAudioAt=0;speaker.setAttribute('aria-pressed','true');
      speaker.innerHTML='Áudio do celular ativo<small>Toque para silenciar neste celular</small>';
      ws.send(JSON.stringify({type:'listen_audio',enabled:true}));
    }catch{resetSpeaker();toast('O navegador não permitiu reproduzir o áudio.');}
  });
  ws.addEventListener('close',resetSpeaker);
  ws.addEventListener('message',event=>{
    let message;try{message=JSON.parse(event.data);}catch{return;}
    if(message.type!=='audio'||!listen||!speakerContext)return;
    try{
      const binary=atob(message.data),bytes=new Uint8Array(binary.length);
      for(let i=0;i<binary.length;i++)bytes[i]=binary.charCodeAt(i);
      const pcm=new Int16Array(bytes.buffer),buffer=speakerContext.createBuffer(1,pcm.length,message.rate);
      const samples=buffer.getChannelData(0);
      for(let i=0;i<pcm.length;i++)samples[i]=pcm[i]/32768;
      const source=speakerContext.createBufferSource();source.buffer=buffer;source.connect(speakerContext.destination);
      scheduledAudio.add(source);source.onended=()=>scheduledAudio.delete(source);
      nextAudioAt=Math.max(speakerContext.currentTime+.06,nextAudioAt);
      source.start(nextAudioAt);nextAudioAt+=buffer.duration;
    }catch{toast('Falha ao reproduzir um trecho de áudio.');}
  });
  document.addEventListener('keydown',e=>{if(e.key==='Escape')closePanelActions();});
  $('actions-sheet').addEventListener('click',e=>{if(e.target===$('actions-sheet'))closePanelActions();});
  document.addEventListener('visibilitychange',poll);
  poll();setInterval(poll,1000);
  let last=0;
  function draw(now){
    requestAnimationFrame(draw);
    if(document.hidden||now-last<(reduced?200:33))return;last=now;
    const rect=canvas.getBoundingClientRect();if(!rect.width||!rect.height)return;
    const ratio=Math.min(devicePixelRatio||1,2),w=rect.width,h=rect.height;
    if(canvas.width!==Math.round(w*ratio)||canvas.height!==Math.round(h*ratio)){canvas.width=Math.round(w*ratio);canvas.height=Math.round(h*ratio);}
    ctx.setTransform(ratio,0,0,ratio,0,0);ctx.clearRect(0,0,w,h);
    const t=reduced?0:now/1000,cx=w/2,cy=h*.46,r=Math.min(w*.37,h*.45);
    $('hud-clock').textContent=new Date().toLocaleTimeString('pt-BR');
    if(state.hud_style!=='face'){
      const active=state.connected&&!state.muted;
      const color=active?'0,225,240':'95,143,159';
      const pulse=reduced?0:(Math.sin(t*2)+1)*.025;
      const level=state.state==='SPEAKING'?Math.max(0,Math.min(1,Number(state.level)||0)):0;
      for(let ring=0;ring<6;ring++){
        const radius=r*(.43+ring*.11),rotation=t*(ring%2?-.09:.07);
        ctx.lineWidth=ring===5?1.5:1;
        ctx.strokeStyle=`rgba(${color},${ring%2?.55:.24})`;
        for(let segment=0;segment<3;segment++){
          const angle=rotation+segment*Math.PI*2/3+ring*.4;
          ctx.beginPath();ctx.arc(cx,cy,radius,angle,angle+Math.PI*.53);ctx.stroke();
        }
      }
      for(let tick=0;tick<72;tick++){
        const angle=tick*Math.PI/36;
        const inner=r*(tick%6===0?.91:.96);
        ctx.strokeStyle=`rgba(${color},${tick%6===0?.75:.3})`;
        ctx.beginPath();ctx.moveTo(cx+Math.cos(angle)*inner,cy+Math.sin(angle)*inner);
        ctx.lineTo(cx+Math.cos(angle)*r,cy+Math.sin(angle)*r);ctx.stroke();
      }
      const core=r*(.34+pulse+level*.04);
      const glow=ctx.createRadialGradient(cx,cy,0,cx,cy,core*1.5);
      glow.addColorStop(0,`rgba(${color},.23)`);glow.addColorStop(.65,`rgba(${color},.09)`);glow.addColorStop(1,`rgba(${color},0)`);
      ctx.fillStyle=glow;ctx.beginPath();ctx.arc(cx,cy,core*1.5,0,Math.PI*2);ctx.fill();
      ctx.strokeStyle=`rgba(${color},.7)`;ctx.lineWidth=2;
      ctx.beginPath();ctx.arc(cx,cy,core,0,Math.PI*2);ctx.stroke();
      ctx.fillStyle=active?'#a9e5ec':'#8ca8b2';ctx.textAlign='center';ctx.textBaseline='middle';
      ctx.font=`bold ${Math.max(12,r*.15)}px monospace`;
      ctx.fillText(state.name||'JARVIS',cx,cy,core*1.7);ctx.textBaseline='alphabetic';
      return;
    }
    for(let i=0;i<3;i++){
      ctx.strokeStyle=i===1?'#ff326c65':'#00d9ee35';ctx.lineWidth=1;
      ctx.beginPath();ctx.arc(cx,cy,r+i*9,t*(i%2?-.12:.08)+i,t*(i%2?-.12:.08)+i+Math.PI*1.55);ctx.stroke();
    }
    if(!mesh){ctx.fillStyle='#85a5b5';ctx.font='11px monospace';ctx.textAlign='center';ctx.fillText('Carregando avatar…',cx,cy);return;}
    const yaw=Math.sin(t*.35)*.12,cs=Math.cos(yaw),sn=Math.sin(yaw),scale=Math.min(w*.22,h*.35);
    const talk=state.state==='SPEAKING'?Math.min(.13,Number(state.level||0)*.18):0;
    const projected=mesh.verts.map((v,i)=>{
      const x=v[0]*cs+v[2]*sn,z=v[2]*cs-v[0]*sn;
      return [cx+x*scale,cy-(v[1]-(mesh.jaw[i]||0)*talk)*scale,z];
    });
    ctx.lineWidth=.65;
    for(const [a,b] of mesh.edges){
      const p=projected[a],q=projected[b];if(!p||!q)continue;
      const alpha=Math.max(.15,Math.min(.85,.55+(p[2]+q[2])*.18));
      ctx.strokeStyle=state.muted?`rgba(100,145,162,${alpha})`:`rgba(0,220,242,${alpha})`;
      ctx.beginPath();ctx.moveTo(p[0],p[1]);ctx.lineTo(q[0],q[1]);ctx.stroke();
    }
    $('hud-clock').textContent=new Date().toLocaleTimeString('pt-BR');
  }
  requestAnimationFrame(draw);
})();
