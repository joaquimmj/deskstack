#!/usr/bin/env python3
"""Build evals/golden.json: questions with known answers, taken straight from the filed data.

Each question names the line item the way an analyst reads it on the face of the statements: the concept, the
period end, and whether it is a flow (one fiscal year) or a balance (an instant). The expected answer is read from
the filed facts:
  - SEC: the companyfacts JSON as filed (test/fixtures/sec). Among annual filings (10-K, 20-F and amendments) that
    report the period, the latest one wins, so restatements count. The original value is kept when it differs.
  - ESEF: the values Arelle reads from each published report (evals/fixtures/esef-arelle.json, written by
    esef_arelle.py), not deskstack's own extractor.
  - CVM (Brazil): the published CSVs read by account code with plain Python (evals/fixtures/cvm-answers.json, written
    by cvm_reader.py), not deskstack's own extractor. No second parser exists for CVM's CSVs.
  - Rates: the Treasury and ECB CSVs, by date.
A few questions check behavior instead of a number: a bank flagged as financial, null where a figure doesn't apply.

What this is not: independent of deskstack's choices. The concepts are picked by hand from the face statements and
usually match deskstack's first choice, and "latest annual filing wins" is deskstack's policy too. The nightly
differential test (evals/differential/) is the independent check: edgartools re-reads each SEC answer from the
filing's own XBRL instance and lists the issuer's filings itself, and Arelle re-reads the ESEF reports.

  python3 evals/build_golden.py           # writes evals/golden.json
  python3 evals/build_golden.py --check   # exits 1 if golden.json is out of date
"""

from __future__ import annotations

import csv
import datetime as dt
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIX = ROOT / "server" / "test" / "fixtures"
OUT = ROOT / "evals" / "golden.json"
ANNUAL_FORMS = {"10-K", "10-K/A", "20-F", "20-F/A", "40-F"}

GROUP = {
    "revenue": "income_statement", "operating_income": "income_statement", "net_income": "income_statement",
    "diluted_eps": "income_statement", "pretax_income": "income_statement", "gross_profit": "income_statement",
    "operating_cash_flow": "cash_flow", "capex": "cash_flow", "d_and_a": "cash_flow",
    "total_assets": "balance_sheet", "cash": "balance_sheet", "total_equity": "balance_sheet",
    "short_term_investments": "balance_sheet",
}
INSTANT = {"total_assets", "cash", "total_equity", "short_term_investments"}
LABEL = {
    "revenue": "revenue", "operating_income": "operating income", "net_income": "net income", "diluted_eps": "diluted EPS",
    "pretax_income": "pre-tax income", "gross_profit": "gross profit", "operating_cash_flow": "operating cash flow",
    "capex": "capital expenditures", "d_and_a": "depreciation and amortization", "total_assets": "total assets",
    "cash": "cash and cash equivalents", "total_equity": "total equity",
    "short_term_investments": "short-term investments",
}

# (ticker, period label, period end, [(metric, concept)], tags)
SEC = [
    ("AAPL", "FY2025", "2025-09-27", [("revenue", "RevenueFromContractWithCustomerExcludingAssessedTax"), ("net_income", "NetIncomeLoss"),
     ("operating_cash_flow", "NetCashProvidedByUsedInOperatingActivities"), ("capex", "PaymentsToAcquirePropertyPlantAndEquipment"),
     ("diluted_eps", "EarningsPerShareDiluted"), ("total_assets", "Assets")], ["us", "52-53-week year", "september-fye"]),
    ("AAPL", "FY2023", "2023-09-30", [("revenue", "RevenueFromContractWithCustomerExcludingAssessedTax"), ("net_income", "NetIncomeLoss")],
     ["us", "53-week year", "september-fye"]),
    ("AAPL", "FY2024", "2024-09-28", [("revenue", "RevenueFromContractWithCustomerExcludingAssessedTax"), ("net_income", "NetIncomeLoss"),
     ("operating_income", "OperatingIncomeLoss"), ("diluted_eps", "EarningsPerShareDiluted"), ("total_assets", "Assets")], ["us", "52-53-week year", "september-fye"]),
    ("MSFT", "FY2026", "2026-06-30", [("revenue", "RevenueFromContractWithCustomerExcludingAssessedTax"), ("net_income", "NetIncomeLoss"),
     ("operating_income", "OperatingIncomeLoss"), ("operating_cash_flow", "NetCashProvidedByUsedInOperatingActivities"),
     ("capex", "PaymentsToAcquirePropertyPlantAndEquipment"), ("diluted_eps", "EarningsPerShareDiluted"), ("total_assets", "Assets")], ["us", "june-fye"]),
    ("MSFT", "FY2025", "2025-06-30", [("revenue", "RevenueFromContractWithCustomerExcludingAssessedTax"), ("net_income", "NetIncomeLoss"),
     ("diluted_eps", "EarningsPerShareDiluted")], ["us", "june-fye"]),
    ("GOOGL", "FY2025", "2025-12-31", [("revenue", "Revenues"), ("net_income", "NetIncomeLoss"), ("operating_income", "OperatingIncomeLoss"),
     ("operating_cash_flow", "NetCashProvidedByUsedInOperatingActivities"), ("capex", "PaymentsToAcquirePropertyPlantAndEquipment"),
     ("diluted_eps", "EarningsPerShareDiluted")], ["us"]),
    ("GOOGL", "FY2024", "2024-12-31", [("revenue", "Revenues"), ("net_income", "NetIncomeLoss"), ("total_assets", "Assets")], ["us"]),
    ("GOOGL", "FY2021", "2021-12-31", [("diluted_eps", "EarningsPerShareDiluted")], ["us", "stock-split"]),
    ("KO", "FY2025", "2025-12-31", [("revenue", "Revenues"), ("gross_profit", "GrossProfit"), ("operating_income", "OperatingIncomeLoss"),
     ("net_income", "NetIncomeLoss"), ("operating_cash_flow", "NetCashProvidedByUsedInOperatingActivities"), ("diluted_eps", "EarningsPerShareDiluted"),
     ("total_assets", "Assets")], ["us"]),
    ("KO", "FY2024", "2024-12-31", [("revenue", "Revenues"), ("net_income", "NetIncomeLoss")], ["us"]),
    ("CAT", "FY2025", "2025-12-31", [("revenue", "Revenues"), ("operating_income", "OperatingIncomeLoss"), ("net_income", "NetIncomeLoss|NetIncomeLossAvailableToCommonStockholdersBasic"),
     ("operating_cash_flow", "NetCashProvidedByUsedInOperatingActivities"), ("diluted_eps", "EarningsPerShareDiluted")], ["us", "industrial"]),
    ("CAT", "FY2024", "2024-12-31", [("revenue", "Revenues"), ("net_income", "NetIncomeLoss|NetIncomeLossAvailableToCommonStockholdersBasic")], ["us", "industrial"]),
    ("JPM", "FY2025", "2025-12-31", [("revenue", "Revenues"), ("net_income", "NetIncomeLoss"), ("diluted_eps", "EarningsPerShareDiluted"),
     ("total_assets", "Assets")], ["us", "bank"]),
    ("JPM", "FY2024", "2024-12-31", [("net_income", "NetIncomeLoss"), ("pretax_income", "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest")], ["us", "bank"]),
    ("SAP", "FY2025", "2025-12-31", [("revenue", "Revenue"), ("operating_income", "ProfitLossFromOperatingActivities"),
     ("net_income", "ProfitLossAttributableToOwnersOfParent"), ("operating_cash_flow", "CashFlowsFromUsedInOperatingActivities"),
     ("diluted_eps", "DilutedEarningsLossPerShare")], ["ifrs", "20-F", "eur"]),
    ("SAP", "FY2024", "2024-12-31", [("revenue", "Revenue"), ("operating_cash_flow", "CashFlowsFromUsedInOperatingActivities"), ("total_assets", "Assets")], ["ifrs", "20-F", "eur"]),
    ("SAP", "FY2022", "2022-12-31", [("revenue", "Revenue"), ("pretax_income", "ProfitLossBeforeTax")], ["ifrs", "20-F", "eur", "discontinued-operations"]),
    ("TM", "FY2025", "2025-03-31", [("revenue", "Revenue"), ("operating_income", "ProfitLossFromOperatingActivities"),
     ("net_income", "ProfitLossAttributableToOwnersOfParent"), ("total_assets", "Assets")], ["ifrs", "20-F", "jpy", "march-fye"]),
    ("UL", "FY2025", "2025-12-31", [("revenue", "Revenue"), ("operating_income", "ProfitLossFromOperatingActivities"),
     ("net_income", "ProfitLossAttributableToOwnersOfParent")], ["ifrs", "20-F", "eur"]),
]

# (LEI, name, period label, report file, period start, end, [(metric, concept)], tags)
ESEF = [
    ("529900S21EQ1BO4ESM68", "TotalEnergies", "FY2025", "529900S21EQ1BO4ESM68-2025-12-31-ESEF-FR-0", "2025-01-01", "2025-12-31",
     [("revenue", "RevenueFromContractsWithCustomers"), ("net_income", "ProfitLossAttributableToOwnersOfParent"), ("total_assets", "Assets"),
      ("cash", "CashAndCashEquivalents"), ("operating_cash_flow", "CashFlowsFromUsedInOperatingActivities")], ["eu", "esef", "usd-reporter"]),
    ("529900S21EQ1BO4ESM68", "TotalEnergies", "FY2024", "529900S21EQ1BO4ESM68-2025-12-31-ESEF-FR-0", "2024-01-01", "2024-12-31",
     [("revenue", "RevenueFromContractsWithCustomers"), ("net_income", "ProfitLossAttributableToOwnersOfParent"), ("total_assets", "Assets"),
      ("cash", "CashAndCashEquivalents"), ("operating_cash_flow", "CashFlowsFromUsedInOperatingActivities")], ["eu", "esef", "usd-reporter", "comparative"]),
    ("549300TTCXZOGZM2EY83", "Inditex", "FY2025", "549300TTCXZOGZM2EY83-2026-01-31-ESEF-ES-0", "2025-02-01", "2026-01-31",
     [("revenue", "Revenue"), ("net_income", "ProfitLossAttributableToOwnersOfParent"), ("total_assets", "Assets"),
      ("short_term_investments", "ShorttermDepositsNotClassifiedAsCashEquivalents"),
      ("cash", "CashAndCashEquivalents"), ("operating_cash_flow", "CashFlowsFromUsedInOperatingActivities")], ["eu", "esef", "january-fye", "ifrs16"]),
    ("549300TTCXZOGZM2EY83", "Inditex", "FY2024", "549300TTCXZOGZM2EY83-2026-01-31-ESEF-ES-0", "2024-02-01", "2025-01-31",
     [("revenue", "Revenue"), ("net_income", "ProfitLossAttributableToOwnersOfParent"), ("total_assets", "Assets"),
      ("cash", "CashAndCashEquivalents")], ["eu", "esef", "january-fye", "comparative"]),
    # Only reported as the comparative in the FY2024 report: its label must be counted back (FY2023), not taken from
    # the end year (2024, which is the next fiscal year's label for a January year-end).
    ("549300TTCXZOGZM2EY83", "Inditex", "FY2023", "549300TTCXZOGZM2EY83-2025-01-31-ESEF-ES-0", "2023-02-01", "2024-01-31",
     [("revenue", "Revenue")], ["eu", "esef", "january-fye", "comparative-only"]),
    # Stars brief lot 2 bis: one issuer per further country, ten questions each (two years, five lines).
    ("724500K5PTPSST86UQ23", "Heineken", "FY2025", "724500K5PTPSST86UQ23-2025-12-31-ESEF-NL-0", "2025-01-01", "2025-12-31",
     [('revenue', 'Revenue'), ('net_income', 'ProfitLossAttributableToOwnersOfParent'), ('operating_cash_flow', 'CashFlowsFromUsedInOperatingActivities'), ('total_assets', 'Assets'), ('cash', 'CashAndCashEquivalents')], ['eu', 'esef', 'nl']),
    ("724500K5PTPSST86UQ23", "Heineken", "FY2024", "724500K5PTPSST86UQ23-2025-12-31-ESEF-NL-0", "2024-01-01", "2024-12-31",
     [('revenue', 'Revenue'), ('net_income', 'ProfitLossAttributableToOwnersOfParent'), ('operating_cash_flow', 'CashFlowsFromUsedInOperatingActivities'), ('total_assets', 'Assets'), ('cash', 'CashAndCashEquivalents')], ['eu', 'esef', 'nl', 'comparative']),
    ("5493009GY1X8GQ66AM14", "Neste", "FY2025", "5493009GY1X8GQ66AM14-2025-12-31-ESEF-FI-0", "2025-01-01", "2025-12-31",
     [('revenue', 'Revenue'), ('net_income', 'ProfitLossAttributableToOwnersOfParent'), ('operating_cash_flow', 'CashFlowsFromUsedInOperatingActivities'), ('total_assets', 'Assets'), ('cash', 'CashAndCashEquivalents')], ['eu', 'esef', 'fi']),
    ("5493009GY1X8GQ66AM14", "Neste", "FY2024", "5493009GY1X8GQ66AM14-2025-12-31-ESEF-FI-0", "2024-01-01", "2024-12-31",
     [('revenue', 'Revenue'), ('net_income', 'ProfitLossAttributableToOwnersOfParent'), ('operating_cash_flow', 'CashFlowsFromUsedInOperatingActivities'), ('total_assets', 'Assets'), ('cash', 'CashAndCashEquivalents')], ['eu', 'esef', 'fi', 'comparative']),
    ("5493008H3828EMEXB082", "AB InBev", "FY2025", "5493008H3828EMEXB082-2025-12-31-ESEF-BE-0", "2025-01-01", "2025-12-31",
     [('revenue', 'Revenue'), ('net_income', 'ProfitLossAttributableToOwnersOfParent'), ('operating_cash_flow', 'CashFlowsFromUsedInOperatingActivities'), ('total_assets', 'Assets'), ('cash', 'CashAndCashEquivalents')], ['eu', 'esef', 'be']),
    ("5493008H3828EMEXB082", "AB InBev", "FY2024", "5493008H3828EMEXB082-2025-12-31-ESEF-BE-0", "2024-01-01", "2024-12-31",
     [('revenue', 'Revenue'), ('net_income', 'ProfitLossAttributableToOwnersOfParent'), ('operating_cash_flow', 'CashFlowsFromUsedInOperatingActivities'), ('total_assets', 'Assets'), ('cash', 'CashAndCashEquivalents')], ['eu', 'esef', 'be', 'comparative']),
    ("815600EBD7FB00525B20", "Moncler", "FY2025", "815600EBD7FB00525B20-2025-12-31-ESEF-IT-0", "2025-01-01", "2025-12-31",
     [('revenue', 'Revenue'), ('net_income', 'ProfitLossAttributableToOwnersOfParent'), ('operating_cash_flow', 'CashFlowsFromUsedInOperatingActivities'), ('total_assets', 'Assets'), ('cash', 'CashAndCashEquivalents')], ['eu', 'esef', 'it']),
    ("815600EBD7FB00525B20", "Moncler", "FY2024", "815600EBD7FB00525B20-2025-12-31-ESEF-IT-0", "2024-01-01", "2024-12-31",
     [('revenue', 'Revenue'), ('net_income', 'ProfitLossAttributableToOwnersOfParent'), ('operating_cash_flow', 'CashFlowsFromUsedInOperatingActivities'), ('total_assets', 'Assets'), ('cash', 'CashAndCashEquivalents')], ['eu', 'esef', 'it', 'comparative']),
    ("2138003319Y7NM75FG53", "Galp", "FY2025", "2138003319Y7NM75FG53-2025-12-31-ESEF-PT-0", "2025-01-01", "2025-12-31",
     [('net_income', 'ProfitLossAttributableToOwnersOfParent'), ('operating_cash_flow', 'CashFlowsFromUsedInOperatingActivities'), ('total_assets', 'Assets'), ('cash', 'CashAndCashEquivalents')], ['eu', 'esef', 'pt']),
    ("2138003319Y7NM75FG53", "Galp", "FY2024", "2138003319Y7NM75FG53-2025-12-31-ESEF-PT-0", "2024-01-01", "2024-12-31",
     [('net_income', 'ProfitLossAttributableToOwnersOfParent'), ('operating_cash_flow', 'CashFlowsFromUsedInOperatingActivities'), ('total_assets', 'Assets'), ('cash', 'CashAndCashEquivalents')], ['eu', 'esef', 'pt', 'comparative']),
    ("2138003319Y7NM75FG53", "Galp", "FY2023", "2138003319Y7NM75FG53-2024-12-31-ESEF-PT-0", "2023-01-01", "2023-12-31",
     [('net_income', 'ProfitLossAttributableToOwnersOfParent'), ('total_assets', 'Assets')], ['eu', 'esef', 'pt', 'comparative']),
    ("549300V62YJ9HTLRI486", "OMV", "FY2025", "549300V62YJ9HTLRI486-2025-12-31-ESEF-AT-0", "2025-01-01", "2025-12-31",
     [('revenue', 'Revenue'), ('pretax_income', 'ProfitLossBeforeTax'), ('operating_cash_flow', 'CashFlowsFromUsedInOperatingActivities'), ('total_assets', 'Assets'), ('cash', 'CashAndCashEquivalents')], ['eu', 'esef', 'at']),
    ("549300V62YJ9HTLRI486", "OMV", "FY2024", "549300V62YJ9HTLRI486-2025-12-31-ESEF-AT-0", "2024-01-01", "2024-12-31",
     [('revenue', 'Revenue'), ('pretax_income', 'ProfitLossBeforeTax'), ('operating_cash_flow', 'CashFlowsFromUsedInOperatingActivities'), ('total_assets', 'Assets'), ('cash', 'CashAndCashEquivalents')], ['eu', 'esef', 'at', 'comparative']),
    ("635400TLVVBNXLFHWC59", "Kerry", "FY2024", "635400TLVVBNXLFHWC59-2024-12-31-ESEF-GB-0", "2024-01-01", "2024-12-31",
     [('revenue', 'Revenue'), ('net_income', 'ProfitLoss'), ('operating_cash_flow', 'CashFlowsFromUsedInOperatingActivities'), ('total_assets', 'Assets'), ('cash', 'CashAndCashEquivalents')], ['eu', 'esef', 'ie']),
    ("635400TLVVBNXLFHWC59", "Kerry", "FY2023", "635400TLVVBNXLFHWC59-2024-12-31-ESEF-GB-0", "2023-01-01", "2023-12-31",
     [('revenue', 'Revenue'), ('operating_cash_flow', 'CashFlowsFromUsedInOperatingActivities'), ('total_assets', 'Assets'), ('cash', 'CashAndCashEquivalents')], ['eu', 'esef', 'ie', 'comparative', 'restated']),
    # The 2024 report tags only total profit for FY2023; the owners' share is tagged in the 2023 report.
    ("635400TLVVBNXLFHWC59", "Kerry", "FY2023", "635400TLVVBNXLFHWC59-2023-12-31-ESEF-GB-0", "2023-01-01", "2023-12-31",
     [('net_income', 'ProfitLossAttributableToOwnersOfParent')], ['eu', 'esef', 'ie']),
    ("2EULGUTUI56JI9SAL165", "ArcelorMittal", "FY2024", "2EULGUTUI56JI9SAL165-2024-12-31-ESEF-LU-0", "2024-01-01", "2024-12-31",
     [('revenue', 'RevenueFromContractsWithCustomers'), ('net_income', 'ProfitLossAttributableToOwnersOfParent'), ('operating_cash_flow', 'CashFlowsFromUsedInOperatingActivities'), ('total_assets', 'Assets'), ('cash', 'CashAndCashEquivalents')], ['eu', 'esef', 'lu']),
    ("2EULGUTUI56JI9SAL165", "ArcelorMittal", "FY2023", "2EULGUTUI56JI9SAL165-2024-12-31-ESEF-LU-0", "2023-01-01", "2023-12-31",
     [('revenue', 'RevenueFromContractsWithCustomers'), ('net_income', 'ProfitLossAttributableToOwnersOfParent'), ('operating_cash_flow', 'CashFlowsFromUsedInOperatingActivities'), ('total_assets', 'Assets'), ('cash', 'CashAndCashEquivalents')], ['eu', 'esef', 'lu', 'comparative']),
    ("549300DAQ1CVT6CXN342", "Novo Nordisk", "FY2025", "549300DAQ1CVT6CXN342-2025-12-31-ESEF-DK-0", "2025-01-01", "2025-12-31",
     [('revenue', 'Revenue'), ('net_income', 'ProfitLoss'), ('operating_cash_flow', 'CashFlowsFromUsedInOperatingActivities'), ('total_assets', 'Assets'), ('cash', 'CashAndCashEquivalents')], ['eu', 'esef', 'dk']),
    ("549300DAQ1CVT6CXN342", "Novo Nordisk", "FY2024", "549300DAQ1CVT6CXN342-2025-12-31-ESEF-DK-0", "2024-01-01", "2024-12-31",
     [('revenue', 'Revenue'), ('net_income', 'ProfitLoss'), ('operating_cash_flow', 'CashFlowsFromUsedInOperatingActivities'), ('total_assets', 'Assets'), ('cash', 'CashAndCashEquivalents')], ['eu', 'esef', 'dk', 'comparative']),
    ("213800T8PC8Q4FYJZR07", "Atlas Copco", "FY2025", "213800T8PC8Q4FYJZR07-2025-12-31-ESEF-SE-0", "2025-01-01", "2025-12-31",
     [('revenue', 'Revenue'), ('net_income', 'ProfitLossAttributableToOwnersOfParent'), ('operating_cash_flow', 'CashFlowsFromUsedInOperatingActivities'), ('total_assets', 'Assets'), ('cash', 'CashAndCashEquivalents')], ['eu', 'esef', 'se']),
    ("213800T8PC8Q4FYJZR07", "Atlas Copco", "FY2024", "213800T8PC8Q4FYJZR07-2025-12-31-ESEF-SE-0", "2024-01-01", "2024-12-31",
     [('revenue', 'Revenue'), ('net_income', 'ProfitLossAttributableToOwnersOfParent'), ('operating_cash_flow', 'CashFlowsFromUsedInOperatingActivities'), ('total_assets', 'Assets'), ('cash', 'CashAndCashEquivalents')], ['eu', 'esef', 'se', 'comparative']),
    ("OW6OFBNCKXC4US5C7523", "Equinor", "FY2025", "OW6OFBNCKXC4US5C7523-2025-12-31-ESEF-NO-0", "2025-01-01", "2025-12-31",
     [('revenue', 'Revenue'), ('net_income', 'ProfitLossAttributableToOwnersOfParent'), ('operating_cash_flow', 'CashFlowsFromUsedInOperatingActivities'), ('total_assets', 'Assets'), ('cash', 'CashAndCashEquivalents')], ['eu', 'esef', 'no']),
    ("OW6OFBNCKXC4US5C7523", "Equinor", "FY2024", "OW6OFBNCKXC4US5C7523-2025-12-31-ESEF-NO-0", "2024-01-01", "2024-12-31",
     [('revenue', 'Revenue'), ('net_income', 'ProfitLossAttributableToOwnersOfParent'), ('operating_cash_flow', 'CashFlowsFromUsedInOperatingActivities'), ('total_assets', 'Assets'), ('cash', 'CashAndCashEquivalents')], ['eu', 'esef', 'no', 'comparative']),
    # UK listed (UKSEF): AstraZeneca reports in USD; Tesco's year ends in February (FY2025 has 53 weeks) and it tags no total assets.
    ("PY6ZZQWO2IZFZC3IOL08", "AstraZeneca", "FY2025", "PY6ZZQWO2IZFZC3IOL08-2025-12-31-ESEF-GB-0", "2025-01-01", "2025-12-31",
     [('revenue', 'Revenue'), ('net_income', 'ProfitLossAttributableToOwnersOfParent'), ('operating_cash_flow', 'CashFlowsFromUsedInOperatingActivities'), ('total_assets', 'Assets'), ('cash', 'CashAndCashEquivalents')], ['eu', 'uksef', 'gb', 'usd-reporter']),
    ("PY6ZZQWO2IZFZC3IOL08", "AstraZeneca", "FY2024", "PY6ZZQWO2IZFZC3IOL08-2025-12-31-ESEF-GB-0", "2024-01-01", "2024-12-31",
     [('revenue', 'Revenue'), ('net_income', 'ProfitLossAttributableToOwnersOfParent'), ('operating_cash_flow', 'CashFlowsFromUsedInOperatingActivities'), ('total_assets', 'Assets'), ('cash', 'CashAndCashEquivalents')], ['eu', 'uksef', 'gb', 'usd-reporter', 'comparative']),
    ("2138002P5RNKC5W2JZ46", "Tesco", "FY2025", "2138002P5RNKC5W2JZ46-2026-02-28-ESEF-GB-0", "2025-02-23", "2026-02-28",
     [('revenue', 'Revenue'), ('net_income', 'ProfitLossAttributableToOwnersOfParent'), ('operating_cash_flow', 'CashFlowsFromUsedInOperatingActivities'), ('cash', 'CashAndCashEquivalents')], ['eu', 'uksef', 'gb', 'february-fye', '53-week year']),
    ("2138002P5RNKC5W2JZ46", "Tesco", "FY2024", "2138002P5RNKC5W2JZ46-2026-02-28-ESEF-GB-0", "2024-02-25", "2025-02-22",
     [('revenue', 'Revenue'), ('net_income', 'ProfitLossAttributableToOwnersOfParent'), ('operating_cash_flow', 'CashFlowsFromUsedInOperatingActivities'), ('cash', 'CashAndCashEquivalents')], ['eu', 'uksef', 'gb', 'february-fye', 'comparative']),
]

# Behavior checks: (id, question, call, read, expected, tags)
BEHAVIOR = [
    ("jpm-financial-flag", "Is JPMorgan Chase flagged as a financial company (EV and EBITDA metrics don't apply)?",
     {"tool": "financial_statements", "args": {"ticker": "JPM", "years": 1}}, {"kind": "path", "path": "company.financial_company"}, True, ["us", "bank"]),
    ("jpm-no-operating-income", "Does JPMorgan Chase's FY2025 operating income come back null (banks don't report it)?",
     {"tool": "financial_statements", "args": {"ticker": "JPM", "years": 2}}, {"kind": "fs", "period": "FY2025", "group": "income_statement", "key": "operating_income"}, None, ["us", "bank", "null"]),
    ("jpm-no-capex", "Does JPMorgan Chase's FY2025 capex come back null rather than 0?",
     {"tool": "financial_statements", "args": {"ticker": "JPM", "years": 2}}, {"kind": "fs", "period": "FY2025", "group": "cash_flow", "key": "capex"}, None, ["us", "bank", "null"]),
    ("aapl-not-financial", "Is Apple not flagged as a financial company?",
     {"tool": "financial_statements", "args": {"ticker": "AAPL", "years": 1}}, {"kind": "path", "path": "company.financial_company"}, False, ["us"]),
    ("sap-ifrs", "Does SAP report under IFRS, in euros?",
     {"tool": "financial_statements", "args": {"ticker": "SAP", "years": 1}}, {"kind": "path", "path": "company.reporting_standard"}, "IFRS", ["ifrs", "20-F"]),
    ("sap-currency", "Is SAP's reporting currency EUR?",
     {"tool": "financial_statements", "args": {"ticker": "SAP", "years": 1}}, {"kind": "path", "path": "company.currency"}, "EUR", ["ifrs", "20-F", "eur"]),
    ("sap-no-ltm", "Does SAP (a 20-F filer with no XBRL interims) have no LTM period?",
     {"tool": "financial_statements", "args": {"ticker": "SAP", "years": 2}}, {"kind": "has_ltm"}, False, ["ifrs", "20-F", "ltm"]),
    ("aapl-has-ltm", "Does Apple have an LTM period?",
     {"tool": "financial_statements", "args": {"ticker": "AAPL", "years": 1}}, {"kind": "has_ltm"}, True, ["us", "ltm"]),
    ("tte-currency", "Is TotalEnergies' reporting currency USD (it reports in dollars, not euros)?",
     {"tool": "financial_statements", "args": {"ticker": "529900S21EQ1BO4ESM68", "years": 5}}, {"kind": "path", "path": "company.currency"}, "USD", ["eu", "esef", "usd-reporter"]),
    ("msft-fye", "Does Microsoft's FY2026 end on 2026-06-30?",
     {"tool": "financial_statements", "args": {"ticker": "MSFT", "years": 2}}, {"kind": "period_end", "period": "FY2026"}, "2026-06-30", ["us", "june-fye"]),
    ("aapl-fye", "Does Apple's FY2025 end on 2025-09-27 (a 52/53-week year)?",
     {"tool": "financial_statements", "args": {"ticker": "AAPL", "years": 2}}, {"kind": "period_end", "period": "FY2025"}, "2025-09-27", ["us", "52-53-week year"]),
    ("itx-fye", "Does Inditex's FY2025 end on 2026-01-31?",
     {"tool": "financial_statements", "args": {"ticker": "549300TTCXZOGZM2EY83", "years": 5}}, {"kind": "period_end", "period": "FY2025"}, "2026-01-31", ["eu", "esef", "january-fye"]),
]


# Behavior that holds on the recorded fixtures but changes with new filings (skipped by the live run).
FIXTURE_ONLY = {"aapl-has-ltm"}  # true only while a 10-Q follows the last 10-K


def _days(a: str, b: str) -> int:
    return (dt.date.fromisoformat(b) - dt.date.fromisoformat(a)).days


def sec_answer(ticker: str, concepts: str, end: str, instant: bool, per_share: bool = False) -> dict:
    """`concepts` may list alternatives, 'A|B': the first one the filer tagged for that period is the answer."""
    for concept in concepts.split("|"):
        try:
            return _sec_answer(ticker, concept, end, instant, per_share)
        except LookupError:
            continue
    raise SystemExit(f"{ticker}: no annual fact for {concepts} ending {end}")


def _sec_answer(ticker: str, concept: str, end: str, instant: bool, per_share: bool) -> dict:
    d = json.loads((FIX / "sec" / f"facts_{ticker}.json").read_text())
    cands = []
    for tax in ("us-gaap", "ifrs-full"):  # the taxonomy is whichever holds the fact, not the first that has the concept
        node = d["facts"].get(tax, {}).get(concept)
        if not node:
            continue
        for unit, facts in node["units"].items():
          if per_share != unit.endswith("/shares") or unit in ("shares", "pure"):
              continue  # EPS in currency per share; amounts in a currency
          for f in facts:
            if f.get("form") not in ANNUAL_FORMS or f["end"] != end:
                continue
            if instant != ("start" not in f or f.get("start") is None):
                continue
            if not instant and not 350 <= _days(f["start"], f["end"]) <= 380:
                continue
            cands.append({**f, "unit": unit, "taxonomy": tax})
    if not cands:
        raise LookupError(concept)
    cands.sort(key=lambda f: (f["filed"], f["accn"]))
    latest, first = cands[-1], cands[0]
    out = {"value": latest["val"], "unit": latest["unit"], "source": {
        "type": "sec-companyfacts", "ticker": ticker, "concept": f"{latest['taxonomy']}:{concept}", "accession": latest["accn"],
        "form": latest["form"], "filed": latest["filed"], "start": latest.get("start"), "end": end}}
    if first["val"] != latest["val"]:
        out["source"]["original"] = {"value": first["val"], "accession": first["accn"], "filed": first["filed"]}
    return out


ARELLE = ROOT / "evals" / "fixtures" / "esef-arelle.json"


def esef_answer(report: str, concept: str, start: str, end: str, instant: bool) -> dict:
    data = json.loads(ARELLE.read_text())
    want = (report, f"ifrs-full:{concept}", None if instant else start, end)
    rows = [f for f in data["facts"] if (f["report"], f["concept"], f["start"], f["end"]) == want]
    if len(rows) != 1:
        raise SystemExit(f"{report}: {concept} {start}..{end} not in {ARELLE.name}: run python3 evals/esef_arelle.py")
    v = rows[0]["value"]
    return {"value": int(v) if float(v).is_integer() else v, "unit": None, "source": {
        "type": "esef", "report": report, "concept": f"ifrs-full:{concept}", "start": None if instant else start, "end": end,
        "parser": data["parser"], "url": f"https://filings.xbrl.org/{report}"}}


# Brazil: CVM DFP, read by fixed account code. (cd_cvm, name, period label, start, end, [(metric, statement, code)], tags)
CVM_ANSWERS = ROOT / "evals" / "fixtures" / "cvm-answers.json"
_BR_LINES = [("revenue", "DRE", "3.01"), ("operating_income", "DRE", "3.05"), ("net_income", "DRE", "3.11.01"),
             ("total_assets", "BPA", "1"), ("cash", "BPA", "1.01.01"), ("operating_cash_flow", "DFC", "6.01")]
CVM = [
    ("009512", "Petrobras", "FY2025", "2025-01-01", "2025-12-31", _BR_LINES, ["br", "cvm"]),
    ("009512", "Petrobras", "FY2024", "2024-01-01", "2024-12-31", [("revenue", "DRE", "3.01"), ("net_income", "DRE", "3.11.01")], ["br", "cvm", "comparative"]),
    ("004170", "Vale", "FY2025", "2025-01-01", "2025-12-31", _BR_LINES, ["br", "cvm"]),
    ("005410", "WEG", "FY2025", "2025-01-01", "2025-12-31", _BR_LINES, ["br", "cvm"]),
    ("023264", "Ambev", "FY2025", "2025-01-01", "2025-12-31", _BR_LINES, ["br", "cvm"]),
    ("020087", "Embraer", "FY2025", "2025-01-01", "2025-12-31", _BR_LINES, ["br", "cvm"]),
    ("020087", "Embraer", "FY2024", "2024-01-01", "2024-12-31", [("revenue", "DRE", "3.01"), ("total_assets", "BPA", "1")], ["br", "cvm", "comparative"]),
]


def cvm_answer(cd: str, statement: str, code: str, start: str, end: str, instant: bool) -> dict:
    data = json.loads(CVM_ANSWERS.read_text())
    rows = [a for a in data["answers"] if (a["cd_cvm"], a["statement"], a["code"], a["start"], a["end"]) ==
            (cd, statement, code, None if instant else start, end)]
    if len(rows) != 1:
        raise SystemExit(f"CVM {cd} {statement} {code} {start}..{end} not in {CVM_ANSWERS.name}: run python3 evals/cvm_reader.py")
    a = rows[0]
    return {"value": a["value"], "unit": None, "source": {"type": "cvm-dfp", "filing": a["filing"], "account": f"{statement} {code}",
            "label": a["label"], "start": a["start"], "end": end, "parser": data["parser"], "url": a["url"]}}


def treasury_answer(date: str, col: str) -> dict:
    year = date[:4]
    with open(FIX / "rates" / f"treasury_{year}.csv") as f:
        for row in csv.DictReader(f):
            m, d_, y = row["Date"].split("/")
            if f"{y}-{m}-{d_}" == date:
                return {"value": round(float(row[col]) / 100, 6), "unit": "decimal", "source": {"type": "treasury-par-yield", "date": date, "column": col}}
    raise SystemExit(f"Treasury {date} not in fixture")


def ecb_answer(cur: str, date: str) -> dict:
    with open(FIX / "rates" / f"ecb_EXR_{cur}_{date[:4]}.csv") as f:
        for row in csv.DictReader(f):
            if row["TIME_PERIOD"] == date:
                return {"value": float(row["OBS_VALUE"]), "unit": f"{cur} per EUR", "source": {"type": "ecb-exr", "series": row["KEY"], "date": date}}
    raise SystemExit(f"ECB {cur} {date} not in fixture")


def build() -> dict:
    qs = []
    for ticker, label, end, items, tags in SEC:
        for metric, concept in items:
            a = sec_answer(ticker, concept, end, metric in INSTANT, metric == "diluted_eps")
            t = list(tags) + (["restated"] if "original" in a["source"] else [])
            qs.append({
                "id": f"{ticker.lower()}-{label.lower()}-{metric.replace('_', '-')}",
                "question": f"What was {ticker}'s {LABEL[metric]} for {label} (period ending {end})?",
                "tags": t,
                "call": {"tool": "financial_statements", "args": {"ticker": ticker, "years": 10}},
                "read": {"kind": "fs", "period": label, "group": GROUP[metric], "key": metric, "end": end,
                         "accession": a["source"]["accession"]},
                "expected": a["value"], "unit": a["unit"], "source": a["source"],
            })
    for lei, name, label, report, start, end, items, tags in ESEF:
        for metric, concept in items:
            a = esef_answer(report, concept, start, end, metric in INSTANT)
            qs.append({
                "id": f"{re.sub('[^a-z0-9]+', '-', name.lower())}-{label.lower()}-{metric.replace('_', '-')}",
                "question": f"What was {name}'s {LABEL[metric]} for {label} (period ending {end})?",
                "tags": list(tags),
                "call": {"tool": "financial_statements", "args": {"ticker": lei, "years": 5}},
                "read": {"kind": "fs", "period": label, "group": GROUP[metric], "key": metric, "end": end},
                "expected": a["value"], "unit": a["unit"], "source": a["source"],
            })
    for cd, name, label, start, end, items, tags in CVM:
        for metric, statement, code in items:
            a = cvm_answer(cd, statement, code, start, end, metric in INSTANT)
            qs.append({
                "id": f"{name.lower()}-{label.lower()}-{metric.replace('_', '-')}",
                "question": f"What was {name}'s {LABEL[metric]} for {label} (period ending {end})?",
                "tags": list(tags),
                "call": {"tool": "financial_statements", "args": {"ticker": f"CVM{int(cd)}", "years": 5}},
                "read": {"kind": "fs", "period": label, "group": GROUP[metric], "key": metric, "end": end,
                         "accession": a["source"]["filing"]},
                "expected": a["value"], "unit": a["unit"], "source": a["source"],
            })
    ltm = json.loads(CVM_ANSWERS.read_text())["ltm"]
    names = {cd: name for cd, name, *_ in CVM}
    for a in ltm:
        metric = {"3.01": "revenue", "3.11.01": "net_income"}.get(a["code"]) if a["statement"] == "DRE" else None
        if not metric:
            continue
        name = names[a["cd_cvm"]]
        label = f"LTM to {a['end']}"
        qs.append({
            "id": f"{name.lower()}-ltm-{metric.replace('_', '-')}",
            "question": f"What was {name}'s {LABEL[metric]} for the last twelve months to {a['end']}?",
            "tags": ["br", "cvm", "ltm"],
            "call": {"tool": "financial_statements", "args": {"ticker": f"CVM{int(a['cd_cvm'])}", "years": 2}},
            "read": {"kind": "fs", "period": label, "group": GROUP[metric], "key": metric, "end": a["end"]},
            "expected": a["value"], "unit": None,
            "source": {"type": "cvm-ltm", "formula": a["formula"], "fy_filing": a["fy_filing"], "itr_filing": a["itr_filing"],
                       "parser": "python csv (evals/cvm_reader.py)"},
        })
    for date in ("2026-10-30", "2025-12-31"):
        a = treasury_answer(date, "10 Yr")
        qs.append({"id": f"ust10y-{date}", "question": f"What was the US 10-year Treasury par yield on {date}?", "tags": ["rates", "us"],
                   "call": {"tool": "risk_free_rate", "args": {"region": "US", "tenor": "10Y", "date": date}},
                   "read": {"kind": "path", "path": "rate_decimal"}, "expected": a["value"], "unit": a["unit"], "source": a["source"]})
    for cur, date in (("USD", "2025-06-30"), ("USD", "2025-12-31"), ("JPY", "2025-12-31")):
        a = ecb_answer(cur, date)
        qs.append({"id": f"eur{cur.lower()}-{date}", "question": f"What was the ECB EUR/{cur} reference rate on {date}?", "tags": ["fx"],
                   "call": {"tool": "fx_rate", "args": {"from": "EUR", "to": cur, "on": date}},
                   "read": {"kind": "path", "path": "rate"}, "expected": a["value"], "unit": a["unit"], "source": a["source"]})
    for qid, q, call, read, expected, tags in BEHAVIOR:
        qs.append({"id": qid, "question": q, "tags": tags, "call": call, "read": read, "expected": expected, "unit": None,
                   "source": {"type": "behavior"}, **({"fixture_only": True} if qid in FIXTURE_ONLY else {})})
    ids = [q["id"] for q in qs]
    assert len(ids) == len(set(ids)), "duplicate ids"
    return {
        "_note": "Generated by evals/build_golden.py from the filed data in server/test/fixtures. Do not edit by hand.",
        "convention": "Flows are one fiscal year; balances are at the period end. When a period was restated, the latest "
                      "annual filing that reports it is the answer; `source.original` keeps the first-filed value. "
                      "Numbers must match exactly as filed (EPS to the cent, rates to the basis point).",
        "count": len(qs),
        "questions": qs,
    }


if __name__ == "__main__":
    data = json.dumps(build(), indent=1, ensure_ascii=False) + "\n"
    if "--check" in sys.argv:
        if not OUT.exists() or OUT.read_text() != data:
            print("evals/golden.json is out of date: run python3 evals/build_golden.py")
            sys.exit(1)
        print("evals/golden.json is current.")
        sys.exit(0)
    OUT.write_text(data)
    print(f"Wrote {OUT} ({json.loads(data)['count']} questions)")
