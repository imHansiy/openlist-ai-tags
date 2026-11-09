import os
os.environ['AI_PROXY_ENABLED']='false'
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from aitags.db import Database
from aitags.app import create_app


class FakeOpenList:
    url='https://files.example.test'
    def __init__(self):
        self.objects={'/public/a.mp4':{'name':'a.mp4','is_dir':False,'size':100,'modified':'2026-11-01','hash_info':{},'hashinfo':'','raw_url':'https://media.example.test/a.mp4'},
                      '/secret/b.mp4':{'name':'b.mp4','is_dir':False,'size':200,'modified':'2026-11-01','raw_url':'https://media.example.test/b.mp4'},
                      '/public':{'name':'public','is_dir':True},'/':{'name':'','is_dir':True}}
        self.calls=[]
    def me(self,token):
        if token=='bad':raise HTTPException(401,'expired')
        return {'role':2 if token=='admin' else 0,'base_path':'/public' if token=='limited' else '/','username':token or 'guest'}
    def admin_token(self):return 'admin'
    def get(self,path,token,password=''):
        self.calls.append((path,token,password))
        actual=('/public'+path) if token=='limited' else path
        if actual.startswith('/secret') and token!='admin' and password!='unlock':raise HTTPException(403,'denied')
        if actual not in self.objects:raise HTTPException(404,'missing')
        return self.objects[actual].copy()
    def listing(self,path,token,page=1,size=200,password=''):
        import posixpath
        values=[v.copy() for k,v in self.objects.items() if k!=path and posixpath.dirname(k)==path]
        return {'content':values[(page-1)*size:page*size],'total':len(values)}
    def close(self):pass


@pytest.fixture
def env(tmp_path):
    db=Database(tmp_path/'db.sqlite3');ol=FakeOpenList();app=create_app(db,ol,False)
    with TestClient(app) as client:
        yield db,ol,app.state.worker,client


def add_video(db,worker,path,ol,tags=None):
    import json
    rid=worker.create_run('/')
    worker.enqueue(path,ol.objects[path],rid)
    db.execute("UPDATE videos SET status='done',result=? WHERE path=?",(json.dumps({'summary':'真实画面简介','tags':tags or ['旅行','城市']}),path))
    db.execute("UPDATE tasks SET state='done' WHERE path=?",(path,))
    return rid
