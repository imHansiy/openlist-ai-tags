import json
from .conftest import add_video


def set_result(db,path,summary,tags):
    db.execute("UPDATE videos SET result=? WHERE path=?",(json.dumps({'summary':summary,'tags':tags},ensure_ascii=False),path))


def test_native_query_uses_same_directory_scope_and_all_words(env):
    db,ol,worker,c=env
    for p in ('/public/a.mp4','/secret/b.mp4'):
        add_video(db,worker,p,ol)
        set_result(db,p,'母亲曾经是大学生',['亲情','动画'])
    r=c.post('/ai/api/native-search',headers={'Authorization':'admin'},json={'parent':'/public','keywords':'母亲 大学生','scope':2})
    assert r.status_code==200 and [x['path'] for x in r.json()['items']]==['/public/a.mp4']
    assert c.post('/ai/api/native-search',headers={'Authorization':'admin'},json={'parent':'/public','keywords':'母亲 大学生','scope':1}).json()['items']==[]
    assert c.post('/ai/api/native-search',headers={'Authorization':'admin'},json={'parent':'/public','keywords':'母亲 游戏'}).json()['items']==[]


def test_native_query_permissions_password_and_user_base_path(env):
    db,ol,worker,c=env
    for p in ('/public/a.mp4','/secret/b.mp4'):
        add_video(db,worker,p,ol)
        set_result(db,p,'乡村生活',['亲情'])
    limited=c.post('/ai/api/native-search',headers={'Authorization':'limited'},json={'parent':'/','keywords':'亲情'}).json()
    assert [x['path'] for x in limited['items']]==['/a.mp4']
    assert c.post('/ai/api/native-search',json={'parent':'/secret','keywords':'亲情'}).json()['items']==[]
    unlocked=c.post('/ai/api/native-search',json={'parent':'/secret','keywords':'亲情','password':'unlock'}).json()
    assert [x['path'] for x in unlocked['items']]==['/secret/b.mp4']
    assert c.post('/ai/api/native-search',headers={'Authorization':'limited'},json={'parent':'/../secret','keywords':'亲情'}).status_code==400


def test_native_tags_aliases_and_changed_file_never_return_old_description(env):
    db,ol,worker,c=env
    p='/public/a.mp4';add_video(db,worker,p,ol)
    set_result(db,p,'学生时期打工',['动画','亲情'])
    db.execute('INSERT INTO aliases(alias,canonical) VALUES (?,?)',('动画片','动画'))
    body={'parent':'/public','keywords':'标签：动画片 #亲情 学生'}
    assert len(c.post('/ai/api/native-search',json=body).json()['items'])==1
    assert len(c.post('/ai/api/native-search',json={'parent':'/public','keywords':'动画片 学生'}).json()['items'])==1
    ol.objects[p]['size']+=1
    assert c.post('/ai/api/native-search',json=body).json()['items']==[]


def test_native_directory_prefix_is_segment_bounded_and_parameters_are_limited(env):
    db,ol,worker,c=env
    ol.objects['/publicity/c.mp4']={**ol.objects['/public/a.mp4'],'name':'c.mp4'}
    add_video(db,worker,'/publicity/c.mp4',ol)
    set_result(db,'/publicity/c.mp4','旅行',['日本'])
    assert c.post('/ai/api/native-search',json={'parent':'/public','keywords':'日本'}).json()['items']==[]
    assert c.post('/ai/api/native-search',json={'keywords':'x'*201}).status_code==422
    assert c.post('/ai/api/native-search',json={'keywords':'日本','scope':3}).status_code==422


def test_native_quoted_tags_and_manual_hidden_tags(env):
    db,ol,worker,c=env
    p='/public/a.mp4';add_video(db,worker,p,ol)
    set_result(db,p,'真实录屏',['screen recording','教程'])
    assert c.post('/ai/api/native-search',json={'keywords':'#"screen recording"'}).json()['items']
    db.execute('UPDATE videos SET removed=? WHERE path=?',(json.dumps(['screen recording']),p))
    assert not c.post('/ai/api/native-search',json={'keywords':'#"screen recording"'}).json()['items']
