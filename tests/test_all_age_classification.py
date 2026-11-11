import json

import httpx
import pytest

from aitags.config import DEFAULTS
from aitags.model import infer, protect_uncertain_minor_content


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


@pytest.mark.parametrize('uncertainty,tags',[
    ('是否成年无法确认。',['性行为','长发']),
    ('画面中存在疑似未成年人性化内容风险。',['长发','人物特写']),
    ('模型提示可能涉及 underage 人物。',['性行为','长发']),
    ('出现未成年人。',['色情','人物特写']),
])
def test_model_flagged_risk_drops_detailed_character_output(uncertainty,tags):
    result=protect_uncertain_minor_content({'summary':'模型分类存在风险。','tags':tags,
        'uncertainty':uncertainty,'analysis':'不应继续暴露的原始分析',
        'characters':[{'name':'人物A'}],'events':['原始事件'],'segments':[{'description':'原始描述'}]})
    assert result['content_review']['status']=='risk-only'
    assert result['tags']==['敏感内容风险','年龄需核实']
    assert not result['characters'] and not result['events'] and not result['segments']
    assert 'analysis' not in result


@pytest.mark.parametrize('summary,tags',[
    ('影片讲述一名少女的成长,成年后进入演艺行业。',['性行为','长发','中年']),
    ('两名成年主角的情感主线,配角是一名青少年学生。',['性行为','长发','成年青年']),
])
def test_ambiguous_age_band_away_from_sexual_terms_keeps_metadata(summary,tags):
    original={'summary':summary,'tags':tags,'uncertainty':'年龄段仅为外观估计。',
              'characters':[{'name':'人物A'}],'segments':[{'description':'原始描述'}]}
    assert protect_uncertain_minor_content(original) is original


@pytest.mark.parametrize('summary,tags',[
    ('青少年之间的性行为画面。',['短发','人物特写']),
    ('人物特写。',['青少年','性行为']),
    ('未成年角色的性化描写。',['长发']),
])
def test_ambiguous_age_band_next_to_a_sexual_term_still_collapses(summary,tags):
    result=protect_uncertain_minor_content({'summary':summary,'tags':tags,
        'uncertainty':'画面证据有限。','characters':[{'name':'人物A'}]})
    assert result['content_review']['status']=='risk-only'
    assert result['tags']==['敏感内容风险','年龄需核实']
    assert not result['characters']


def test_age_boilerplate_without_a_minor_reference_does_not_collapse():
    original={'summary':'成年人访谈记录。','tags':['访谈','中年','短发'],
              'uncertainty':'抽样局限:部分年龄段无法确认。'}
    assert protect_uncertain_minor_content(original) is original


def test_strict_mode_restores_whole_result_collapse(monkeypatch):
    from aitags import model
    monkeypatch.setattr(model,'PROTECT_MINOR_MODE','strict')
    original={'summary':'影片讲述一名少女的成长,成年后进入演艺行业。','tags':['性行为','长发']}
    collapsed=model.protect_uncertain_minor_content(original)
    assert collapsed['content_review']['status']=='risk-only'


def test_explicit_negated_minor_claim_does_not_erase_adult_metadata():
    original={'summary':'成年人内容分类。','tags':['性行为','中年'],
              'uncertainty':'没有未成年人；具体年龄不明。'}
    assert protect_uncertain_minor_content(original) is original


def test_neutral_child_scene_is_not_flagged_by_a_negative_risk_statement():
    original={'summary':'儿童普通舞蹈。','tags':['儿童舞蹈','短发'],
              'uncertainty':'未发现未成年人性化内容，具体年龄无法确认。'}
    assert protect_uncertain_minor_content(original) is original


def test_inference_applies_risk_only_output_after_structuring(monkeypatch):
    calls=[]
    unsafe={'summary':'年龄信息不足的敏感内容。','tags':['性行为','长发'],
            'uncertainty':'是否成年无法确认。'}
    def reply(url,**kwargs):
        calls.append(kwargs['json'])
        text='模型提示年龄与内容风险。' if len(calls)==1 else json.dumps(unsafe,ensure_ascii=False)
        return httpx.Response(200,request=httpx.Request('POST',url),json={
            'choices':[{'message':{'content':text}}]})
    monkeypatch.setattr(httpx,'post',reply)
    result=infer({'duration':10,'network_bytes':0,'video':'AAAA','video_bytes':3},DEFAULTS,key='test')
    assert result['content_review']['status']=='risk-only'
    assert '长发' not in result['tags'] and '性行为' not in result['tags']
    assert 'analysis' not in result
    assert result['sampling']['prompt_version']=='whole-video-evidence-v16'
