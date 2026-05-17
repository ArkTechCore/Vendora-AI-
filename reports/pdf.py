from __future__ import annotations

from io import BytesIO

from PIL import Image


PAGE_WIDTH = 612
PAGE_HEIGHT = 792
MARGIN = 42
CONTENT_WIDTH = PAGE_WIDTH - (MARGIN * 2)


def _escape(text):
    return str(text).replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _money(value):
    try:
        return f"${float(value):,.2f}"
    except (TypeError, ValueError):
        return str(value)


def _quantity(value):
    try:
        text = f"{float(value):,.3f}".rstrip("0").rstrip(".")
        return text or "0"
    except (TypeError, ValueError):
        return str(value)


def _wrap(text, width=38):
    words = str(text or "").split()
    lines = []
    current = ""
    for word in words or [""]:
        candidate = f"{current} {word}".strip()
        if len(candidate) <= width:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word[:width]
    if current:
        lines.append(current)
    return lines or [""]


def _fit_lines(text, width_points, size=10):
    chars = max(4, int(width_points / (size * 0.54)))
    return _wrap(text, chars)


class SimplePDF:
    def __init__(self, title):
        self.title = title
        self.pages = []
        self.lines = []
        self.images = []
        self.y = PAGE_HEIGHT - MARGIN

    def _new_page(self):
        self.pages.append(self.lines)
        self.lines = []
        self.y = PAGE_HEIGHT - MARGIN

    def _ensure_space(self, height):
        if self.y - height < MARGIN:
            self._new_page()
            return True
        return False

    def _text_width(self, text, size=10, bold=False):
        weight = 0.58 if bold else 0.54
        return min(len(str(text)) * size * weight, CONTENT_WIDTH)

    def text(self, text, x=MARGIN, y=None, size=10, bold=False, color=(0.17, 0.23, 0.25)):
        if y is None:
            y = self.y
        font = "F2" if bold else "F1"
        r, g, b = color
        self.lines.append(f"{r:.3f} {g:.3f} {b:.3f} rg")
        self.lines.append(f"BT /{font} {size} Tf {x:.2f} {y:.2f} Td ({_escape(text)}) Tj ET")

    def right_text(self, text, x_right=PAGE_WIDTH - MARGIN, y=None, size=10, bold=False, color=(0.17, 0.23, 0.25)):
        width = self._text_width(text, size=size, bold=bold)
        self.text(text, x=x_right - width, y=y, size=size, bold=bold, color=color)

    def line(self, y=None, x1=MARGIN, x2=PAGE_WIDTH - MARGIN, width=1, color=(0.2, 0.25, 0.27)):
        if y is None:
            y = self.y
        r, g, b = color
        self.lines.append(f"{r:.3f} {g:.3f} {b:.3f} RG")
        self.lines.append(f"{width:.2f} w {x1:.2f} {y:.2f} m {x2:.2f} {y:.2f} l S")

    def rect(self, x, y, w, h, fill=(0.86, 0.89, 0.90)):
        r, g, b = fill
        self.lines.append(f"{r:.3f} {g:.3f} {b:.3f} rg")
        self.lines.append(f"{x:.2f} {y:.2f} {w:.2f} {h:.2f} re f")

    def image(self, path, x, y, width, height):
        name = None
        for existing in self.images:
            if existing["path"] == path:
                name = existing["name"]
                break
        if not name:
            with Image.open(path) as image:
                name = f"Im{len(self.images) + 1}"
                self.images.append({
                    "name": name,
                    "path": path,
                    "width": image.width,
                    "height": image.height,
                    "mode": image.mode,
                })
        self.lines.append(f"q {width:.2f} 0 0 {height:.2f} {x:.2f} {y:.2f} cm /{name} Do Q")

    def add_document_header(self, business, meta):
        self._ensure_space(170)
        logo_path = business.get("logo_path")
        if logo_path:
            self.image(logo_path, MARGIN, self.y - 70, 70, 70)
            title_x = MARGIN + 92
        else:
            title_x = MARGIN
        self.text("VendoraOps", x=title_x, y=self.y - 4, size=20, bold=True, color=(0.13, 0.18, 0.20))
        self.text("Restaurant operations, inventory, cash control, and reporting", x=title_x, y=self.y - 24, size=8, bold=True, color=(0.38, 0.43, 0.47))
        self.text((business.get("name") or "Business").upper(), x=title_x, y=self.y - 48, size=11, bold=True)
        left_lines = [
            business.get("owner_name") or "",
            business.get("phone") or "",
            business.get("email") or "",
        ]
        y = self.y - 64
        for line in [value for value in left_lines if value]:
            self.text(line, x=title_x, y=y, size=9)
            y -= 14

        self.right_text("REPORT", y=self.y - 4, size=18, bold=True, color=(0.13, 0.18, 0.20))
        right_x = 372
        y = self.y - 44
        for label, value in meta:
            self.text(label.upper(), x=right_x, y=y, size=10, bold=True)
            self.text(value, x=right_x + 108, y=y, size=10)
            y -= 16

        self.y -= 124
        self.line(width=1.4, color=(0.22, 0.27, 0.29))
        self.y -= 20

    def add_report_title(self, title, meta, logo_path=None):
        self._ensure_space(104)
        if logo_path:
            self.image(logo_path, MARGIN, self.y - 40, 40, 40)
            brand_x = MARGIN + 58
        else:
            brand_x = MARGIN
        self.text("VendoraOps", x=brand_x, y=self.y - 2, size=14, bold=True, color=(0.13, 0.18, 0.20))
        self.text("Restaurant operations reporting", x=brand_x, y=self.y - 18, size=8, bold=True, color=(0.38, 0.43, 0.47))
        self.text(title.upper(), x=brand_x, y=self.y - 42, size=17, bold=True)
        self.right_text("REPORT", y=self.y - 2, size=12, bold=True, color=(0.38, 0.43, 0.47))
        self.y -= 68
        x = brand_x
        for label, value in meta:
            self.text(label.upper(), x=x, y=self.y, size=9, bold=True)
            self.text(value, x=x + 88, y=self.y, size=9)
            self.y -= 14
        self.y -= 8
        self.line(width=1.2, color=(0.22, 0.27, 0.29))
        self.y -= 22

    def add_section(self, title):
        self._ensure_space(58)
        self.line(width=1.1, color=(0.22, 0.27, 0.29))
        self.y -= 20
        self.text(title.upper(), y=self.y, size=12, bold=True)
        self.y -= 20

    def add_table(self, headers, rows, columns):
        base_row_h = 26
        line_h = 13
        row_pad_top = 10
        row_pad_bottom = 10

        def draw_header():
            header_y = self.y
            x = MARGIN
            for column in columns:
                header, width, _align = column[:3]
                self.text(header.upper()[:max(3, int(width / 6))], x=x + 3, y=header_y, size=9, bold=True)
                x += width
            self.y -= 12
            self.line(width=1.1)
            self.y -= 24

        draw_header()

        if not rows:
            self.rect(MARGIN, self.y - 5, CONTENT_WIDTH, base_row_h, fill=(0.93, 0.95, 0.96))
            self.text("No records for this report.", y=self.y + 4, size=10)
            self.y -= base_row_h + 4
            return

        for index, row in enumerate(rows):
            wrapped = []
            max_lines = 1
            for value, column in zip(row, columns):
                _header, width, align = column[:3]
                wrap = column[3] if len(column) > 3 else align != "right"
                display = str(value)
                lines = _fit_lines(display, width - 8) if wrap else [display[:max(4, int(width / 5.4))]]
                wrapped.append((lines, column))
                max_lines = max(max_lines, len(lines))
            row_h = max(base_row_h, (line_h * max_lines) + row_pad_top + row_pad_bottom)
            if self._ensure_space(row_h + 44):
                draw_header()
            row_top = self.y + row_pad_top
            row_bottom = row_top - row_h
            if index % 2 == 0:
                self.rect(MARGIN, row_bottom, CONTENT_WIDTH, row_h, fill=(0.87, 0.92, 0.95))
            x = MARGIN
            for lines, column in wrapped:
                _header, width, align = column[:3]
                if align == "right":
                    display = lines[0]
                    self.right_text(display, x_right=x + width - 4, y=self.y, size=9, bold=display.startswith("$"))
                else:
                    for line_index, line in enumerate(lines):
                        self.text(line, x=x + 3, y=self.y - (line_index * line_h), size=9)
                x += width
            self.y -= row_h
        self.line(y=self.y + 8, width=1)
        self.y -= 22

    def add_summary_grid(self, rows):
        rows = list(rows)
        self.add_section("Summary")
        col_w = CONTENT_WIDTH / 2
        row_h = 30
        for index in range(0, len(rows), 2):
            self._ensure_space(row_h + 8)
            self.rect(MARGIN, self.y - 8, CONTENT_WIDTH, row_h, fill=(0.94, 0.96, 0.96) if index % 4 == 0 else (1, 1, 1))
            for offset, row in enumerate(rows[index:index + 2]):
                x = MARGIN + (offset * col_w)
                label, value = row
                self.text(str(label).upper(), x=x + 4, y=self.y + 1, size=9, bold=True)
                self.right_text(str(value), x_right=x + col_w - 8, y=self.y + 1, size=10, bold=True)
            self.y -= row_h
        self.y -= 14

    def add_totals_block(self, rows):
        self._ensure_space(36 + (len(rows) * 18))
        self.line(width=1.4)
        self.y -= 21
        label_x = 360
        for label, value in rows:
            self.text(label.upper(), x=label_x, y=self.y, size=11, bold=True)
            self.right_text(value, y=self.y, size=11, bold=True)
            self.y -= 18
        self.y -= 8

    def add_footer(self, text="Generated by VendoraOps. Restaurant operations, inventory, cash control, and reporting.", logo_path=None):
        self._ensure_space(58)
        self.line(width=0.6, color=(0.82, 0.84, 0.86))
        self.y -= 20
        if logo_path:
            self.image(logo_path, MARGIN, self.y - 14, 22, 22)
            self.text("VendoraOps", x=MARGIN + 30, y=self.y, size=11, bold=True, color=(0.02, 0.42, 0.46))
            self.text(text, x=MARGIN + 30, y=self.y - 14, size=8, color=(0.38, 0.43, 0.47))
        else:
            self.text("VendoraOps", size=11, bold=True, color=(0.02, 0.42, 0.46))
            self.text(text, y=self.y - 14, size=8, color=(0.38, 0.43, 0.47))

    def render(self):
        if self.lines:
            self.pages.append(self.lines)

        objects = [
            b"<< /Type /Catalog /Pages 2 0 R >>",
            None,
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>",
        ]

        image_object_numbers = {}
        for image in self.images:
            with open(image["path"], "rb") as handle:
                image_bytes = handle.read()
            color_space = "/DeviceCMYK" if image["mode"] == "CMYK" else "/DeviceRGB"
            image_object_numbers[image["name"]] = len(objects) + 1
            objects.append(
                f"<< /Type /XObject /Subtype /Image /Width {image['width']} /Height {image['height']} "
                f"/ColorSpace {color_space} /BitsPerComponent 8 /Filter /DCTDecode "
                f"/Length {len(image_bytes)} >>\nstream\n".encode() + image_bytes + b"\nendstream"
            )

        page_object_indexes = []
        content_object_indexes = []
        for page_lines in self.pages:
            content = "\n".join(page_lines).encode("latin-1", "replace")
            content_obj = f"<< /Length {len(content)} >>\nstream\n".encode() + content + b"\nendstream"
            content_object_indexes.append(len(objects) + 1)
            objects.append(content_obj)
            page_object_indexes.append(len(objects) + 1)
            objects.append(
                f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {PAGE_WIDTH} {PAGE_HEIGHT}] "
                f"/Resources << /Font << /F1 3 0 R /F2 4 0 R >> {_xobject_resource(image_object_numbers)} >> "
                f"/Contents {content_object_indexes[-1]} 0 R >>".encode()
            )

        kids = " ".join(f"{idx} 0 R" for idx in page_object_indexes)
        objects[1] = f"<< /Type /Pages /Kids [{kids}] /Count {len(page_object_indexes)} >>".encode()

        output = BytesIO()
        output.write(b"%PDF-1.4\n")
        offsets = [0]
        for idx, obj in enumerate(objects, start=1):
            offsets.append(output.tell())
            output.write(f"{idx} 0 obj\n".encode())
            output.write(obj)
            output.write(b"\nendobj\n")
        xref = output.tell()
        output.write(f"xref\n0 {len(objects) + 1}\n".encode())
        output.write(b"0000000000 65535 f \n")
        for offset in offsets[1:]:
            output.write(f"{offset:010d} 00000 n \n".encode())
        output.write(
            f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref}\n%%EOF".encode()
        )
        return output.getvalue()


__all__ = ["SimplePDF", "_money", "_quantity"]


def _xobject_resource(image_object_numbers):
    if not image_object_numbers:
        return ""
    refs = " ".join(f"/{name} {number} 0 R" for name, number in image_object_numbers.items())
    return f"/XObject << {refs} >>"
