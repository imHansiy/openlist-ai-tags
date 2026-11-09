"""Private, bounded cache of compressed evidence, keyed by current OpenList identity."""
import hashlib
import json
import os
import time
import uuid
from pathlib import Path
from . import config


class EvidenceCache:
    def __init__(self, root):
        self.root = Path(root)

    def path(self, path, fingerprint, use_subtitles, settings):
        policy = ['whole-evidence-v4',path,fingerprint,bool(use_subtitles),
                  settings.get('context_frames',5),config.SUBTITLE_OCR_CROP,config.TESSDATA_DIR,config.SUBTITLE_OCR_AUTO_CROP]
        key = hashlib.sha256(json.dumps(policy,ensure_ascii=False).encode()).hexdigest()
        return self.root / (key+'.json')

    def load(self, path):
        if config.EVIDENCE_CACHE_MAX_BYTES <= 0 or config.EVIDENCE_CACHE_TTL <= 0:
            return None
        try:
            stat = path.stat()
            if stat.st_size > config.EVIDENCE_CACHE_MAX_BYTES or time.time()-stat.st_mtime > config.EVIDENCE_CACHE_TTL:
                path.unlink(missing_ok=True)
                return None
            sample = json.loads(path.read_text(encoding='utf-8'))
            if not isinstance(sample,dict) or not isinstance(sample.get('video'),str):
                return None
            size = sample['video_bytes']
            if not 0 < size <= 23*1024**2 or len(sample['video']) != 4*((size+2)//3) or sample['duration'] <= 0:
                return None
            sample['cached_network_bytes'] = sample.get('network_bytes',0)
            sample['network_bytes'] = 0
            sample['evidence_cache_hit'] = True
            return sample
        except (OSError,ValueError,KeyError,TypeError):
            return None

    def save(self, path, sample):
        if not sample.get('video') or config.EVIDENCE_CACHE_MAX_BYTES <= 0 or config.EVIDENCE_CACHE_TTL <= 0:
            return
        self.root.mkdir(mode=0o700,parents=True,exist_ok=True)
        temp = path.with_suffix('.'+uuid.uuid4().hex+'.tmp')
        try:
            with os.fdopen(os.open(temp,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600),'w',encoding='utf-8') as out:
                json.dump(sample,out,ensure_ascii=False,separators=(',',':'))
            if temp.stat().st_size <= config.EVIDENCE_CACHE_MAX_BYTES:
                temp.replace(path)
        finally:
            temp.unlink(missing_ok=True)
        self.prune()

    def prune(self):
        entries = []
        for path in self.root.glob('*.json'):
            try:
                stat = path.stat()
                entries.append((stat.st_mtime,stat.st_size,path))
            except FileNotFoundError:
                pass
        used = 0
        for index,(modified,size,path) in enumerate(sorted(entries,reverse=True)):
            used += size
            if used > config.EVIDENCE_CACHE_MAX_BYTES or index >= 8 or time.time()-modified > config.EVIDENCE_CACHE_TTL:
                path.unlink(missing_ok=True)
