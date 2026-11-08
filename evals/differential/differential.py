#!/usr/bin/env python3
"""Differential test (brief §8.1): re-read every golden answer from the filing itself, with independent parsers.

- US (SEC): edgartools (MIT) opens each answer's 10-K / 20-F by accession and reads the concept from the filing's
  own XBRL instance (not the companyfacts API that deskstack reads).
- EU (ESEF): Arelle (Apache-2.0) loads the issuer's report package from filings.xbrl.org (not the OIM JSON that
  deskstack reads).

Each check is exact as filed (amounts to the unit, EPS to the cent). It reports:
  - the filing differs from the golden answer, or from deskstack's live answer (golden-live.json from
    server/scripts/golden.ts);
  - for SEC, a later annual filing reports the same period: edgartools lists the issuer's filings itself, so the
    golden builder's choice of filing is checked, not trusted;
  - nothing could be checked (an oracle skipped or a filing unreadable): the run fails rather than pass silently.

  SEC_USER_AGENT="deskstack-ci you@example.com" python3 evals/differential/differential.py \
      [--live evals/results/golden-live.json] [--only sec|esef] [--out evals/results/differential.json]

Network: SEC (with the User-Agent the SEC requires) and filings.xbrl.org. Nightly only (.github/workflows/evals.yml).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ANNUAL = ["10-K", "10-K/A", "20-F", "20-F/A", "40-F"]


def same(a: float, b: float, unit: str | None) -> bool:
    """Exact as filed, with the same rule as server/scripts/golden-lib.ts."""
    tol = 0.005 if unit and unit.endswith("/shares") else 1e-6 if abs(b) < 1000 else 0.5
    return abs(a - b) <= tol


# ---- oracles ------------------------------------------------------------------------------

class EdgarOracle:
    """Facts from SEC filings' own XBRL instances (edgartools), read without the calculation linkbase.

    XBRL.from_filing applies calculation weights and negates facts such as capex (weight -1 under investing cash
    flow). Parsing the instance alone keeps every value as filed.
    """

    def __init__(self, identity: str):
        from edgar import set_identity

        set_identity(identity)
        self._cache: dict[str, object] = {}
        self._filings: dict[str, list] = {}

    def _xbrl(self, accession: str):
        if accession not in self._cache:
            from edgar import find
            from edgar.xbrl.xbrl import XBRL, XBRLAttachments

            filing = find(accession)
            if filing is None:
                raise LookupError(f"filing {accession} not found")
            inst = XBRLAttachments(filing.attachments).get("instance")
            if inst is None:
                raise LookupError(f"no XBRL instance in {accession}")
            x = XBRL()
            x.parser.parse_instance_content(inst.content)
            self._cache[accession] = x
        return self._cache[accession]

    def value(self, accession: str, concept: str, start: str | None, end: str) -> float:
        x = self._xbrl(accession)
        local = concept.split(":", 1)[-1]
        df = x.facts.query().by_concept(local).by_dimension(None).to_dataframe()
        if df is None or len(df) == 0:
            raise LookupError(f"{concept} not in {accession}")
        rows = []
        for _, r in df.iterrows():
            c = str(r.get("concept", ""))
            if c.replace("_", ":").split(":")[-1] != local:
                continue
            if start is None:
                if str(r.get("period_instant", ""))[:10] != end:
                    continue
            elif str(r.get("period_start", ""))[:10] != start or str(r.get("period_end", ""))[:10] != end:
                continue
            v = r.get("numeric_value")
            if v is not None and v == v:
                rows.append(float(v))
        if not rows:
            raise LookupError(f"{concept} {start}..{end} not in {accession}")
        if len(set(rows)) > 1:
            raise LookupError(f"{concept} {start}..{end} has {len(set(rows))} different values in {accession}: {sorted(set(rows))}")
        return rows[0]

    def latest(self, ticker: str, concept: str, start: str | None, end: str, max_filings: int = 6) -> tuple[str, float]:
        """(accession, value) from the most recent annual filing that reports this period, found independently."""
        if ticker not in self._filings:
            from edgar import Company

            fs = Company(ticker).get_filings(form=ANNUAL)
            self._filings[ticker] = sorted(((str(f.filing_date), f.accession_no) for f in fs), reverse=True)
        found = None
        tried = 0
        for filed, accn in self._filings[ticker]:
            if filed[:10] <= end:
                continue  # filed before the period ended: can't report it
            tried += 1
            try:
                found = (accn, self.value(accn, concept, start, end))
                break  # newest first: the first filing that reports it is the latest
            except LookupError:
                if tried >= max_filings:
                    break
        if found is None:
            raise LookupError(f"no annual filing of {ticker} reports {concept} {start}..{end}")
        return found


class ArelleOracle:
    """Value of a non-dimensional fact in an ESEF report (Arelle reading the inline XBRL in the report package).

    The package comes from filings.xbrl.org. Arelle applies the inline transforms, scale and sign itself, so this
    is independent of the OIM JSON that deskstack reads.
    """

    API = "https://filings.xbrl.org/api/entities/{lei}/filings?page[size]=100"

    def __init__(self, workdir: str | None = None):
        from arelle import Cntlr, PackageManager

        self._cntlr = Cntlr.Cntlr(logFileName="logToBuffer")
        PackageManager.init(self._cntlr, loadPackagesConfig=False)
        self._dir = workdir or tempfile.mkdtemp(prefix="esef-")
        self._cache: dict[str, object] = {}

    def _package(self, report: str) -> tuple[str, str]:
        lei = report.split("-", 1)[0]
        with urllib.request.urlopen(self.API.format(lei=lei), timeout=60) as r:
            data = json.load(r)["data"]
        for f in data:
            a = f["attributes"]
            if a["fxo_id"] == report and a.get("package_url"):
                url = "https://filings.xbrl.org" + a["package_url"]
                path = os.path.join(self._dir, url.rsplit("/", 1)[-1])
                if not os.path.exists(path):
                    urllib.request.urlretrieve(url, path)
                return path, (a.get("report_url") or "").rsplit("/", 1)[-1]
        raise LookupError(f"no report package for {report} on filings.xbrl.org")

    def _model(self, report: str):
        if report not in self._cache:
            import zipfile

            from arelle import FileSource, PackageManager

            path, wanted = self._package(report)
            entries = [n for n in zipfile.ZipFile(path).namelist() if "/reports/" in n and n.endswith((".xhtml", ".html"))]
            entries.sort(key=lambda n: (not n.endswith(wanted), n))
            if not entries:
                raise LookupError(f"no inline XBRL report in {os.path.basename(path)}")
            PackageManager.addPackage(self._cntlr, path)
            model = self._cntlr.modelManager.load(FileSource.openFileSource(f"{path}/{entries[0]}", self._cntlr))
            if model is None or not getattr(model, "facts", None):
                raise LookupError(f"Arelle could not load {report}")
            self._cache[report] = model
        return self._cache[report]

    def value(self, report: str, concept: str, start: str | None, end: str) -> float:
        import datetime as dt

        model = self._model(report)
        local = concept.split(":", 1)[-1]
        vals = set()
        for f in model.facts:
            if f.qname is None or f.qname.localName != local or f.context is None or f.context.qnameDims:
                continue
            ctx = f.context
            # XBRL period ends are exclusive midnights: 2026-02-01T00:00 is the period ending 2026-01-31.
            if start is None:
                if not ctx.isInstantPeriod or (ctx.instantDatetime - dt.timedelta(days=1)).date().isoformat() != end:
                    continue
            else:
                if ctx.isInstantPeriod or ctx.startDatetime.date().isoformat() != start:
                    continue
                if (ctx.endDatetime - dt.timedelta(days=1)).date().isoformat() != end:
                    continue
            v = f.xValue if f.xValue is not None else f.value  # value: the inline transform with scale and sign applied
            try:
                vals.add(float(v))
            except (TypeError, ValueError):
                continue
        if len(vals) != 1:
            raise LookupError(f"{concept} {start}..{end}: {len(vals)} value(s) in {report}")
        return vals.pop()


# ---- comparison -----------------------------------------------------------------------------

def compare(questions: list[dict], live: dict[str, object], sec=None, esef=None) -> list[dict]:
    """One row per golden question with a filed source: filing value, golden value, live value, verdict."""
    rows = []
    for q in questions:
        src = q.get("source", {})
        kind = src.get("type")
        oracle, key = (sec, src.get("accession")) if kind == "sec-companyfacts" else (esef, src.get("report")) if kind == "esef" else (None, None)
        if oracle is None or key is None:
            continue
        unit = q.get("unit")
        row = {"id": q["id"], "expected": q["expected"], "live": live.get(q["id"]), "concept": src["concept"], "filing": key}
        try:
            v = oracle.value(key, src["concept"], src.get("start"), src["end"])
            row["filed"] = v
            problems = []
            if not same(v, float(q["expected"]), unit):
                problems.append("golden answer differs from the filing")
            if q["id"] in live:
                lv = live[q["id"]]
                if not isinstance(lv, (int, float)) or not same(v, float(lv), unit):
                    problems.append("deskstack differs from the filing")
            if kind == "sec-companyfacts" and hasattr(oracle, "latest") and src.get("ticker"):
                accn, lv2 = oracle.latest(src["ticker"], src["concept"], src.get("start"), src["end"])
                row["latest_filing"] = accn
                if accn != key and not same(lv2, float(q["expected"]), unit):
                    problems.append(f"a later filing ({accn}) reports {lv2:g} for this period")
            row["status"] = "disagree" if problems else "agree"
            row["problems"] = problems
        except Exception as e:  # noqa: BLE001 - recorded as unchecked; the run then fails
            row["status"] = "unchecked"
            row["problems"] = [f"{type(e).__name__}: {e}"]
        rows.append(row)
    return rows


def summarize(rows: list[dict]) -> dict:
    n = {s: sum(1 for r in rows if r["status"] == s) for s in ("agree", "disagree", "unchecked")}
    return {"total": len(rows), **n}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--golden", default=str(ROOT / "evals" / "golden.json"))
    ap.add_argument("--live", help="golden-live.json from server/scripts/golden.ts")
    ap.add_argument("--only", choices=["sec", "esef"])
    ap.add_argument("--out", default=str(ROOT / "evals" / "results" / "differential.json"))
    a = ap.parse_args(argv)
    questions = json.loads(Path(a.golden).read_text())["questions"]
    live = {}
    if a.live and Path(a.live).exists():
        live = {r["id"]: r.get("got") for r in json.loads(Path(a.live).read_text())["results"]}
    sec = esef = None
    skipped = []
    if a.only in (None, "sec"):
        ua = os.environ.get("SEC_USER_AGENT", "").strip()
        if not ua or "@" not in ua:
            skipped.append("SEC (SEC_USER_AGENT, a name and contact email as the SEC requires, is not set)")
        else:
            sec = EdgarOracle(ua)
    if a.only in (None, "esef"):
        esef = ArelleOracle()
    rows = compare(questions, live, sec, esef)
    s = summarize(rows)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps({"summary": s, "skipped": skipped, "rows": rows}, indent=1) + "\n")
    print(f"differential: {s['agree']} agree, {s['disagree']} disagree, {s['unchecked']} unchecked (of {s['total']})")
    for x in skipped:
        print(f"  skipped {x}")
    for r in rows:
        if r["status"] != "agree":
            print(f"  {r['status']} {r['id']}: filed {r.get('filed')}, golden {r['expected']}, live {r['live']}; {'; '.join(r['problems'])}")
    # Fail loudly: a disagreement, a filing we couldn't read, or a whole side skipped all mean the check didn't hold.
    return 1 if (s["disagree"] or s["unchecked"] or skipped or not rows) else 0


if __name__ == "__main__":
    sys.exit(main())
