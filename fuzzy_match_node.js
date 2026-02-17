/**
 * n8n Code Node — Fuzzy Match
 * Mode: Run Once for All Items
 *
 * Input (from "Fetch and Parse CSVs"):
 *   $input.first().json = { bank_transactions: [...], erp_payables: [...] }
 *
 * Output:
 *   [{ json: { results: [...], stats: {...} } }]
 *
 * Algorithm: Jaro-Winkler similarity for names + ±5% amount tolerance
 */

// ─── Config ──────────────────────────────────────────────────────────────────
const SIM_THRESHOLD = 0.72;   // minimum name similarity to consider a candidate
const AMT_TOLERANCE = 0.05;   // 5% amount difference → "pending" boundary

// ─── Jaro Similarity (core) ───────────────────────────────────────────────────
function jaroSim(s1, s2) {
  if (s1 === s2) return 1.0;
  if (!s1 || !s2) return 0.0;

  const maxDist = Math.floor(Math.max(s1.length, s2.length) / 2) - 1;
  if (maxDist < 0) return 0.0;

  const s1m = new Array(s1.length).fill(false);
  const s2m = new Array(s2.length).fill(false);
  let matches = 0;

  for (let i = 0; i < s1.length; i++) {
    const lo = Math.max(0, i - maxDist);
    const hi = Math.min(i + maxDist + 1, s2.length);
    for (let j = lo; j < hi; j++) {
      if (s2m[j] || s1[i] !== s2[j]) continue;
      s1m[i] = true;
      s2m[j] = true;
      matches++;
      break;
    }
  }

  if (matches === 0) return 0.0;

  let t = 0, k = 0;
  for (let i = 0; i < s1.length; i++) {
    if (!s1m[i]) continue;
    while (!s2m[k]) k++;
    if (s1[i] !== s2[k]) t++;
    k++;
  }

  return (matches / s1.length + matches / s2.length + (matches - t / 2) / matches) / 3;
}

// ─── Jaro-Winkler (prefix boost, p=0.1, max prefix=4) ────────────────────────
function jaroWinkler(s1, s2) {
  const j = jaroSim(s1, s2);
  let prefix = 0;
  const n = Math.min(s1.length, s2.length, 4);
  for (let i = 0; i < n; i++) {
    if (s1[i] === s2[i]) prefix++;
    else break;
  }
  return j + prefix * 0.1 * (1 - j);
}

// ─── Main logic ───────────────────────────────────────────────────────────────
const data = $input.first().json;
const bank = data.bank_transactions || [];
const erp  = data.erp_payables     || [];

const results  = [];
const erpUsed  = new Set();   // track matched ERP indices

for (const tx of bank) {
  let best = null;
  let bestScore = 0;

  // Find best ERP candidate for this bank transaction
  for (const inv of erp) {
    if (erpUsed.has(inv._idx)) continue;

    const sim     = jaroWinkler(tx.beneficiary_normalized, inv.supplier_normalized);
    if (sim < SIM_THRESHOLD) continue;

    const amtDiff = Math.abs(tx.amount - inv.amount) / Math.max(tx.amount, inv.amount, 0.01);

    // Weighted score: 60% name similarity + 40% amount closeness
    const score = sim * 0.6 + (1 - Math.min(amtDiff, 1)) * 0.4;

    if (score > bestScore) {
      bestScore = score;
      best = { inv, sim, amtDiff };
    }
  }

  if (best) {
    const { sim, amtDiff, inv } = best;
    erpUsed.add(inv._idx);

    let matchStatus;
    let issue = null;

    if (amtDiff <= 0.01 && sim >= 0.90) {
      matchStatus = "matched";
    } else if (amtDiff <= AMT_TOLERANCE) {
      matchStatus = "pending";
      issue = amtDiff > 0.01
        ? `Amount variance ${(amtDiff * 100).toFixed(2)}% (within 5% tolerance)`
        : `Name fuzzy match ${(sim * 100).toFixed(0)}% — verify company identity`;
    } else {
      matchStatus = "discrepant";
      issue = `Amount variance ${(amtDiff * 100).toFixed(2)}% exceeds 5% threshold`;
    }

    results.push({
      bank_reference:   tx.reference,
      bank_beneficiary: tx.beneficiary,
      bank_amount:      tx.amount,
      bank_date:        tx.date,
      bank_status:      tx.status,
      invoice_id:       inv.invoice_id,
      erp_supplier:     inv.supplier,
      erp_amount:       inv.amount,
      erp_due_date:     inv.due_date,
      erp_status:       inv.status,
      match_status:     matchStatus,
      name_similarity:  parseFloat(sim.toFixed(4)),
      amount_diff_pct:  parseFloat((amtDiff * 100).toFixed(2)),
      amount_variance:  parseFloat((tx.amount - inv.amount).toFixed(2)),
      issue:            issue,
      match_score:      parseFloat(bestScore.toFixed(4)),
    });

  } else {
    // Bank transaction with no ERP counterpart
    results.push({
      bank_reference:   tx.reference,
      bank_beneficiary: tx.beneficiary,
      bank_amount:      tx.amount,
      bank_date:        tx.date,
      bank_status:      tx.status,
      invoice_id:       null,
      erp_supplier:     null,
      erp_amount:       null,
      match_status:     "unmatched_bank",
      issue:            "No ERP payable found for this bank transaction",
    });
  }
}

// ERP payables with no bank counterpart
for (const inv of erp) {
  if (!erpUsed.has(inv._idx)) {
    results.push({
      bank_reference:   null,
      bank_beneficiary: null,
      bank_amount:      null,
      invoice_id:       inv.invoice_id,
      erp_supplier:     inv.supplier,
      erp_amount:       inv.amount,
      erp_due_date:     inv.due_date,
      erp_status:       inv.status,
      match_status:     "unmatched_erp",
      issue:            "No bank transaction found for this ERP payable",
    });
  }
}

// ─── Stats ────────────────────────────────────────────────────────────────────
const counts = results.reduce((acc, r) => {
  acc[r.match_status] = (acc[r.match_status] || 0) + 1;
  return acc;
}, {});

const amtAtRisk = results
  .filter(r => ["pending", "discrepant", "unmatched_bank", "unmatched_erp"].includes(r.match_status))
  .reduce((sum, r) => sum + Math.abs(r.amount_variance || r.bank_amount || r.erp_amount || 0), 0);

return [{
  json: {
    results,
    stats: {
      total_bank:      bank.length,
      total_erp:       erp.length,
      matched:         counts.matched         || 0,
      pending:         counts.pending         || 0,
      discrepant:      counts.discrepant      || 0,
      unmatched_bank:  counts.unmatched_bank  || 0,
      unmatched_erp:   counts.unmatched_erp   || 0,
      total_at_risk_usd: parseFloat(amtAtRisk.toFixed(2)),
    },
  },
}];
