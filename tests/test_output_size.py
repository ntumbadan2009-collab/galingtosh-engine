from app.core.renderer import output_size

def test_output_size_respects_aspect_ratio():
    film={"format":{"aspect":"9:16"},"render":{"resolution":"720p"}}
    width,height=output_size(film)
    assert width==720 and height==1280

def test_ultrawide_1080p_exceeds_safe_pixel_budget():
    film={"format":{"aspect":"21:9"},"render":{"resolution":"1080p"}}
    width,height=output_size(film)
    assert width*height > 1920*1080
