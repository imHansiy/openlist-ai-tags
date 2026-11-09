/* OpenList native UI adapter. No model/admin service credentials belong here. */
(() => {
  'use strict';
  if (window.__openlistAITags) return;
  window.__openlistAITags = true;
  const asset = new URL(document.currentScript?.src || '/ai/assets/ai.js', location.href);
  const base = asset.pathname.replace(/\/assets\/ai\.js$/, '');
  const css = document.createElement('link');
  css.rel = 'stylesheet'; css.href = `${base}/assets/ai.css`; document.head.append(css);
  const state = { admin: false, cache: new Map(), context: null, token: null, userName: null, error: '', refreshed: 0 };
  const statuses = { pending:'未识别', running:'识别中', done:'已识别', failed:'识别失败', cancelled:'已取消' };
  let videoRE = /\.(mp4|mkv|avi|mov|webm|m4v|ts|flv)$/i;
  const el = (tag, text, cls) => { const n = document.createElement(tag); if (text != null) n.textContent = text; if (cls) n.className = cls; return n; };
  function button(text, fn, cls='') {
    const b = el('button', text, `ai-button ${cls}`); b.type='button';
    b.addEventListener('click', e => { e.preventDefault(); e.stopPropagation(); Promise.resolve().then(fn).catch(error => notify(error.message)); });
    return b;
  }
  async function api(path, options={}) {
    const r = await fetch(`${base}/api${path}`, { ...options, headers:{ 'Authorization':localStorage.getItem('token') || '', 'Content-Type':'application/json', ...options.headers } });
    const body = await r.json().catch(() => ({}));
    if (!r.ok) throw Error(typeof body.detail === 'string' ? body.detail : `AI 服务请求失败 (${r.status})`);
    return body;
  }
  const post = (path,body={}) => api(path,{method:'POST',body:JSON.stringify(body)});
  function notify(message) {
    let n=document.querySelector('#ai-toast');
    if (!n) { n=el('div',null,'ai-toast'); n.id='ai-toast'; n.setAttribute('role','status'); document.body.append(n); }
    n.textContent=message; n.hidden=false; setTimeout(()=>n.hidden=true,6500);
  }
  function password() {
    const pair=document.cookie.split('; ').find(v=>v.startsWith('browser-password='));
    try { return pair ? decodeURIComponent(pair.slice(pair.indexOf('=')+1)) : ''; } catch { return ''; }
  }
  function decoded(path) { try { return decodeURIComponent(path); } catch { return path; } }
  const currentPath = () => decoded(location.pathname);
  const managePath = () => /^\/@manage(?:\/|$)/.test(location.pathname);
  const manageTabs = {settings:'模型与扫描配置',jobs:'识别任务',tags:'标签规则',history:'历史与错误日志'};
  function manageLocation(tab='settings') {
    return `/@manage?${new URLSearchParams({ai:'video-tags',view:tab})}`;
  }
  function openManage(tab='settings') {
    window.history.pushState({},'',manageLocation(tab));
    window.dispatchEvent(new PopStateEvent('popstate'));
  }
  function clearManagePanel() {
    document.querySelector('#ai-manage-panel')?.remove();
    document.querySelectorAll('.ai-manage-host').forEach(n=>n.classList.remove('ai-manage-host'));
  }
  function restoreManageNavigation() {
    if(typeof state.manageTitle==='string' && document.title==='AI 视频标签 | OpenList 管理')document.title=state.manageTitle;
    state.manageTitle=undefined;
    document.querySelectorAll('.ai-manage-native-active').forEach(n=>n.classList.remove('ai-manage-native-active'));
    document.querySelectorAll('[data-ai-current]').forEach(a=>{
      a.removeAttribute('data-ai-current');
      if(new URL(a.href,location.href).pathname===location.pathname)a.setAttribute('aria-current','page');
    });
  }
  async function ensureManage() {
    if(!managePath() || !state.admin) {
      clearManagePanel();
      restoreManageNavigation();
      document.querySelectorAll('.ai-manage-link,#ai-manage-shortcut').forEach(n=>n.remove());
      return;
    }
    const active=new URLSearchParams(location.search).get('ai')==='video-tags';
    const profiles=[...document.querySelectorAll('a[href="/@manage"]')];
    for(const profile of profiles) {
      const menu=profile.parentElement;
      if(menu.querySelectorAll('a[href^="/@manage"]').length<2)continue;
      menu.classList.toggle('ai-manage-native-active',active);
      if(active)menu.querySelectorAll('a[aria-current="page"]:not(.ai-manage-link)').forEach(a=>{
        a.setAttribute('data-ai-current','page');a.removeAttribute('aria-current');
      });
      let link=menu.querySelector('.ai-manage-link');
      if(!link) {
        const template=menu.querySelector('a[href="/@manage/about"]') || profile;
        link=el('a',null,`${template.className} ai-manage-link`);
        link.href=manageLocation();
        const icon=el('span','AI','ai-manage-icon');icon.setAttribute('aria-hidden','true');
        link.append(icon,el('span','AI 视频标签'));
        link.addEventListener('click',e=>{
          if(e.ctrlKey || e.metaKey || e.shiftKey || e.altKey || e.button!==0)return;
          e.preventDefault();e.stopPropagation();
          link.closest('.hope-drawer__content')?.querySelector('.hope-modal__close-button')?.click();
          openManage();
        });
        menu.append(link);
      }
      link.classList.toggle('ai-manage-active',active);
      if(active)link.setAttribute('aria-current','page');else link.removeAttribute('aria-current');
    }
    const header=[...document.querySelectorAll('header')].find(h=>h.nextElementSibling?.children.length===2);
    if(header && !document.querySelector('#ai-manage-shortcut')) {
      const shortcut=button('AI 视频标签',()=>openManage(),'ai-manage-shortcut');shortcut.id='ai-manage-shortcut';
      (header.firstElementChild?.lastElementChild || header).prepend(shortcut);
    }
    if(!active) {clearManagePanel();restoreManageNavigation();return;}
    if(state.manageTitle===undefined)state.manageTitle=document.title;
    if(document.title!=='AI 视频标签 | OpenList 管理')document.title='AI 视频标签 | OpenList 管理';
    const host=document.querySelector('[data-openlist-manage-content]') || header?.nextElementSibling?.lastElementChild;
    if(!host)return;
    const query=new URLSearchParams(location.search);
    const tab=Object.hasOwn(manageTabs,query.get('view')) ? query.get('view') : 'settings';
    const old=document.querySelector('#ai-manage-panel');
    if(old?.dataset.view===tab && old.aiSession===state.token)return;
    clearManagePanel();host.classList.add('ai-manage-host');
    const panel=el('section',null,'ai-manage-page');panel.id='ai-manage-panel';panel.dataset.view=tab;
    // Compare session changes without placing a token in DOM attributes.
    panel.aiSession=state.token;
    const heading=el('h1','AI 视频标签插件');
    const nav=el('nav',null,'ai-manage-tabs');nav.setAttribute('aria-label','AI 插件管理分区');
    Object.entries(manageTabs).forEach(([key,label])=>{
      const b=button(label,()=>openManage(key));
      b.setAttribute('aria-current',key===tab?'page':'false');nav.append(b);
    });
    const view=el('div',null,'ai-dialog-content');view.id='ai-manage-view';
    view.append(el('p','正在加载插件管理选项…','ai-muted'));
    panel.append(heading,el('p','在 OpenList 管理后台配置模型、扫描目录和识别任务。','ai-muted'),nav,view);host.append(panel);
    try {
      view.replaceChildren();
      await ({settings,jobs,tags:tagManager,history})[tab](view);
    } catch(e) {
      if(view.isConnected)view.replaceChildren(el('p',e.message,'ai-error'),button('重新加载',()=>{clearManagePanel();return ensureManage();}));
    }
  }
  function rowPath(row) {
    const a=row.matches('a[href]') ? row : row.querySelector('a[href]');
    return a ? decoded(new URL(a.getAttribute('href'),location.href).pathname) : null;
  }
  function modal(title) {
    document.querySelector('#ai-dialog')?.remove();
    const d=el('dialog',null,'ai-dialog'); d.id='ai-dialog';
    const head=el('div',null,'ai-dialog-head'); head.append(el('h2',title),button('关闭',()=>d.close()));
    const content=el('div',null,'ai-dialog-content'); d.append(head,content); document.body.append(d);
    d.addEventListener('close',()=>d.remove());
    d.addEventListener('click',e=>{if(e.target===d && (e.clientX<d.getBoundingClientRect().left || e.clientX>d.getBoundingClientRect().right)) d.close();});
    d.showModal(); return { d,content };
  }
  async function refreshAuth() {
    const token=localStorage.getItem('token') || '';
    if(state.token!==token) {
      if(state.token!==null){clearNativeResults();sessionStorage.removeItem('ai-native-search-pending');}
      closeHoverCard();if(state.token!==null){directoryListing=null;document.querySelector('#ai-image-videos')?.remove();}state.cache.clear();state.refreshed=0;state.token=token;document.querySelectorAll('.ai-badges').forEach(n=>n.remove());document.querySelector('#ai-toolbar')?.remove();
    }
    try {
      const me=await api('/me');
      if(token!==(localStorage.getItem('token') || '')){state.admin=false;schedule();return;}
      state.admin=me.admin;
      state.userName=me.username || '';
      const extensions=me.extensions?.filter(x=>/^[a-z0-9]+$/i.test(x));
      if(extensions?.length)videoRE=new RegExp(`\\.(${extensions.join('|')})$`,'i');
      state.error='';
    }
    catch(e) { state.admin=false;state.userName=null;closeHoverCard();clearNativeResults();state.error=e.message; }
  }
  async function recognize(path,contentType='auto',useSubtitles=false) {
    await post('/recognize',{paths:[path],content_type:contentType,use_subtitles:useSubtitles}); state.refreshed=0; notify('已加入真实视频识别队列'); await jobs();
  }
  async function details(path) {
    const {content}=modal('AI 视频识别结果');
    content.append(el('p',path,'ai-muted'));
    const items=await post('/videos/batch',{paths:[path],password:password()});
    const item=items[0];
    if(state.admin) content.append(button('按电影剧情识别',()=>recognize(path,'movie')));
    if(state.admin) content.append(button('字幕与电影联合识别',()=>recognize(path,'movie',true)));
    if (!item) {
      content.append(el('p','此视频尚未识别，或当前账户无权读取结果。'));
      if(state.admin) content.append(button('AI 识别',()=>recognize(path)));
      return;
    }
    content.append(el('p',statuses[item.status] || item.status), el('p',item.result.summary || '等待识别真实视频内容。'));
    if(item.status!=='done' && item.result.summary) content.append(el('p','以下为上一次识别结果，当前任务尚未完成。','ai-muted'));
    const tags=el('div',null,'ai-tags');
    item.ai_tags.forEach(t=>tags.append(button(t,()=>filterTag(t),'ai-tag')));
    item.manual_tags.forEach(t=>tags.append(button(`${t} · 人工`,()=>filterTag(t),'ai-tag ai-manual'))); content.append(tags);
    if(item.error) content.append(el('p',item.error,'ai-error'));
    if(item.result.visible_text?.length) content.append(el('h3','画面文字'),el('p',item.result.visible_text.join('；')));
    if(item.result.characters?.length) {
      content.append(el('h3','主要人物与关系'));
      item.result.characters.forEach(c=>{
        content.append(el('p',`${c.name}：${c.role}${c.relationships?.length ? '；'+c.relationships.join('；') : ''}`));
        if(c.evidence) content.append(el('p',c.evidence,'ai-muted'));
      });
    }
    if(item.result.segments?.length) {
      content.append(el('h3',item.result.verification ? '画面与对白引用时间' : '时间段内容'));
      item.result.segments.forEach(s=>content.append(el('p',`${s.start}–${s.end} 秒：${s.description}`)));
    }
    if(item.result.events?.length) {
      content.append(el('h3','关键事件顺序'));
      item.result.events.forEach((s,i)=>content.append(el('p',`${i+1}. ${s}`)));
    }
    if(item.result.uncertainty) content.append(el('p',item.result.uncertainty,'ai-muted'));
    if(item.result.sampling) {
      const s=item.result.sampling;
      const input=s.method==='compressed-video-v1'
        ? `整段压缩视频 ${(s.video_bytes/1048576).toFixed(2)} MiB`
        : `抽样 ${s.timestamps.length} 帧`;
      const fallback=s.fallback_reason ? ` · ${s.fallback_reason}，已使用抽帧` : '';
      content.append(el('p',`模型：${s.model} · ${input} · 读取 ${(s.network_bytes/1048576).toFixed(1)} MiB${fallback}`,'ai-muted'));
      if(s.context_timestamps?.length) content.append(el('p',`补充清晰画面 ${s.context_timestamps.length} 张，用于核对字幕和人物。`,'ai-muted'));
      if(s.thinking) content.append(el('p','已启用模型推理模式。','ai-muted'));
      if(s.evidence_cache_hit) content.append(el('p','本次复用了仍与原文件信息匹配的压缩视频证据。','ai-muted'));
      if(s.subtitles) {
        content.append(el('p',`字幕证据 ${s.subtitles.count} 条 · ${s.subtitles.source==='burned-in-ocr'?'画面 OCR，可能漏字或错字':'文本字幕轨'}`,'ai-muted'));
        content.append(button('下载提取的字幕',async()=>{
          const data=await post('/subtitles',{paths:[path],password:password()});
          const url=URL.createObjectURL(new Blob([data.srt],{type:'application/x-subrip;charset=utf-8'}));
          const link=el('a'); link.href=url; link.download='video-subtitles.srt'; link.click();
          setTimeout(()=>URL.revokeObjectURL(url),1000);
        }));
      }
    }
    if(state.admin) {
      content.append(el('hr'),el('h3','人工标签（重新识别后保留）'));
      const input=el('input'); input.value=item.manual_tags.join('，'); input.placeholder='使用逗号分隔'; input.setAttribute('aria-label','人工标签'); content.append(input);
      content.append(el('p','取消勾选可隐藏 AI 标签；重新识别后仍然保留此选择。','ai-muted'));
      const checks=[];
      (item.result.tags || []).forEach(tag=>{ const label=el('label',null,'ai-check'); const c=el('input'); c.type='checkbox'; c.checked=!item.removed.includes(tag); label.append(c,document.createTextNode(tag)); content.append(label); checks.push([tag,c]); });
      content.append(button('保存标签',async()=>{
        await post('/videos/edit',{path,manual_tags:input.value.split(/[,，]/).map(x=>x.trim()).filter(Boolean),removed:checks.filter(x=>!x[1].checked).map(x=>x[0])});
        state.refreshed=0; notify('标签已保存'); await details(path);
      }),button('重新识别',()=>recognize(path)));
    }
  }
  let nativeSearch=null;
  let pendingSearch=false;
  function clearNativeResults() {
    if(!nativeSearch)return;
    nativeSearch.controller?.abort();nativeSearch.seq++;nativeSearch.items=[];
    nativeSearch.body=null;nativeSearch.cursor=null;nativeSearch.signature='';nativeSearch.message='标签和视频简介也会参与这次搜索。';
    nativeSearch.section.replaceChildren();
    nativeSearch.dialog.querySelectorAll('.ai-native-note').forEach(n=>n.remove());
    nativeSearch.dialog.querySelectorAll('[data-ai-native-empty]').forEach(n=>{n.hidden=false;n.removeAttribute('data-ai-native-empty');});
  }
  function renderNativeResults() {
    const n=nativeSearch;
    if(!n || !n.input.isConnected)return;
    const root=n.input.parentElement.parentElement;
    const list=[...root.children].find(x=>x!==n.input.parentElement && x.classList.contains('hope-stack') && x.id!=='ai-native-search-results');
    if(!list)return;
    const existing=new Map();
    list.querySelectorAll('a[href]').forEach(a=>{
      if(a.closest('#ai-native-search-results'))return;
      try{existing.set(decoded(new URL(a.href,location.href).pathname),a);}catch{}
    });
    if(n.items.length && !existing.size) {
      [...root.children].filter(x=>x.tagName==='P').forEach(x=>{x.hidden=true;x.setAttribute('data-ai-native-empty','true');});
    } else root.querySelectorAll('[data-ai-native-empty]').forEach(x=>{x.hidden=false;x.removeAttribute('data-ai-native-empty');});
    const signature=JSON.stringify([n.message,n.items,n.cursor,[...existing.keys()]]);
    const needsNote=n.items.some(x=>existing.has(x.path) && !existing.get(x.path).querySelector('.ai-native-note'));
    if(n.signature===signature && n.section.isConnected && !needsNote)return;
    n.signature=signature;
    n.dialog.querySelectorAll('.ai-native-note').forEach(x=>x.remove());
    n.section.replaceChildren(el('h3','视频标签与简介匹配'));
    if(n.message)n.section.append(el('p',n.message,'ai-muted'));
    n.items.forEach(item=>{
      if(existing.has(item.path)) {
        const a=existing.get(item.path);const note=el('div',null,'ai-native-note');
        note.append(el('p',item.tags.join(' · '),'ai-muted'),el('p',(item.result.summary || '').slice(0,300)));
        (a.querySelector('.hope-stack') || a).append(note);return;
      }
      const card=el('article',null,'ai-native-result');
      const a=el('a',item.path.split('/').at(-1));a.href=item.path.split('/').map(encodeURIComponent).join('/')+'?from=search';
      card.append(a,el('p',item.path,'ai-muted'),el('p',(item.result.summary || '').slice(0,300)));
      const tags=el('div',null,'ai-tags');item.tags.forEach(t=>tags.append(button(t,()=>filterTag(t),'ai-tag')));
      card.append(tags,button('查看 AI 结果',()=>details(item.path)));n.section.append(card);
    });
    if(n.cursor!==null)n.section.append(button('继续查找标签与简介匹配',()=>submitNativeSearch(n.body,true)));
    if(n.items.length && !existing.size) {
      [...root.children].filter(x=>x.tagName==='P').forEach(x=>{x.hidden=true;x.setAttribute('data-ai-native-empty','true');});
    } else {
      root.querySelectorAll('[data-ai-native-empty]').forEach(x=>{x.hidden=false;x.removeAttribute('data-ai-native-empty');});
    }
    list.append(n.section);
  }
  function ensureNativeSearch() {
    const input=document.querySelector('#search-input');const dialog=input?.closest('[role="dialog"]');
    if(!input || !dialog || !input.getClientRects().length)return;
    if(nativeSearch?.input!==input) {
      clearNativeResults();
      const section=el('section',null,'ai-native-search');section.id='ai-native-search-results';section.setAttribute('aria-live','polite');
      nativeSearch={input,dialog,section,seq:0,items:[],cursor:null,body:null,message:'同时查找当前目录下的视频标签和简介；#动画 #亲情 表示组合标签。'};
      input.placeholder='搜索文件名、AI 标签或视频简介';
      input.addEventListener('input',()=>{clearNativeResults();renderNativeResults();});
    }
    renderNativeResults();
  }
  async function submitNativeSearch(body,more=false) {
    ensureNativeSearch();const n=nativeSearch;
    if(!n || !n.input.isConnected || n.input.value!==body.keywords)return;
    const key=JSON.stringify([body.parent,body.keywords,body.scope,body.password]);
    if(!more && n.key===key && n.body && body.page>1)return;
    n.controller?.abort();n.controller=new AbortController();const seq=++n.seq;
    const token=localStorage.getItem('token') || '';
    if(!more){n.items=[];n.cursor=null;}
    n.body=body;n.key=key;n.message='正在匹配视频标签与简介…';renderNativeResults();
    try {
      const data=await api('/native-search',{method:'POST',body:JSON.stringify({parent:body.parent,keywords:body.keywords,password:body.password,scope:body.scope,cursor:more?n.cursor || 0:0,limit:30}),signal:n.controller.signal});
      if(nativeSearch!==n || seq!==n.seq || !n.input.isConnected || token!==(localStorage.getItem('token') || ''))return;
      const items=new Map(n.items.map(x=>[x.path,x]));data.items.forEach(x=>items.set(x.path,x));n.items=[...items.values()];n.cursor=data.next_cursor;
      n.message=body.scope===1?'文件夹范围不检索视频内容。':n.items.length?`已找到 ${n.items.length} 个可访问视频。`:n.cursor!==null?'当前批次没有匹配，可继续查找。':'未找到标签或简介匹配的视频。';
    } catch(e) {
      if(e.name==='AbortError' || nativeSearch!==n || seq!==n.seq)return;
      n.cursor=null;n.message='标签与简介检索暂不可用，OpenList 文件名搜索仍可使用。';
    }
    if(nativeSearch===n && seq===n.seq)renderNativeResults();
  }
  function observeSearch(method,url,body) {
    try {
      const u=new URL(url,location.href);
      if(method.toUpperCase()!=='POST' || u.origin!==location.origin || u.pathname!=='/api/fs/search' || typeof body!=='string' || body.length>65536)return;
      const q=JSON.parse(body);
      if(typeof q.parent==='string' && typeof q.keywords==='string')submitNativeSearch({parent:q.parent,keywords:q.keywords,password:q.password || '',scope:q.scope || 0,page:Number(q.page) || 1}).catch(()=>{});
    } catch{}
  }
  // Observe the native request; never alter, delay, cancel, or replace its response.
  const xhrRequests=new WeakMap();
  let directoryListing=null;
  function rememberListing(url,body,response){
    try{if(new URL(url,location.href).pathname==='/api/fs/list' && response.code===200){const q=JSON.parse(body);directoryListing={path:q.path,items:response.data.content || []};document.querySelector('#ai-image-videos')?.remove();schedule();}}catch{}
  }
  const originalOpen=XMLHttpRequest.prototype.open,originalSend=XMLHttpRequest.prototype.send;
  XMLHttpRequest.prototype.open=function(method,url,...args){xhrRequests.set(this,{method,url});return originalOpen.call(this,method,url,...args);};
  XMLHttpRequest.prototype.send=function(body){const q=xhrRequests.get(this);if(q && new URL(q.url,location.href).pathname==='/api/fs/list')this.addEventListener('load',()=>{try{rememberListing(q.url,body,this.responseType==='json'?this.response:JSON.parse(this.responseText));}catch{}},{once:true});const value=originalSend.call(this,body);if(q)observeSearch(q.method,q.url,body);return value;};
  const originalFetch=window.fetch;
  window.fetch=function(input,options){
    const response=originalFetch.apply(this,arguments);
    if(typeof input==='string' || input instanceof URL){observeSearch(options?.method || 'GET',String(input),options?.body);if(new URL(String(input),location.href).pathname==='/api/fs/list')response.then(r=>r.clone().json()).then(data=>rememberListing(String(input),options?.body,data)).catch(()=>{});}
    else if(input instanceof Request && new URL(input.url).pathname==='/api/fs/search')input.clone().text().then(body=>observeSearch(options?.method || input.method,input.url,options?.body || body)).catch(()=>{});
    return response;
  };
  function ensureImageVideoCards(){
    const host=document.querySelector('.image-folders')?.parentElement || document.querySelector('.image-images')?.parentElement;
    if(!host){document.querySelector('#ai-image-videos')?.remove();return;}
    if(document.querySelector('#ai-image-videos') || directoryListing?.path!==currentPath())return;
    const videos=directoryListing.items.filter(x=>!x.is_dir && videoRE.test(x.name));if(!videos.length)return;
    const section=el('section',null,'ai-image-videos');section.id='ai-image-videos';section.setAttribute('aria-label','视频');
    videos.forEach(item=>{
      const a=el('a',null,'grid-item viselect-item ai-image-video');a.href=(currentPath().replace(/\/$/,'')+'/'+item.name).split('/').map(encodeURIComponent).join('/');
      const thumb=el('div',null,'ai-video-thumbnail');
      if(item.thumb){const img=el('img');img.src=item.thumb;img.loading='lazy';img.alt='';thumb.append(img);}else thumb.append(el('span','▶'));
      a.append(thumb,el('span',item.name,'name'));section.append(a);
    });host.append(section);
  }
  async function openNativeSearch(query,redirect=true) {
    document.querySelector('#ai-dialog')?.close();
    let input=document.querySelector('#search-input');
    if(!input?.getClientRects().length)document.dispatchEvent(new KeyboardEvent('keydown',{key:'k',ctrlKey:true,bubbles:true}));
    for(let i=0;i<20;i++) {
      input=document.querySelector('#search-input');if(input?.getClientRects().length)break;
      await new Promise(resolve=>setTimeout(resolve,80));
    }
    if(!input?.getClientRects().length) {
      if(redirect && videoRE.test(currentPath())) {
        const parent=currentPath().slice(0,currentPath().lastIndexOf('/')) || '/';
        sessionStorage.setItem('ai-native-search-pending',JSON.stringify({parent,query,user:state.userName,expires:Date.now()+120000}));
        location.assign(parent.split('/').map(encodeURIComponent).join('/') || '/');
      } else if(redirect)notify('请打开 OpenList 原生搜索（Ctrl+K）后输入标签或简介关键词。');
      return false;
    }
    // A tag targets videos even if the previous native search selected folders.
    const controls=input.parentElement,select=controls.querySelector('select');
    if(select){select.value='2';select.dispatchEvent(new Event('change',{bubbles:true}));}
    else {
      const combo=controls.querySelector('[role="combobox"]');
      if(combo){
        combo.click();
        for(let i=0;i<10;i++){
          const options=document.getElementById(combo.getAttribute('aria-controls'))?.querySelectorAll('[role="option"]');
          if(options?.length===3){options[2].click();break;}
          await new Promise(resolve=>setTimeout(resolve,30));
        }
        if(combo.getAttribute('aria-expanded')==='true')combo.click();
      }
    }
    input.value=query;input.dispatchEvent(new Event('input',{bubbles:true}));input.focus();
    input.dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',bubbles:true}));return true;
  }
  function filterTag(t) {return openNativeSearch('#'+(t.includes(' ')?JSON.stringify(t):t));}
  async function resumeNativeSearch() {
    if(pendingSearch)return;
    try {
      const pending=JSON.parse(sessionStorage.getItem('ai-native-search-pending') || 'null');
      if(!pending)return;
      if(pending.user!==state.userName){sessionStorage.removeItem('ai-native-search-pending');return;}
      if(pending.expires<Date.now()){sessionStorage.removeItem('ai-native-search-pending');return;}
      if(pending.parent!==currentPath())return;
      pendingSearch=true;
      if(await openNativeSearch(pending.query,false))sessionStorage.removeItem('ai-native-search-pending');
    }catch{}finally{pendingSearch=false;}
  }
  function ensureToolbar() {
    const body=document.querySelector('.body');
    if(!body || location.pathname.startsWith('/@') || location.pathname.startsWith('/login'))return;
    if(!videoRE.test(currentPath())){document.querySelector('#ai-toolbar')?.remove();return;}
    if(document.querySelector('#ai-toolbar'))return;
    const bar=el('section',null,'ai-toolbar');bar.id='ai-toolbar';bar.setAttribute('aria-label','AI 视频标签');
    const tools=el('div',null,'ai-tools');
    if(state.error)tools.append(el('span',state.error,'ai-error'));
    bar.append(tools);body.prepend(bar);
    bar.append(button('查看此视频 AI 结果',()=>details(currentPath())));
  }
  async function jobs(target) {
    const {content,d}=target ? {content:target,d:target} : modal('AI 扫描任务');
    const render=async()=>{
      if(!d.isConnected) return;
      const data=await api('/jobs'); if(!d.isConnected) return;
      content.replaceChildren(button('扫描全部已配置目录',async()=>{const s=await api('/settings');await post('/scan',{paths:s.settings.roots});await render();}),el('p','暂停后停止领取新任务；正在解码或推理的任务可能继续完成。取消后结果不会提交。','ai-muted'));
      data.forEach(job=>{
        const card=el('article',null,'ai-job'); const t=job.tasks;
        card.append(el('strong',`#${job.id} ${job.root}`),el('p',`${job.state} · 总数 ${Object.values(t).reduce((a,b)=>a+b,0)} · 完成 ${t.done || 0} · 失败 ${t.failed || 0} · 等待 ${t.queued || 0} · 识别中 ${t.running || 0}`));
        const progress=el('progress'); progress.max=Math.max(1,Object.values(t).reduce((a,b)=>a+b,0)); progress.value=(t.done||0)+(t.failed||0)+(t.cancelled||0); card.append(progress);
        if(job.error) card.append(el('p',job.error,'ai-error'));
        const actions=job.state==='running' ? [['pause','暂停'],['cancel','取消']] : job.state==='paused' ? [['resume','恢复'],['cancel','取消']] : ['failed','done'].includes(job.state) ? [['retry','重试失败任务']] : [];
        actions.forEach(([a,label])=>card.append(button(label,async()=>{await post(`/jobs/${job.id}/${a}`);await render();}))); content.append(card);
      });
      if(!data.length)content.append(el('p','尚无扫描任务。'));
    };
    await render(); const timer=setInterval(()=>{
      if(!d.isConnected){clearInterval(timer);return;}
      render().catch(()=>{});
    },3000); d.addEventListener('close',()=>clearInterval(timer),{once:true});
  }
  async function settings(target) {
    const content=target || modal('AI 插件管理').content; const data=await api('/settings');
    content.append(el('p',`模型密钥：${data.model_key_configured?'已在服务端配置':'未配置（本地模型可不需要）'}。现有密钥不会回传浏览器。`,'ai-muted'));
    const key=el('input');key.type='password';key.autocomplete='new-password';key.placeholder='输入新模型密钥（不会回显现有密钥）';key.setAttribute('aria-label','新模型密钥');
    content.append(key,button('更新模型密钥',async()=>{await api('/model/key',{method:'PUT',body:JSON.stringify({key:key.value})});key.value='';notify('模型密钥已保存到服务端，不会回显');}));
    const form=el('form',null,'ai-settings'); const fields={};
    const labels={model_url:'模型服务基础地址',model_name:'模型规格',roots:'扫描目录（每行一个）',exclude:'排除目录（每行一个）',extensions:'视频扩展名（逗号分隔）',interval_minutes:'定时扫描间隔（分钟，0 关闭）',concurrency:'识别并发（1–4）',frames:'每个视频抽帧数量（2–48）',max_video_bytes:'视频大小上限（字节）',max_network_bytes:'每个视频读取流量上限（字节）',media_timeout:'解码总超时（秒）',model_timeout:'模型超时（秒）',page_size:'目录分页大小',max_depth:'最大目录深度',max_files:'最大视频索引数量',scan_delay:'扫描请求间隔（秒）'};
    Object.assign(labels,{model_thinking:'官方 MiniCPM 推理模式（增加计算量）',video_num_frames:'官方接口视频采样帧数（0 使用服务默认，最多 128）',context_frames:'字幕关系补充画面（0–8 张）'});
    Object.entries(data.settings).forEach(([key,value])=>{
      const label=el('label',labels[key] || key); const input=el(Array.isArray(value)?'textarea':'input');
      input.value=Array.isArray(value)?value.join(key==='extensions'?',':'\n'):String(value); input.name=key;
      if(typeof value==='number') {input.type='number'; input.step='any';}
      if(typeof value==='boolean') {input.type='checkbox'; input.checked=value;}
      if(key==='model_name') { input.setAttribute('list','ai-models'); const list=el('datalist'); list.id='ai-models'; ['MiniCPM-V-4.7-1B','MiniCPM-V-4.7-35B-A3B','openbmb/MiniCPM-V-4.7-1B','openbmb/MiniCPM-V-4.7-35B-A3B'].forEach(v=>{const o=el('option');o.value=v;list.append(o);});label.append(list); }
      label.append(input);form.append(label);fields[key]=input;
    });
    form.addEventListener('submit',e=>e.preventDefault());
    content.append(form,button('保存配置',async()=>{
      const s={}; Object.entries(data.settings).forEach(([k,v])=>s[k]=Array.isArray(v)?fields[k].value.split(k==='extensions'?/[,，]/:/\n/).map(x=>x.trim()).filter(Boolean):typeof v==='boolean'?fields[k].checked:typeof v==='number'?Number(fields[k].value):fields[k].value);
      await api('/settings',{method:'PUT',body:JSON.stringify(s)});notify('配置已保存');
    }),button('测试已保存模型（真实视觉请求）',async()=>{notify('正在发送测试图片…'); const r=await post('/model/test');notify(r.summary);}),button('同义标签与常用标签',()=>target?openManage('tags'):tagManager()),button('识别历史 / 错误日志',()=>target?openManage('history'):history()),button('下载数据备份',async()=>{
      const r=await fetch(`${base}/api/backup`,{method:'POST',headers:{Authorization:localStorage.getItem('token')||''}}); if(!r.ok)throw Error('备份失败');
      const url=URL.createObjectURL(await r.blob()); const a=el('a'); a.href=url;a.download=`aitags-${new Date().toISOString().slice(0,10)}.sqlite3`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
    }));
    content.append(el('p',`媒体主机白名单：${data.media_allowed_hosts.join(', ') || '仅 OpenList 本站'}。模型密钥更新后立即生效；媒体白名单需在服务端修改并重启 AI 服务。`,'ai-muted'));
  }
  async function tagManager(target) {
    const content=target || modal('同义标签与常用标签').content;const data=await api('/tags');
    content.append(el('p','同义标签每行填写“别名=标准标签”，不允许循环或多级映射。'));
    const aliases=el('textarea');aliases.value=data.aliases.map(a=>`${a.alias}=${a.canonical}`).join('\n'); aliases.setAttribute('aria-label','同义标签');
    const favorites=el('input');favorites.value=data.favorites.join('，');favorites.setAttribute('aria-label','常用标签');content.append(aliases,el('p','常用标签，逗号分隔'),favorites);
    data.favorites.forEach(t=>content.append(target?el('span',t,'ai-tag'):button(t,()=>filterTag(t),'ai-tag')));
    content.append(button('保存',async()=>{
      await api('/tags',{method:'PUT',body:JSON.stringify({aliases:aliases.value.split('\n').filter(x=>x.trim()).map(x=>{const [alias,canonical]=x.split('=');return {alias:alias?.trim(),canonical:canonical?.trim()};}),favorites:favorites.value.split(/[,，]/).map(x=>x.trim()).filter(Boolean)})});state.refreshed=0;notify('标签规则已保存');
    }));
  }
  async function history(target) {
    const content=target || modal('识别历史与错误日志').content;let before='';
    const load=async()=>{const rows=await api(`/history${before?`?before=${before}`:''}`); rows.forEach(r=>content.append(el('p',`${new Date(r.created*1000).toLocaleString()} · ${r.path} · ${r.state} · ${r.message}`))); before=rows.at(-1)?.id;more.hidden=rows.length<100;};
    const more=button('加载较早记录',load);content.append(more);await load();
  }
  let hoverCard=null,hoverAnchor=null,hoverTimer;
  function closeHoverCard(){clearTimeout(hoverTimer);hoverCard?.remove();hoverCard=null;hoverAnchor?.setAttribute('aria-expanded','false');hoverAnchor=null;}
  function positionHoverCard(){
    if(!hoverCard || !hoverAnchor?.isConnected){closeHoverCard();return;}
    const r=(hoverAnchor.closest('.ai-video-row') || hoverAnchor).getBoundingClientRect();
    const below=innerHeight-r.bottom-22,above=r.top-22,down=below>=above;
    hoverCard.style.maxHeight=Math.max(100,Math.min(520,down?below:above))+'px';
    const c=hoverCard.getBoundingClientRect();
    const left=Math.max(12,Math.min(r.right-c.width,innerWidth-c.width-12));
    let top=down?r.bottom+10:Math.max(12,r.top-c.height-10);
    hoverCard.style.left=left+'px';hoverCard.style.top=top+'px';
  }
  function showHoverCard(anchor,path){
    clearTimeout(hoverTimer);if(hoverAnchor===anchor && hoverCard)return;
    closeHoverCard();hoverAnchor=anchor;anchor.setAttribute('aria-expanded','true');
    const data=state.cache.get(path),card=el('section',null,'ai-hover-card');hoverCard=card;card.id='ai-hover-card';card.setAttribute('role','region');card.setAttribute('aria-label','视频 AI 信息');
    const head=el('div',null,'ai-hover-head');head.append(el('span',statuses[data?.status] || '未识别',`ai-status ai-${data?.status||'pending'}`),button('关闭',closeHoverCard));
    const summary=el('p',data?.result?.summary || (data?.status==='failed'?'识别失败，可打开完整结果查看原因。':'尚无视频简介。'),'ai-hover-summary');
    card.append(head,el('h3',path.split('/').at(-1)),summary);
    if((data?.result?.summary || '').length>150){
      const expand=button('展开简介',()=>{const expanded=summary.classList.toggle('ai-expanded');expand.textContent=expanded?'收起简介':'展开简介';expand.setAttribute('aria-expanded',String(expanded));positionHoverCard();});expand.setAttribute('aria-expanded','false');card.append(expand);
    }
    const tags=el('div',null,'ai-tags');(data?.tags || []).forEach(t=>tags.append(button(t,()=>{closeHoverCard();return filterTag(t);},'ai-tag'+(data.manual_tags?.includes(t)?' ai-manual':''))));card.append(tags);
    card.append(button('查看完整 AI 结果',()=>{closeHoverCard();return details(path);}));
    if(state.admin)card.append(button(data?'重新识别':'AI 识别',()=>{closeHoverCard();return recognize(path);}));
    card.addEventListener('pointerenter',()=>clearTimeout(hoverTimer));card.addEventListener('pointerleave',()=>{hoverTimer=setTimeout(closeHoverCard,240);});
    card.addEventListener('focusout',()=>setTimeout(()=>{if(hoverCard && !hoverCard.contains(document.activeElement) && document.activeElement!==hoverAnchor)closeHoverCard();},0));
    document.body.append(card);positionHoverCard();
  }
  document.addEventListener('pointerdown',e=>{if(hoverCard && !hoverCard.contains(e.target) && !e.target.closest?.('.ai-badges'))closeHoverCard();},true);
  document.addEventListener('keydown',e=>{if(e.key==='Escape')closeHoverCard();});
  window.addEventListener('resize',positionHoverCard);window.addEventListener('scroll',e=>{if(hoverCard && !hoverCard.contains(e.target))closeHoverCard();},true);
  function paintRow(row,path) {
    const data=state.cache.get(path); const signature=JSON.stringify(data || null);
    const old=row.querySelector('.ai-badges'); if(old?.dataset.signature===signature)return;
    old?.remove();const badges=el('span',null,'ai-badges');badges.dataset.signature=signature;
    const trigger=button('AI',()=>{showHoverCard(trigger,path);},`ai-status ai-${data?.status||'pending'}`);
    trigger.setAttribute('aria-label',statuses[data?.status] || '未识别');trigger.setAttribute('aria-expanded','false');trigger.setAttribute('aria-controls','ai-hover-card');
    trigger.title='查看视频简介与标签';
    trigger.addEventListener('focus',()=>showHoverCard(trigger,path));
    trigger.addEventListener('keydown',e=>{if(e.key==='ArrowDown'){e.preventDefault();showHoverCard(trigger,path);hoverCard?.querySelector('button')?.focus();}});
    row.onpointerenter=e=>{if(e.pointerType!=='touch')showHoverCard(trigger,path);};
    row.onpointerleave=()=>{hoverTimer=setTimeout(closeHoverCard,240);};
    badges.append(trigger);row.append(badges);row.classList.add('ai-video-row');
    if(row.classList.contains('list-item'))row.classList.add('ai-list-row');
  }
  let busy=false;
  async function update() {
    if(busy || document.hidden)return; busy=true;
    try {
      await refreshAuth(); await ensureManage(); ensureToolbar();ensureNativeSearch();resumeNativeSearch().catch(()=>{});
      if(managePath())return;
      ensureImageVideoCards();
      const rows=[...document.querySelectorAll('.list-item[href],.grid-item[href]')].map(row=>[row,rowPath(row)]).filter(([,path])=>path && videoRE.test(path));
      const missing=rows.map(([,p])=>p).filter(p=>!state.cache.has(p));
      const paths=[...new Set(missing.length?missing:Date.now()-state.refreshed>20000?rows.map(([,p])=>p):[])].slice(0,60);
      if(paths.length) {
        const data=await post('/videos/batch',{paths,password:password()}); paths.forEach(p=>state.cache.set(p,null));data.forEach(x=>state.cache.set(x.path,x));state.refreshed=Date.now();
      }
      rows.forEach(([row,path])=>paintRow(row,path));
      // Extend the existing OpenList context menu without replacing its original actions.
      if(state.context) {
        const menu=[...document.querySelectorAll('[role="menu"],.solid-contextmenu,.contexify')].find(n=>n.getBoundingClientRect().width>0);
        if(menu && !menu.querySelector('.ai-context')) {
          const actions=el('div',null,'ai-context');actions.append(button('查看 AI 结果',()=>details(state.context)));
          if(state.admin) actions.append(button('AI 识别 / 重新识别',()=>recognize(state.context)),button('编辑 AI / 人工标签',()=>details(state.context)));menu.append(actions);
        }
      }
    } catch(e) { state.error=e.message; }
    finally {busy=false;}
  }
  let debounce;
  const schedule=()=>{clearTimeout(debounce);debounce=setTimeout(update,350);};
  document.addEventListener('click',e=>{
    if(!managePath() || new URLSearchParams(location.search).get('ai')!=='video-tags' ||
       e.ctrlKey || e.metaKey || e.shiftKey || e.altKey || e.button!==0)return;
    const a=e.target.closest?.('a[href]');
    if(!a || a.classList.contains('ai-manage-link'))return;
    const url=new URL(a.href,location.href);
    if(url.origin!==location.origin || !/^\/@manage(?:\/|$)/.test(url.pathname))return;
    const before=location.pathname+location.search;
    // Solid can change only the query without rendering or emitting popstate.
    setTimeout(()=>{
      if(before!==location.pathname+location.search){
        oldPath=location.pathname+location.search;clearManagePanel();restoreManageNavigation();schedule();
      }
    },0);
  },true);
  document.addEventListener('contextmenu',e=>{const row=e.target.closest('.list-item,.grid-item');const path=row&&rowPath(row);state.context=path && videoRE.test(path)?path:null;document.querySelectorAll('.ai-context').forEach(n=>n.remove());schedule();},true);
  window.addEventListener('popstate',()=>{closeHoverCard();oldPath=location.pathname+location.search;state.refreshed=0;document.querySelector('#ai-toolbar')?.remove();clearManagePanel();schedule();});
  window.addEventListener('storage',e=>{if(e.key==='token'){clearManagePanel();clearNativeResults();sessionStorage.removeItem('ai-native-search-pending');schedule();}});
  let oldPath=location.pathname+location.search;
  new MutationObserver(records=>{
    if(oldPath!==location.pathname+location.search){closeHoverCard();oldPath=location.pathname+location.search;state.refreshed=0;document.querySelector('#ai-toolbar')?.remove();clearManagePanel();}
    if(records.some(r=>!r.target.closest?.('[id^="ai-"],.ai-badges,.ai-context')))schedule();
  }).observe(document.documentElement,{childList:true,subtree:true});
  setInterval(update,8000);schedule();
})();
