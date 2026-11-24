from app.core.editorial import level3, timeline_issues

def make(shots):
    return {"info":{"editorialLevel":3},"scenes":[{"durationSec":6,"shots":shots}]}

def test_level3_is_opt_in():
    assert not level3({})
    assert level3(make([]))

def test_covered_timeline():
    assert not timeline_issues(make([{"order":1,"inSec":0,"outSec":3},{"order":2,"inSec":3,"outSec":6}]))

def test_gap_overlap_and_flash_rejected():
    for shots in [
        [{"inSec":1,"outSec":6}],
        [{"order":1,"inSec":0,"outSec":4},{"order":2,"inSec":3,"outSec":6}],
        [{"order":1,"inSec":0,"outSec":0.5},{"order":2,"inSec":0.5,"outSec":6}],
        [{"inSec":0,"outSec":5}],
    ]:
        assert timeline_issues(make(shots))
