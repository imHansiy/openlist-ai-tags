"""Install/remove only our customize_body marker after routing /ai to this service."""
import argparse
import re
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from aitags.openlist import OpenList

p=argparse.ArgumentParser(description='安装或卸载 OpenList AI 原界面脚本；无需修改源码')
p.add_argument('action',choices=['install','uninstall'])
a=p.parse_args()
begin='<!-- openlist-ai-tags:begin -->'
end='<!-- openlist-ai-tags:end -->'
ol=OpenList()
try:
    token=ol.admin_token()
    if ol.me(token).get('role')!=2:raise RuntimeError('需要管理员权限')
    if a.action=='install':
        health=ol.client.get(ol.url+'/ai/health')
        if health.status_code!=200 or health.json().get('status')!='ok':
            raise RuntimeError('请先在 OpenList 域名下配置 /ai/ 反向代理，健康检查必须通过')
    rows=ol.call('GET','admin/setting/list',token)
    setting=next(x for x in rows if x['key']=='customize_body')
    current=setting['value']
    value=re.sub(re.escape(begin)+r'.*?'+re.escape(end),'',current,flags=re.S).rstrip()
    if a.action=='install':
        value+='\n'+begin+'\n<script defer src="/ai/assets/ai.js"></script>\n'+end
    if value==current:
        print('配置已符合要求，无需修改')
    else:
        ol.call('POST','admin/setting/save',token,[{**setting,'value':value}])
        verified=ol.call('GET','admin/setting/list',token)
        if next(x['value'] for x in verified if x['key']=='customize_body')!=value:
            raise RuntimeError('写入后回读校验失败，请检查 OpenList 配置')
        print('已安装并回读验证' if a.action=='install' else '已卸载并回读验证')
finally:
    ol.close()
