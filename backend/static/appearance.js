(function(){
  'use strict';
  const root=document.documentElement, themeKey='multimarket.theme', views=['tiles','compact','list'];
  function read(key,fallback){try{return localStorage.getItem(key)||fallback;}catch{return fallback;}}
  function save(key,value){try{localStorage.setItem(key,value);}catch{}}
  function theme(value){root.dataset.theme=value==='dark'?'dark':'light';const button=document.querySelector('.theme-switch');if(button){button.textContent=root.dataset.theme==='dark'?'☀ Светлая тема':'☾ Тёмная тема';button.setAttribute('aria-label',button.textContent);}}
  theme(read(themeKey,'light'));
  function view(scope,value){root.dataset[scope+'View']=views.includes(value)?value:'tiles';}
  view('search',read('multimarket.view.search','tiles'));view('product',read('multimarket.view.product','tiles'));
  document.addEventListener('DOMContentLoaded',()=>{
    const header=document.querySelector('.topbar');if(header){const button=document.createElement('button');button.type='button';button.className='theme-switch';button.addEventListener('click',()=>{const next=root.dataset.theme==='dark'?'light':'dark';theme(next);save(themeKey,next);});header.append(button);theme(root.dataset.theme);}
    for(const [scope,selector] of [['search','#offers-list'],['product','#product-offers']]){
      const target=document.querySelector(selector);if(!target)continue;
      const wrap=document.createElement('div');wrap.className='view-switch';const label=document.createElement('label');label.textContent=scope==='search'?'Вид товаров':'Вид предложений';label.htmlFor=scope+'-view';
      const select=document.createElement('select');select.id=scope+'-view';for(const [value,title] of [['tiles','Крупные карточки'],['compact','Компактные карточки'],['list','Список']])select.add(new Option(title,value));select.value=root.dataset[scope+'View'];select.addEventListener('change',()=>{view(scope,select.value);save('multimarket.view.'+scope,select.value);});wrap.append(label,select);target.before(wrap);
    }
  });
  window.addEventListener('storage',event=>{if(event.key===themeKey)theme(event.newValue||'light');for(const scope of ['search','product'])if(event.key==='multimarket.view.'+scope){view(scope,event.newValue||'tiles');const select=document.getElementById(scope+'-view');if(select)select.value=root.dataset[scope+'View'];}});
})();
