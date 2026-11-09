import json

import httpx
import pytest

from aitags.config import DEFAULTS
from aitags.model import CONTENT_OBSERVATION_RULES, infer


@pytest.mark.parametrize('mode', ['frames','frames-retry','video','movie','audit','repair'])
def test_fact_based_classification_survives_all_model_stages(monkeypatch, mode):
    requests = []
    expected = {'summary':'医学检查画面，局部裸露；不能据此认定为性行为。',
                'tags':['医学场景','局部裸露'],'uncertainty':'人物年龄无法确认。'}

    def reply(url, **kwargs):
        payload = kwargs['json']
        requests.append(json.loads(json.dumps(payload)))
        first = len(requests) == 1
        content = json.dumps(expected, ensure_ascii=False)
        if first and mode == 'frames-retry':
            content = '无效 JSON'
        elif first and mode not in ('frames','frames-retry'):
            content = expected['summary']
        elif mode == 'repair' and len(requests) == 2:
            content = '{"summary":true,"tags":"医学场景"}'
        return httpx.Response(200, request=httpx.Request('POST',url),
            json={'choices':[{'message':{'content':content}}]})

    monkeypatch.setattr(httpx,'post',reply)
    sample = {'duration':10,'network_bytes':0}
    if mode.startswith('frames'):
        sample['frames'] = [{'second':1,'data':'AAAA'}]
    else:
        sample.update(video='AAAA',video_bytes=3)
    if mode in ('movie','audit','repair'):
        sample['content_type'] = 'movie'
    if mode in ('audit','repair'):
        sample['subtitles'] = {'source':'text-track','cues':[{'start':1,'end':2,'text':'医学教学'}]}
    result = infer(sample,DEFAULTS,key='test')
    assert result['tags'] == expected['tags']
    assert result['summary'] == expected['summary']
    assert result['uncertainty'] == expected['uncertainty']
    assert len(requests) == (3 if mode=='repair' else 1 if mode=='frames' else 2)
    for request in requests:
        instruction = request['messages'][0]['content']
        if isinstance(instruction,list):
            instruction = instruction[0]['text']
        assert CONTENT_OBSERVATION_RULES in instruction
    if 'video' in sample:
        assert result['sampling']['prompt_version'] == 'whole-video-evidence-v13'
        assert sum(block.get('type')=='video_url' for request in requests
            for message in request['messages'] if isinstance(message['content'],list)
            for block in message['content']) == 1


def test_non_sensitive_labels_are_not_automatically_reclassified(monkeypatch):
    def reply(url,**kwargs):
        return httpx.Response(200,request=httpx.Request('POST',url),json={
            'choices':[{'message':{'content':'{"summary":"城市夜景","tags":["城市","夜景"]}'}}]})
    monkeypatch.setattr(httpx,'post',reply)
    result=infer({'duration':10,'network_bytes':0,'frames':[{'second':1,'data':'AAAA'}]},DEFAULTS,key='test')
    assert result['tags']==['城市','夜景']
