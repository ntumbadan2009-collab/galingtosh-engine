import pytest
from app.media.tts import synthesize_tts_tracks

@pytest.mark.asyncio
async def test_tts_invalid_text_is_skipped(tmp_path):
    film={"audio":{"tracks":[{"id":"voice1","tts":{"provider":"edge-tts","text":" "}}]}}
    files,warnings=await synthesize_tts_tracks(film,tmp_path)
    assert files=={}
    assert warnings and "Texte TTS invalide" in warnings[0]
