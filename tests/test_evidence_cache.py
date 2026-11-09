import os
import time
from aitags.evidence_cache import EvidenceCache


def test_cache_identity_expiry_and_limits(tmp_path,monkeypatch):
    cache=EvidenceCache(tmp_path)
    settings={'context_frames':5}
    key=cache.path('/movie.mp4','first',True,settings)
    sample={'video':'AAAA','video_bytes':3,'duration':10,'network_bytes':50}
    cache.save(key,sample)
    hit=cache.load(key)
    assert hit['evidence_cache_hit'] and hit['network_bytes']==0 and hit['cached_network_bytes']==50
    assert cache.load(cache.path('/movie.mp4','changed',True,settings)) is None
    assert cache.load(cache.path('/movie.mp4','first',False,settings)) is None
    assert cache.load(cache.path('/movie.mp4','first',True,{'context_frames':0})) is None
    os.utime(key,(time.time()-90000,time.time()-90000))
    assert cache.load(key) is None and not key.exists()
    for i in range(10):
        cache.save(cache.path('/movie.mp4',str(i),True,settings),sample)
    assert len(list(tmp_path.glob('*.json')))<=8
    monkeypatch.setattr('aitags.config.EVIDENCE_CACHE_MAX_BYTES',250)
    cache.prune()
    assert sum(p.stat().st_size for p in tmp_path.glob('*.json'))<=250
    key.write_text('corrupt',encoding='utf-8')
    assert cache.load(key) is None


def test_worker_reuses_only_current_file_evidence(env,monkeypatch):
    db,ol,worker,_=env
    prepared=[]
    samples=[]
    def prepare(*args,**kwargs):
        prepared.append(1)
        return {'video':'AAAA','video_bytes':3,'duration':1,'network_bytes':50}
    def infer(sample,settings):
        samples.append(sample)
        return {'summary':'视频内容','tags':['真实画面']}
    monkeypatch.setattr('aitags.worker.compress_video',prepare)
    monkeypatch.setattr('aitags.worker.infer',infer)
    for iteration in range(3):
        if iteration==2:
            ol.objects['/public/a.mp4']['size']+=1
        rid=worker.create_run('/')
        assert worker.enqueue('/public/a.mp4',ol.objects['/public/a.mp4'],rid,force=True)
        assert worker.work_once()
        db.execute("UPDATE directories SET state='done'")
        db.execute("UPDATE runs SET state='done'")
    assert len(prepared)==2
    assert samples[1]['evidence_cache_hit'] and not samples[2].get('evidence_cache_hit')


def test_cached_movie_upgrades_images_without_decoding_or_ocr(env,monkeypatch,tmp_path):
    from aitags.worker import fingerprint
    db,ol,worker,client=env
    monkeypatch.setattr('aitags.config.DATA',tmp_path)
    p='/public/a.mp4'
    sample={'video':'AAAA','video_bytes':3,'duration':10,'network_bytes':50,
            'subtitles':{'source':'text-track','cues':[{'start':1,'end':2,'text':'我的名字叫小林'}]}}
    key=worker.evidence_cache.path(p,fingerprint(ol.objects[p]),True,db.settings())
    worker.evidence_cache.save(key,sample)
    def refresh(old,*args):
        assert old['video']==sample['video'] and old['subtitles']==sample['subtitles']
        return {**old,'context_revision':3,'context_frames':[],'network_bytes':7}
    def no_decode(*args,**kwargs):
        raise AssertionError('Full video must not be decoded')
    seen=[]
    monkeypatch.setattr('aitags.worker.refresh_context_frames',refresh)
    monkeypatch.setattr('aitags.worker.compress_video',no_decode)
    monkeypatch.setattr('aitags.worker.infer',lambda s,settings:seen.append(s) or {'summary':'主线','tags':['家庭']})
    r=client.post('/ai/api/recognize',headers={'Authorization':'admin'},
                  json={'paths':[p],'content_type':'movie','use_subtitles':True})
    assert r.status_code==200 and worker.work_once()
    assert seen[0]['context_revision']==3 and seen[0]['network_bytes']==7
    assert worker.evidence_cache.load(key)['context_revision']==3
