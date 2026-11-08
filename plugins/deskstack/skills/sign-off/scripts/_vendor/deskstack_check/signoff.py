"""The human gate for /sign-off: one page of every check, then a signed copy only after the user approves.

`summary(...)` reads the reports (tie-out, model review, compliance, red team), checks each one is the right kind
and was made from this exact file (SHA-256), and lists every open item. It ends with an approval token: a hash of
the file, the reports and the open items, so the export matches exactly what the user saw.

`export(...)` re-reads everything and writes the signed copy only when:
  - the token matches (nothing changed since the summary was shown);
  - the user's words are an affirmative approval (refusals, questions and conditions are rejected);
  - every blocking item is accepted with a real reason, and any missing review is named in `accept_missing`.
The original workbook is never modified; the copy is written atomically.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
import os
import re
import shutil
import tempfile
import zipfile
from pathlib import Path

from openpyxl import load_workbook
from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE
from openpyxl.styles import Font

from .model import file_sha256
from .xlsxio import inject_values

SHEET = "Sign-off"
REVIEWS = {"tieout": "Tie-out to filings (/associate)", "review": "Model review (/vp-review)", "compliance": "Compliance (/compliance)"}
# An approval is an affirmative statement, at the start of the reply.
AFFIRM = re.compile(
    r"^\s*(yes[,.!]?\s+|oui[,.!]?\s+|ok[,.!]?\s+)?(i\s+)?(approve|approved|sign(ed)?[- ]off|go ahead|ship it|"
    r"export it|j'?approuve|approuv[ée]|je valide|valid[ée]|vas-y|ok pour l'?export)\b",
    re.I,
)
# Anything that negates, defers or conditions it is not an approval.
NOT_APPROVAL = re.compile(
    r"\b(not|no|never|don'?t|do not|pas|ne|sans|jamais|until|unless|before|first|need|needs|awaiting|wait|"
    r"later|if|once|refuse|reject|but)\b|n't\b|\?",
    re.I,
)
TRIVIAL_REASONS = {"n/a", "na", "ok", "okay", "fine", "yes", "none", "-", "accepted", "accept", "skip", "test"}


class GateError(ValueError):
    pass


def is_approval(text: str | None) -> bool:
    if not text or not text.strip():
        return False
    t = text.strip()
    return bool(AFFIRM.search(t)) and not NOT_APPROVAL.search(t)


def _real_reason(r: str | None) -> bool:
    return bool(r) and len(r.strip()) >= 15 and r.strip().lower() not in TRIVIAL_REASONS


def _read(path: str | None):
    if not path:
        return None, None
    raw = Path(path).read_bytes()
    try:
        return json.loads(raw), hashlib.sha256(raw).hexdigest()
    except (json.JSONDecodeError, UnicodeDecodeError):
        return raw.decode("utf-8", "replace"), hashlib.sha256(raw).hexdigest()


def _valid(kind: str, r) -> str | None:
    """Why `r` isn't a usable report of this kind, or None."""
    if not isinstance(r, dict):
        return "not a JSON report"
    if r.get("report") != kind:
        return f"not a {kind} report (it says {r.get('report')!r}); produce it with the {kind} command's --json"
    if kind == "tieout" and not (isinstance(r.get("rows"), list) and r["rows"] and isinstance(r.get("counts"), dict)):
        return "the tie-out has no rows"
    if kind == "review" and not (isinstance(r.get("findings"), list) and isinstance(r.get("counts"), dict)):
        return "the review has no findings list"
    if kind == "compliance" and not (isinstance(r.get("items"), list) and r["items"] and isinstance(r.get("counts"), dict)):
        return "the compliance report has no checks"
    return None


def summary(model: str, tieout: str | None = None, review: str | None = None, compliance: str | None = None,
            redteam: str | None = None) -> dict:
    sha = file_sha256(model)
    paths = {"tieout": tieout, "review": review, "compliance": compliance}
    checks, open_items, missing, digests = [], [], [], {}

    for kind, path in paths.items():
        r, digest = _read(path)
        digests[kind] = digest
        why = "not given" if r is None else _valid(kind, r)
        if why:
            checks.append({"check": REVIEWS[kind], "key": kind, "status": "missing", "detail": f"No usable report: {why}."})
            missing.append(kind)
            continue
        if r.get("model_sha256") != sha:
            checks.append({"check": REVIEWS[kind], "key": kind, "status": "stale",
                           "detail": "Made from a different version of the file. Re-run it on this file."})
            open_items.append({"from": kind, "severity": "blocker", "ref": "-", "issue": f"{REVIEWS[kind]} is stale: re-run it on the current file."})
            continue
        if kind == "tieout":
            k = r["counts"]
            bad = sum(k.get(x, 0) for x in ("mismatch", "not_found", "ambiguous", "not_checked"))
            checks.append({"check": REVIEWS[kind], "key": kind, "status": "fail" if bad else ("warn" if k.get("unsourced") else "pass"),
                           "detail": ", ".join(f"{k.get(x, 0)} {x.replace('_', ' ')}" for x in ("match", "mismatch", "not_found", "ambiguous", "not_checked", "unsourced"))})
            for row in r["rows"]:
                if row.get("status") in ("mismatch", "not_found", "ambiguous", "not_checked"):
                    hint = "; ".join(row.get("hints") or [])
                    open_items.append({"from": "tie-out", "severity": "blocker", "ref": row.get("ref", "-"),
                                       "issue": f"{row.get('label')}: {row['status'].replace('_', ' ')}. {hint}".strip()})
        elif kind == "review":
            rows = (r.get("companion") or {}).get("merged") or r["findings"]
            n = {s: sum(1 for f in rows if f.get("severity") == s) for s in ("blocker", "major", "minor")}
            checks.append({"check": REVIEWS[kind], "key": kind, "status": "fail" if n["blocker"] else ("warn" if n["major"] else "pass"),
                           "detail": f"{n['blocker']} blocker, {n['major']} major, {n['minor']} minor"})
            for f in rows:
                if f.get("severity") in ("blocker", "major"):
                    open_items.append({"from": "model review", "severity": f["severity"], "ref": f.get("ref", "-"),
                                       "issue": f"{f.get('rule')}: {f.get('message')}"})
        else:
            fails = [i for i in r["items"] if i.get("status") == "fail"]
            c = r["counts"]
            checks.append({"check": REVIEWS[kind], "key": kind, "status": "fail" if fails else "pass",
                           "detail": f"{c.get('pass', 0)} pass, {c.get('fail', 0)} fail, {c.get('warn', 0)} warn"})
            for i in fails:
                open_items.append({"from": "compliance", "severity": "blocker", "ref": ", ".join(i.get("refs", [])[:3]) or "-",
                                   "issue": f"{i.get('id')} {i.get('check')}: {i.get('detail')}"})

    m, digests["redteam"] = _read(redteam)
    if isinstance(m, str) and m.strip():
        hashes = re.findall(r"\b[0-9a-f]{64}\b", m)
        n = len(re.findall(r"^\s*(\d+[.)]|[-*])\s+\S", m, re.M))
        status = "info" if sha in hashes else "stale?"
        detail = f"Memo attached ({n} listed point(s)); objections are for judgment, not pass/fail."
        if sha not in hashes:
            detail += " It doesn't name this file's SHA-256, so it may be about another version."
        checks.append({"check": "Red team (/md-redteam)", "key": "redteam", "status": status, "detail": detail})
    else:
        checks.append({"check": "Red team (/md-redteam)", "key": "redteam", "status": "missing", "detail": "No red-team memo (optional)."})

    blocking = sum(1 for i in open_items if i["severity"] == "blocker")
    token = hashlib.sha256(json.dumps({"sha": sha, "reports": digests, "open": open_items}, sort_keys=True).encode()).hexdigest()[:12]
    return {"model": model, "sha256": sha, "checks": checks, "open_items": open_items, "blocking": blocking,
            "missing": missing, "ready": not blocking and not missing, "token": token}


def to_markdown(s: dict) -> str:
    lines = [f"## Sign-off summary: {Path(s['model']).name}", f"File SHA-256: `{s['sha256']}`", "",
             "| Check | Status | Detail |", "|---|---|---|"]
    for ch in s["checks"]:
        lines.append(f"| {ch['check']} | {ch['status']} | {ch['detail']} |")
    lines += ["", f"**Open items: {len(s['open_items'])}** ({s['blocking']} blocking). Missing reviews: {', '.join(s['missing']) or 'none'}."]
    for i, o in enumerate(s["open_items"], 1):
        lines.append(f"{i}. [{o['severity']}] `{o['ref']}` ({o['from']}): {o['issue']}")
    lines += ["", f"Approval token: `{s['token']}` (it changes if the file, a report or an open item changes).", "",
              "Nothing is exported until you approve in your own words. Blocking items must be fixed, or accepted "
              "with a reason that is recorded on the sign-off sheet.", "", "Draft for human review. Not investment advice."]
    return "\n".join(lines)


UNSUPPORTED = [
    ("xl/charts/", "charts"), ("xl/media/", "images"), ("xl/drawings/", "drawings"), ("vbaProject.bin", "macros"),
    ("xl/pivot", "pivot tables"), ("xl/slicer", "slicers"), ("xl/timeline", "timelines"),
    ("xl/threadedComments/", "threaded comments"), ("xl/connections.xml", "data connections"),
    ("xl/queryTables/", "query tables"), ("customXml/", "custom XML"),
]


def _unsupported_parts(path: str) -> list[str]:
    """Parts openpyxl doesn't carry over; a copy would silently lose them."""
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        x14 = any("x14:" in z.read(n).decode("utf-8", "ignore") for n in names if n.startswith("xl/worksheets/sheet"))
    found = sorted({label for key, label in UNSUPPORTED if any(key in n for n in names)})
    if x14:
        found.append("sparklines or newer conditional formats")
    return found


def _clean(text) -> str:
    return ILLEGAL_CHARACTERS_RE.sub("", str(text)).strip()


def export(model: str, out: str, reports: dict, approver: str, approval_text: str, token: str,
           accept_open: str | None = None, accept_missing: list[str] | None = None) -> dict:
    """Write the signed copy. Raises GateError on anything short of an explicit, informed approval."""
    s = summary(model, **reports)
    approver, approval_text = _clean(approver or ""), _clean(approval_text or "")
    if not approver:
        raise GateError("Who approves? Ask the user for their name; never guess it.")
    if not is_approval(approval_text):
        raise GateError("Not an approval. Pass the user's own affirmative words (e.g. 'I approve the export'); refusals, "
                        "questions and conditions ('not yet', 'approve?', 'once fixed') don't count.")
    if token != s["token"]:
        raise GateError("The approval token doesn't match: the file, a report or an open item changed since the summary "
                        "was shown. Show the new summary and ask again.")
    if s["missing"]:
        named = set(accept_missing or [])
        if not set(s["missing"]) <= named or not _real_reason(accept_open):
            raise GateError(f"Missing review(s): {', '.join(s['missing'])}. Run them, or have the user accept each by name "
                            "(--accept-missing) with a reason (--accept-open).")
    if s["blocking"] and not _real_reason(accept_open):
        raise GateError(f"{s['blocking']} blocking item(s) are open. Fix them, or pass --accept-open with the user's reason "
                        "(a real sentence, not 'ok' or 'n/a').")
    out_p = Path(out)
    if out_p.resolve() == Path(model).resolve():
        raise GateError("The signed copy must be a new file, not the model itself.")
    if out_p.exists():
        raise GateError(f"{out_p} already exists. Choose a new name; signed files are never overwritten.")
    out_p.parent.mkdir(parents=True, exist_ok=True)

    now = _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    record = {"approved_by": approver, "approved_at": now, "approval_text": approval_text,
              "accepted_open_items": _clean(accept_open) if accept_open else None,
              "accepted_missing_reviews": sorted(accept_missing or []), **s}
    unsupported = _unsupported_parts(model)
    if unsupported:
        out_p = out_p.with_name(out_p.stem + "-signoff.xlsx")
        if out_p.exists():
            raise GateError(f"{out_p} already exists. Choose a new name.")
        record["note"] = (f"The model has {', '.join(unsupported)}, which this tool can't copy without loss: the "
                          "sign-off is a separate workbook and the model is unchanged.")
    fd, tmp = tempfile.mkstemp(suffix=".xlsx", dir=out_p.parent)
    os.close(fd)
    try:
        if unsupported:
            from openpyxl import Workbook

            wb = Workbook()
            _write_sheet(wb.active, record, model)
            wb.active.title = SHEET
            wb.save(tmp)
        else:
            shutil.copy2(model, tmp)
            vals = load_workbook(model, data_only=True)
            wb = load_workbook(tmp)
            cached = {}
            for ws in wb.worksheets:
                for row in ws.iter_rows():
                    for c in row:
                        if c.data_type == "f":
                            v = vals[ws.title][c.coordinate].value
                            if v is not None:
                                cached[(ws.title, c.coordinate)] = v
            if SHEET in wb.sheetnames:  # keep earlier sign-offs as history
                k = 1
                while f"{SHEET} (previous {k})" in wb.sheetnames:
                    k += 1
                wb[SHEET].title = f"{SHEET} (previous {k})"
            _write_sheet(wb.create_sheet(SHEET), record, model)
            wb.save(tmp)
            inject_values(tmp, cached, wb.sheetnames)  # openpyxl drops cached results on save; put them back
        os.replace(tmp, out_p)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
    record["output"] = str(out_p)
    record["output_sha256"] = file_sha256(str(out_p))
    Path(str(out_p) + ".signoff.json").write_text(json.dumps(record, indent=1, default=str))
    return record


def _write_sheet(ws, rec: dict, model: str) -> None:
    b = Font(bold=True)
    rows = [
        ("Sign-off", ""),
        ("Model", Path(model).name),
        ("Model SHA-256 (as reviewed)", rec["sha256"]),
        ("Approved by", rec["approved_by"]),
        ("Approved at", rec["approved_at"]),
        ("Approval, in the approver's words", rec["approval_text"]),
        ("Open items accepted, and why", rec["accepted_open_items"] or "None open"),
        ("Reviews not run, accepted", ", ".join(rec["accepted_missing_reviews"]) or "None"),
        ("", ""),
        ("Check", "Status / detail"),
    ]
    rows += [(c["check"], f"{c['status']}: {c['detail']}") for c in rec["checks"]]
    rows += [("", ""), ("Open items at sign-off", str(len(rec["open_items"])))]
    rows += [(f"[{o['severity']}] {o['ref']}", f"{o['from']}: {o['issue']}") for o in rec["open_items"]]
    rows += [("", ""), ("Draft for human review. Not investment advice.", ""),
             ("Reviews reduce errors; they don't replace the approver's own judgment.", "")]
    for i, (a, v) in enumerate(rows, start=1):
        for j, x in ((1, a), (2, v)):
            x = _clean(x)
            cell = ws.cell(i, j, x)
            if x[:1] in ("=", "+", "-", "@"):
                cell.data_type = "s"  # the user's words are text, never a formula
        if a in ("Sign-off", "Check") or a.startswith("Open items at"):
            ws.cell(i, 1).font = b
    ws.column_dimensions["A"].width = 44
    ws.column_dimensions["B"].width = 110
