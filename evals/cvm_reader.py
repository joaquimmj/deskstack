#!/usr/bin/env python3
"""Read the golden answers for Brazil straight from CVM's published CSVs, without deskstack's extractor.

No second parser exists for CVM's open data (it is CSV, not XBRL), so this is the independent reading: plain Python's
csv module on the recorded files (server/test/fixtures/cvm), by fixed account code. Its rules are written out here:
  - a filing is the latest VERSAO of a company's DFP for a reference date;
  - a value is VL_CONTA x ESCALA_MOEDA (MIL = thousand, UNIDADE = one), in reais;
  - when two filings report the same period (this year's and next year's comparative), the one CVM received last
    (DT_RECEB) wins, so restatements count.

  python3 evals/cvm_reader.py     # writes evals/fixtures/cvm-answers.json
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIX = ROOT / "server" / "test" / "fixtures" / "cvm"
OUT = ROOT / "evals" / "fixtures" / "cvm-answers.json"
SCALE = {"MIL": 1000, "UNIDADE": 1}
STATEMENTS = ("DRE", "BPA", "BPP", "DFC_MI", "DFC_MD")
# The lines the golden questions ask: revenue, EBIT, owners' profit, total assets, cash, equity, minorities, operating cash flow.
ASKED = {("DRE", "3.01"), ("DRE", "3.05"), ("DRE", "3.11.01"), ("BPA", "1"), ("BPA", "1.01.01"), ("BPP", "2.03"), ("BPP", "2.03.09"), ("DFC", "6.01")}


def rows(name: str):
    with open(FIX / name, encoding="utf-8", newline="") as f:
        yield from csv.DictReader(f, delimiter=";")


def read() -> list[dict]:
    filings = {}  # (cd_cvm, refer) -> latest filing
    for path in sorted(FIX.glob("dfp_cia_aberta_20??.csv")):
        for r in rows(path.name):
            key = (r["CD_CVM"], r["DT_REFER"])
            if key not in filings or int(r["VERSAO"]) > int(filings[key]["VERSAO"]):
                filings[key] = r
    best = {}  # (cd_cvm, statement, code, start, end) -> answer
    for path in sorted(FIX.glob("dfp_cia_aberta_*_con_20??.csv")):
        st = next(s for s in STATEMENTS if f"_{s}_con_" in path.name)
        for r in rows(path.name):
            f = filings.get((r["CD_CVM"], r["DT_REFER"]))
            if not f or r["VERSAO"] != f["VERSAO"] or r["MOEDA"] != "REAL" or r["ESCALA_MOEDA"] not in SCALE:
                continue
            instant = st in ("BPA", "BPP")
            start = None if instant else r["DT_INI_EXERC"]
            key = (r["CD_CVM"], "DFC" if st.startswith("DFC") else st, r["CD_CONTA"], start, r["DT_FIM_EXERC"])
            if (key[1], key[2]) not in ASKED:
                continue
            value = round(float(r["VL_CONTA"]) * SCALE[r["ESCALA_MOEDA"]])
            cand = {"cd_cvm": r["CD_CVM"], "statement": key[1], "code": r["CD_CONTA"], "label": r["DS_CONTA"],
                    "start": start, "end": r["DT_FIM_EXERC"], "value": value, "filing": f"CVM-DFP-{f['ID_DOC']}",
                    "received": f["DT_RECEB"], "url": f["LINK_DOC"]}
            if key not in best or cand["received"] > best[key]["received"]:
                best[key] = cand
    return sorted(best.values(), key=lambda a: (a["cd_cvm"], a["statement"], a["code"], a["end"]))


def read_ltm() -> list[dict]:
    """LTM for each company's latest ITR: the last DFP's fiscal year + this year to date - last year's same period."""
    itr = {}
    for path in sorted(FIX.glob("itr_cia_aberta_20??.csv")):
        for r in rows(path.name):
            key = (r["CD_CVM"], r["DT_REFER"])
            if key not in itr or int(r["VERSAO"]) > int(itr[key]["VERSAO"]):
                itr[key] = r
    latest = {}
    for (cd, refer), f in itr.items():
        if cd not in latest or refer > latest[cd]["DT_REFER"]:
            latest[cd] = f
    annual = {(a["cd_cvm"], a["statement"], a["code"], a["end"]): a for a in read() if a["start"]}
    out = []
    for cd, f in sorted(latest.items()):
        end = f["DT_REFER"]
        y = int(end[:4])
        fy_end = f"{y - 1}-12-31"
        for path in sorted(FIX.glob(f"itr_cia_aberta_*_con_{y}.csv")):
            st = next(s for s in STATEMENTS if f"_{s}_con_" in path.name)
            stmt = "DFC" if st.startswith("DFC") else st
            if stmt in ("BPA", "BPP"):
                continue
            ytd, prior = {}, {}
            for r in rows(path.name):
                if r["CD_CVM"] != cd or r["DT_REFER"] != end or r["VERSAO"] != f["VERSAO"] or (stmt, r["CD_CONTA"]) not in ASKED:
                    continue
                v = round(float(r["VL_CONTA"]) * SCALE[r["ESCALA_MOEDA"]])
                if r["DT_INI_EXERC"] == f"{y}-01-01" and r["DT_FIM_EXERC"] == end:
                    ytd[r["CD_CONTA"]] = v
                elif r["DT_INI_EXERC"] == f"{y - 1}-01-01" and r["DT_FIM_EXERC"] == f"{y - 1}{end[4:]}":
                    prior[r["CD_CONTA"]] = v
            for code in sorted(ytd):
                fy = annual.get((cd, stmt, code, fy_end))
                if fy is None or code not in prior:
                    continue
                out.append({"cd_cvm": cd, "statement": stmt, "code": code, "end": end, "value": fy["value"] + ytd[code] - prior[code],
                            "formula": "FY + YTD - prior YTD", "fy_filing": fy["filing"], "itr_filing": f"CVM-ITR-{f['ID_DOC']}"})
    return out


if __name__ == "__main__":
    answers = read()
    ltm = read_ltm()
    OUT.write_text(json.dumps({"_note": "Written by evals/cvm_reader.py from server/test/fixtures/cvm. Contains information from the CVM "
                                         "Open Data Portal (https://dados.cvm.gov.br/), under the ODbL.",
                               "parser": "python csv (evals/cvm_reader.py)", "answers": answers, "ltm": ltm}, indent=1, ensure_ascii=False) + "\n")
    print(f"Wrote {OUT} ({len(answers)} answers, {len(ltm)} LTM)")
