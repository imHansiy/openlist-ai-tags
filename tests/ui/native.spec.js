const {test,expect}=require('@playwright/test');
const fs=require('fs');
const script=fs.readFileSync('aitags/static/ai.js','utf8');
const css=fs.readFileSync('aitags/static/ai.css','utf8');
const video={path:'/videos/clip.mp4',status:'done',tags:['旅行','城市'],ai_tags:['旅行','城市'],manual_tags:[],removed:[],error:'',result:{summary:'夜晚的城市街景',tags:['旅行','城市'],visible_text:[],verification:{method:'targeted-evidence-audit-v1'},characters:[{name:'小林',role:'姐姐',relationships:['小海的姐姐'],evidence:'10秒：我是姐姐'}],events:['先辞职','再迁居'],segments:[{start:1,end:2,description:'街道'}],uncertainty:'抽样结果'}};

async function boot(page,{admin=true,grid=false,manage=false,start,nativeRows=[]}={}) {
  const requests=[];
  await page.addInitScript(()=>{
    document.addEventListener('keydown',e=>{
      if(!e.ctrlKey || e.key.toLowerCase()!=='k' || location.pathname.startsWith('/@'))return;
      e.preventDefault();const old=document.querySelector('#native-search-modal');if(old){old.remove();return;}
      const modal=document.createElement('section');modal.id='native-search-modal';modal.setAttribute('role','dialog');
      modal.innerHTML='<div class="hope-modal__body"><div class="hope-stack"><div class="hope-stack"><select aria-label="原生搜索范围"><option value="0">全部</option><option value="1">文件夹</option><option value="2">文件</option></select><input id="search-input"><button aria-label="search">搜索</button></div><p>暂无结果</p><div class="hope-stack" id="native-file-results"></div></div></div>';
      document.body.append(modal);const input=modal.querySelector('input'),row=input.parentElement,root=row.parentElement,results=modal.querySelector('#native-file-results');
      const run=async()=>{
        root.querySelector(':scope>p')?.remove();
        const r=await fetch('/api/fs/search',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({parent:decodeURIComponent(location.pathname),keywords:input.value,password:'',scope:Number(row.querySelector('select').value),page:1,per_page:100})});
        const data=(await r.json()).data;results.replaceChildren();
        if(!data.content.length){const empty=document.createElement('p');empty.textContent='暂无结果';root.insertBefore(empty,results);}
        data.content.forEach(item=>{const a=document.createElement('a');a.href=item.parent+'/'+item.name+'?from=search';const label=document.createElement('div');label.className='hope-stack';label.textContent=item.name;a.append(label);results.append(a);});
      };
      row.querySelector('button').onclick=run;input.onkeydown=e=>{if(e.key==='Enter')run();};input.focus();
    });
  });
  await page.route('http://openlist.test/**',async route=>{
    const req=route.request(); const path=new URL(req.url()).pathname;
    if(path==='/ai/assets/ai.js')return route.fulfill({contentType:'application/javascript; charset=utf-8',body:script});
    if(path==='/ai/assets/ai.css')return route.fulfill({contentType:'text/css',body:css});
    if(path==='/api/fs/search'){requests.push({path,method:req.method(),body:req.postDataJSON()});return route.fulfill({json:{code:200,data:{content:nativeRows,total:nativeRows.length}}});}
    if(path.startsWith('/ai/api/')){
      requests.push({path,method:req.method(),body:req.postDataJSON()});
      let data={};
      if(path.endsWith('/me'))data={admin,username:'test'};
      if(path.endsWith('/videos/batch'))data=[video];
      if(path.endsWith('/search'))data={items:[video],next_cursor:null};
      if(path.endsWith('/native-search'))data={items:req.postDataJSON().scope===1?[]:[video],next_cursor:null};
      if(path.endsWith('/videos/edit'))data=video;
      if(path.endsWith('/jobs'))data=[];
      if(path.endsWith('/tags'))data={aliases:[],favorites:['家庭']};
      if(path.endsWith('/history'))data=[];
      if(path.endsWith('/settings'))data={settings:{model_url:'https://api.modelbest.ai/v1',
        model_name:'MiniCPM-V-4.7-35B-A3B',model_thinking:true,video_num_frames:32,context_frames:5,roots:['/videos'],exclude:[],extensions:['mp4','mkv']},
        model_key_configured:true,media_allowed_hosts:[]};
      return route.fulfill({json:data});
    }
    if(path.startsWith('/@manage'))return route.fulfill({contentType:'text/html; charset=utf-8',body:`<!doctype html><html><head><meta charset="utf-8"><script defer src="/ai/assets/ai.js"></script><style>body{margin:0}.native-row{display:flex}aside{width:224px;flex-shrink:0}main{flex:1;min-width:0;padding:16px}header>div{display:flex;justify-content:space-between}@media(max-width:600px){aside{display:none}}</style></head><body><div><header><div><h2>OpenList 管理</h2><div>退出</div></div></header><div class="native-row"><aside><nav><a href="/@manage">个人资料</a><a href="/@manage/storages">存储</a><a href="/@manage/about">关于</a></nav></aside><main data-openlist-manage-content><div id="native-manage-content">${path.endsWith('/storages')?'存储管理':'个人资料内容'}</div></main></div></div></body></html>`});
    return route.fulfill({contentType:'text/html; charset=utf-8',body:`<!doctype html><html><head><meta charset="utf-8"><script defer src="/ai/assets/ai.js"></script></head><body><main class="body"><div class="viselect-container"><a class="${grid?'grid-item':'list-item'} viselect-item" href="/videos/clip.mp4"><span class="name">clip.mp4</span></a><a class="list-item" href="/videos/notes.txt">notes.txt</a></div></main></body></html>`});
  });
  await page.goto('http://openlist.test'+(start || (manage?'/@manage':'/videos')));
  if(manage){if(admin)await expect(page.locator('.ai-manage-link')).toBeAttached();}
  else{await expect(page.locator('#ai-toolbar')).toHaveCount(0);await expect(page.locator('.ai-badges')).toBeVisible();}
  return requests;
}

test('native list tags, tag search, details and manual edits',async({page})=>{
  const requests=await boot(page);
  await page.locator('.ai-badges').getByRole('button',{name:'已识别',exact:true}).click();
  await page.locator('#ai-hover-card').getByRole('button',{name:'旅行',exact:true}).click();
  await expect(page.locator('#ai-native-search-results')).toContainText('夜晚的城市街景');
  await expect(page.locator('#search-input')).toHaveValue('#旅行');
  await expect(page.locator('#ai-query,#ai-results')).toHaveCount(0);
  await page.locator('#ai-native-search-results').getByRole('button',{name:'查看 AI 结果'}).click();
  await expect(page.locator('#ai-dialog')).toContainText('画面与对白引用时间');
  await expect(page.locator('#ai-dialog')).toContainText('小海的姐姐');
  await expect(page.locator('#ai-dialog')).toContainText('10秒：我是姐姐');
  await expect(page.locator('#ai-dialog')).toContainText('关键事件顺序');
  await expect(page.locator('#ai-dialog')).toContainText('再迁居');
  await page.getByLabel('人工标签').fill('日本，夜景');
  await page.getByLabel('城市',{exact:true}).uncheck();
  await page.getByRole('button',{name:'保存标签',exact:true}).click();
  await expect.poll(()=>requests.find(r=>r.path.endsWith('/videos/edit'))?.body).toEqual({path:video.path,manual_tags:['日本','夜景'],removed:['城市']});
  expect(requests.some(r=>r.path.endsWith('/native-search'))).toBeTruthy();
});

test('ordinary user sees tags without admin controls',async({page})=>{
  await boot(page,{admin:false});
  await expect(page.getByRole('button',{name:'扫描当前目录'})).toHaveCount(0);
  await page.locator('.ai-badges').getByRole('button',{name:'已识别',exact:true}).click();
  await expect(page.locator('#ai-hover-card')).toContainText('夜晚的城市街景');
  await page.locator('#ai-hover-card').getByRole('button',{name:'查看完整 AI 结果'}).click();
  await expect(page.getByLabel('人工标签')).toHaveCount(0);
});

test('mobile grid dark mode retains file navigation',async({page})=>{
  await page.setViewportSize({width:390,height:844});
  await boot(page,{grid:true});
  await page.locator('html').evaluate(n=>n.setAttribute('data-theme','dark'));
  await expect(page.locator('.grid-item .ai-badges')).toBeVisible();
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
  await expect(page.locator('.grid-item')).toHaveAttribute('href','/videos/clip.mp4');
  await page.locator('.ai-badges').getByRole('button',{name:'已识别',exact:true}).click();
  await page.locator('#ai-hover-card').getByRole('button',{name:'查看完整 AI 结果'}).click();
  expect(await page.locator('dialog').evaluate(n=>n.getBoundingClientRect().width)).toBeLessThanOrEqual(390);
});

test('native operation menu gains AI actions',async({page})=>{
  await boot(page);
  await page.evaluate(()=>{const menu=document.createElement('div');menu.className='contexify';menu.textContent='下载';document.body.append(menu);});
  await page.locator('.list-item').first().click({button:'right'});
  await expect(page.locator('.contexify .ai-context')).toContainText('编辑 AI / 人工标签');
});

test('unsafe model strings render as text',async({page})=>{
  const saved=video.result.summary;
  video.result.summary='<img src=x onerror="window.pwned=true">';
  try{
    await boot(page);await page.locator('.ai-badges').getByRole('button',{name:'已识别',exact:true}).click();
    await expect(page.locator('#ai-hover-card')).toContainText('<img');
    expect(await page.evaluate(()=>window.pwned)).toBeUndefined();
  }finally{video.result.summary=saved;}
});

test('model controls preserve boolean and numeric types',async({page})=>{
  const requests=await boot(page,{manage:true,start:'/@manage?ai=video-tags'});
  await page.getByLabel('官方 MiniCPM 推理模式（增加计算量）').uncheck();
  await page.getByLabel('官方接口视频采样帧数（0 使用服务默认，最多 128）').fill('64');
  await page.getByRole('button',{name:'保存配置',exact:true}).click();
  await expect.poll(()=>requests.find(r=>r.path.endsWith('/settings') && r.method==='PUT')?.body.model_thinking).toBe(false);
  expect(requests.find(r=>r.path.endsWith('/settings') && r.method==='PUT').body.video_num_frames).toBe(64);
});


test('admin sidebar opens inline plugin management and preserves unsaved settings',async({page})=>{
 const requests=await boot(page,{manage:true});
 await expect(page.locator('#native-manage-content')).toBeVisible();
 await page.locator('.ai-manage-link').click();
 await expect(page.locator('#ai-manage-panel')).toBeVisible();
 await expect(page).toHaveTitle('AI 视频标签 | OpenList 管理');
 await expect(page.getByRole('dialog')).toHaveCount(0);
 await expect(page.locator('#native-manage-content')).toBeHidden();
 await page.getByLabel('扫描目录（每行一个）').fill('/OneDrive/电影');
 await page.waitForTimeout(8500);
 await expect(page.getByLabel('扫描目录（每行一个）')).toHaveValue('/OneDrive/电影');
 await page.getByRole('button',{name:'保存配置',exact:true}).click();
 await expect.poll(()=>requests.find(r=>r.path.endsWith('/settings') && r.method==='PUT')?.body.roots).toEqual(['/OneDrive/电影']);
 await page.getByRole('button',{name:'识别任务',exact:true}).click();
 await expect(page.locator('#ai-manage-view')).toContainText('尚无扫描任务');
 await page.getByRole('button',{name:'标签规则',exact:true}).click();
 await page.getByLabel('同义标签').fill('动画片=动画');
 await page.getByRole('button',{name:'保存',exact:true}).click();
 await expect.poll(()=>requests.find(r=>r.path.endsWith('/tags') && r.method==='PUT')?.body.aliases).toEqual([{alias:'动画片',canonical:'动画'}]);
 await page.getByRole('button',{name:'历史与错误日志',exact:true}).click();
 await expect.poll(()=>requests.some(r=>r.path.endsWith('/history'))).toBeTruthy();
 await page.evaluate(()=>document.querySelector('a[href="/@manage"]').addEventListener('click',e=>{e.preventDefault();window.history.pushState({},'', '/@manage');}));
 await page.getByRole('link',{name:'个人资料',exact:true}).click();
 await expect(page.locator('#ai-manage-panel')).toHaveCount(0);
 await expect(page.locator('#native-manage-content')).toBeVisible();
 await page.locator('.ai-manage-link').click();
 await expect(page.locator('#ai-manage-panel')).toBeVisible();
 await page.getByRole('link',{name:'存储',exact:true}).click();
 await expect(page.locator('#native-manage-content')).toBeVisible();
 await expect(page.locator('#ai-manage-panel')).toHaveCount(0);
});

test('mobile management supports direct refresh and browser back without overflow',async({page})=>{
 await page.setViewportSize({width:390,height:844});
 await boot(page,{manage:true,start:'/@manage?ai=video-tags&view=tags'});
 await expect(page.locator('#ai-manage-panel')).toBeVisible();
 await expect(page.locator('#ai-manage-shortcut')).toBeVisible();
 await expect(page.getByLabel('常用标签')).toHaveValue('家庭');
 await page.reload();
 await expect(page.getByLabel('常用标签')).toHaveValue('家庭');
 await page.getByRole('button',{name:'模型与扫描配置',exact:true}).click();
 await expect(page.getByLabel('模型服务基础地址')).toBeVisible();
 await page.goBack();
 await expect(page.getByLabel('常用标签')).toBeVisible();
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
});

test('ordinary account cannot expose admin options through management query',async({page})=>{
 const requests=await boot(page,{admin:false,manage:true,start:'/@manage?ai=video-tags'});
 await page.waitForTimeout(800);
 await expect(page.locator('#ai-manage-panel,.ai-manage-link,#ai-manage-shortcut')).toHaveCount(0);
 await expect(page.locator('#native-manage-content')).toBeVisible();
 expect(requests.some(r=>r.path.endsWith('/settings'))).toBeFalsy();
});


test('management closes and clears private form on session change',async({page})=>{
 await boot(page,{manage:true,start:'/@manage?ai=video-tags'});
 await page.getByLabel('新模型密钥').fill('test-unsaved-key');
 await page.route('**/ai/api/me',route=>route.fulfill({json:{admin:false,username:'guest'}}));
 await page.evaluate(()=>{localStorage.setItem('token','guest');window.dispatchEvent(new StorageEvent('storage',{key:'token'}));});
 await expect(page.locator('#ai-manage-panel,.ai-manage-link,#ai-manage-shortcut')).toHaveCount(0);
 await expect(page.locator('#native-manage-content')).toBeVisible();
});


test('mobile native drawer entry closes drawer and opens inline settings',async({page})=>{
 await page.setViewportSize({width:390,height:844});
 await boot(page,{manage:true});
 await page.evaluate(()=>{
  const drawer=document.createElement('section');drawer.className='hope-drawer__content';drawer.setAttribute('role','dialog');
  const close=document.createElement('button');close.className='hope-modal__close-button';close.textContent='关闭菜单';close.onclick=()=>drawer.remove();
  const nav=document.createElement('nav');nav.innerHTML='<a href="/@manage">个人资料</a><a href="/@manage/about">关于</a>';
  drawer.append(close,nav);document.body.append(drawer);
 });
 await page.locator('.hope-drawer__content .ai-manage-link').click();
 await expect(page.getByRole('dialog')).toHaveCount(0);
 await expect(page.getByLabel('模型服务基础地址')).toBeVisible();
});


test('native search matches content, deduplicates filename rows and preserves folder scope',async({page})=>{
 const requests=await boot(page,{nativeRows:[{parent:'/videos',name:'clip.mp4',is_dir:false,size:100}]});
 await page.keyboard.press('Control+k');
 await page.locator('#search-input').fill('城市');await page.locator('#search-input').press('Enter');
 await expect(page.locator('#native-file-results>a')).toHaveCount(1);
 await expect(page.locator('.ai-native-note')).toContainText('夜晚的城市街景');
 await expect(page.locator('.ai-native-result')).toHaveCount(0);
 expect(requests.find(r=>r.path==='/api/fs/search').body.keywords).toBe('城市');
 await page.getByLabel('原生搜索范围').selectOption('1');
 await page.locator('#search-input').press('Enter');
 await expect(page.locator('#ai-native-search-results')).toContainText('文件夹范围不检索视频内容');
 await expect(page.locator('.ai-native-note')).toHaveCount(0);
 await page.locator('.ai-badges').getByRole('button',{name:'已识别',exact:true}).click();
  await page.locator('#ai-hover-card').getByRole('button',{name:'旅行',exact:true}).click();
 await expect(page.getByLabel('原生搜索范围')).toHaveValue('2');
 await expect(page.locator('.ai-native-note')).toContainText('夜晚的城市街景');
});

test('AI search failure leaves native filename search usable',async({page})=>{
 await boot(page,{nativeRows:[{parent:'/videos',name:'clip.mp4',is_dir:false,size:100}]});
 await page.route('**/ai/api/native-search',route=>route.fulfill({status:503,json:{detail:'AI offline'}}));
 await page.keyboard.press('Control+k');await page.locator('#search-input').fill('城市');await page.locator('#search-input').press('Enter');
 await expect(page.locator('#native-file-results>a')).toContainText('clip.mp4');
 await expect(page.locator('#ai-native-search-results')).toContainText('文件名搜索仍可使用');
});

test('native XMLHttpRequest body and response remain unchanged',async({page})=>{
 const requests=await boot(page);
 await page.keyboard.press('Control+k');await page.locator('#search-input').fill('#旅行 #城市');
 await page.evaluate(()=>{const x=new XMLHttpRequest();x.open('POST','/api/fs/search');x.setRequestHeader('Content-Type','application/json');x.onload=()=>{window.nativeSearchResponse=JSON.parse(x.responseText);};x.send(JSON.stringify({parent:'/videos',keywords:'#旅行 #城市',scope:2,password:'',page:1,per_page:100}));});
 await expect(page.locator('#ai-native-search-results')).toContainText('夜晚的城市街景');
 await expect.poll(()=>page.evaluate(()=>window.nativeSearchResponse?.code)).toBe(200);
 expect(await page.evaluate(()=>window.nativeSearchResponse.data.total)).toBe(0);
 expect(requests.find(r=>r.path.endsWith('/native-search')).body).toMatchObject({parent:'/videos',keywords:'#旅行 #城市',scope:2});
});


test('native query changes never display an older AI response',async({page})=>{
 await boot(page);let release,oldStarted=false;
 await page.route('**/ai/api/native-search',async route=>{
  const q=route.request().postDataJSON().keywords;
  if(q==='旧查询'){oldStarted=true;await new Promise(resolve=>release=resolve);}
  await route.fulfill({json:{items:[{...video,result:{...video.result,summary:q==='旧查询'?'旧结果':'新结果'}}],next_cursor:null}}).catch(()=>{});
 });
 await page.keyboard.press('Control+k');await page.locator('#search-input').fill('旧查询');await page.locator('#search-input').press('Enter');
 await expect.poll(()=>oldStarted).toBe(true);
 await page.locator('#search-input').fill('新查询');await page.locator('#search-input').press('Enter');
 await expect(page.locator('#ai-native-search-results')).toContainText('新结果');
 release();await page.waitForTimeout(100);
 await expect(page.locator('#ai-native-search-results')).not.toContainText('旧结果');
});

for(const layout of ['list','grid','image'])test(`${layout} view floats AI information without growing file rows`,async({page})=>{
 await boot(page,{grid:layout!=='list'});
 const row=page.locator('.viselect-item').first(),before=await row.evaluate(n=>n.getBoundingClientRect().height);
 await row.hover();
 await expect(page.locator('#ai-hover-card')).toContainText('夜晚的城市街景');
 await expect(page.locator('#ai-hover-card .ai-tag')).toHaveCount(2);
 expect(await row.evaluate(n=>n.getBoundingClientRect().height)).toBe(before);
 await expect(row.locator('.ai-tag')).toHaveCount(0);
 await page.keyboard.press('Escape');await expect(page.locator('#ai-hover-card')).toHaveCount(0);
 await row.locator('.ai-status').focus();await expect(page.locator('#ai-hover-card')).toBeVisible();
 await page.keyboard.press('Escape');
 await page.setViewportSize({width:390,height:400});
 await row.locator('.ai-status').dispatchEvent('pointerenter',{pointerType:'touch'});
 await expect(page.locator('#ai-hover-card')).toHaveCount(0);
 await row.locator('.ai-status').click();
 const bounds=await page.locator('#ai-hover-card').boundingBox();
 expect(bounds.x).toBeGreaterThanOrEqual(0);expect(bounds.x+bounds.width).toBeLessThanOrEqual(390);
 expect(bounds.y).toBeGreaterThanOrEqual(0);expect(bounds.y+bounds.height).toBeLessThanOrEqual(400);
});

test('first visit selects native card layout once and respects later choices',async({page})=>{
 await boot(page);
 await page.evaluate(()=>{
  const b=document.createElement('button');b.setAttribute('aria-label','switch layout');document.body.append(b);
  b.onclick=()=>{['list','grid','image'].forEach(layout=>{const item=document.createElement('button');item.setAttribute('role','menuitem');item.textContent=layout;item.onclick=()=>{localStorage.setItem('fixture-layout',layout);document.querySelectorAll('[role="menuitem"]').forEach(x=>x.remove());};document.body.append(item);});};
 });
 await expect.poll(()=>page.evaluate(()=>localStorage.getItem('fixture-layout'))).toBe('grid');
 expect(await page.evaluate(()=>localStorage.getItem('global_default_layout'))).toBe('grid');
 await page.evaluate(()=>{localStorage.setItem('fixture-layout','list');document.body.append(document.createElement('p'));});
 await page.waitForTimeout(600);
 expect(await page.evaluate(()=>localStorage.getItem('fixture-layout'))).toBe('list');
 await expect(page.getByRole('menuitem')).toHaveCount(0);
});
test('native image view adds video cards from the existing directory response',async({page})=>{
 await boot(page);
 await page.route('**/api/fs/list',r=>r.fulfill({json:{code:200,data:{content:[{name:'clip.mp4',is_dir:false},{name:'notes.txt',is_dir:false}]}}}));
 await page.evaluate(async()=>{
  await fetch('/api/fs/list',{method:'POST',body:JSON.stringify({path:'/videos'})});
  document.querySelector('.viselect-container').innerHTML='<div class="image-folders"></div><h2>没有图片</h2>';
 });
 await expect(page.locator('#ai-image-videos .grid-item')).toHaveCount(1);
 await expect(page.locator('#ai-image-videos .ai-status')).toBeVisible();
 await page.locator('#ai-image-videos .grid-item').hover();
 await expect(page.locator('#ai-hover-card')).toContainText('夜晚的城市街景');
 await expect(page.locator('#ai-image-videos a')).toHaveAttribute('href','/videos/clip.mp4');
 await page.evaluate(()=>{localStorage.setItem('token','other');window.dispatchEvent(new StorageEvent('storage',{key:'token'}));});
 await expect(page.locator('#ai-hover-card')).toHaveCount(0);
});
