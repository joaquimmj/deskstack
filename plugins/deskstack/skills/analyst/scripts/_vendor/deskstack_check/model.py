"""Workbook access for the checks: formulas and cached values side by side.

openpyxl reads a workbook twice: once for formulas, once for the values Excel
cached when it last saved the file. A workbook written by a script and never
opened in Excel has no cached values; value-based checks then report that
they were skipped instead of guessing.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterator

from openpyxl import load_workbook
from openpyxl.cell.cell import Cell
from openpyxl.utils import column_index_from_string, get_column_letter

# A cell reference inside a formula: optional sheet ('My Sheet'! or Sheet1!), optional $, column, row.
REF_RE = re.compile(
    r"(?:(?P<sheet>'[^']+'|[A-Za-z_][A-Za-z0-9_.]*)!)?(?P<cd>\$?)(?P<col>[A-Z]{1,3})(?P<rd>\$?)(?P<row>[0-9]{1,7})(?![0-9A-Za-z(])"
)
RANGE_RE = re.compile(
    r"(?:(?P<sheet>'[^']+'|[A-Za-z_][A-Za-z0-9_.]*)!)?\$?(?P<c1>[A-Z]{1,3})\$?(?P<r1>[0-9]{1,7}):\$?(?P<c2>[A-Z]{1,3})\$?(?P<r2>[0-9]{1,7})"
)
STRING_RE = re.compile(r'"(?:[^"]|"")*"')
ERROR_VALUES = ("#REF!", "#DIV/0!", "#N/A", "#VALUE!", "#NAME?", "#NUM!", "#NULL!")

# Excel font colors that mean "input" (blue) under the banking convention.
BLUE = {"FF0000FF", "000000FF", "0000FF"}


@dataclass
class CellInfo:
    sheet: str
    coord: str
    row: int
    col: int
    formula: str | None
    constant: object | None
    cached: object | None
    font_color: str | None

    @property
    def ref(self) -> str:
        return f"{self.sheet}!{self.coord}"

    @property
    def is_number_constant(self) -> bool:
        return self.formula is None and isinstance(self.constant, (int, float)) and not isinstance(self.constant, bool)


@dataclass
class Workbook:
    path: str
    cells: dict[str, dict[str, CellInfo]] = field(default_factory=dict)  # sheet -> coord -> cell
    sheet_order: list[str] = field(default_factory=list)
    has_cached_values: bool = False
    iterate: bool = False
    external_links: int = 0

    def get(self, sheet: str, coord: str) -> CellInfo | None:
        return self.cells.get(sheet, {}).get(coord)

    def all(self) -> Iterator[CellInfo]:
        for s in self.sheet_order:
            yield from self.cells[s].values()

    def value(self, c: CellInfo) -> object | None:
        """The number to use for value checks: the cached result of a formula, or the constant."""
        return c.cached if c.formula is not None else c.constant


def _color(cell: Cell) -> str | None:
    try:
        c = cell.font.color
        if c is not None and c.type == "rgb" and isinstance(c.rgb, str):
            return c.rgb.upper()
    except Exception:  # noqa: BLE001 - malformed styles must not stop the review
        return None
    return None


LAYOUT_SHEET = "_deskstack"  # hidden sheet written by build.py for the review scripts; not part of the model


def load(path: str, include_layout: bool = False) -> Workbook:
    wf = load_workbook(path, data_only=False)
    wv = load_workbook(path, data_only=True)
    names = [n for n in wf.sheetnames if include_layout or n != LAYOUT_SHEET]
    wb = Workbook(path=path, sheet_order=names)
    try:
        wb.iterate = bool(wf.calculation.iterate)
    except Exception:  # noqa: BLE001
        wb.iterate = False
    wb.external_links = len(getattr(wf, "_external_links", []) or [])
    for name in names:
        sf, sv = wf[name], wv[name]
        cells: dict[str, CellInfo] = {}
        for row in sf.iter_rows():
            for cell in row:
                if cell.value is None:
                    continue
                raw = cell.value
                formula = raw if isinstance(raw, str) and raw.startswith("=") else None
                cached = sv[cell.coordinate].value
                if formula is not None and cached is not None:
                    wb.has_cached_values = True
                cells[cell.coordinate] = CellInfo(
                    sheet=name,
                    coord=cell.coordinate,
                    row=cell.row,
                    col=cell.column,
                    formula=formula,
                    constant=None if formula else raw,
                    cached=cached,
                    font_color=_color(cell),
                )
        wb.cells[name] = cells
    return wb


def file_sha256(path: str) -> str:
    """Identifies the exact file a report was made from (reports carry it; sign-off compares it)."""
    import hashlib
    from pathlib import Path

    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def strip_strings(formula: str) -> str:
    return STRING_RE.sub('""', formula)


def references(formula: str, own_sheet: str) -> list[tuple[str, str]]:
    """(sheet, coord) for every cell a formula reads; small ranges are expanded (≤ 400 cells)."""
    f = strip_strings(formula)
    out: list[tuple[str, str]] = []
    for m in RANGE_RE.finditer(f):
        sheet = (m.group("sheet") or own_sheet).strip("'")
        c1, c2 = column_index_from_string(m.group("c1")), column_index_from_string(m.group("c2"))
        r1, r2 = int(m.group("r1")), int(m.group("r2"))
        if (abs(c2 - c1) + 1) * (abs(r2 - r1) + 1) <= 400:
            for c in range(min(c1, c2), max(c1, c2) + 1):
                for r in range(min(r1, r2), max(r1, r2) + 1):
                    out.append((sheet, f"{get_column_letter(c)}{r}"))
    f2 = RANGE_RE.sub(" ", f)
    for m in REF_RE.finditer(f2):
        out.append(((m.group("sheet") or own_sheet).strip("'"), f"{m.group('col')}{m.group('row')}"))
    return out


def relative_form(formula: str, row: int, col: int) -> str:
    """The formula with references made relative to its own cell (R1C1-like), to compare across a row."""

    def rel(m: re.Match[str]) -> str:
        sheet = m.group("sheet")
        cidx, ridx = column_index_from_string(m.group("col")), int(m.group("row"))
        # $-anchored parts stay absolute (R5C3), the rest becomes relative (R[-1]C[0]).
        cpart = f"C{cidx}" if m.group("cd") else f"C[{cidx - col}]"
        rpart = f"R{ridx}" if m.group("rd") else f"R[{ridx - row}]"
        return f"{(sheet + '!') if sheet else ''}{rpart}{cpart}"

    return REF_RE.sub(rel, strip_strings(formula))


def label_of(wb: Workbook, c: CellInfo) -> str:
    """The row label: the first text cell to the left on the same row (usually column A or B)."""
    for col in range(1, c.col):
        other = wb.get(c.sheet, f"{get_column_letter(col)}{c.row}")
        if other is not None and isinstance(other.constant, str) and other.constant.strip():
            return other.constant.strip()
    return ""


def rows_labeled(wb: Workbook, pattern: re.Pattern[str]) -> list[tuple[str, int, str]]:
    """(sheet, row, label) for rows whose label matches."""
    out = []
    for s in wb.sheet_order:
        for c in wb.cells[s].values():
            if isinstance(c.constant, str) and pattern.search(c.constant.strip()):
                out.append((s, c.row, c.constant.strip()))
    return out


def row_numbers(wb: Workbook, sheet: str, row: int) -> list[CellInfo]:
    """Numeric cells (constants or formulas) on a row, left to right."""
    cells = [c for c in wb.cells[sheet].values() if c.row == row and (c.formula is not None or c.is_number_constant)]
    return sorted(cells, key=lambda c: c.col)
