"""Extract the month well sheets from a PDF print of Hayah's Excel workbook.

Usage:  python scripts/workbook_pdf_extract.py book.pdf out.json

A PDF is a picture of the sheets, not the sheets themselves, so this is a best
effort: Excel splits each sheet's columns across several pages, and Arabic text
comes out in visual order. Rows are matched across pages by their height on the
page. Every row keeps the page numbers it came from, and anything that cannot be
read cleanly is listed under "problems" for a person to check. An .xlsx export
of the workbook gives an exact import and should be preferred.

Needs pdfplumber (pip install pdfplumber). Not used by the running app.
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime

import pdfplumber

AR = re.compile(r"[؀-ۿ]")
LATIN_RUN = re.compile(r"[A-Za-z0-9$.,/()\-+:#@&%]+(?: [A-Za-z0-9$.,/()\-+:#@&%]+)*")
DATE = re.compile(r"^\d{2}/\d{2}/\d{4}$")
MONEY = re.compile(r"^\(?\$[\d,]+(?:\.\d+)?\)?$|^-$")
CONTRACTOR = re.compile(r"^(Pak|Nep|India|Bang|Tiz|TZ|Tz)\s*\d+$", re.I)

# The month sheets found in the PDF: (sheet, list of page bands left to right).
# Each band is the list of pages that hold one slice of the columns, in row order.
SHEETS = [
    ("2026-04", [[6, 7], [8, 9]]),
    ("2026-05", [[10, 11], [12, 13]]),
    ("2026-06", [[14], [15]]),
    ("2026-07", [[16], [17]]),
    ("2026-08", [[18], [19]]),
    ("2026-09", [[26, 27], [28, 29], [30, 31]]),
]

HEADERS = {  # header text in the PDF -> field
    "الرقم": "well_id", "تاريخ الطلب": "order_date", "اسم البئر": "customer_name",
    "تاريخ الاستلام": "received_date", "تاريخ التسليم": "delivery_date", "المقاول": "contractor",
    "نوع البئر": "well_type", "التكلفة": "cost", "سعر البيع": "sale_amount", "الربح": "profit",
    "متابع": "follow_up", "تاريخ المتابعة": "follow_up", "notes": "notes", "مصدر الشراء": "sales_source",
    "مصدر الشزا،": "sales_source", "طريقة الدفع": "payment_method", "الإضافات": "extras",
}
TOTAL_WORDS = ("الإجمالي", "الاجمالي", "Total", "TOTAL")


def _width(c):
    return c["x1"] - c["x0"]


def page_lines(pg):
    """Lines of a page, each a list of {x0, x1, t} cells, Arabic put in reading order."""
    chars = pg.chars
    solid = [c for c in chars if _width(c) > 1.0 and c["text"].strip()]
    tops = sorted({round(c["top"], 1) for c in solid})
    clusters: list[list[float]] = []
    for t in tops:
        if clusters and t - clusters[-1][-1] <= 2.0:
            clusters[-1].append(t)
        else:
            clusters.append([t])
    centers = [sum(c) / len(c) for c in clusters]
    buckets: dict[int, list] = {i: [] for i in range(len(centers))}
    for c in chars:
        if not centers:
            break
        i = min(range(len(centers)), key=lambda k: abs(centers[k] - c["top"]))
        if abs(centers[i] - c["top"]) < 9:  # marks drawn a little above/below the line
            buckets[i].append(c)
    out = []
    for i, cs in buckets.items():
        sol = [c for c in cs if _width(c) > 0.3]

        def key(c):
            # Zero-width marks (a final ر, a trailing ي) sit inside the glyph they follow.
            if _width(c) > 0.3:
                return c["x0"]
            hosts = [h for h in sol if h["x0"] - 0.5 <= c["x0"] <= h["x1"] + 0.5 and h["text"].strip()]
            return (min(hosts, key=lambda h: h["x0"])["x0"] - 0.001) if hosts else c["x0"]

        cs.sort(key=key)
        segs, cur = [], []
        for c in cs:
            sx = [x["x1"] for x in cur if _width(x) > 0.3]
            if cur and sx and key(c) - max(sx) > 6.0:
                segs.append(cur)
                cur = []
            cur.append(c)
        if cur:
            segs.append(cur)
        cells = []
        for s in segs:
            txt = "".join(c["text"] for c in s)
            if AR.search(txt):
                txt = "".join(c["text"] for c in reversed(s))
                txt = LATIN_RUN.sub(lambda m: m.group(0)[::-1], txt)
            txt = re.sub(r"\s+", " ", txt).strip()
            if txt:
                cells.append({"x0": s[0]["x0"], "x1": max(c["x1"] for c in s), "t": txt})
        if cells:
            out.append({"top": round(centers[i], 1), "cells": cells})
    return out


def _norm_header(t):
    return t.replace("تاري خ", "تاريخ").replace("الرب ح", "الربح").strip()


def _columns(lines):
    """Header line of a band -> list of (field, x-center)."""
    for ln in lines[:2]:
        cols = [(HEADERS.get(_norm_header(c["t"])), (c["x0"] + c["x1"]) / 2) for c in ln["cells"]]
        if sum(1 for f, _ in cols if f) >= 2:
            return [(f, x) for f, x in cols if f], ln["top"]
    return None, None


def _money(t):
    if t in ("-", ""):
        return None
    neg = t.startswith("(")
    v = float(t.strip("()$").replace(",", ""))
    return -v if neg else v


def _date(t):
    """The sheets use month/day/year. A value that only works as day/month is
    read that way and reported, never silently guessed."""
    try:
        return datetime.strptime(t, "%m/%d/%Y").date().isoformat(), None
    except ValueError:
        return datetime.strptime(t, "%d/%m/%Y").date().isoformat(), f"date {t} typed day/month/year; read as {t[:2]} {datetime.strptime(t, '%d/%m/%Y'):%B}"


def extract(pdf_path):
    pdf = pdfplumber.open(pdf_path)
    result = {"source": pdf_path, "sheets": [], "problems": []}
    for month, bands in SHEETS:
        band_rows = []  # per band: list of (page_index_in_band, top, {field: text})
        totals = {}
        for band in bands:
            cols = None
            rows = []
            for k, pno in enumerate(band):
                lines = page_lines(pdf.pages[pno - 1])
                if k == 0:
                    cols, htop = _columns(lines)
                    lines = [ln for ln in lines if ln["top"] > htop]
                for ln in lines:
                    if any(c["t"] in TOTAL_WORDS for c in ln["cells"]):
                        for c in ln["cells"]:
                            if MONEY.match(c["t"]):
                                f = min(cols, key=lambda fx: abs(fx[1] - (c["x0"] + c["x1"]) / 2))[0]
                                totals[f] = _money(c["t"])
                        continue
                    vals: dict[str, str] = {}
                    for c in ln["cells"]:
                        cx = (c["x0"] + c["x1"]) / 2
                        f = min(cols, key=lambda fx: abs(fx[1] - cx))[0]
                        vals[f] = (vals[f] + " " + c["t"]) if f in vals else c["t"]
                    rows.append((pno, ln["top"], vals))
            band_rows.append(rows)
        # Join bands: same page position in the band + same height on the page.
        base = band_rows[0]
        sheet_rows = []
        for i, (pno, top, vals) in enumerate(base):
            page_pos = bands[0].index(pno)
            row = {"_pages": [pno], "_line": i}
            row.update(vals)
            for b, rows in enumerate(band_rows[1:], start=1):
                want_page = bands[b][page_pos]
                match = [r for r in rows if r[0] == want_page and abs(r[1] - top) < 3]
                if match:
                    row["_pages"].append(want_page)
                    for f, v in match[0][2].items():
                        row[f] = (row[f] + " " + v) if f in row and isinstance(row[f], str) else v
            sheet_rows.append(row)
        result["sheets"].append({"month": month, "rows": [clean(r, month, result["problems"]) for r in sheet_rows],
                                 "pdf_totals": totals})
    return result


WELL_TYPES = {  # as written in the sheet -> kept as written (the sheet is the source)
}


def clean(r, month, problems):
    out = {"month": month, "pages": r["_pages"]}
    r = dict(r)
    # A long name can spill into the next column on the printed page: split it back.
    for f in ("order_date", "received_date", "delivery_date"):
        v = r.get(f) or ""
        m = re.search(r"\d{2}/\d{2}/\d{4}", v)
        if m and v.strip() != m.group(0):
            rest = (v[:m.start()] + v[m.end():]).strip()
            r[f] = m.group(0)
            if AR.search(rest) and not r.get("customer_name"):
                r["customer_name"] = rest
            elif rest:
                r["customer_name"] = (r.get("customer_name", "") + " " + rest).strip()
    # "- ($50)" in the profit column = an empty sale price plus the profit.
    p = (r.get("profit") or "").split()
    if len(p) == 2 and "sale_amount" not in r:
        r["sale_amount"], r["profit"] = p
    def note(msg):
        problems.append({"month": month, "well_id": out.get("well_id"), "pages": r["_pages"], "problem": msg})
    wid = r.get("well_id", "")
    if re.fullmatch(r"\d{3,6}", wid or ""):
        out["well_id"] = int(wid)
    else:
        out["well_id"] = None
        note(f"no clear Well ID in this row ({wid!r}); not imported")
    for f in ("order_date", "received_date", "delivery_date"):
        v = r.get(f)
        if v:
            if DATE.match(v):
                out[f], warn = _date(v)
                if warn:
                    note(f"{f}: {warn}")
            else:
                note(f"{f} is not a date: {v!r}")
    for f in ("cost", "sale_amount", "profit"):
        v = r.get(f)
        if v is None:
            continue
        if MONEY.match(v):
            out[f] = _money(v)
        else:
            note(f"{f} is not an amount: {v!r}")
    c = r.get("contractor")
    if c:
        if CONTRACTOR.match(c):
            out["contractor"] = c
        else:
            note(f"contractor not recognised: {c!r}")
    for f in ("customer_name", "well_type", "payment_method", "extras", "sales_source", "follow_up", "notes"):
        if r.get(f):
            # a final ي or ن printed as a separate mark comes out as "حسي ن"
            out[f] = re.sub(r"(?<=[؀-ۿ]) ([ين])(?=\s|$)", r"\1", r[f])
    if out.get("cost") is not None and out.get("cost") < 0:
        note("negative cost")
    return out


if __name__ == "__main__":
    data = extract(sys.argv[1])
    json.dump(data, open(sys.argv[2], "w"), ensure_ascii=False, indent=1)
    for s in data["sheets"]:
        rows = [r for r in s["rows"] if r.get("well_id")]
        tot = {f: round(sum(r.get(f) or 0 for r in rows), 2) for f in ("cost", "sale_amount", "profit")}
        print(s["month"], len(rows), "wells", rows[0]["well_id"] if rows else "", "-", rows[-1]["well_id"] if rows else "",
              "sum", tot, "pdf totals", s["pdf_totals"])
    print(len(data["problems"]), "problems")
