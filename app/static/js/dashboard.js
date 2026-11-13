/* Gráficos descriptivos calculados por el servidor. Sin datos de demostración. */
(()=>{'use strict';
const source=document.getElementById('dashboard-data');if(!source)return;
const data=JSON.parse(source.textContent),ns='http://www.w3.org/2000/svg';
const currency=c=>'$ '+(c/100).toLocaleString('es-CO',{maximumFractionDigits:2}),shortDate=d=>new Date(d+'T12:00:00Z').toLocaleDateString('es-CO',{day:'2-digit',month:'2-digit',timeZone:'UTC'});
function element(name,attrs,text){const e=document.createElementNS(ns,name);for(const [k,v]of Object.entries(attrs))e.setAttribute(k,String(v));if(text!==undefined)e.textContent=text;return e;}
const stock=document.getElementById('dashboard-stock');
if(stock){const svg=element('svg',{viewBox:'0 0 140 140',role:'img','aria-label':data.states.map(s=>`${s.name}: ${s.count} equipos`).join(', ')||'Sin equipos registrados'}),total=data.states.reduce((n,s)=>n+s.count,0),length=2*Math.PI*50;
 svg.append(element('circle',{cx:70,cy:70,r:50,fill:'none',stroke:'#edf2fc','stroke-width':14}));
 const colors={blue:'var(--blue)',green:'#16875b',amber:'#e6a633',slate:'#8093af'};let offset=0;
 for(const state of data.states){const arc=total?state.count/total*length:0;if(arc){svg.append(element('circle',{cx:70,cy:70,r:50,fill:'none',stroke:colors[state.style]||colors.slate,'stroke-width':14,'stroke-dasharray':`${Math.max(0,arc-3)} ${length-Math.max(0,arc-3)}`,'stroke-dashoffset':-offset,transform:'rotate(-90 70 70)'}));offset+=arc;}}
 stock.prepend(svg);
}
const area=document.getElementById('dashboard-flow');
if(area&&data.financial){const svg=area.querySelector('svg'),tooltip=area.querySelector('.dash-chart-tooltip');let groups=[],plot={};
 function draw(){const w=Math.max(220,area.clientWidth-28),h=245,L=52,R=12,T=31,B=39,iw=w-L-R,ih=h-T-B,step=Math.max(1,Math.ceil(data.days.length/7));groups=[];
  for(let i=0;i<data.days.length;i+=step){const days=data.days.slice(i,i+step);groups.push({first:days[0].date,last:days.at(-1).date,sales:days.reduce((n,d)=>n+d.sales,0),collections:days.reduce((n,d)=>n+d.collections,0)});}
  const largest=Math.max(1,...groups.flatMap(g=>[g.sales,g.collections])),power=10**Math.floor(Math.log10(largest)),tick=Math.max(1,Math.ceil(largest/power/3)*power),max=Math.ceil(largest/tick)*tick,unit=max>=1e8?1e8:100,unitLabel=max>=1e8?'Millones de COP':'COP',y=n=>T+ih-n/max*ih,groupWidth=iw/Math.max(groups.length,1),barWidth=Math.max(3,Math.min(18,(groupWidth-10)/2));
  svg.setAttribute('viewBox',`0 0 ${w} ${h}`);svg.replaceChildren();svg.append(element('title',{},'Ventas netas y cobros registrados por fecha'),element('desc',{},groups.map(g=>`${g.first} a ${g.last}: ventas ${currency(g.sales)}, cobros ${currency(g.collections)}`).join('. ')));
  const text=(x,y,t,anchor='start')=>element('text',{x,y,'text-anchor':anchor,'font-size':11,fill:'#62718a','font-family':'Inter,Segoe UI,Arial,sans-serif'},t);
  svg.append(text(L,15,unitLabel));
  for(let v=0;v<=max;v+=tick){svg.append(element('line',{x1:L,x2:w-R,y1:y(v),y2:y(v),stroke:'#e5ebf4','stroke-width':1}),text(L-8,y(v)+4,(v/unit).toLocaleString('es-CO',{maximumFractionDigits:1}),'end'));}
  const interval=w<410&&groups.length>4?2:1;
  groups.forEach((g,i)=>{const cx=L+groupWidth*(i+.5);svg.append(element('rect',{x:cx-barWidth-2,y:y(g.sales),width:barWidth,height:Math.max(0,y(0)-y(g.sales)),rx:3,fill:'var(--blue)'}),element('rect',{x:cx+2,y:y(g.collections),width:barWidth,height:Math.max(0,y(0)-y(g.collections)),rx:3,fill:'#16875b'}));if(i%interval===0||i===groups.length-1)svg.append(text(cx,h-19,shortDate(g.first),'middle'));});
  svg.append(text(w-R,h-3,step===1?'Fecha':`Inicio de cada bloque de ${step} días`,'end'));plot={L,R,T,ih,iw,w,groupWidth};tooltip.hidden=true;
 }
 function inspect(event){if(!groups.length)return;const rect=svg.getBoundingClientRect(),x=(event.clientX-rect.left)*plot.w/rect.width;if(x<plot.L||x>plot.w-plot.R){tooltip.hidden=true;return;}const index=Math.min(groups.length-1,Math.max(0,Math.floor((x-plot.L)/plot.groupWidth))),g=groups[index];tooltip.textContent=(g.first===g.last?g.first:`${g.first} a ${g.last}`)+`\nVentas netas: ${currency(g.sales)}\nCobros: ${currency(g.collections)}`;tooltip.hidden=false;const available=area.clientWidth-tooltip.offsetWidth-8;tooltip.style.left=Math.max(8,Math.min(available,event.clientX-area.getBoundingClientRect().left+10))+'px';tooltip.style.top='38px';}
 svg.addEventListener('pointermove',inspect);svg.addEventListener('pointerdown',inspect);svg.addEventListener('pointerleave',()=>{tooltip.hidden=true;});document.addEventListener('keydown',e=>{if(e.key==='Escape')tooltip.hidden=true;});
 draw();if(typeof ResizeObserver!=='undefined')new ResizeObserver(draw).observe(area);else window.addEventListener('resize',draw);
}
const choice=document.getElementById('dashboard-period-choice'),custom=document.getElementById('dashboard-custom-dates');
choice?.addEventListener('change',()=>{const show=choice.value==='personalizado';custom.hidden=!show;custom.disabled=!show;if(show)custom.querySelector('input')?.focus();else choice.form.requestSubmit();});
})();
