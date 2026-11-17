from pathlib import Path
import httpx
import pytest
from app.storage.supabase import SupabaseREST, SupabaseError
from app.media.graphics import sanitize_svg_to_png, GraphicsError
from app.media.tts import synthesize_tts_tracks
from app.media.effects import build_video_filters
from app.core.task_manager import TaskManager
from app.config import Settings

@pytest.mark.asyncio
async def test_upload_stream_works_with_async_http_client(tmp_path, monkeypatch):
    payload = b'video-data' * 20000
    source = tmp_path / 'test.mp4'
    source.write_bytes(payload)
    received = []
    async def handler(request):
        received.append(await request.aread())
        return httpx.Response(200, json={'Key':'renders/project/test.mp4'})
    client = httpx.AsyncClient
    monkeypatch.setattr(httpx, 'AsyncClient', lambda **kw: client(transport=httpx.MockTransport(handler), **kw))
    await SupabaseREST('https://example.supabase.co','test').upload_file('renders','project/test.mp4',source)
    assert received == [payload]

@pytest.mark.asyncio
async def test_lost_worker_cannot_complete_reassigned_job(monkeypatch):
    async def handler(request):
        assert request.url.params['worker_id'] == 'eq.worker-one'
        assert request.url.params['status'] == 'eq.running'
        return httpx.Response(200,json=[])
    client=httpx.AsyncClient
    monkeypatch.setattr(httpx,'AsyncClient',lambda **kw:client(transport=httpx.MockTransport(handler),**kw))
    with pytest.raises(SupabaseError,match='réattribuée'):
        await SupabaseREST('https://example.supabase.co','test').patch_render_job('job',{'status':'done'},worker_id='worker-one')

def test_svg_css_external_reference_is_rejected(tmp_path):
    svg=tmp_path/'bad.svg'
    svg.write_text('<svg xmlns="http://www.w3.org/2000/svg"><style>rect{fill:url(https://example.com/a)}</style><rect width="10" height="10"/></svg>')
    with pytest.raises(GraphicsError,match='CSS'):
        sanitize_svg_to_png(svg,tmp_path/'out.png')

@pytest.mark.asyncio
async def test_legacy_tts_defaults_resolve_to_supported_voice(tmp_path,monkeypatch):
    import edge_tts
    voices=[]
    class Voice:
        def __init__(self,text,voice):voices.append(voice)
        async def save(self,path):Path(path).write_bytes(b'fake-audio')
    monkeypatch.setattr(edge_tts,'Communicate',Voice)
    film={'info':{'language':'fr'},'audio':{'tracks':[{'id':'voice','tts':{'provider':'default','voice':'fr-FR-Standard-A','text':'Bonjour'}}]}}
    files,warnings=await synthesize_tts_tracks(film,tmp_path)
    assert files['voice'].is_file() and not warnings
    assert voices==['fr-FR-DeniseNeural']

def test_effect_target_and_top_position():
    filters,warnings=build_video_filters([{'type':'title_overlay','target':'shot','params':{'text':'Bonjour','position':'top'}}],10,1280,720,{'shot':(3,6)})
    assert not warnings
    assert "between(t,3.0000,6.0000)" in filters[0]
    assert 'y=2*text_h' in filters[0]

@pytest.mark.asyncio
async def test_worker_finishes_short_job_without_25_second_delay(monkeypatch):
    manager=TaskManager(Settings(),None)
    finished=[]
    async def process(job):finished.append(job['id'])
    monkeypatch.setattr(manager,'_process_job',process)
    import asyncio
    await asyncio.wait_for(manager.process_job({'id':'test'}),timeout=1)
    assert finished==['test']

def test_worker_instances_have_distinct_leases():
    assert TaskManager(Settings(),None).worker_id != TaskManager(Settings(),None).worker_id
