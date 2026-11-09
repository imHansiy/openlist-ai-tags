import json
import shutil
import threading
from http.server import SimpleHTTPRequestHandler,ThreadingHTTPServer
from functools import partial
import pytest
from aitags.model import parse_result
from aitags.model import infer
import httpx
from aitags.media import NATIVE_VIDEO_MAX_BYTES,MediaError,approve_url,compress_video,sample_frames,run_process
from aitags.config import DEFAULTS,FFMPEG


def test_result_validation():
    r=parse_result('```json\n'+json.dumps({'summary':'烹饪','tags':['美食','美食',' 厨房 '],'segments':[]})+'\n```',10)
    assert r['tags']==['美食','厨房']
    r=parse_result(json.dumps({'summary':'主线','tags':['家庭'],'characters':[
        {'name':'小林','evidence':['1秒：我叫小林','2秒：搬到乡下']}]}),10)
    assert r['characters'][0]['evidence']=='1秒：我叫小林；2秒：搬到乡下'
    assert parse_result('已完成核对。\n```json\n{"summary":"主线","tags":["家庭"]}\n```\n请查看上述结果。',10)['tags']==['家庭']
    r=parse_result(json.dumps({'summary':'先辞职，再迁居','tags':['家庭'],
        'events':['辞职','迁居'],'segments':[{'start':0,'end':0,'description':'未知时间'}]}),100)
    assert r['segments']==[] and r['events']==['辞职','迁居']
    with pytest.raises(ValueError):parse_result('{}',10)
    with pytest.raises(ValueError):parse_result(json.dumps({'summary':'x','tags':[],'segments':[{'start':10,'end':5,'description':'x'}]}),20)
    with pytest.raises(ValueError):parse_result(json.dumps({'summary':'x','tags':[],'segments':[{'start':1,'end':30,'description':'x'}]}),20)


def test_relationship_guard_omits_conflicts_without_guessing_replacements():
    from aitags.model import consistent_relationships
    r=consistent_relationships({'characters':[
        {'name':'阿青','role':'母亲','relationships':['小林的母亲']},
        {'name':'小林','role':'阿青的女儿','relationships':['阿青的妻子','阿青的儿子','小海的姐姐']}],
        'uncertainty':''})
    assert r['characters'][1]['relationships']==['小海的姐姐']
    assert r['quality_flags'] and '已省略' in r['uncertainty']

def test_media_policy(monkeypatch):
    with pytest.raises(MediaError):approve_url('file:///etc/passwd','https://openlist.test')
    with pytest.raises(MediaError):approve_url('http://evil.example/a.mp4','https://openlist.test')
    approve_url('http://127.0.0.1:5244/p/a','http://127.0.0.1:5244')
    with pytest.raises(MediaError):approve_url('http://127.0.0.1:80/a','http://127.0.0.1:5244')
    monkeypatch.setattr('aitags.config.MEDIA_HOSTS',['*'])
    with pytest.raises(MediaError):approve_url('http://127.0.0.1/a','https://openlist.test')


def test_model_network_and_auth_errors_are_actionable(monkeypatch):
    sample={'duration':1,'network_bytes':0,'frames':[]}
    def timeout(*args,**kwargs):raise httpx.ConnectTimeout('internal sensitive address')
    monkeypatch.setattr(httpx,'post',timeout)
    with pytest.raises(RuntimeError,match='超时') as err:infer(sample,DEFAULTS,key='secret')
    assert 'sensitive' not in str(err.value) and 'secret' not in str(err.value)
    def denied(*args,**kwargs):
        return httpx.Response(401,request=httpx.Request('POST','https://api.example.test'),json={'error':'secret'})
    monkeypatch.setattr(httpx,'post',denied)
    with pytest.raises(RuntimeError,match='服务区域') as err:infer(sample,DEFAULTS,key='secret')
    assert 'secret' not in str(err.value)


def test_invalid_native_result_does_not_reupload(monkeypatch):
    requests=[]
    def invalid(url, **kwargs):
        requests.append(kwargs['json']['messages'][0]['content'])
        return httpx.Response(200,request=httpx.Request('POST',url),
                              json={'choices':[{'message':{'content':'invalid'}}]})
    monkeypatch.setattr(httpx,'post',invalid)
    with pytest.raises(RuntimeError,match='JSON'):
        infer({'duration':190,'network_bytes':3,'video':'AAAA','video_bytes':3},DEFAULTS,key='test')
    assert len(requests)==2
    assert requests[0][1]['type']=='video_url'
    assert isinstance(requests[1],str)


@pytest.mark.parametrize('with_subtitles',[False,True])
def test_movie_prompt_and_text_structuring(monkeypatch,with_subtitles):
    requests=[]
    def completed(url,**kwargs):
        requests.append(kwargs['json'])
        content='原始视频分析' if len(requests)==1 else json.dumps({
            'summary':'整理后的摘要','tags':['殡葬','亲情'],'uncertainty':'相遇细节不确定',
            'characters':[{'name':'小林','role':'姐姐','relationships':['小海的姐姐'],'evidence':'10秒：我是你姐姐'}]})
        return httpx.Response(200,request=httpx.Request('POST',url),
                              json={'choices':[{'message':{'content':content}}]})
    monkeypatch.setattr(httpx,'post',completed)
    sample={'duration':6400,'video':'AAAA','video_bytes':3,'network_bytes':4,'content_type':'movie'}
    if with_subtitles:
        sample.update(source_name='示例电影.mp4',subtitles={'source':'burned-in-ocr','interval':1,'cues':[
            {'start':10,'end':12,'text':'外婆在哪里'}]})
    result=infer(sample,DEFAULTS,key='test')
    assert requests[0]['messages'][0]['content'][0]['text'].startswith('这是一部电影的完整视频。')
    assert requests[0]['max_tokens']==8192
    assert requests[0]['media_io_kwargs']=={'video':{'num_frames':32}}
    assert requests[0]['chat_template_kwargs']=={'enable_thinking':True}
    assert requests[1]['chat_template_kwargs']=={'enable_thinking':with_subtitles}
    final_input=requests[1]['messages'][1]['content']
    assert '原始视频分析' in (final_input[0]['text'] if isinstance(final_input,list) else final_input)
    assert result['analysis']=='原始视频分析' and result['uncertainty']=='相遇细节不确定'
    assert result['characters'][0]['relationships']==['小海的姐姐']
    if with_subtitles:
        assert '外婆在哪里' in requests[0]['messages'][0]['content'][1]['text']
        assert result['sampling']['subtitles']['title_hint_source']=='resource-filename'


def test_context_frames_fit_request_without_dropping_video(monkeypatch):
    requests=[]
    def completed(url,**kwargs):
        requests.append(kwargs['json'])
        content='有证据的主线' if len(requests)==1 else json.dumps({'summary':'主线','tags':['亲情']})
        return httpx.Response(200,request=httpx.Request('POST',url),
                              json={'choices':[{'message':{'content':content}}]})
    monkeypatch.setattr(httpx,'post',completed)
    size=23*1024**2
    sample={'duration':10,'video':'A'*(4*((size+2)//3)),'video_bytes':size,'network_bytes':1,
            'context_frames':[{'second':i,'data':'A'*(512*1024)} for i in range(5)]}
    result=infer(sample,DEFAULTS,key='test')
    content=requests[0]['messages'][0]['content']
    assert len(json.dumps(requests[0],ensure_ascii=False,separators=(',',':')).encode())<=32*1024**2
    assert sum(x['type']=='video_url' for x in content)==1
    assert 0<len(result['sampling']['context_timestamps'])<5


def test_audit_format_repair_does_not_upload_video_twice(monkeypatch):
    requests=[]
    def reply(url,**kwargs):
        requests.append(kwargs['json'])
        outputs=['### 三、剧情摘要\n小林搬家。',json.dumps({'summary':'小林搬家','tags':['家庭'],
            'characters':[{'name':'小林','evidence':{'line':'1秒：我叫小林'}}]}),
            json.dumps({'summary':'小林搬家','tags':['家庭'],
                'characters':[{'name':'小林','evidence':'1秒：我叫小林'}]})]
        return httpx.Response(200,request=httpx.Request('POST',url),
            json={'choices':[{'message':{'content':outputs[len(requests)-1]}}]})
    monkeypatch.setattr(httpx,'post',reply)
    result=infer({'duration':10,'video':'AAAA','video_bytes':3,'network_bytes':0,'content_type':'movie',
        'subtitles':{'source':'text-track','cues':[{'start':1,'end':2,'text':'我叫小林'}]}},DEFAULTS,key='test')
    assert result['verification']['format_repaired']
    assert result['characters'][0]['name']=='小林'
    assert len(requests)==3
    assert sum(x.get('type')=='video_url' for r in requests for m in r['messages']
        for x in (m['content'] if isinstance(m['content'],list) else []))==1


def test_custom_provider_keeps_portable_request(monkeypatch):
    requests=[]
    def completed(url,**kwargs):
        requests.append(kwargs['json'])
        return httpx.Response(200,request=httpx.Request('POST',url),json={'choices':[{'message':{
            'content':json.dumps({'summary':'主线','tags':['亲情']})}}]})
    monkeypatch.setattr(httpx,'post',completed)
    infer({'duration':10,'video':'AAAA','video_bytes':3,'network_bytes':1},
          {**DEFAULTS,'model_url':'https://custom.test/v1','model_name':'custom'},key='test')
    assert all('media_io_kwargs' not in r and 'chat_template_kwargs' not in r for r in requests)

@pytest.mark.skipif(not shutil.which(FFMPEG) or not shutil.which('ffprobe'),reason='requires ffmpeg + ffprobe')
def test_real_video_decode_and_budget(tmp_path):
    file=tmp_path/'sample.mp4'
    run_process([FFMPEG,'-v','error','-f','lavfi','-i','testsrc=duration=2:size=320x240:rate=10','-c:v','libx264','-pix_fmt','yuv420p','-movflags','+faststart',str(file)],30)
    long_file=tmp_path/'long.mp4'
    run_process([FFMPEG,'-v','error','-f','lavfi','-i','testsrc=duration=190:size=64x64:rate=2','-c:v','libx264','-pix_fmt','yuv420p','-movflags','+faststart',str(long_file)],30)
    subtitle=tmp_path/'test.srt'
    subtitle.write_text('1\n00:00:00,000 --> 00:00:01,500\n外婆在天上\n',encoding='utf-8')
    run_process([FFMPEG,'-v','error','-i',str(file),'-i',str(subtitle),'-c:v','copy',
                 '-c:s','mov_text','-movflags','+faststart',str(tmp_path/'captioned.mp4')],30)
    class Quiet(SimpleHTTPRequestHandler):
        def log_message(self,*args):pass
    server=ThreadingHTTPServer(('127.0.0.1',0),partial(Quiet,directory=str(tmp_path)))
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    origin=f'http://127.0.0.1:{server.server_port}'
    try:
        settings={**DEFAULTS,'frames':3,'media_timeout':30}
        sample=sample_frames(origin+'/sample.mp4',origin,settings)
        assert len(sample['frames'])==3 and sample['duration']==pytest.approx(2,.1)
        assert 0<sample['network_bytes']<=settings['max_network_bytes']
        video=compress_video(origin+'/sample.mp4',origin,settings)
        assert video['duration']==pytest.approx(2,.1)
        assert 0<video['video_bytes']<=NATIVE_VIDEO_MAX_BYTES
        assert len(video['video'])==4*((video['video_bytes']+2)//3)
        assert video['encoding']['preset']=='veryfast' and video['encoding']['passes']==2
        long_video=compress_video(origin+'/long.mp4',origin,settings)
        assert long_video['duration']==pytest.approx(190,abs=.1)
        captioned=compress_video(origin+'/captioned.mp4',origin,settings,subtitles=True)
        assert captioned['subtitles']['source']=='text-track'
        assert captioned['subtitles']['cues'][0]['text']=='外婆在天上'
        from unittest.mock import patch
        with patch('aitags.config.VIDEO_WORK_MAX_BYTES',1024):
            with pytest.raises(MediaError,match='中间视频'):
                compress_video(origin+'/long.mp4',origin,settings)
        with pytest.raises(MediaError):sample_frames(origin+'/sample.mp4',origin,{**settings,'max_network_bytes':10})
    finally:
        server.shutdown();server.server_close();thread.join(2)
