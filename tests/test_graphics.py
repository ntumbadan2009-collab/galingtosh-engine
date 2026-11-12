from pathlib import Path
import pytest
from app.media.graphics import GraphicsError, chart_to_png, sanitize_svg_to_png

def test_bar_chart_is_rendered(tmp_path: Path):
    output=tmp_path/"chart.png"
    chart_to_png({"type":"bar","title":"Test","labels":["A","B"],"series":[{"name":"S","values":[2,5]}]},output)
    assert output.is_file() and output.stat().st_size>1000

def test_invalid_pie_chart_rejected(tmp_path: Path):
    with pytest.raises(GraphicsError):
        chart_to_png({"type":"pie","labels":["A"],"series":[{"values":[-1]}]},tmp_path/"bad.png")

def test_svg_rasterization(tmp_path: Path):
    source=tmp_path/"safe.svg"; output=tmp_path/"safe.png"
    source.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="100" height="50"><rect width="100" height="50" fill="red"/></svg>')
    sanitize_svg_to_png(source,output)
    assert output.is_file()

def test_svg_script_rejected(tmp_path: Path):
    source=tmp_path/"bad.svg"; output=tmp_path/"bad.png"
    source.write_text('<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>')
    with pytest.raises(GraphicsError):
        sanitize_svg_to_png(source,output)
