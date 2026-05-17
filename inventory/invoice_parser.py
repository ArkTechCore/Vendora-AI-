import re
from datetime import datetime
from decimal import Decimal, InvalidOperation

from pypdf import PdfReader


MONEY_RE = re.compile(r"\$?\s*([0-9][0-9,]*(?:\.[0-9]{2})?)")
DATE_RE = re.compile(r"(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}[/-]\d{1,2}[/-]\d{1,2})")
WORD_DATE_RE = re.compile(r"([A-Z][a-z]+ \d{1,2}, \d{4})")
INVOICE_RE = re.compile(r"(?:invoice|inv)\s*(?:number|no|#)?\s*[:#]?\s*([A-Z0-9-]{3,})", re.I)
TOTAL_RE = re.compile(r"(?:grand\s+total|invoice\s+total|total)\s*[:$ ]+\s*\$?\s*([0-9][0-9,]*(?:\.[0-9]{2})?)", re.I)
ITEM_RE = re.compile(
    r"^(?P<name>.+?)\s+\$?\s*(?P<rate>[0-9][0-9,]*(?:\.[0-9]{2})?)\s+"
    r"(?P<qty>[0-9][0-9,]*(?:\.[0-9]{1,3})?)\s+\$?\s*(?P<amount>[0-9][0-9,]*(?:\.[0-9]{2})?)$",
    re.I,
)


def _to_decimal(value):
    try:
        return Decimal(str(value).replace(",", "")).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        return None


def _to_date(value):
    for fmt in ("%m/%d/%Y", "%m/%d/%y", "%m-%d-%Y", "%m-%d-%y", "%Y-%m-%d", "%Y/%m/%d", "%B %d, %Y", "%b %d, %Y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


def _find_value_after_label(lines, label):
    label = label.lower()
    for index, line in enumerate(lines):
        if line.lower() == label and index + 1 < len(lines):
            return lines[index + 1].strip()
    return ""


def extract_pdf_text(uploaded_file):
    uploaded_file.seek(0)
    reader = PdfReader(uploaded_file)
    text = "\n".join(page.extract_text() or "" for page in reader.pages)
    uploaded_file.seek(0)
    return text


def parse_purchase_invoice(uploaded_file, ingredients, vendors):
    text = extract_pdf_text(uploaded_file)
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    joined = "\n".join(lines)

    invoice_number = ""
    invoice_match = INVOICE_RE.search(joined)
    if invoice_match:
        invoice_number = invoice_match.group(1)
    else:
        invoice_number = _find_value_after_label(lines, "invoice")

    invoice_date = None
    date_value = _find_value_after_label(lines, "date")
    if date_value:
        invoice_date = _to_date(date_value)
    if invoice_date is None:
        date_match = DATE_RE.search(joined) or WORD_DATE_RE.search(joined)
        if date_match:
            invoice_date = _to_date(date_match.group(1))

    total = None
    total_match = TOTAL_RE.search(joined)
    if total_match:
        total = _to_decimal(total_match.group(1))

    vendor_id = None
    lower_text = joined.lower()
    for vendor in vendors:
        if vendor.name.lower() in lower_text:
            vendor_id = vendor.id
            break

    rows = []
    for ingredient in ingredients:
        ingredient_name = ingredient.name.lower()
        for line in lines:
            if ingredient_name not in line.lower():
                continue
            item_match = ITEM_RE.match(line)
            if item_match:
                rows.append({
                    "ingredient_id": ingredient.id,
                    "quantity": _to_decimal(item_match.group("qty")) or Decimal("0.00"),
                    "total_cost": _to_decimal(item_match.group("amount")) or Decimal("0.00"),
                    "source_line": line,
                })
                break
            numbers = [_to_decimal(match) for match in MONEY_RE.findall(line)]
            numbers = [number for number in numbers if number is not None]
            if not numbers:
                continue
            quantity = numbers[0]
            total_cost = numbers[-1] if len(numbers) > 1 else Decimal("0.00")
            rows.append({
                "ingredient_id": ingredient.id,
                "quantity": quantity,
                "total_cost": total_cost,
                "source_line": line,
            })
            break

    return {
        "invoice_number": invoice_number,
        "invoice_date": invoice_date,
        "vendor_id": vendor_id,
        "total": total,
        "rows": rows[:20],
        "text_found": bool(joined.strip()),
    }
