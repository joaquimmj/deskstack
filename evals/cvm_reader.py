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
# The lines the golden questions ask: revenue, EBIT, owners' profit, total assets, cash, equity, operating cash flow.
ASKED = {("DRE", "3.01"), ("DRE", "3.05"), ("DRE", "3.11.01"), ("BPA", "1"), ("BPA", "1.01.01"), ("BPP", "2.03"), ("DFC", "6.01")}


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


if __name__ == "__main__":
    answers = read()
    OUT.write_text(json.dumps({"_note": "Written by evals/cvm_reader.py from server/test/fixtures/cvm. Contains information from the CVM "
                                         "Open Data Portal (https://dados.cvm.gov.br/), under the ODbL.",
                               "parser": "python csv (evals/cvm_reader.py)", "answers": answers}, indent=1, ensure_ascii=False) + "\n")
    print(f"Wrote {OUT} ({len(answers)} answers)")
