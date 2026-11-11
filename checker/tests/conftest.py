"""Before any test imports openpyxl: write workbooks without lxml, as CI does (examples/build.py explains why)."""

import os

os.environ["OPENPYXL_LXML"] = "False"
