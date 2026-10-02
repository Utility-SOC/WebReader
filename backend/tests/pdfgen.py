"""Tiny PDF builder for tests: positioned text in Helvetica / Helvetica-Bold, ruled lines, raw RGB images."""

PAGE_W, PAGE_H = 612, 792


def _esc(s):
    return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


class Page:
    def __init__(self):
        self.ops = []
        self.images = []  # (name, w, h, rgb_bytes)

    def text(self, x, top, size, s, bold=False):
        y = PAGE_H - top - size
        self.ops.append(f"BT /{'F2' if bold else 'F1'} {size} Tf {x} {y} Td ({_esc(s)}) Tj ET")
        return self

    def lines(self, x, top, size, strings, leading=None, bold=False):
        leading = leading or size * 1.3
        for i, s in enumerate(strings):
            self.text(x, top + i * leading, size, s, bold)
        return self

    def rule(self, x0, top0, x1, top1):
        self.ops.append(f"{x0} {PAGE_H - top0} m {x1} {PAGE_H - top1} l S")
        return self

    def grid(self, x, top, col_w, row_h, cols, rows):
        for r in range(rows + 1):
            self.rule(x, top + r * row_h, x + cols * col_w, top + r * row_h)
        for c in range(cols + 1):
            self.rule(x + c * col_w, top, x + c * col_w, top + rows * row_h)
        return self

    def image(self, x, top, w, h):
        name = f"Im{len(self.images) + 1}"
        self.images.append((name, 2, 2, bytes([200, 30, 30] * 4)))
        self.ops.append(f"q {w} 0 0 {h} {x} {PAGE_H - top - h} cm /{name} Do Q")
        return self


def build_pdf(pages, title=None, lang=None, tagged=False):
    objs = []  # list of bytes bodies, 1-indexed by position + 1

    def add(body):
        objs.append(body if isinstance(body, bytes) else body.encode("latin-1"))
        return len(objs)

    cat = add("")      # 1 placeholder
    pgs = add("")      # 2 placeholder
    f1 = add("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    f2 = add("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>")
    kids = []
    for pg in pages:
        img_refs = []
        for (name, w, h, rgb) in pg.images:
            ref = add(b"<< /Type /XObject /Subtype /Image /Width %d /Height %d /ColorSpace /DeviceRGB /BitsPerComponent 8 /Length %d >>\nstream\n" % (w, h, len(rgb)) + rgb + b"\nendstream")
            img_refs.append(f"/{name} {ref} 0 R")
        stream = "\n".join(pg.ops)
        content = add(f"<< /Length {len(stream)} >>\nstream\n{stream}\nendstream")
        xobj = f"/XObject << {' '.join(img_refs)} >>" if img_refs else ""
        page = add(f"<< /Type /Page /Parent {pgs} 0 R /MediaBox [0 0 {PAGE_W} {PAGE_H}] /Contents {content} 0 R "
                   f"/Resources << /Font << /F1 {f1} 0 R /F2 {f2} 0 R >> {xobj} >> >>")
        kids.append(page)
    extra = ""
    if lang:
        extra += f" /Lang ({lang})"
    if tagged:
        struct = add("<< /Type /StructTreeRoot >>")
        extra += f" /MarkInfo << /Marked true >> /StructTreeRoot {struct} 0 R"
    objs[cat - 1] = f"<< /Type /Catalog /Pages {pgs} 0 R{extra} >>".encode("latin-1")
    objs[pgs - 1] = f"<< /Type /Pages /Kids [{' '.join(f'{k} 0 R' for k in kids)}] /Count {len(kids)} >>".encode("latin-1")
    info = ""
    if title:
        info_ref = add(f"<< /Title ({_esc(title)}) >>")
        info = f" /Info {info_ref} 0 R"

    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, body in enumerate(objs, 1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(objs) + 1} /Root {cat} 0 R{info} >>\nstartxref\n{xref}\n%%EOF".encode()
    return bytes(out)
