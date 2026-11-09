"""Write formula results into an .xlsx the way Excel does when it saves.

openpyxl writes formulas without results, so viewers that don't recalculate
show empty cells and value checks have nothing to read. Builders that know
each formula's value pass it here; it is written into the sheet XML as <v>.
"""

from __future__ import annotations

import datetime as _dt
import re
import zipfile
from pathlib import Path

MAX_UNZIPPED = 300 * 1024 * 1024  # a real financial model is a few MB unzipped
_DTD = re.compile(rb"<!(DOCTYPE|ENTITY)", re.I)


class UnsafeWorkbook(ValueError):
    pass


def check_safe(path: Path | str) -> None:
    """Refuse a workbook that could hang the parser: an XML DTD (entity expansion, the "billion laughs") or a zip
    that expands to hundreds of MB. Real .xlsx files never carry a DTD. Older expat builds (macOS's system Python
    3.9 ships 2.2.8) have no entity-expansion limit (security audit 2026-11-09)."""
    try:
        z = zipfile.ZipFile(path)
    except zipfile.BadZipFile as e:
        raise UnsafeWorkbook(f"{Path(path).name} is not a valid .xlsx file ({e}).") from None
    with z:
        infos = z.infolist()
        if sum(i.file_size for i in infos) > MAX_UNZIPPED:
            raise UnsafeWorkbook(f"{Path(path).name} expands to more than {MAX_UNZIPPED // 2**20} MB: refused.")
        for i in infos:
            if not i.filename.lower().endswith((".xml", ".rels", ".vml")):
                continue
            with z.open(i) as f:
                head = f.read(4096)  # a DTD comes before the root element
            if _DTD.search(head):
                raise UnsafeWorkbook(f"{Path(path).name} has an XML DTD in {i.filename}, which Excel never writes: refused.")


def safe_load_workbook(path: Path | str, **kw):
    """openpyxl's load_workbook, after check_safe."""
    from openpyxl import load_workbook

    check_safe(path)
    return load_workbook(path, **kw)


CELL_RE = r'<c r="{coord}"([^>]*)>(<f>.*?</f>)(<v>.*?</v>|<v\s*/>)?</c>'
ERRORS = {"#NULL!", "#DIV/0!", "#VALUE!", "#REF!", "#NAME?", "#NUM!", "#N/A"}


def inject_values(path: Path | str, cached: dict[tuple[str, str], object], sheets: list[str]) -> None:
    path = Path(path)
    tmp = path.with_suffix(".tmp.xlsx")
    with zipfile.ZipFile(path) as zin, zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            m = re.match(r"xl/worksheets/sheet(\d+)\.xml$", item.filename)
            if m:
                name = sheets[int(m.group(1)) - 1]
                xml = data.decode("utf-8")
                for (s, coord), v in cached.items():
                    if s == name:
                        xml = _set(xml, coord, v)
                data = xml.encode("utf-8")
            zout.writestr(item, data)
    tmp.replace(path)


def _set(xml: str, coord: str, v: object) -> str:
    pat = CELL_RE.format(coord=coord)
    if isinstance(v, str) and v in ERRORS:  # an error result such as #DIV/0!
        return re.sub(pat, lambda m: f'<c r="{coord}"{_t(m.group(1), "e")}>{m.group(2)}<v>{v}</v></c>', xml)
    if isinstance(v, str):
        esc = v.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        return re.sub(pat, lambda m: f'<c r="{coord}"{_t(m.group(1), "str")}>{m.group(2)}<v>{esc}</v></c>', xml)
    if isinstance(v, bool):
        return re.sub(pat, lambda m: f'<c r="{coord}"{_t(m.group(1), "b")}>{m.group(2)}<v>{int(v)}</v></c>', xml)
    if isinstance(v, (_dt.date, _dt.time, _dt.timedelta)):  # dates are serial numbers in the file
        from openpyxl.utils.datetime import to_excel

        v = to_excel(v)
    if not isinstance(v, (int, float)):
        return xml  # unknown type: leave the cell without a cached value rather than corrupt it
    val = repr(float(v))
    return re.sub(pat, lambda m: f'<c r="{coord}"{m.group(1)}>{m.group(2)}<v>{val}</v></c>', xml)


def _t(attrs: str, t: str) -> str:
    attrs = re.sub(r'\st="[^"]*"', "", attrs)
    return f'{attrs} t="{t}"'
