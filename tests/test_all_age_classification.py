import json

import httpx
import pytest

from aitags.config import DEFAULTS
from aitags.model import infer


@pytest.mark.parametrize('age_band',['儿童','青少年','成年青年','中年','老年'])
def test_non_sexual_age_bands_remain_available(monkeypatch,age_band):
    expected={'summary':'普通运动教学中的人物，年龄段仅为外观估计。',
              'tags':['运动教学',age_band,'短发','匀称'],
              'uncertainty':'外观年龄不能作为身份或年龄核验。'}
    def reply(url,**kwargs):
        instruction=kwargs['json']['messages'][0]['content'][0]['text']
        assert '普通非性内容' in instruction
        assert '儿童、青少年、成年青年、中年、老年' in instruction
        return httpx.Response(200,request=httpx.Request('POST',url),json={
            'choices':[{'message':{'content':json.dumps(expected,ensure_ascii=False)}}]})
    monkeypatch.setattr(httpx,'post',reply)
    result=infer({'duration':10,'network_bytes':0,'frames':[{'second':1,'data':'AAAA'}]},DEFAULTS,key='test')
    assert result['tags']==expected['tags']
    assert 'content_review' not in result


def test_inference_returns_model_output_unchanged(monkeypatch):
    """Post-processing must not rewrite the summary, tags or the raw analysis."""
    calls=[]
    observed={'summary':'年龄信息不足的敏感内容。','tags':['性行为','长发'],
              'uncertainty':'是否成年无法确认。'}
    def reply(url,**kwargs):
        calls.append(kwargs['json'])
        text='模型提示年龄与内容风险。' if len(calls)==1 else json.dumps(observed,ensure_ascii=False)
        return httpx.Response(200,request=httpx.Request('POST',url),json={
            'choices':[{'message':{'content':text}}]})
    monkeypatch.setattr(httpx,'post',reply)
    result=infer({'duration':10,'network_bytes':0,'video':'AAAA','video_bytes':3},DEFAULTS,key='test')
    assert result['summary']==observed['summary']
    assert result['tags']==observed['tags']
    assert result['uncertainty']==observed['uncertainty']
    assert result['analysis']=='模型提示年龄与内容风险。'
    assert 'content_review' not in result
    assert result['sampling']['prompt_version']=='whole-video-evidence-v16'
