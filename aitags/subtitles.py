"""Bounded subtitle extraction from text tracks or burned-in captions."""
import csv
import hashlib
import io
import json
import os
import re
import subprocess
import threading
import time
from difflib import SequenceMatcher
from pathlib import Path
from . import config


MAX_TEXT = 120000
OCR_WIDTH = 1920
OCR_HEIGHT = 64


def crop_filter(value):
    try:
        x,y,w,h = [float(v) for v in value.split(',')]
        valid = 0 <= x < 1 and 0 <= y < 1 and w > 0 and h > 0 and x+w <= 1 and y+h <= 1
    except (ValueError,TypeError):
        valid = False
    if not valid:
        raise RuntimeError('字幕裁剪区域配置无效')
    return (f"crop=iw*{w}:ih*{h}:iw*{x}:ih*{y},scale={OCR_WIDTH}:{OCR_HEIGHT-16}:force_original_aspect_ratio=decrease,"
            "format=gray,lut=y='if(gte(val,200),0,255)',"
            f"pad={OCR_WIDTH}:{OCR_HEIGHT}:(ow-iw)/2:8:color=white")


def recognize_pgm(image, timeout):
    command = [config.TESSERACT,'stdin','stdout','-l','chi_sim','--oem','1','--psm','7']
    if config.TESSDATA_DIR:
        command.extend(['--tessdata-dir',config.TESSDATA_DIR])
    command.extend(['-c','tessedit_create_tsv=1','-c','tessedit_create_txt=0'])
    result = subprocess.run(command,input=image,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,
                            env={**os.environ,'OMP_THREAD_LIMIT':'1'},timeout=timeout)
    if result.returncode:
        raise RuntimeError('字幕 OCR 失败，请检查 Tesseract 和 chi_sim 字库')
    return ocr_line(result.stdout.decode('utf-8',errors='replace'))


def parse_srt(text):
    cues = []
    pattern = r'(\d+):(\d+):(\d+)[,.](\d+)'
    for block in re.split(r'\n\s*\n', text.replace('\r', '')):
        lines = block.strip().splitlines()
        index = next((i for i, line in enumerate(lines) if '-->' in line), None)
        if index is None:
            continue
        times = re.findall(pattern, lines[index])
        if len(times) != 2:
            continue
        start, end = [int(h)*3600 + int(m)*60 + int(s) + int(ms)/1000 for h,m,s,ms in times]
        value = re.sub(r'<[^>]*>|\{[^}]*\}', '', ' '.join(lines[index+1:])).strip()
        if value and end > start:
            cues.append({'start':start,'end':end,'text':value[:500]})
    return cues


def ocr_line(tsv):
    words = []
    confidence = []
    rows = csv.DictReader(io.StringIO(tsv), delimiter='\t')
    if not rows.fieldnames or not {'conf','text'}.issubset(rows.fieldnames):
        raise RuntimeError('OCR 未返回置信度字段，请检查 Tesseract TSV 输出配置')
    for row in rows:
        value = (row.get('text') or '').strip()
        score = float(row.get('conf') or -1)
        if value and score >= 40:
            words.append(value)
            confidence.extend([score] * len(value))
    text = ' '.join(words)
    text = re.sub(r'(?<=[\u4e00-\u9fff])\s+(?=[\u4e00-\u9fff])', '', text)
    text = text.strip(' |[]{}~_')
    if len(re.findall(r'[\u4e00-\u9fff]', text)) < 2 or not confidence or sum(confidence)/len(confidence) < 65:
        return ''
    return text[:200]


def add_cue(cues, second, interval, text):
    if not text:
        return
    if cues and second <= cues[-1]['end'] + .1 and SequenceMatcher(None, cues[-1]['text'], text).ratio() >= .9:
        cues[-1]['end'] = second + interval
    else:
        cues.append({'start':round(second,2),'end':round(second+interval,2),'text':text})


def relation_points(subtitles, duration, limit):
    """Select identity introductions and relationship dialogue, without assuming their truth."""
    if not limit:
        return []
    points = []
    named = re.compile(
        r'(?:这是我(?:的)?(?:小妹|小弟|妹妹|弟弟|姐姐|哥哥|朋友|同事)|'
        r'我的(?:爸爸|妈妈|兄弟|朋友|同事))([\u4e00-\u9fff]{2,8})')

    def select(cue):
        second = min(max(0,(cue['start']+cue['end'])/2),max(0,duration-.1))
        if len(points) < limit and all(abs(second-p['second']) >= 20 for p in points):
            points.append({'second':round(second,2),'text':cue['text']})
            return True
        return False

    for cue in subtitles['cues']:
        match = named.search(cue['text'])
        if match and not match[1].startswith(('的','这','那','一个')):
            select(cue)
    # Prefer evidence that resolves identity and life-stage conflicts, before generic family mentions.
    for pattern in (r'名字叫|名叫|叫做',r'曾是.*所|大学|学生|学校',
                    r'去世|死亡|死了|离世',r'又生下|生下.*弟|生下.*妹|姐弟|兄妹',
                    r'辞掉|辞职|休学',r'混血|末裔|血脉',r'消失'):
        for cue in subtitles['cues']:
            if re.search(pattern,cue['text']) and select(cue):
                break
    for terms in (('怀孕','结婚','收养'),('亲妈','亲爸','生母','生父'),('妈妈','爸爸','外婆')):
        for cue in subtitles['cues']:
            if any(term in cue['text'] for term in terms) and select(cue):
                break
    return sorted(points,key=lambda p:p['second'])


def decode_with_ocr(args, timeout, interval, cancelled):
    """Consume one caption crop per interval while FFmpeg writes the lossless video."""
    deadline = time.monotonic() + timeout
    cues = []
    errors = []
    count = [0]
    proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)

    def consume():
        try:
            while not cancelled() and time.monotonic() < deadline:
                frame = proc.stdout.read(OCR_WIDTH * OCR_HEIGHT)
                if not frame:
                    return
                if len(frame) != OCR_WIDTH * OCR_HEIGHT:
                    raise RuntimeError('字幕图像未完整解码')
                image = f'P5\n{OCR_WIDTH} {OCR_HEIGHT}\n255\n'.encode() + frame
                text = recognize_pgm(image,min(12,max(.1,deadline-time.monotonic())))
                add_cue(cues,count[0]*interval,interval,text)
                count[0] += 1
        except BaseException as exc:
            errors.append(exc)

    thread = threading.Thread(target=consume, daemon=True)
    thread.start()
    try:
        while proc.poll() is None:
            if cancelled() or time.monotonic() >= deadline:
                raise RuntimeError('字幕提取超时或任务取消')
            if errors:
                raise RuntimeError('字幕 OCR 失败，请检查字库、临时目录和超时设置') from errors[0]
            time.sleep(.1)
        thread.join(max(.1, deadline-time.monotonic()))
        if errors:
            raise RuntimeError('字幕 OCR 未完成') from errors[0]
        if thread.is_alive() or proc.returncode:
            raise RuntimeError('字幕或视频解码未完成')
        return {'source':'burned-in-ocr','interval':interval,'frames':count[0],'cues':cues}
    finally:
        if proc.poll() is None:
            proc.kill()
        proc.wait()
        thread.join(13)
        proc.stdout.close()


def transcript(subtitles):
    lines = []
    length = 0
    for cue in subtitles['cues']:
        line = f"[{cue['start']:.1f}–{cue['end']:.1f}秒] {cue['text']}"
        if length + len(line) + 1 > MAX_TEXT:
            break
        lines.append(line)
        length += len(line) + 1
    return '\n'.join(lines), len(lines) < len(subtitles['cues'])


def identity_context(subtitles, limit=6000):
    """Re-surface bounded dialogue windows; never supply external character facts."""
    cues = subtitles.get('cues', [])
    groups = [r'名字|名叫|叫做|叫我', r'姐姐|弟弟|妹妹|哥哥|生下|出生',
              r'去世|死亡|死了|离世|遗体', r'辞掉|辞职|休学|打工|存款']
    selected = set()
    for pattern in groups:
        hits = 0
        last = -100
        for i, cue in enumerate(cues):
            if re.search(pattern, cue['text']) and cue['start']-last >= 15:
                selected.update(j for j,c in enumerate(cues) if cue['start']-20 <= c['start'] <= cue['end']+20)
                last = cue['start']
                hits += 1
                if hits >= 2:
                    break
    lines = []
    used = 0
    for i in sorted(selected):
        cue = cues[i]
        line = f"[{cue['start']:.1f}–{cue['end']:.1f}秒] {cue['text']}"
        if used+len(line)+1 > limit:
            break
        lines.append(line)
        used += len(line)+1
    return '\n'.join(lines)


def artifact_path(path, fingerprint):
    key = hashlib.sha256((path+'\0'+fingerprint).encode()).hexdigest()
    return config.DATA / 'subtitles' / (key+'.json')


def save_subtitles(path, fingerprint, subtitles):
    target = artifact_path(path, fingerprint)
    target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temp = target.with_suffix('.tmp')
    with temp.open('w',encoding='utf-8') as out:
        json.dump(subtitles,out,ensure_ascii=False)
    temp.replace(target)


def srt(subtitles):
    def clock(second):
        ms = max(0, round(second * 1000))
        return f'{ms//3600000:02}:{ms//60000%60:02}:{ms//1000%60:02},{ms%1000:03}'
    return '\n\n'.join(f"{i}\n{clock(c['start'])} --> {clock(c['end'])}\n{c['text']}"
                       for i,c in enumerate(subtitles['cues'],1)) + '\n'
