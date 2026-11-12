// A budget per floor (connect/budget.py): what each floor's agents have spent today, in new tokens, against
// the budget company.json gives it. Plain module, so tests/test_budget_words.py can run it under Node.

// Today on this computer's clock, as connect/budget.py writes it: 2026-11-12.
export const localDay = (d = new Date()) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;

// 1,200,000 as "1.2 million", for people.
export function tokensSaid(n) {
  if (n >= 1e6) return `${(n / 1e6).toFixed(1).replace(/\.0$/, '')} million`;
  if (n >= 1000) return `${Math.round(n / 1000)} thousand`;
  return String(Math.max(0, Math.round(n)));
}

// A floor's budget for a day: its own, or the company's for every floor. Null for none.
export function budgetOf(org, floor) {
  for (const given of [floor?.budget, org?.budget]) if (Number.isFinite(given) && given > 0) return Math.floor(given);
  return null;
}

// What a floor's conversations spent today. A spending with no day is today's (the made-up sample's).
export function spentToday(conversations, project, day = localDay()) {
  let total = 0;
  for (const c of conversations) {
    const s = c?.project === project ? c.spent : null;
    if (s && typeof s === 'object' && (s.day == null || s.day === day) && Number.isFinite(s.tokens)) total += s.tokens;
  }
  return total;
}

// A floor's spending in words, with how full its budget is (`times` lets it go past, as control allows):
// { spent, limit, over, share, text } or null when it has spent nothing and has no budget.
export function floorSpend(org, floor, conversations, times = 1, day = localDay()) {
  const spent = spentToday(conversations, floor.project, day);
  const budget = budgetOf(org, floor);
  if (!spent && !budget) return null;
  const limit = budget ? budget * times : null;
  const over = !!limit && spent >= limit;
  return {
    spent, limit, over, share: limit ? Math.min(1, spent / limit) : null,
    text: limit ? `${tokensSaid(spent)} of ${tokensSaid(limit)} tokens today${over ? ', over budget' : ''}` : `${tokensSaid(spent)} tokens today`,
  };
}
