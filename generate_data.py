"""
B2B Payments Reconciliation — Synthetic Data Generator
Generates bank_transactions.csv and erp_payables.csv in ./data/
Run: pip install pandas faker && python generate_data.py
"""

import pandas as pd
import numpy as np
from faker import Faker
import random
import os
from datetime import datetime, timedelta

# ── Reproducibility ──────────────────────────────────────────────────────────
SEED = 42
fake = Faker("en_US")
Faker.seed(SEED)
random.seed(SEED)
np.random.seed(SEED)

os.makedirs("./data", exist_ok=True)

# ── Company variants (bank name → list of ERP fuzzy aliases) ─────────────────
COMPANY_VARIANTS: dict[str, list[str]] = {
    "Acme Corp":            ["Acme Corporation", "ACME Corp.", "Acme", "Acme Co"],
    "TechSoft Ltd":         ["TechSoft Limited", "Tech Soft Ltd.", "Techsoft Ltd", "TechSoft"],
    "Global Supplies Co":   ["Global Supplies", "Global Supply Co.", "GlobalSupplies Inc"],
    "Nexus Solutions":      ["Nexus Solution", "Nexus Solutions LLC", "NexusSol"],
    "Alpha Industries":     ["Alpha Ind.", "Alpha Industries Ltd", "Alpha Industria"],
    "Beta Systems Inc":     ["Beta Sys.", "Beta Systems", "Beta System Inc."],
    "Omega Services":       ["Omega Service", "Omega Services Ltd.", "Omega Svcs"],
    "Delta Trading Co":     ["Delta Trade", "Delta Trading", "Delta Trdg. Co"],
    "Sigma Analytics":      ["Sigma Analytic", "Sigma Analytics Inc.", "SigmaAnalytics"],
    "Gamma Resources":      ["Gamma Resource Ltd.", "Gamma Resources", "Gamma Res."],
    "Epsilon Tech":         ["Epsilon Technology", "Epsilon Tech LLC", "Epsilon"],
    "Zeta Manufacturing":   ["Zeta Mfg.", "Zeta Manufacturing Co.", "ZetaManuf"],
    "Theta Consulting":     ["Theta Consult", "Theta Consulting Group", "Theta Consultants"],
    "Iota Logistics":       ["Iota Logistic", "Iota Logistics Inc.", "Iota Log."],
    "Kappa Ventures":       ["Kappa Venture", "Kappa Ventures Ltd.", "KappaVentures"],
}

BANK_COMPANIES = list(COMPANY_VARIANTS.keys())
BASE_AMOUNTS   = {c: round(random.uniform(1_500, 75_000), 2) for c in BANK_COMPANIES}

START_DATE = datetime(2024, 1, 1)


# ─────────────────────────────────────────────────────────────────────────────
# 1. bank_transactions.csv — 100 rows
# ─────────────────────────────────────────────────────────────────────────────
bank_rows: list[dict] = []
unique_refs: list[dict] = []

for i in range(87):
    company = random.choice(BANK_COMPANIES)
    base    = BASE_AMOUNTS[company]
    amount  = round(base * random.uniform(0.97, 1.03), 2)   # ±3% bank-side variance
    date    = START_DATE + timedelta(days=random.randint(0, 364))
    ref     = f"TXN-{i + 1:05d}"
    status  = random.choices(
        ["completed", "pending", "failed"],
        weights=[0.72, 0.20, 0.08],
    )[0]

    row = {
        "date":        date.strftime("%Y-%m-%d"),
        "amount":      amount,
        "beneficiary": company,
        "reference":   ref,
        "status":      status,
    }
    bank_rows.append(row)
    unique_refs.append(row)

# 13 intentional duplicates (same reference + amount → duplicate detection test)
for _ in range(13):
    orig = random.choice(unique_refs)
    bank_rows.append({
        "date":        orig["date"],
        "amount":      orig["amount"],           # exact same amount
        "beneficiary": orig["beneficiary"],
        "reference":   orig["reference"],        # ← duplicate reference
        "status":      "completed",
    })

random.shuffle(bank_rows)
bank_df = pd.DataFrame(bank_rows[:100])
bank_df.to_csv("./data/bank_transactions.csv", index=False)
print(f"✓  bank_transactions.csv  →  {len(bank_df)} rows")
print(f"   Status distribution    :  {bank_df['status'].value_counts().to_dict()}")
print(f"   Duplicate refs         :  {bank_df['reference'].duplicated().sum()}")


# ─────────────────────────────────────────────────────────────────────────────
# 2. erp_payables.csv — 100 rows
# ─────────────────────────────────────────────────────────────────────────────
erp_rows: list[dict] = []

# 72 fuzzy-matchable records
for i in range(72):
    company_key  = random.choice(BANK_COMPANIES)
    supplier     = random.choice(COMPANY_VARIANTS[company_key])  # fuzzy alias
    base         = BASE_AMOUNTS[company_key]
    amount       = round(base * random.uniform(0.96, 1.04), 2)   # ±4% ERP-side variance
    due_date     = START_DATE + timedelta(days=random.randint(0, 364))
    invoice_id   = f"INV-{i + 1:05d}"
    status       = random.choices(
        ["paid", "outstanding", "overdue"],
        weights=[0.60, 0.30, 0.10],
    )[0]

    erp_rows.append({
        "invoice_id": invoice_id,
        "supplier":   supplier,
        "amount":     amount,
        "due_date":   due_date.strftime("%Y-%m-%d"),
        "status":     status,
    })

# 28 fully unmatched ERP payables (unknown vendor, no bank counterpart)
for i in range(28):
    erp_rows.append({
        "invoice_id": f"INV-{72 + i + 1:05d}",
        "supplier":   fake.company(),                                       # random vendor
        "amount":     round(random.uniform(500, 30_000), 2),
        "due_date":   (START_DATE + timedelta(days=random.randint(0, 364))).strftime("%Y-%m-%d"),
        "status":     random.choice(["outstanding", "overdue"]),
    })

random.shuffle(erp_rows)
erp_df = pd.DataFrame(erp_rows[:100])
erp_df.to_csv("./data/erp_payables.csv", index=False)
print(f"\n✓  erp_payables.csv       →  {len(erp_df)} rows")
print(f"   Status distribution    :  {erp_df['status'].value_counts().to_dict()}")

# ─────────────────────────────────────────────────────────────────────────────
# Quick sanity check
# ─────────────────────────────────────────────────────────────────────────────
print("\n── Sample bank_transactions (first 3 rows) ──────────────────────────")
print(bank_df.head(3).to_string(index=False))

print("\n── Sample erp_payables (first 3 rows) ───────────────────────────────")
print(erp_df.head(3).to_string(index=False))

print("\n✅  Done. Files saved to ./data/")
print("    Intentional mismatches injected:")
print("      • Fuzzy company names  (e.g. 'Acme Corp' ↔ 'Acme Corporation')")
print("      • Amount variance ±5%  (bank ±3%, ERP ±4%)")
print(f"     • Duplicate bank refs   ({bank_df['reference'].duplicated().sum()} rows)")
print(f"     • Unmatched ERP entries (~28 rows with unknown vendors)")
