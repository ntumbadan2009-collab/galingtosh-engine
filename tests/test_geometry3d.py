from PIL import Image,ImageChops
from app.media.motion_graphics import _draw_frame
from app.core.motion_policy import motion_spec_issues

def test_geometric_templates_require_literal_shape_and_motion():
    quote="Le cube tourne autour de son axe."
    assert not motion_spec_issues(quote,quote,{"type":"cube_rotation","items":[{"text":quote}]})
    assert motion_spec_issues(quote,quote,{"type":"sphere_rotation","items":[{"text":quote}]})
    static="Le cube possède plusieurs faces."
    assert motion_spec_issues(static,static,{"type":"cube_rotation","items":[{"text":static}]})

def test_rotation_changes_the_rendered_geometry_not_the_caption():
    for kind,quote in [("cube_rotation","Le cube tourne autour de son axe."),("sphere_rotation","La sphère tourne autour de son axe.")]:
        args=dict(width=720,height=1280,kind=kind,items=[{"text":quote}],scene_title="Géométrie",scene_number=1,duration=6)
        a=_draw_frame(**args,time_sec=.3);b=_draw_frame(**args,time_sec=1.2)
        assert ImageChops.difference(a.crop((0,300,720,850)),b.crop((0,300,720,850))).getbbox()
        assert ImageChops.difference(a.crop((0,950,720,1280)),b.crop((0,950,720,1280))).getbbox() is None
        a.close();b.close()
