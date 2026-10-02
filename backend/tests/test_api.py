import pytest
from fastapi.testclient import TestClient
from backend.main import app

client = TestClient(app)

def test_read_main():
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {"message": "WebReader API", "version": "1.0"}

def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "running"}


def _tiny_pdf(text: str) -> bytes:
    """Hand-built one-page 200x200 PDF with `text` at the top-left (no extra deps)."""
    stream = f"BT /F1 8 Tf 10 170 Td ({text}) Tj ET"
    objs = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 200] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        f"<< /Length {len(stream)} >>\nstream\n{stream}\nendstream",
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out, offsets = "%PDF-1.4\n", []
    for i, o in enumerate(objs, 1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n{o}\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n"
    out += "".join(f"{off:010d} 00000 n \n" for off in offsets)
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF"
    return out.encode("latin-1")


def test_box_text_preview(tmp_path):
    from backend.utils import box_text_preview
    pdf = tmp_path / "t.pdf"
    pdf.write_bytes(_tiny_pdf("alpha beta gamma delta epsilon zeta"))
    # Relative box covering the top strip of the page, where the text sits
    res = box_text_preview(str(pdf), 0, {"x": 0, "y": 0, "w": 1, "h": 0.3, "relative": True}, n=2)
    assert res["word_count"] == 6
    assert res["first"] == "alpha beta"
    assert res["last"] == "epsilon zeta"
    # Out-of-range page is rejected
    with pytest.raises(IndexError):
        box_text_preview(str(pdf), 3, {"x": 0, "y": 0, "w": 1, "h": 1, "relative": True})
