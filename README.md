# B2B Payments Reconciliation Bot

An end-to-end automation that cross-references bank transaction exports against ERP payables, flags discrepancies, and delivers a structured summary — no API keys required to run locally.

---

## The Problem

Finance teams at B2B companies spend significant time every month-close manually matching bank statements to their ERP's accounts payable records. The process breaks down in three predictable ways:

1. **Name mismatches** — the same vendor appears as "Acme Corp" in the bank feed and "Acme Corporation" in the ERP, so a simple string comparison fails.
2. **Amount discrepancies** — exchange-rate rounding, partial payments, or bank charges create small but systematic deltas between what was posted and what was invoiced.
3. **Missing records** — transactions land in the bank without a corresponding ERP payable, or invoices sit as outstanding with no payment ever recorded.

Together these issues produce a reconciliation backlog that slows audits, delays supplier payments, and introduces financial risk.

---

## Solution

This project automates the full reconciliation pipeline using n8n as the orchestration layer. A single webhook call receives two CSV URLs — one for bank transactions, one for ERP payables — and returns a structured JSON summary with every transaction classified as `matched`, `pending`, `discrepant`, `unmatched_bank`, or `unmatched_erp`.

The matching logic is deterministic and runs entirely inside n8n Code nodes, so the workflow can be demonstrated and tested with zero external dependencies.

---

## Architecture

```
GET /webhook/reconcile?bank_url=<url>&erp_url=<url>
         │
         ▼
┌─────────────────────┐
│  Fetch and Parse    │  HTTP helper fetches both CSVs;
│  CSVs  [Code]       │  strips legal suffixes, lowercases names
└────────┬────────────┘
         │
         ▼
┌─────────────────────┐
│  Fuzzy Match        │  Jaro-Winkler similarity for names (threshold 0.72)
│  [Code]             │  ± 5% amount tolerance → matched / pending / discrepant
└────────┬────────────┘
         │
         ▼
┌─────────────────────┐
│  Rules-Based        │  Aggregates counts, builds example_discrepancies list
│  Summary  [Code]    │  and a human-readable message string
└──────┬──────┬───────┘
       │      │
       │      ├──► Log to Google Sheets   [active, needs credentials]
       │      │
       │      └──► (Optional) LLM Classification  [DISABLED by default]
       │                      │
       │                      └──► (Optional) Slack Alert  [DISABLED by default]
       │
       ▼
┌─────────────────────┐
│  Respond to         │  Returns JSON: summary counts + top discrepancies
│  Webhook            │
└─────────────────────┘
```

---

## Two Operating Modes

### Local Demo Mode (default — no API keys needed)

Import the workflow, activate it, spin up a local file server, and fire the webhook. The entire flow runs with only the n8n instance itself.

```bash
# 1. Generate synthetic CSVs
pip install pandas faker
python generate_data.py

# 2. Serve the CSV files locally
cd data && python3 -m http.server 8888

# 3. Trigger the webhook
curl -s "http://localhost:5678/webhook/reconcile\
?bank_url=http://localhost:8888/bank_transactions.csv\
&erp_url=http://localhost:8888/erp_payables.csv" | python3 -m json.tool
```

**Expected response:**
```json
{
  "summary": {
    "run_id": "REC-1739800000000",
    "matched_count": 48,
    "pending_count": 14,
    "discrepant_count": 6,
    "unmatched_bank_count": 12,
    "unmatched_erp_count": 20,
    "total_at_risk_usd": 312450.75,
    "example_discrepancies": [...]
  },
  "message": "Reconciliation complete — Matched: 48 | Pending: 14 | ..."
}
```

### Optional AI Mode

Enable the two disabled nodes to add LLM-powered narrative and Slack delivery:

| Step | Action |
|------|--------|
| Set environment variable | `ANTHROPIC_API_KEY=sk-ant-...` in n8n settings |
| Enable node | Right-click `(Optional) LLM Classification` → Enable |
| Enable node | Right-click `(Optional) Slack Alert` → Enable |
| Set Slack channel | Update the `channel` field in the Slack node |
| Activate | The LLM classifies each discrepancy and posts a formatted summary |

An LLM (e.g. Claude or ChatGPT) can optionally receive the fuzzy match output to generate per‑transaction risk scores and a narrative summary of the main issues.

---

## Tech Stack

| Layer | Tool | Purpose |
|-------|------|---------|
| Data generation | Python — pandas, Faker | Synthetic bank + ERP CSVs with controlled mismatches |
| Orchestration | n8n (self-hosted) | Webhook trigger, HTTP requests, Code nodes, outputs |
| Fuzzy matching | Jaro-Winkler (pure JS) | Name similarity + amount-diff classification, no external libraries |
| Logging | Google Sheets | One summary row per reconciliation run |
| AI classification | Claude claude-opus-4-6 (optional) | Risk scoring and narrative for discrepant records |
| Alerting | Slack (optional) | Real-time summary post to a finance channel |

---

## Matching Logic

Names are normalised before comparison: lowercased, punctuation stripped, and common legal suffixes removed (`Corp`, `Ltd`, `Inc`, `LLC`, `Solutions`, etc.). The Jaro-Winkler algorithm is implemented from scratch in the Code node — no npm packages, no external calls.

```
sim = jaroWinkler(bank_name_normalised, erp_name_normalised)
amt_diff = |bank_amount − erp_amount| / max(bank_amount, erp_amount)

if sim ≥ 0.90 AND amt_diff ≤ 1%  →  matched
if sim ≥ 0.72 AND amt_diff ≤ 5%  →  pending
if sim ≥ 0.72 AND amt_diff > 5%  →  discrepant
if no candidate above sim 0.72   →  unmatched_bank / unmatched_erp
```

Candidate selection uses a weighted score (`0.6 × name_sim + 0.4 × amount_closeness`) to pick the best ERP match for each bank transaction.

---

## Project Structure

```
.
├── generate_data.py                  # Synthetic data generator
├── data/
│   ├── bank_transactions.csv         # 100 rows: date, amount, beneficiary, reference, status
│   └── erp_payables.csv              # 100 rows: invoice_id, supplier, amount, due_date, status
├── n8n_reconciliation_workflow.json  # Import-ready n8n workflow
├── fuzzy_match_node.js               # Standalone reference for the Fuzzy Match Code node
├── claude_system_prompt.txt          # System prompt for the optional LLM node
└── README.md
```

---

## Quick Import

1. Open your n8n instance → **Workflows** → **Import from file**
2. Select `n8n_reconciliation_workflow.json`
3. The workflow imports as **inactive** — review, then click **Activate**
4. For Google Sheets logging: create an OAuth2 credential and update `YOUR_GOOGLE_SHEET_ID_HERE`

---

## Intentional Data Quality Issues (for demo realism)

The synthetic CSVs were generated with specific mismatches to stress-test the matching engine:

- **Fuzzy vendor names** across 15 company pairs (`"Delta Trading Co"` ↔ `"Delta Trdg. Co"`)
- **Amount variance** of ±3% on bank side and ±4% on ERP side, producing real discrepancies
- **13 duplicate bank references** — same `TXN-xxxxx` appearing twice, simulating double-posting
- **28 unmatched ERP payables** from synthetic vendors with no bank counterpart

---

## About

Built as a portfolio project to demonstrate end-to-end process automation for B2B payment operations — from data modelling through orchestration to AI-assisted classification — using open-source and freely self-hostable tools.
