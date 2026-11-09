from aitags.subtitles import add_cue,ocr_line,parse_srt,srt,save_subtitles,transcript,relation_points
from .conftest import add_video
import pytest


def test_identity_windows_keep_negation_and_adjacent_chronology():
    from aitags.subtitles import identity_context
    cues=[{'start':i*20,'end':i*20+2,'text':v} for i,v in enumerate([
        '我叫小林','那是我的姐姐','我们早期靠打工生活','后来已辞掉工作','此后搬到了乡下',
        '他没有死了，是我看错了','现在还不能确认'])]
    text=identity_context({'cues':cues})
    assert text.index('靠打工') < text.index('已辞掉') < text.index('搬到了')
    assert '他没有死了，是我看错了' in text and '还不能确认' in text
    assert len(identity_context({'cues':cues},limit=90)) <= 90


def test_caption_crop_geometry():
    from aitags.subtitles import crop_filter
    assert 'ih*0.925' in crop_filter('0.1,0.925,0.8,0.075')
    for invalid in ('0,0,2,1','0,-1,1,1','nan,0,1,1','bad','0,0,0,1'):
        with pytest.raises(RuntimeError,match='裁剪'):
            crop_filter(invalid)


def test_crop_detection_refuses_empty_probe_and_can_find_later_caption(monkeypatch,tmp_path):
    from aitags.media import detect_subtitle_crop,MediaError
    def fake_decode(args,*rest):
        if args[-1]!='-':
            from pathlib import Path
            Path(args[-1]).write_bytes(b'jpeg')
        return b'pgm'
    monkeypatch.setattr('aitags.media.run_process',fake_decode)
    monkeypatch.setattr('aitags.subtitles.recognize_pgm',lambda *args:'')
    with pytest.raises(MediaError,match='未读取到可靠文字'):
        detect_subtitle_crop('source',[],7000,tmp_path,lambda:60,lambda:False)
    readings=iter(['']*7+['这是我的妈妈','','这是我的妈妈','','这是我的妈妈','','这是我的妈妈'])
    monkeypatch.setattr('aitags.subtitles.recognize_pgm',lambda *args:next(readings))
    assert detect_subtitle_crop('source',[],7000,tmp_path,lambda:60,lambda:False)=='0.1,0.925,0.8,0.075'


def test_timed_subtitles_and_confidence_filter():
    cues=parse_srt('1\n00:01:02,500 --> 00:01:04,000\n<i>我的爸爸</i>\n叫莫三妹\n')
    assert cues==[{'start':62.5,'end':64.0,'text':'我的爸爸 叫莫三妹'}]
    assert parse_srt(srt({'cues':cues}))==cues
    add_cue(cues,64,1,'我的爸爸 叫莫三妹')
    assert cues[0]['end']==65
    add_cue(cues,90,1,'我的爸爸 叫莫三妹')
    assert len(cues)==2
    tsv='conf\ttext\n92\t外\n93\t婆\n10\t神奇\n'
    assert ocr_line(tsv)=='外婆'
    assert not ocr_line('conf\ttext\n10\t妈妈\n')
    with pytest.raises(RuntimeError,match='置信度'):
        ocr_line('没有置信度的纯文本输出')
    text,cut=transcript({'cues':cues})
    assert '62.5' in text and not cut


def test_subtitle_download_checks_video_permissions(env,monkeypatch,tmp_path):
    db,ol,worker,client=env
    monkeypatch.setattr('aitags.config.DATA',tmp_path)
    for path in ('/public/a.mp4','/secret/b.mp4'):
        add_video(db,worker,path,ol)
        row=db.one('SELECT * FROM videos WHERE path=?',(path,))
        save_subtitles(path,row['fingerprint'],{'source':'text-track','cues':[
            {'start':0,'end':1,'text':'只有授权用户可见'}]})
    good=client.post('/ai/api/subtitles',headers={'Authorization':'limited'},json={'paths':['/a.mp4']})
    assert good.status_code==200 and '只有授权用户可见' in good.json()['srt']
    assert client.post('/ai/api/subtitles',json={'paths':['/secret/b.mp4']}).status_code==404
    ol.objects['/public/a.mp4']['size']+=1
    assert client.post('/ai/api/subtitles',headers={'Authorization':'limited'},json={'paths':['/a.mp4']}).status_code==404


def test_relation_points_use_dialogue_without_assuming_identity():
    cues=[{'start':t,'end':t+2,'text':text} for t,text in [
        (10,'这是我妹妹的本'),(50,'这是我小妹小雨'),(52,'她是亲妈'),
        (100,'我的爸爸张三'),(200,'我怀孕了'),(300,'她的生父是谁')]]
    points=relation_points({'cues':cues},400,5)
    assert [p['second'] for p in points]==[51,101,201,301]
    assert relation_points({'cues':cues},400,0)==[]
    cues=[{'start':t,'end':t+2,'text':text} for t,text in [
        (10,'我的名字叫小林'),(50,'她曾是一所学校的学生'),(100,'父亲已经去世'),
        (150,'血脉传给了后人'),(200,'后来辞掉工作')]]
    assert [p['second'] for p in relation_points({'cues':cues},300,5)]==[11,51,101,151,201]
