import json
import sqlite3
from .conftest import add_video

ADMIN={'Authorization':'admin'}

def test_permissions_and_base_path(env):
    db,ol,w,c=env
    add_video(db,w,'/public/a.mp4',ol)
    add_video(db,w,'/secret/b.mp4',ol,['机密'])
    assert len(c.get('/ai/api/search').json()['items'])==1
    result=c.get('/ai/api/search',headers={'Authorization':'limited'}).json()
    assert [x['path'] for x in result['items']]==['/a.mp4']
    assert c.get('/ai/api/search?tags=机密').json()['items']==[]
    assert c.get('/ai/api/search',headers={'Authorization':'bad'}).status_code==401
    for path in ('settings','jobs','history','tags'):
        assert c.get('/ai/api/'+path).status_code==403
    assert c.post('/ai/api/scan',json={'paths':['/']}).status_code==403
    assert c.post('/ai/api/recognize',json={'paths':['/public/a.mp4']}).status_code==403
    assert c.post('/ai/api/backup').status_code==403

def test_batch_requires_fresh_permission(env):
    db,ol,w,c=env
    add_video(db,w,'/secret/b.mp4',ol)
    payload={'paths':['/secret/b.mp4']}
    assert c.post('/ai/api/videos/batch',json=payload).json()==[]
    payload['password']='unlock'
    assert len(c.post('/ai/api/videos/batch',json=payload).json())==1
    del ol.objects['/secret/b.mp4']
    assert c.post('/ai/api/videos/batch',json=payload,headers=ADMIN).json()==[]

def test_manual_labels_and_aliases(env):
    db,ol,w,c=env
    add_video(db,w,'/public/a.mp4',ol)
    body={'path':'/public/a.mp4','manual_tags':['日本','日本'],'removed':['城市']}
    assert c.post('/ai/api/videos/edit',json=body).status_code==403
    r=c.post('/ai/api/videos/edit',json=body,headers=ADMIN)
    assert r.status_code==200 and r.json()['tags']==['旅行','日本']
    r=c.put('/ai/api/tags',headers=ADMIN,json={'aliases':[{'alias':'旅行','canonical':'旅游'}],'favorites':['旅游']})
    assert r.status_code==200
    r=c.get('/ai/api/search?tags=旅游,日本').json()
    assert len(r['items'])==1
    r=c.put('/ai/api/tags',headers=ADMIN,json={'aliases':[{'alias':'甲','canonical':'乙'},{'alias':'乙','canonical':'甲'}]})
    assert r.status_code==400

def test_settings_validation_and_no_secrets(env):
    db,ol,w,c=env
    r=c.get('/ai/api/settings',headers=ADMIN)
    assert 'api_key' not in r.text and 'password' not in r.text
    settings=r.json()['settings'];settings['concurrency']=99
    assert c.put('/ai/api/settings',headers=ADMIN,json=settings).status_code==422
    settings['concurrency']=2;settings['roots']=['/../secret']
    assert c.put('/ai/api/settings',headers=ADMIN,json=settings).status_code==400
    settings['roots']=['/public'];settings['model_url']='http://user:secret@host/v1'
    assert c.put('/ai/api/settings',headers=ADMIN,json=settings).status_code==400

def test_backup_is_valid_sqlite(env,tmp_path):
    db,ol,w,c=env
    add_video(db,w,'/public/a.mp4',ol)
    r=c.post('/ai/api/backup',headers=ADMIN)
    assert r.status_code==200
    path=tmp_path/'copy.sqlite3';path.write_bytes(r.content)
    with sqlite3.connect(path) as backup:
        assert backup.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        assert backup.execute('SELECT count(*) FROM videos').fetchone()[0]==1

def test_traversal_and_limits(env):
    *_,c=env
    assert c.post('/ai/api/videos/batch',json={'paths':['/../secret']}).status_code==400
    assert c.get('/ai/api/search?limit=10000').status_code==400
    assert c.post('/ai/api/scan',headers=ADMIN,json={'paths':['/public/a.mp4']}).status_code==400
    assert c.post('/ai/api/videos/batch',json={'paths':['/x']*201}).status_code==422

def test_search_pagination_never_returns_protected(env):
    db,ol,w,c=env
    for i in range(35):
        path=f'/secret/{i}.mp4';ol.objects[path]=dict(ol.objects['/secret/b.mp4']);add_video(db,w,path,ol)
    add_video(db,w,'/public/a.mp4',ol)
    r=c.get('/ai/api/search?limit=1').json()
    assert [x['path'] for x in r['items']]==['/public/a.mp4']
    assert 'total' not in r


def test_secret_write_only(env,tmp_path,monkeypatch):
    from aitags import config
    *_,c=env
    monkeypatch.setattr(config,'DATA',tmp_path)
    monkeypatch.setattr(config,'MODEL_KEY','')
    value='test-secret-do-not-return'
    assert c.put('/ai/api/model/key',json={'key':value}).status_code==403
    r=c.put('/ai/api/model/key',json={'key':value},headers=ADMIN)
    assert r.json()=={'configured':True}
    assert value not in c.get('/ai/api/settings',headers=ADMIN).text
    assert config.MODEL_KEY==value
    assert json.loads((tmp_path/'model-secret.json').read_text())=={'key':value}


def test_stale_results_not_exposed_as_current(env):
    db,ol,w,c=env
    add_video(db,w,'/public/a.mp4',ol)
    ol.objects['/public/a.mp4']['size']=101
    r=c.post('/ai/api/videos/batch',json={'paths':['/public/a.mp4']}).json()[0]
    assert r['status']=='pending' and r['tags']==[] and r['result']=={}
    assert c.get('/ai/api/search?tags=旅行').json()['items']==[]
def test_movie_recognition_persists_context(env):
    db,ol,w,c=env
    r=c.post('/ai/api/recognize',headers=ADMIN,json={'paths':['/public/a.mp4'],'content_type':'movie'})
    assert r.status_code==200
    rid=r.json()['ids'][0]
    assert db.one('SELECT content_type FROM runs WHERE id=?',(rid,))['content_type']=='movie'
    assert c.post('/ai/api/recognize',headers=ADMIN,json={
        'paths':['/public/a.mp4'],'content_type':'invalid'}).status_code==422
