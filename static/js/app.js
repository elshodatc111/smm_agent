(function(){
  const root=document.documentElement;
  function setTheme(t){root.setAttribute('data-theme',t);try{localStorage.setItem('theme',t)}catch(e){}}
  const saved=(function(){try{return localStorage.getItem('theme')}catch(e){return null}})();
  setTheme(document.body.dataset.userTheme||saved||document.body.dataset.defaultTheme||'light');
  window.toggleTheme=function(){
    const t=root.getAttribute('data-theme')==='dark'?'light':'dark';setTheme(t);
    const csrf=document.querySelector('meta[name=csrf]').content;
    fetch('/mavzu/',{method:'POST',headers:{'X-CSRFToken':csrf,'Content-Type':'application/x-www-form-urlencoded'},body:'theme='+t}).catch(()=>{});
  };
  document.addEventListener('htmx:configRequest',e=>{e.detail.headers['X-CSRFToken']=document.querySelector('meta[name=csrf]').content;});
  window.apexTheme=function(){return root.getAttribute('data-theme')==='dark'?'dark':'light'};
  window.lineChart=function(id,labels,series,colors){
    const el=document.getElementById(id);if(!el||!window.ApexCharts)return;
    new ApexCharts(el,{chart:{type:'area',height:260,toolbar:{show:false},background:'transparent',fontFamily:'inherit'},theme:{mode:apexTheme()},
      series:series,xaxis:{categories:labels,labels:{rotate:-30}},stroke:{curve:'smooth',width:2.5},dataLabels:{enabled:false},
      colors:colors||['#E11D2E','#2563EB','#16A34A'],fill:{type:'gradient',gradient:{opacityFrom:.35,opacityTo:.02}},grid:{borderColor:'rgba(128,128,128,.2)'}}).render();
  };
  window.barChart=function(id,labels,series,colors,horizontal){
    const el=document.getElementById(id);if(!el||!window.ApexCharts)return;
    new ApexCharts(el,{chart:{type:'bar',height:260,toolbar:{show:false},background:'transparent',fontFamily:'inherit'},theme:{mode:apexTheme()},
      series:series,xaxis:{categories:labels},plotOptions:{bar:{borderRadius:6,horizontal:!!horizontal}},dataLabels:{enabled:false},
      colors:colors||['#2563EB','#E11D2E'],grid:{borderColor:'rgba(128,128,128,.2)'}}).render();
  };
})();
