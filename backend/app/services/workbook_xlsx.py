"""Read Hayah's Excel workbook (.xlsx) into one plain dict that the importer loads.

What is read (sheet names as in the workbook):
  * April … Nov            -> wells (month sheets)
  * S MAY, S OCT, S NOV    -> sacrifices
  * Pak 1-5, Bang 1, Nep 1-2, India 1-3, Ahmed Masri -> contractor payments and extra charges
  * UK Account             -> Wise bank rows
  * Mo, Ghazi, Cliq        -> partner accounts
  * Ads                    -> ad channel for each ad row, and ads paid by partners
  * TANZANIA               -> Tanzania trip expenses
  * Financial Summary      -> the workbook's own totals, used only to check the import
Nothing is guessed silently: every judgement call is written to "problems".
"""
from __future__ import annotations

import re
import warnings
from datetime import date, datetime, timedelta
from decimal import Decimal

WELL_SHEETS = {"April": "2026-04", "May": "2026-05", "June": "2026-06", "July": "2026-07", "Aug": "2026-08",
               "Sep": "2026-09", "Oct": "2026-10", "Nov": "2026-11"}
SAC_SHEETS = {"S MAY": "2026-05", "S OCT": "2026-10", "S NOV": "2026-11"}
LEDGERS = ["Pak 1", "Pak 2", "Pak 3", "Pak 4", "Pak 5", "Bang 1", "Nep 1", "Nep 2", "India 1", "India 2", "India 3", "Ahmed Masri"]

WELL_HEADERS = {
    "الرقم": "well_id", "تاريخ الطلب": "order_date", "اسم البئر": "customer_name", "تاريخ الاستلام": "received_date",
    "تاريخ التسليم": "delivery_date", "المقاول": "contractor", "نوع البئر": "well_type", "التكلفة": "cost",
    "سعر البيع": "sale_amount", "طريقة الدفع": "payment_method", "الإضافات": "extras", "مصدر الشراء": "sales_source",
    "مصدر الشزا،": "sales_source", "متابع": "follow_up", "تاريخ المتابعة": "follow_up", "notes": "notes", "": "notes2",
}
SAC_HEADERS = {
    "الرقم": "sacrifice_no", "تاريخ الطلب": "order_date", "اسم الأضحية": "donor_name", "اسم الذبيحة": "donor_name", "تاريخ الاستلام": "received_date",
    "تاريخ التسليم": "delivery_date", "المقاول": "contractor", "نوع الأضحية": "animal_type", "نوع الذبيحة": "animal_type", "نوع": "animal_type",
    "التكلفة": "cost", "التكلفة (Out)": "cost", "سعر البيع": "sale_price", "سعر البيع (In)": "sale_price",
    "طريقة الدفع": "payment_method", "الإضافات": "extras", "مصدر الشراء": "sales_source", "ملاحظات": "intention",
}
# UK Account category -> transaction kind
UK_KIND = {
    "Income": "income", "Advertising": "ad_spend", "Contractor payment": "contractor_payment",
    "Partner transfer": "transfer", "Tanzania trip": "transfer", "Cancelled (refunded)": "other", "Unclear – ask": "other",
    "Company admin": "operating_expense", "Software & AI": "operating_expense", "Website": "operating_expense",
    "Equipment": "operating_expense", "Travel & other": "operating_expense", "Content": "operating_expense",
    "Operating – water projects": "operating_expense",
}
COST_OF_GOODS_WORDS = ("contractor", "wells", "adahi")  # partner outs that are well/sacrifice costs, not overheads


def contractor_code(text) -> str | None:
    if not text:
        return None
    t = str(text).strip().lower()
    if t == "ahmed masri":
        return "TZ1"
    m = re.fullmatch(r"(pak|pk|nep|india|bang|tz|tiz)\s*(\d+)", t)
    if not m:
        return None
    pre = {"pak": "PAK", "pk": "PAK", "nep": "NEP", "india": "IND", "bang": "BANG", "tz": "TZ", "tiz": "TZ"}[m.group(1)]
    return f"{pre}{int(m.group(2))}"


def hint_contractor(desc: str) -> str | None:
    d = (desc or "").lower()
    found = set()
    for m in re.finditer(r"\b(pak|pk)\s*(\d)", d):
        found.add(f"PAK{m.group(2)}")
    for m in re.finditer(r"\bindia\s*(\d)", d):
        found.add(f"IND{m.group(1)}")
    if "bang" in d:
        found.add("BANG1")
    if "ahmed masri" in d:
        found.add("TZ1")
    return found.pop() if len(found) == 1 else None


def _num(v) -> Decimal | None:
    if v is None or (isinstance(v, str) and not v.strip()):
        return None
    if isinstance(v, (int, float)):
        return Decimal(str(round(v, 2)))
    try:
        return Decimal(str(v).replace("$", "").replace(",", "").strip())
    except Exception:
        return None


class Reader:
    def __init__(self, path):
        import openpyxl
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            self.wb = openpyxl.load_workbook(path, data_only=True)
        self.sheets = {ws.title.strip(): ws for ws in self.wb.worksheets}
        self.out = {"wells": [], "sacrifices": [], "transactions": [], "ledger_costs": [], "problems": [], "expected": {}}

    def problem(self, where, msg, kind="check"):
        self.out["problems"].append({"where": where, "problem": msg, "kind": kind})

    def date(self, v, where, field="date"):
        """Returns (date | None, leftover text)."""
        if v is None or (isinstance(v, str) and not v.strip()):
            return None, None
        if isinstance(v, datetime):
            return v.date(), None
        if isinstance(v, date):
            return v, None
        if isinstance(v, (int, float)) and 40000 < v < 60000:  # an Excel date serial left as a number
            return date(1899, 12, 30) + timedelta(days=int(v)), None
        s = str(v).strip()
        for fmt in ("%m/%d/%Y", "%Y-%m-%d"):
            try:
                return datetime.strptime(s, fmt).date(), None
            except ValueError:
                pass
        try:
            d = datetime.strptime(s, "%d/%m/%Y").date()
            self.problem(where, f"{field} '{s}' is day/month/year; read as {d:%d %b %Y}", "info")
            return d, None
        except ValueError:
            return None, s

    def rows(self, name, min_row=2):
        ws = self.sheets[name]
        hdr = [(str(c.value).strip() if c.value is not None else "") for c in ws[1]]
        for r in ws.iter_rows(min_row=min_row, max_row=min(ws.max_row, 2000)):
            yield r[0].row, hdr, [c.value for c in r]

    # ---------- wells ----------
    def wells(self):
        for name, month in WELL_SHEETS.items():
            if name not in self.sheets:
                self.problem(name, "sheet not found")
                continue
            for rown, hdr, vals in self.rows(name):
                rec = {}
                for i, h in enumerate(hdr[:16]):
                    f = WELL_HEADERS.get(h)
                    if f and i < len(vals) and vals[i] is not None and f not in rec:
                        rec[f] = vals[i]
                wid = rec.get("well_id")
                if wid is None:
                    continue
                where = f"{name}!A{rown}"
                w = {"month": month, "sheet": name, "row": rown}
                if isinstance(wid, (int, float)) and float(wid).is_integer():
                    w["well_id"] = int(wid)
                else:
                    w["well_id"] = None
                    w["raw_id"] = str(wid)
                    self.problem(where, f"Well ID '{wid}' is not a number, so this row was not imported as a well "
                                        f"(its cost is still on the contractor's tab as an extra charge)", "action")
                notes = []
                for f in ("order_date", "received_date", "delivery_date"):
                    d, left = self.date(rec.get(f), where, f)
                    w[f] = d
                    if left:
                        notes.append(f"{f.replace('_', ' ')}: {left}")
                for f in ("cost", "sale_amount"):
                    w[f] = _num(rec.get(f))
                c = rec.get("contractor")
                w["contractor"] = contractor_code(c)
                if c and not w["contractor"]:
                    self.problem(where, f"contractor '{c}' not recognised")
                for f in ("customer_name", "well_type", "payment_method", "extras", "sales_source"):
                    v = rec.get(f)
                    w[f] = str(v).strip() if v is not None and str(v).strip() else None
                for f in ("follow_up", "notes", "notes2"):
                    v = rec.get(f)
                    if v is not None and str(v).strip():
                        v = v.date().isoformat() if isinstance(v, datetime) else str(v).strip()
                        notes.append(f"Follow-up: {v}" if f == "follow_up" else v)
                w["notes"] = notes
                self.out["wells"].append(w)

    # ---------- sacrifices ----------
    def sacrifices(self):
        for name, month in SAC_SHEETS.items():
            if name not in self.sheets:
                self.problem(name, "sheet not found")
                continue
            for rown, hdr, vals in self.rows(name):
                rec = {}
                for i, h in enumerate(hdr[:15]):
                    f = SAC_HEADERS.get(h)
                    if f and i < len(vals) and vals[i] is not None and f not in rec:
                        rec[f] = vals[i]
                no = rec.get("sacrifice_no")
                if not isinstance(no, (int, float)):
                    continue
                where = f"{name}!A{rown}"
                s = {"month": month, "sheet": name, "row": rown, "sacrifice_no": int(no), "notes": []}
                for f in ("order_date", "received_date", "delivery_date"):
                    d, left = self.date(rec.get(f), where, f)
                    s[f] = d
                    if left:
                        s["notes"].append(f"{f.replace('_', ' ')}: {left}")
                if not s["order_date"]:
                    s["order_date"] = date.fromisoformat(month + "-01")
                    s["notes"].append(f"No order date in the {name} sheet; filed under {month}.")
                c = str(rec.get("contractor") or "").strip()
                code = contractor_code(c)
                if code == "TZ2":
                    code = "TZ1"
                    s["notes"].append("Sheet says TZ 2; it is on Ahmed Masri's ledger (TZ 1).")
                if c and not code:
                    s["notes"].append(f"Contractor in the sheet: {c}")
                s["contractor"] = code
                s["cost"], s["sale_price"] = _num(rec.get("cost")), _num(rec.get("sale_price"))
                for f in ("donor_name", "animal_type", "payment_method", "extras", "sales_source", "intention"):
                    v = rec.get(f)
                    s[f] = str(v).strip() if v is not None and str(v).strip() else None
                self.out["sacrifices"].append(s)
        may = [s for s in self.out["sacrifices"] if s["sheet"] == "S MAY"]
        if may:
            self.problem("S MAY", f"{len(may)} sacrifices have no order dates and are numbered 1-{len(may)}; "
                                  "imported as numbers 1-13 under May. Their contractor (Tanzania/Nepal) is kept in notes.", "check")

    # ---------- contractor ledgers ----------
    def ledgers(self):
        self.ledger_payments = []
        for name in LEDGERS:
            if name not in self.sheets:
                self.problem(name, "ledger sheet not found")
                continue
            code = contractor_code(name)
            last_date = None
            for rown, hdr, vals in self.rows(name):
                vals = (vals + [None] * 7)[:7]
                _, d, wid, desc, cost, paid, _bal = vals
                if desc is not None and "ملخص" in str(desc):
                    break
                where = f"{name}!A{rown}"
                dt, _ = self.date(d, where)
                if dt:
                    last_date = dt
                cost, paid = _num(cost), _num(paid)
                is_well = isinstance(wid, (int, float))
                if cost is not None and is_well:
                    self.out["ledger_costs"].append({"contractor": code, "id": int(wid), "cost": cost, "where": where,
                                                     "kind": "sacrifice" if name == "Ahmed Masri" else "well"})
                elif cost is not None:
                    self.out["transactions"].append({
                        "date": dt or last_date, "kind": "operating_expense", "direction": "out", "account": None,
                        "contractor": code, "category": "Contractor extra work", "amount": cost,
                        "description": f"{str(desc or '').strip() or 'Extra work'}{f' (well {wid})' if wid else ''}",
                        "reference": where})
                    self.problem(where, f"{name}: extra charge ${cost} ('{str(desc or wid).strip()}') recorded as extra "
                                        "contractor work (an expense that adds to what is owed)", "info")
                if paid is not None:
                    if not dt:
                        if last_date:
                            self.problem(where, f"{name}: payment ${paid} has no date; dated {last_date} like the row above", "check")
                        else:
                            self.problem(where, f"{name}: payment ${paid} has no date and no dated row above; dated 2026-03-01", "check")
                    self.ledger_payments.append({"contractor": code, "date": dt or last_date or date(2026, 3, 1),
                                                 "amount": paid, "where": where, "desc": str(desc or "").strip(),
                                                 "dated": dt is not None})

    # ---------- ads sheet ----------
    def ads(self):
        self.ad_channel = {}   # ("UK"|"Mo"|"Cliq", excel row) -> channel
        self.partner_ads = []
        for rown, hdr, vals in self.rows("Ads"):
            vals = (vals + [None] * 9)[:9]
            no, d, _m, desc, channel, paid_from, amount, src, typ = vals
            if not isinstance(no, (int, float)):
                continue
            m = re.match(r"\s*(UK Account|Mo|Cliq) row (\d+)", str(src or ""))
            if not m:
                self.problem(f"Ads!A{rown}", f"cannot tell where ad row {no} was paid from ('{src}')")
                continue
            key = ({"UK Account": "UK"}.get(m.group(1), m.group(1)), int(m.group(2)))
            ch = "Agency" if channel == "Agency & other" else channel
            self.ad_channel[key] = ch
            if key[0] != "UK":
                dt, _ = self.date(d, f"Ads!B{rown}")
                self.partner_ads.append({"key": key, "date": dt, "amount": _num(amount), "channel": ch,
                                         "description": f"{str(desc).strip()} (paid by {paid_from})", "where": f"Ads!A{rown}"})

    # ---------- UK account ----------
    def uk_account(self):
        uk = []
        for rown, hdr, vals in self.rows("UK Account"):
            vals = (vals + [None] * 8)[:8]
            no, d, _m, desc, inn, out, _bal, cat = vals
            if not isinstance(no, (int, float)):
                continue
            where = f"UK Account!A{rown}"
            dt, _ = self.date(d, where)
            inn, out = _num(inn) or Decimal(0), _num(out) or Decimal(0)
            direction, amount = ("in", inn) if inn > 0 else ("out", out)
            desc = str(desc or "").strip()
            cat = str(cat or "").strip()
            kind = UK_KIND.get(cat)
            if ("UK", rown) in self.ad_channel:
                kind = "ad_spend"  # the Ads sheet lists it (e.g. an ad refund filed as Income)
            if not kind:
                self.problem(where, f"category '{cat}' not known; recorded as Other")
                kind = "other"
            t = {"date": dt, "kind": kind, "direction": direction, "account": "WISE", "contractor": None,
                 "category": cat, "amount": amount, "description": desc, "reference": where, "_row": rown}
            if kind == "ad_spend":
                t["channel"] = self.ad_channel.get(("UK", rown))
                if not t["channel"]:
                    low = desc.lower()
                    t["channel"] = next((c for c in ("Facebook", "Google", "Instagram") if c.lower() in low), "Agency")
                    self.problem(where, f"ad payment '{desc}' ${amount} on {dt} is in the UK Account but missing from the "
                                        "Ads sheet, so the workbook's ad total leaves it out; it is counted here", "action")
            uk.append(t)
        self.uk_rows = uk

    def match_contractor_payments(self):
        """Pair each UK contractor payment with the ledger row it pays. The ledger amount is what the
        contractor is credited; any difference is a transfer fee."""
        pending = list(self.ledger_payments)
        for t in [u for u in self.uk_rows if u["kind"] == "contractor_payment"]:
            hint = hint_contractor(t["description"])
            cands = [p for p in pending if (hint is None or p["contractor"] == hint)
                     and abs((p["date"] - t["date"]).days) <= 4
                     and t["amount"] * Decimal("0.85") <= p["amount"] <= t["amount"] + Decimal("0.01")]
            if hint is None:  # no name in the description: only an exact amount on the same day is safe
                cands = [p for p in cands if p["amount"] == t["amount"] and p["date"] == t["date"]]
            if len(cands) > 1:
                exact = [p for p in cands if p["amount"] == t["amount"]]
                cands = exact if len(exact) == 1 else sorted(cands, key=lambda p: abs((p["date"] - t["date"]).days))[:1]
            if cands:
                p = cands[0]
                pending.remove(p)
                t["contractor"] = p["contractor"]
                t["ledger"] = p["where"]
                fee = t["amount"] - p["amount"]
                t["amount"] = p["amount"]
                t["description"] = f"{t['description']} (ledger {p['where']})"
                if fee > Decimal("0.005"):
                    self.out["transactions"].append({
                        "date": t["date"], "kind": "operating_expense", "direction": "out", "account": "WISE",
                        "contractor": None, "category": "Transfer fees", "amount": fee,
                        "description": f"Fee on payment to {p['contractor']} ({t['reference']})", "reference": t["reference"]})
            else:
                t["kind"] = "other"
                t["category"] = "Contractor payment – not on a ledger"
                self.problem(t["reference"], f"UK payment '{t['description']}' ${t['amount']} on {t['date']} does not match "
                                             "any contractor ledger payment; kept in Wise as 'not on a ledger'", "action")
        for p in pending:
            self.out["transactions"].append({
                "date": p["date"], "kind": "contractor_payment", "direction": "out", "account": None,
                "contractor": p["contractor"], "category": "Paid outside the UK account", "amount": p["amount"],
                "description": f"{p['desc'] or 'Payment'} (from {p['where'].split('!')[0]} ledger)", "reference": p["where"]})
            self.problem(p["where"], f"ledger payment ${p['amount']} on {p['date']} is not in the UK Account; "
                                     "recorded as paid from outside the company account", "info")
        for t in self.uk_rows:
            t.pop("_row", None)
            self.out["transactions"].append(t)

    # ---------- partners ----------
    def partner(self, sheet, code, layout):
        last = None
        for rown, hdr, vals in self.rows(sheet):
            vals = (vals + [None] * 8)[:8]
            if layout == "mo":      # No | Date | Source | In | Description | Out
                no, d, src, inn, desc, out = vals[:6]
                in_desc, out_desc = src, desc
            elif layout == "ghazi":  # No | Date | Description | In | Out
                no, d, desc, inn, out = vals[:5]
                in_desc = out_desc = desc
            else:                    # Cliq: No | Month | Date | Description | In | Out
                no, _mm, d, desc, inn, out = vals[:6]
                in_desc = out_desc = desc
            if not isinstance(no, (int, float)):
                continue
            where = f"{sheet}!A{rown}"
            dt, _ = self.date(d, where)
            if not dt:
                dt = last
                self.problem(where, f"{sheet} row {int(no)} has no date; dated {last} like the row above", "check")
            last = dt
            inn, out = _num(inn), _num(out)
            if inn:
                self.out["transactions"].append({"date": dt, "kind": "partner_took", "direction": "out", "account": code,
                                                 "contractor": None, "category": "Taken from company", "amount": inn,
                                                 "description": str(in_desc or "").strip(), "reference": where})
            if out:
                od = str(out_desc or "").strip()
                self.out["transactions"].append({"date": dt, "kind": "partner_spent", "direction": "in", "account": code,
                                                 "contractor": None, "category": "Spent on company", "amount": out,
                                                 "description": od, "reference": where})
                key = ({"MOHAMMED": "Mo", "CLIQ": "Cliq"}.get(code), rown)
                if key in self.ad_channel:
                    continue  # the ad itself is added from the Ads sheet
                if any(w in od.lower() for w in COST_OF_GOODS_WORDS) or od in ("ابار",):
                    self.problem(where, f"{sheet}: '{od}' ${out} paid by the partner for wells/sacrifices; counted as "
                                        "partner spending only (the well costs are already on the month sheets)", "info")
                    continue
                self.out["transactions"].append({"date": dt, "kind": "operating_expense", "direction": "out", "account": None,
                                                 "contractor": None, "category": f"Paid by {sheet.strip()}", "amount": out,
                                                 "description": od, "reference": where})

    def partner_ads_rows(self):
        for a in self.partner_ads:
            self.out["transactions"].append({"date": a["date"], "kind": "ad_spend", "direction": "out", "account": None,
                                             "contractor": None, "channel": a["channel"], "category": "Advertising",
                                             "amount": a["amount"], "description": a["description"], "reference": a["where"]})

    def tanzania(self):
        if "TANZANIA" not in self.sheets:
            return
        for rown, hdr, vals in self.rows("TANZANIA"):
            vals = (vals + [None] * 5)[:5]
            no, d, desc, inn, out = vals
            if not isinstance(no, (int, float)) or not _num(out):
                continue
            where = f"TANZANIA!A{rown}"
            dt, _ = self.date(d, where)
            if dt and dt.year == 2027:
                self.problem(where, f"date {dt} is in 2027; read as {dt.replace(year=2026)}", "check")
                dt = dt.replace(year=2026)
            self.out["transactions"].append({"date": dt, "kind": "operating_expense", "direction": "out", "account": None,
                                             "contractor": None, "category": "Tanzania business trip", "amount": _num(out),
                                             "description": str(desc or "").strip(), "reference": where})

    def cost_check(self):
        wells = {w["well_id"]: w for w in self.out["wells"] if w.get("well_id")}
        sacs = {s["sacrifice_no"]: s for s in self.out["sacrifices"]}
        seen = set()
        for lc in self.out["ledger_costs"]:
            src = sacs if lc["kind"] == "sacrifice" else wells
            item = src.get(lc["id"])
            seen.add((lc["kind"], lc["id"]))
            if not item:
                self.problem(lc["where"], f"{lc['kind']} {lc['id']} is on the ledger (${lc['cost']}) but not on any month sheet", "action")
                continue
            if item.get("contractor") != lc["contractor"]:
                self.problem(lc["where"], f"{lc['kind']} {lc['id']}: month sheet says contractor {item.get('contractor')}, "
                                          f"ledger is {lc['contractor']}", "action")
            if (item.get("cost") or 0) != lc["cost"]:
                self.problem(lc["where"], f"{lc['kind']} {lc['id']}: cost is ${item.get('cost')} on the month sheet but "
                                          f"${lc['cost']} on the ledger (the system uses the month sheet)", "action")
        for w in wells.values():
            if w.get("contractor") and w["contractor"] in {c["contractor"] for c in self.out["ledger_costs"]} \
                    and ("well", w["well_id"]) not in seen:
                self.problem(f"{w['sheet']}!A{w['row']}", f"well {w['well_id']} ({w['contractor']}, ${w.get('cost')}) is not on "
                                                          "its contractor's ledger", "action")

    def expected(self):
        ws = self.sheets.get("Financial Summary")
        if not ws:
            return
        e = {}
        for r in ws.iter_rows(max_col=6):
            a = str(r[0].value or "").strip()
            vals = [c.value for c in r[1:6]]
            if a and isinstance(vals[0], (int, float)):
                e.setdefault(a, vals)
        self.out["expected"] = e

    def run(self):
        self.wells()
        self.sacrifices()
        self.ledgers()
        self.ads()
        self.uk_account()
        self.match_contractor_payments()
        self.partner("Mo", "MOHAMMED", "mo")
        self.partner("Ghazi", "GHAZI", "ghazi")
        self.partner("Cliq", "CLIQ", "cliq")
        self.partner_ads_rows()
        self.tanzania()
        self.cost_check()
        self.problem("PayPal Mo", "not imported: it only passes well payments on to Mo, and the 815 transfer is on Mo's tab", "info")
        self.expected()
        return self.out


def read_workbook(path) -> dict:
    return Reader(path).run()
