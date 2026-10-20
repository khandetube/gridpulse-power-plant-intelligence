/* Keeps the advanced 3D renderer inside the CAD workbench instead of covering the whole site. */
(function(){
  'use strict';
  const HIDE='gridpulse-3d-hidden';
  function setVisible(visible){
    const root=document.getElementById('gp3d');
    if(!root) return false;
    root.classList.toggle(HIDE,!visible);
    root.style.setProperty('display',visible?'grid':'none','important');
    if(visible){
      window.dispatchEvent(new Event('resize'));
      const canvas=document.getElementById('gpCanvas');
      if(canvas) canvas.focus?.();
    }
    return true;
  }
  function wire(){
    const root=document.getElementById('gp3d');
    if(root){
      if(!root.dataset.gpGuarded){
        root.dataset.gpGuarded='1';
        setVisible(false);
        const back=root.querySelector('#gpBack');
        if(back) back.addEventListener('click',()=>setVisible(false));
      }
    }
    document.querySelectorAll('[data-view="iso"]').forEach(btn=>{
      if(btn.dataset.gp3dWired) return;
      btn.dataset.gp3dWired='1';
      btn.addEventListener('click',function(){
        if(setVisible(true)){
          document.querySelectorAll('[data-view]').forEach(b=>b.classList.toggle('active',b===btn));
        }
      });
    });
    document.querySelectorAll('[data-view="plan"]').forEach(btn=>{
      if(btn.dataset.gp3dPlanWired) return;
      btn.dataset.gp3dPlanWired='1';
      btn.addEventListener('click',()=>setVisible(false));
    });
  }
  const observer=new MutationObserver(wire);
  function start(){
    wire();
    observer.observe(document.body,{childList:true,subtree:true});
  }
  if(document.readyState==='loading') document.addEventListener('DOMContentLoaded',start,{once:true}); else start();
})();
