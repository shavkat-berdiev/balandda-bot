-- ═══════════════════════════════════════════════════════════════════════════
-- FIX 1 — Наргис: hammam commission typo + the mistaken "возврат"
--
-- What happened:
--   Correct amount to pay SPA masters: 1,260,000
--   Entered instead (expense 855, report 554): 12,600,000   ← 10x typo
--   Then a REFUND entry was added (expense 864, report 559): 11,340,000
--   ...expecting «возвраты» to give the money back. REFUND is an ordinary
--   expense category, so it DEDUCTED a second time.
--
--   Should have been deducted:  1,260,000
--   Actually deducted:         23,940,000
--   Over-deducted by:          22,680,000
--   Wallet now:                -8,990,448  →  after fix: +13,689,552
-- ═══════════════════════════════════════════════════════════════════════════

\pset border 2
\echo '--- BEFORE: the four rows this script touches ---'
SELECT 'expense' AS t, id, amount::bigint, description FROM expense_entries WHERE id IN (855, 864)
UNION ALL
SELECT 'wallet',  id, amount::bigint, note FROM wallet_transactions WHERE id IN (1615, 1632)
ORDER BY 1, 2;

BEGIN;

-- ── 1. The 10x typo: 12,600,000 → 1,260,000 (expense + its wallet deduction) ──
UPDATE expense_entries
   SET amount = 1260000,
       description = description || ' (исправлено 04.08.26: было 12 600 000)'
 WHERE id = 855 AND amount = 12600000;

UPDATE wallet_transactions
   SET amount = 1260000,
       note = COALESCE(note,'') || ' (исправлено 04.08.26: было 12 600 000)'
 WHERE id = 1615 AND amount = 12600000 AND transaction_type = 'EXPENSE';

UPDATE structured_reports
   SET total_expense = total_expense - 11340000
 WHERE id = 554;

-- ── 2. The mistaken «возврат» — it was never a real payment, remove it ──
UPDATE structured_reports
   SET total_expense = total_expense - 11340000
 WHERE id = 559;

DELETE FROM expense_entries     WHERE id = 864  AND amount = 11340000;
DELETE FROM wallet_transactions WHERE id = 1632 AND amount = 11340000;

-- ── 3. Safety check: exactly 5 rows should have been affected above ──
-- If the AFTER block below does not show the expected numbers, run ROLLBACK;

COMMIT;

\echo ''
\echo '--- AFTER: rows should now read 1,260,000 and the two 11,340,000 rows gone ---'
SELECT 'expense' AS t, id, amount::bigint, description FROM expense_entries WHERE id IN (855, 864)
UNION ALL
SELECT 'wallet',  id, amount::bigint, note FROM wallet_transactions WHERE id IN (1615, 1632)
ORDER BY 1, 2;

\echo ''
\echo '--- HER NEW BALANCE (expect +13,689,552) ---'
WITH me AS (SELECT telegram_id FROM users WHERE full_name ILIKE '%аргис%'),
     t  AS (SELECT telegram_id FROM me LIMIT 1)
SELECT
  (SELECT COALESCE(SUM(amount),0) FROM wallet_transactions
     WHERE ((sender_telegram_id=(SELECT telegram_id FROM t) AND transaction_type='CASH_IN')
         OR (receiver_telegram_id=(SELECT telegram_id FROM t) AND transaction_type='TRANSFER_TO_EMPLOYEE'))
       AND status='COMPLETED')
- (SELECT COALESCE(SUM(amount),0) FROM wallet_transactions
     WHERE sender_telegram_id=(SELECT telegram_id FROM t)
       AND transaction_type IN ('TRANSFER_TO_EMPLOYEE','TRANSFER_TO_SHAVKAT','CASH_TO_BANK','PURCHASE','SALARY','EXPENSE')
       AND status IN ('PENDING','COMPLETED'))
+ (SELECT COALESCE(SUM(amount),0) FROM wallet_transactions
     WHERE sender_telegram_id=(SELECT telegram_id FROM t)
       AND transaction_type='ADJUSTMENT' AND status='COMPLETED') AS balance;
