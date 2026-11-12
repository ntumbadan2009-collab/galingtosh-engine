from app.media.effects import build_video_filters

def test_invalid_effect_parameters_are_skipped():
    filters,warnings=build_video_filters([
        {"type":"fade_in","params":{"durationSec":"not-a-number"}},
        {"type":"text_overlay","params":{"fontSize":"large","text":"Hello"}}
    ],10,1280,720)
    assert filters==[]
    assert len(warnings)==2
