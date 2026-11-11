from aitags.db import Database
from aitags.worker import identity
from .conftest import add_video
import pytest


def test_scan_pagination_incremental_and_exclusion(env):
    db,ol,w,c=env
    db.save_settings({'page_size':1,'exclude':['/secret']})
    rid=w.create_run('/')
    assert w.create_run('/')==rid
    for _ in range(8):w.scan_once()
    assert db.one('SELECT count(*) n FROM tasks')['n']==1
    assert db.one('SELECT path FROM tasks')['path']=='/public/a.mp4'
    assert not w.scan_once()
    db.execute("UPDATE videos SET status='done'")
    db.execute("UPDATE tasks SET state='done'")
    w.finish_runs()
    w.create_run('/')
    for _ in range(8):w.scan_once()
    assert db.one('SELECT count(*) n FROM tasks')['n']==1

def test_restart_recovers_running_and_preserves_pause(env,tmp_path):
    db,ol,w,c=env
    rid=w.create_run('/');w.enqueue('/public/a.mp4',ol.objects['/public/a.mp4'],rid)
    db.execute("UPDATE tasks SET state='running'")
    db.execute("UPDATE directories SET state='running'")
    w.control(rid,'pause')
    restarted=Database(db.path)
    restarted.recover()
    assert restarted.one('SELECT state FROM tasks')['state']=='queued'
    assert restarted.one('SELECT state FROM directories')['state']=='queued'
    assert restarted.one('SELECT state FROM runs')['state']=='paused'
    assert not w.work_once()
    w.control(rid,'resume')
    assert db.one('SELECT state FROM runs')['state']=='running'

def test_reidentify_preserves_manual_and_handles_change(env,monkeypatch):
    db,ol,w,c=env
    add_video(db,w,'/public/a.mp4',ol)
    db.execute("UPDATE videos SET manual='[\"人工\"]',removed='[\"城市\"]' WHERE path='/public/a.mp4'")
    w.finish_runs()
    db.execute("UPDATE directories SET state='done'")
    db.execute("UPDATE runs SET state='done'")
    rid2=w.create_run('/')
    assert w.enqueue('/public/a.mp4',ol.objects['/public/a.mp4'],rid2,True)
    monkeypatch.setattr('aitags.worker.compress_video',lambda *a,**kw:{'frames':[]})
    monkeypatch.setattr('aitags.worker.infer',lambda *a,**kw:{'summary':'画面内容','tags':['城市','旅行']})
    w.work_once()
    row=db.public_video(db.one("SELECT * FROM videos WHERE path='/public/a.mp4'"))
    assert row['status']=='done' and row['tags']==['旅行','人工']
    ol.objects['/public/a.mp4']['size']=111
    db.execute("UPDATE tasks SET state='done'")
    db.execute("UPDATE runs SET state='done'")
    rid3=w.create_run('/')
    assert w.enqueue('/public/a.mp4',ol.objects['/public/a.mp4'],rid3)

def test_cancel_and_retry(env,monkeypatch):
    db,ol,w,c=env
    rid=w.create_run('/');w.enqueue('/public/a.mp4',ol.objects['/public/a.mp4'],rid)
    monkeypatch.setattr('aitags.worker.compress_video',lambda *a,**kw:(_ for _ in ()).throw(RuntimeError('decode failed')))
    w.work_once();db.execute("UPDATE directories SET state='done'");w.finish_runs()
    assert db.one('SELECT state FROM runs')['state']=='failed'
    w.control(rid,'retry')
    assert db.one('SELECT state FROM tasks')['state']=='queued'
    w.control(rid,'cancel')
    assert db.one('SELECT state FROM tasks')['state']=='cancelled'
    assert not w.work_once()

def test_cancel_during_inference_does_not_commit(env,monkeypatch):
    db,ol,w,c=env
    rid=w.create_run('/');w.enqueue('/public/a.mp4',ol.objects['/public/a.mp4'],rid)
    monkeypatch.setattr('aitags.worker.compress_video',lambda *a,**kw:{})
    def cancel(*args):
        w.control(rid,'cancel');return {'summary':'不得提交','tags':['错误']}
    monkeypatch.setattr('aitags.worker.infer',cancel)
    w.work_once()
    assert db.one('SELECT state FROM tasks')['state']=='cancelled'
    assert db.one('SELECT result FROM videos')['result']=='{}'

def test_move_reuse_requires_strong_hash(env):
    db,ol,w,c=env
    obj=ol.objects['/public/a.mp4'];obj['hash_info']={'sha1':'a'*40}
    add_video(db,w,'/public/a.mp4',ol)
    rid=w.create_run('/')
    assert not w.enqueue('/public/renamed.mp4',obj,rid)
    assert db.one("SELECT status FROM videos WHERE path='/public/renamed.mp4'")['status']=='done'
    assert identity({'size':100,'modified':'x'})==''

def test_changed_during_inference_rejected(env,monkeypatch):
    db,ol,w,c=env
    rid=w.create_run('/');w.enqueue('/public/a.mp4',ol.objects['/public/a.mp4'],rid)
    monkeypatch.setattr('aitags.worker.compress_video',lambda *a,**kw:{})
    def change(*args):
        ol.objects['/public/a.mp4']['size']=123;return {'summary':'旧内容','tags':[]}
    monkeypatch.setattr('aitags.worker.infer',change)
    w.work_once()
    assert db.one('SELECT state FROM tasks')['state']=='failed'
    assert db.one('SELECT result FROM videos')['result']=='{}'


def test_single_worker_lock(tmp_path):
    from aitags.lock import WorkerLock
    first=WorkerLock(tmp_path/'worker.lock')
    try:
        with pytest.raises(RuntimeError):WorkerLock(tmp_path/'worker.lock')
    finally:first.close()
    WorkerLock(tmp_path/'worker.lock').close()
