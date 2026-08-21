from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def test_tutorial_page_fetches_manifest_and_handles_missing_and_broken_video():
    js=(ROOT/'app/mesflow/web/static/app.js').read_text(encoding='utf-8')
    assert "fetch('/tutorials/manifest.json'" in js
    assert 'Video hướng dẫn chưa được publish.' in js
    assert 'manifest.videos||manifest.items' in js
    assert '.sort((a,b)=>Number(a.order||0)-Number(b.order||0))' in js
    assert 'video.onerror=' in js
    assert '<video id="tutorialVideo" controls preload="metadata" playsinline>' in js


def test_tutorial_response_declares_range_and_cache_contract():
    source=(ROOT/'app/mesflow/web/app.py').read_text(encoding='utf-8')
    assert "response.headers['Accept-Ranges']='bytes'" in source
    assert "filename=='manifest.json'" in source
    assert "public, max-age=86400" in source
