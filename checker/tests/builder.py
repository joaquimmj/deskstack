"""Build synthetic models for the checker tests: formulas AND the values Excel would cache.

openpyxl writes formulas without results. Tests of value checks need results,
so the builder records the intended value of every formula cell and writes it
into the sheet XML as <v>, the way Excel does when it saves.
"""

from __future__ import annotations

import re
import zipfile
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Font

BLUE = Font(color="FF0000FF")
BLACK = Font(color="FF000000")


class Model:
    def __init__(self) -> None:
        self.wb = Workbook()
        self.wb.remove(self.wb.active)
        self.cached: dict[tuple[str, str], object] = {}

    def sheet(self, name: str):
        return self.wb[name] if name in self.wb.sheetnames else self.wb.create_sheet(name)

    def text(self, sheet: str, coord: str, s: str) -> None:
        self.sheet(sheet)[coord] = s

    def inp(self, sheet: str, coord: str, v: float, blue: bool = True) -> None:
        c = self.sheet(sheet)[coord]
        c.value = v
        c.font = BLUE if blue else BLACK

    def f(self, sheet: str, coord: str, formula: str, value: object, blue: bool = False) -> None:
        c = self.sheet(sheet)[coord]
        c.value = formula
        c.font = BLUE if blue else BLACK
        self.cached[(sheet, coord)] = value

    def save(self, path: Path, cache: bool = True) -> Path:
        self.wb.save(path)
        if cache:
            _inject_values(path, self.cached, self.wb.sheetnames)
        return path


def _inject_values(path: Path, cached: dict[tuple[str, str], object], sheets: list[str]) -> None:
    tmp = path.with_suffix(".tmp.xlsx")
    with zipfile.ZipFile(path) as zin, zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            m = re.match(r"xl/worksheets/sheet(\d+)\.xml$", item.filename)
            if m:
                name = sheets[int(m.group(1)) - 1]
                xml = data.decode("utf-8")
                for (s, coord), v in cached.items():
                    if s != name:
                        continue
                    if isinstance(v, str):  # an error result such as #DIV/0!
                        val = f'<v>{v}</v>'
                        xml = re.sub(rf'<c r="{coord}"([^>]*)>(<f>.*?</f>)(<v>.*?</v>|<v\s*/>)?</c>',
                                     lambda mm: f'<c r="{coord}"{_t(mm.group(1), "e")}>{mm.group(2)}{val}</c>', xml)
                    else:
                        val = f"<v>{'1' if v is True else '0' if v is False else repr(float(v))}</v>"
                        xml = re.sub(rf'<c r="{coord}"([^>]*)>(<f>.*?</f>)(<v>.*?</v>|<v\s*/>)?</c>',
                                     lambda mm: f'<c r="{coord}"{mm.group(1)}>{mm.group(2)}{val}</c>', xml)
                data = xml.encode("utf-8")
            zout.writestr(item, data)
    tmp.replace(path)


def _t(attrs: str, t: str) -> str:
    attrs = re.sub(r'\st="[^"]*"', "", attrs)
    return f'{attrs} t="{t}"'


def clean_dcf() -> Model:
    """A small, correct 5-year DCF with a balanced balance sheet: no blocker or major finding expected."""
    m = Model()
    # Inputs (blue, each cited in Sources)
    m.text("Inputs", "A1", "Inputs (USD in millions)")
    rows = [("Revenue FY2024", 1000.0), ("Revenue growth", 0.05), ("EBIT margin", 0.2), ("Tax rate", 0.25),
            ("D&A % revenue", 0.04), ("Capex % revenue", 0.05), ("WACC", 0.09), ("Terminal growth", 0.025),
            ("Net debt", 300.0), ("Shares outstanding", 100.0)]
    for i, (label, v) in enumerate(rows, start=3):
        m.text("Inputs", f"A{i}", label)
        m.inp("Inputs", f"B{i}", v)
    m.text("Inputs", "A14", "Mid-year convention")
    m.text("Inputs", "B14", "No")
    # Sources: one row per typed input
    m.text("Sources", "A1", "Cell")
    m.text("Sources", "B1", "Source")
    for i in range(3, 13):
        m.text("Sources", f"A{i - 1}", f"Inputs!B{i}")
        m.text("Sources", f"B{i - 1}", "SEC EDGAR 10-K FY2024, accession 0000320193-24-000123 (deskstack verify_value: match)")
    # DCF (USD in millions)
    s = "DCF"
    m.text(s, "A1", "DCF (USD in millions)")
    years = ["C", "D", "E", "F", "G"]
    m.text(s, "A2", "Year")
    for i, col in enumerate(years):
        m.inp(s, f"{col}2", 2025 + i, blue=False)  # header row: fiscal years
    m.text(s, "A11", "Period")
    for i, col in enumerate(years):
        m.f(s, f"{col}11", f"={col}2-$C$2+1", i + 1)
    m.text(s, "A3", "Revenue")
    rev = 1000.0
    revs, fcfs, dfs = [], [], []
    for i, col in enumerate(years):
        prev = "Inputs!B3" if i == 0 else f"{years[i - 1]}3"
        rev = rev * 1.05
        revs.append(rev)
        m.f(s, f"{col}3", f"={prev}*(1+Inputs!$B$4)", rev)
    m.text(s, "A4", "EBIT")
    m.text(s, "A5", "NOPAT")
    m.text(s, "A6", "D&A")
    m.text(s, "A7", "Capex")
    m.text(s, "A8", "Free cash flow")
    m.text(s, "A9", "Discount factor")
    m.text(s, "A10", "PV of FCF")
    for i, col in enumerate(years):
        r = revs[i]
        ebit, nopat, da, cap = r * 0.2, r * 0.2 * 0.75, r * 0.04, r * 0.05
        fcf = nopat + da - cap
        df = 1 / 1.09 ** (i + 1)
        fcfs.append(fcf)
        dfs.append(df)
        m.f(s, f"{col}4", f"={col}3*Inputs!$B$5", ebit)
        m.f(s, f"{col}5", f"={col}4*(1-Inputs!$B$6)", nopat)
        m.f(s, f"{col}6", f"={col}3*Inputs!$B$7", da)
        m.f(s, f"{col}7", f"={col}3*Inputs!$B$8", cap)
        m.f(s, f"{col}8", f"={col}5+{col}6-{col}7", fcf)
        m.f(s, f"{col}9", f"=1/(1+Inputs!$B$9)^{col}11", df)
        m.f(s, f"{col}10", f"={col}8*{col}9", fcf * df)
    tv = fcfs[-1] * 1.025 / (0.09 - 0.025)
    pv_tv = tv * dfs[-1]
    sum_pv = sum(f * d for f, d in zip(fcfs, dfs))
    m.text(s, "A12", "Terminal value")
    m.f(s, "B12", "=G8*(1+Inputs!B10)/(Inputs!B9-Inputs!B10)", tv)
    m.text(s, "A13", "PV of terminal value")
    m.f(s, "B13", "=B12*G9", pv_tv)
    m.text(s, "A14", "Sum of PV of FCF")
    m.f(s, "B14", "=SUM(C10:G10)", sum_pv)
    m.text(s, "A15", "Enterprise value")
    m.f(s, "B15", "=B13+B14", pv_tv + sum_pv)
    m.text(s, "A16", "Equity value")
    m.f(s, "B16", "=B15-Inputs!B11", pv_tv + sum_pv - 300)
    m.text(s, "A17", "Value per share")
    m.f(s, "B17", "=B16/Inputs!B12", (pv_tv + sum_pv - 300) / 100)
    m.text(s, "A19", "WACC")
    m.f(s, "B19", "=Inputs!B9", 0.09)
    m.text(s, "A20", "Terminal growth")
    m.f(s, "B20", "=Inputs!B10", 0.025)
    # Balance sheet (balances) and cash flow (ties)
    b = "BS"
    m.text(b, "A1", "Balance sheet (USD in millions)")
    m.text(b, "A3", "Cash")
    m.f(b, "C3", "=CF!C5", 120.0)
    m.text(b, "A4", "Other assets")
    m.inp(b, "C4", 880.0)
    m.text(b, "A5", "Total assets")
    m.f(b, "C5", "=C3+C4", 1000.0)
    m.text(b, "A6", "Liabilities")
    m.inp(b, "C6", 600.0)
    m.text(b, "A7", "Equity")
    m.inp(b, "C7", 400.0)
    m.text(b, "A8", "Total liabilities and equity")
    m.f(b, "C8", "=C6+C7", 1000.0)
    c = "CF"
    m.text(c, "A1", "Cash flow (USD in millions)")
    m.text(c, "A3", "Beginning cash")
    m.inp(c, "C3", 100.0)
    m.text(c, "A4", "Net change in cash")
    m.inp(c, "C4", 20.0)
    m.text(c, "A5", "Ending cash")
    m.f(c, "C5", "=C3+C4", 120.0)
    for sheet, coord in [("BS", "C4"), ("BS", "C6"), ("BS", "C7"), ("CF", "C3"), ("CF", "C4")]:
        n = len([k for k in m.sheet("Sources").iter_rows() if any(x.value for x in k)]) + 1
        m.text("Sources", f"A{n}", f"{sheet}!{coord}")
        m.text("Sources", f"B{n}", "Company 10-K FY2024 balance sheet / cash flow statement")
    return m
