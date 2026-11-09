import hashlib
import json
import posixpath
import threading
import time
from pathlib import Path
from fastapi import HTTPException
from . import config
from .openlist import clean_path
from .media import compress_video, sample_frames, refresh_context_frames
from .model import infer
from .subtitles import save_subtitles
from .evidence_cache import EvidenceCache
from .lock import WorkerLock


def fingerprint(obj):
    value = {k: obj.get(k) for k in ('size','modified','hash_info','hashinfo')}
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def identity(obj):
    # Only strong full-file hashes allow safe reuse across rename/copy.
    hashes = obj.get('hash_info') or {}
    strong = {k.lower():v for k,v in hashes.items() if k.lower() in ('sha1','sha256','md5') and v}
    return json.dumps({'size':obj.get('size'), 'hashes':strong}, sort_keys=True) if strong else ''


def safe_error(exc):
    if isinstance(exc, HTTPException):
        return str(exc.detail)[:500]
    # Our own errors have no signed URLs or credentials. Third-party errors are not persisted.
    if isinstance(exc, RuntimeError):
        return str(exc)[:500]
    return '处理失败：' + type(exc).__name__


class Worker:
    def __init__(self, db, ol):
        self.db, self.ol = db, ol
        self.evidence_cache = EvidenceCache(Path(db.path).parent/'evidence-cache')
        self.stop = threading.Event()
        self.threads = []

    def start(self):
        self.process_lock=WorkerLock(self.db.path+'.worker.lock')
        self.db.recover()
        for fn, args in [(self.scan_loop, ()), *[(self.work_loop,(i,)) for i in range(4)]]:
            t = threading.Thread(target=fn, args=args, daemon=True)
            t.start()
            self.threads.append(t)

    def close(self):
        self.stop.set()
        for t in self.threads:
            t.join(timeout=20)
        if hasattr(self,'process_lock') and not any(t.is_alive() for t in self.threads):
            self.process_lock.close()

    def create_run(self, root):
        root = clean_path(root)
        with self.db.connect() as c:
            existing = c.execute("SELECT id FROM runs WHERE root=? AND state IN ('running','paused')", (root,)).fetchone()
            if existing:
                return existing['id']
            rid = c.execute('INSERT INTO runs(root,created) VALUES (?,?)', (root,time.time())).lastrowid
            c.execute('INSERT INTO directories(run_id,path) VALUES (?,?)', (rid,root))
            return rid

    def enqueue(self, path, obj, rid, force=False):
        fp, ident = fingerprint(obj), identity(obj)
        now = time.time()
        with self.db.connect() as c:
            old = c.execute('SELECT * FROM videos WHERE path=?', (path,)).fetchone()
            if old and old['fingerprint'] == fp and old['status'] == 'done' and not force:
                return False
            if c.execute("SELECT id FROM tasks WHERE path=? AND state IN ('queued','running')", (path,)).fetchone():
                return False
            reuse = c.execute("SELECT * FROM videos WHERE identity=? AND status='done' LIMIT 1", (ident,)).fetchone() if ident and not old else None
            c.execute('''INSERT INTO videos(path,fingerprint,identity,size,modified,updated) VALUES (?,?,?,?,?,?)
              ON CONFLICT(path) DO UPDATE SET fingerprint=excluded.fingerprint,identity=excluded.identity,
              size=excluded.size,modified=excluded.modified,status='pending',error='',updated=excluded.updated,
              result=CASE WHEN videos.fingerprint=excluded.fingerprint THEN videos.result ELSE '{}' END''',
                      (path,fp,ident,obj.get('size',0),obj.get('modified',''),now))
            if reuse and not force:
                c.execute("UPDATE videos SET status='done',result=?,manual=?,removed=? WHERE path=?",
                          (reuse['result'],reuse['manual'],reuse['removed'],path))
                return False
            c.execute("""INSERT INTO tasks(run_id,path,fingerprint,created) VALUES (?,?,?,?)
              ON CONFLICT(run_id,path) DO UPDATE SET fingerprint=excluded.fingerprint,
              state='queued',error='',created=excluded.created""", (rid,path,fp,now))
            return True

    def excluded(self, path, settings):
        return any(path == p or path.startswith(p.rstrip('/') + '/') for p in settings['exclude'])

    def scan_once(self):
        settings = self.db.settings()
        with self.db.connect() as c:
            row = c.execute("SELECT d.* FROM directories d JOIN runs r ON r.id=d.run_id WHERE d.state='queued' AND r.state='running' ORDER BY d.id LIMIT 1").fetchone()
            if not row:
                return False
            row = dict(row)
            c.execute("UPDATE directories SET state='running' WHERE id=?", (row['id'],))
        try:
            if self.excluded(row['path'], settings):
                self.db.execute("UPDATE directories SET state='done' WHERE id=?", (row['id'],))
                return True
            data = self.ol.listing(row['path'], self.ol.admin_token(), row['page'], settings['page_size'])
            objects = data.get('content') or []
            for obj in objects:
                run = self.db.one('SELECT state FROM runs WHERE id=?', (row['run_id'],))
                if self.stop.is_set() or run['state'] == 'cancelled':
                    return True
                name = obj.get('name','')
                if not name or '/' in name or '\\' in name or name in ('.','..'):
                    continue
                path = clean_path(posixpath.join(row['path'],name))
                if self.excluded(path,settings):
                    continue
                if obj.get('is_dir'):
                    if row['depth'] >= settings['max_depth']:
                        self.db.event(path,'skipped','超过目录深度上限')
                        continue
                    self.db.execute('INSERT OR IGNORE INTO directories(run_id,path,depth) VALUES (?,?,?)', (row['run_id'],path,row['depth']+1))
                elif posixpath.splitext(name)[1].lstrip('.').lower() in settings['extensions']:
                    count = self.db.one('SELECT count(*) n FROM videos')['n']
                    if count >= settings['max_files'] and not self.db.one('SELECT path FROM videos WHERE path=?',(path,)):
                        raise RuntimeError('超过视频索引数量上限')
                    self.enqueue(path,obj,row['run_id'])
            more = len(objects) > 0 and row['page'] * settings['page_size'] < data.get('total',0)
            self.db.execute('UPDATE directories SET state=?,page=page+? WHERE id=?', ('queued' if more else 'done',int(more),row['id']))
        except Exception as exc:
            message = safe_error(exc)
            self.db.execute("UPDATE directories SET state='failed' WHERE id=?",(row['id'],))
            self.db.execute('UPDATE runs SET error=? WHERE id=?',(message,row['run_id']))
            self.db.event(row['path'],'failed',message)
        return True

    def finish_runs(self):
        self.db.execute("""UPDATE runs SET state=CASE WHEN error!='' OR EXISTS(
          SELECT 1 FROM tasks WHERE run_id=runs.id AND state='failed') THEN 'failed' ELSE 'done' END
          WHERE state='running' AND NOT EXISTS(SELECT 1 FROM directories WHERE run_id=runs.id AND state IN ('queued','running'))
          AND NOT EXISTS(SELECT 1 FROM tasks WHERE run_id=runs.id AND state IN ('queued','running'))""")

    def scan_loop(self):
        while not self.stop.is_set():
            busy=False
            try:
                s = self.db.settings()
                interval = s['interval_minutes'] * 60
                last = self.db.one("SELECT value FROM settings WHERE key='last_schedule'")
                if interval and time.time() - (float(json.loads(last['value'])) if last else 0) >= interval:
                    for root in s['roots']:
                        self.create_run(root)
                    self.db.save_settings({'last_schedule':time.time()})
                busy=self.scan_once()
                self.finish_runs()
            except Exception:
                # Keep service alive, but make orchestration failures observable without secrets.
                self.db.event('/','failed','扫描调度失败，请检查配置和 OpenList 连接')
            self.stop.wait(max(.1,self.db.settings()['scan_delay']) if busy else 5)

    def work_once(self):
        with self.db.connect() as c:
            row = c.execute("SELECT t.*,r.content_type,r.use_subtitles FROM tasks t JOIN runs r ON r.id=t.run_id WHERE t.state='queued' AND r.state='running' ORDER BY t.id LIMIT 1").fetchone()
            if not row:
                return False
            task = dict(row)
            c.execute("UPDATE tasks SET state='running',attempts=attempts+1 WHERE id=?",(task['id'],))
            c.execute("UPDATE videos SET status='running',error='' WHERE path=?",(task['path'],))
        def cancelled():
            run = self.db.one('SELECT state FROM runs WHERE id=?',(task['run_id'],))
            return self.stop.is_set() or not run or run['state'] == 'cancelled'
        try:
            obj = self.ol.get(task['path'],self.ol.admin_token())
            if fingerprint(obj) != task['fingerprint']:
                raise RuntimeError('视频已变化，请重新扫描后识别')
            settings = self.db.settings()
            if obj.get('size',0) > settings['max_video_bytes']:
                raise RuntimeError('视频超过大小上限')
            if not obj.get('raw_url') or obj.get('is_dir'):
                raise RuntimeError('视频没有可读取的媒体地址')
            if config.MODEL_NATIVE_VIDEO and obj.get('size',0) > settings['max_network_bytes']:
                raise RuntimeError('源视频超过整段读取流量上限，请在 AI 设置中提高读取上限')
            if task['use_subtitles'] and not config.MODEL_NATIVE_VIDEO:
                raise RuntimeError('字幕联合识别需要启用整片视频模式')
            if config.MODEL_NATIVE_VIDEO:
                cache_path = self.evidence_cache.path(task['path'],task['fingerprint'],task['use_subtitles'],settings)
                sample = self.evidence_cache.load(cache_path)
                if (sample is not None and sample.get('subtitles') and task['content_type']=='movie'
                        and sample.get('context_revision',0)<3 and settings.get('context_frames',5)>0):
                    sample = refresh_context_frames(sample,obj['raw_url'],self.ol.url,settings,cancelled)
                    try:
                        self.evidence_cache.save(cache_path,sample)
                    except OSError:
                        self.db.event(task['path'],'warning','补充画面缓存未能保存，本次继续识别')
                if sample is None:
                    sample = compress_video(obj['raw_url'],self.ol.url,settings,cancelled,
                                            subtitles=bool(task['use_subtitles']))
                    try:
                        self.evidence_cache.save(cache_path,sample)
                    except OSError:
                        self.db.event(task['path'],'warning','压缩证据缓存未能保存，本次继续识别')
            else:
                sample = sample_frames(obj['raw_url'],self.ol.url,settings,cancelled)
            sample['content_type'] = task['content_type']
            if sample.get('subtitles'):
                sample['source_name'] = obj.get('name','')[:500]
                save_subtitles(task['path'],task['fingerprint'],sample['subtitles'])
            if cancelled():
                raise RuntimeError('任务已取消')
            result = infer(sample,settings)
            # Re-read identity after inference so changed files cannot inherit stale results.
            latest = self.ol.get(task['path'],self.ol.admin_token())
            if fingerprint(latest) != task['fingerprint']:
                raise RuntimeError('识别期间视频发生变化，请重新扫描')
            with self.db.connect() as c:
                if cancelled():
                    raise RuntimeError('任务已取消')
                c.execute("UPDATE videos SET status='done',result=?,error='',updated=? WHERE path=? AND fingerprint=?",
                          (json.dumps(result,ensure_ascii=False),time.time(),task['path'],task['fingerprint']))
                c.execute("UPDATE tasks SET state='done',error='' WHERE id=?",(task['id'],))
            self.db.event(task['path'],'done','压缩视频识别完成' if 'video' in sample else '视频抽帧识别完成')
        except Exception as exc:
            message = safe_error(exc)
            with self.db.connect() as c:
                state = 'queued' if self.stop.is_set() else ('cancelled' if cancelled() else 'failed')
                c.execute('UPDATE tasks SET state=?,error=? WHERE id=?',(state,message,task['id']))
                c.execute('UPDATE videos SET status=?,error=?,updated=? WHERE path=?',
                          ('pending' if state=='queued' else state,message,time.time(),task['path']))
            self.db.event(task['path'],state,message)
        return True

    def work_loop(self,index):
        while not self.stop.is_set():
            busy=False
            try:
                if index < self.db.settings()['concurrency']:
                    busy=self.work_once()
            except Exception:
                self.db.event('/','failed','识别调度失败')
            self.stop.wait(.5 if busy else 3)

    def control(self,rid,action):
        with self.db.connect() as c:
            run = c.execute('SELECT * FROM runs WHERE id=?',(rid,)).fetchone()
            if not run:
                raise HTTPException(404,'任务不存在')
            if action == 'pause' and run['state']=='running':
                c.execute("UPDATE runs SET state='paused' WHERE id=?",(rid,))
            elif action == 'resume' and run['state']=='paused':
                c.execute("UPDATE runs SET state='running' WHERE id=?",(rid,))
            elif action == 'cancel':
                c.execute("UPDATE runs SET state='cancelled' WHERE id=?",(rid,))
                c.execute("UPDATE videos SET status='cancelled' WHERE path IN (SELECT path FROM tasks WHERE run_id=? AND state='queued')",(rid,))
                c.execute("UPDATE tasks SET state='cancelled' WHERE run_id=? AND state='queued'",(rid,))
                c.execute("UPDATE directories SET state='cancelled' WHERE run_id=? AND state='queued'",(rid,))
            elif action == 'retry' and run['state'] in ('done','failed'):
                c.execute("UPDATE runs SET state='running',error='' WHERE id=?",(rid,))
                c.execute("UPDATE directories SET state='queued' WHERE run_id=? AND state='failed'",(rid,))
                c.execute("UPDATE tasks SET state='queued',error='' WHERE run_id=? AND state='failed' AND path NOT IN (SELECT path FROM tasks WHERE state IN ('running','queued'))",(rid,))
                c.execute("UPDATE videos SET status='pending',error='' WHERE path IN (SELECT path FROM tasks WHERE run_id=? AND state='queued')",(rid,))
            else:
                raise HTTPException(409,'当前状态不支持此操作')
