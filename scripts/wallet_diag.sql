\pset pager off
\pset border 2

-- ═══════════════════════════════════════════════════════════════════
-- 1. WHO IS SHE (check the telegram_id printed here is the right one)
-- ═══════════════════════════════════════════════════════════════════
\echo '=== 1. USER ==='
SELECT telegram_id, full_name, username, role, is_active
FROM users
WHERE full_name ILIKE '%аргиз%' OR full_name ILIKE '%аргис%' OR full_name ILIKE '%argi%';

-- ═══════════════════════════════════════════════════════════════════
-- 2. HER WALLET LEDGER, SUMMED BY TYPE  (what makes the balance)
-- ═══════════════════════════════════════════════════════════════════
\echo ''
\echo '=== 2. LEDGER BY TYPE ==='
WITH me AS (
  SELECT telegram_id FROM users
  WHERE full_name ILIKE '%аргиз%' OR full_name ILIKE '%аргис%' OR full_name ILIKE '%argi%'
)
SELECT
  CASE WHEN w.sender_telegram_id IN (SELECT telegram_id FROM me) THEN 'OUT/self' ELSE 'IN/received' END AS side,
  w.transaction_type, w.status,
  COUNT(*) AS n,
  TO_CHAR(SUM(w.amount), 'FM999,999,999,999') AS total
FROM wallet_transactions w
WHERE w.sender_telegram_id IN (SELECT telegram_id FROM me)
   OR w.receiver_telegram_id IN (SELECT telegram_id FROM me)
GROUP BY 1, 2, 3
ORDER BY 1, 2, 3;

\echo ''
\echo '=== 2b. COMPUTED BALANCE (same formula as the app) ==='
WITH me AS (
  SELECT telegram_id FROM users
  WHERE full_name ILIKE '%аргиз%' OR full_name ILIKE '%аргис%' OR full_name ILIKE '%argi%'
), t AS (SELECT telegram_id FROM me LIMIT 1)
SELECT
  (SELECT COALESCE(SUM(amount),0) FROM wallet_transactions
     WHERE ((sender_telegram_id=(SELECT telegram_id FROM t) AND transaction_type='CASH_IN')
         OR (receiver_telegram_id=(SELECT telegram_id FROM t) AND transaction_type='TRANSFER_TO_EMPLOYEE'))
       AND status='COMPLETED') AS total_in,
  (SELECT COALESCE(SUM(amount),0) FROM wallet_transactions
     WHERE sender_telegram_id=(SELECT telegram_id FROM t)
       AND transaction_type IN ('TRANSFER_TO_EMPLOYEE','TRANSFER_TO_SHAVKAT','CASH_TO_BANK','PURCHASE','SALARY','EXPENSE')
       AND status IN ('PENDING','COMPLETED')) AS total_out,
  (SELECT COALESCE(SUM(amount),0) FROM wallet_transactions
     WHERE sender_telegram_id=(SELECT telegram_id FROM t)
       AND transaction_type='ADJUSTMENT' AND status='COMPLETED') AS total_adj;

-- ═══════════════════════════════════════════════════════════════════
-- 3. THE MAIN TEST: cash income in HER reports vs CASH_IN in wallet
-- ═══════════════════════════════════════════════════════════════════
\echo ''
\echo '=== 3. REPORTS WHERE CASH INCOME != WALLET CASH_IN (hers) ==='
WITH me AS (
  SELECT telegram_id FROM users
  WHERE full_name ILIKE '%аргиз%' OR full_name ILIKE '%аргис%' OR full_name ILIKE '%argi%'
),
cash AS (
  SELECT report_id, SUM(amount) AS amt, COUNT(*) AS n
  FROM income_entries WHERE payment_method='CASH' GROUP BY report_id
),
cin AS (
  SELECT report_id, SUM(amount) AS amt, COUNT(*) AS n
  FROM wallet_transactions
  WHERE transaction_type='CASH_IN' AND status='COMPLETED' AND report_id IS NOT NULL
  GROUP BY report_id
)
SELECT r.id AS report, r.report_date, r.business_unit, r.status,
       COALESCE(cash.amt,0) AS cash_income, COALESCE(cash.n,0) AS cash_rows,
       COALESCE(cin.amt,0)  AS wallet_cash_in, COALESCE(cin.n,0) AS tx_rows,
       COALESCE(cash.amt,0) - COALESCE(cin.amt,0) AS not_credited
FROM structured_reports r
LEFT JOIN cash ON cash.report_id = r.id
LEFT JOIN cin  ON cin.report_id  = r.id
WHERE r.submitted_by IN (SELECT telegram_id FROM me)
  AND COALESCE(cash.amt,0) <> COALESCE(cin.amt,0)
ORDER BY r.report_date DESC;

\echo ''
\echo '=== 3b. SAME TEST FOR EVERYONE (is it systemic?) ==='
WITH cash AS (
  SELECT report_id, SUM(amount) AS amt FROM income_entries WHERE payment_method='CASH' GROUP BY report_id
), cin AS (
  SELECT report_id, SUM(amount) AS amt FROM wallet_transactions
  WHERE transaction_type='CASH_IN' AND status='COMPLETED' AND report_id IS NOT NULL GROUP BY report_id
)
SELECT u.full_name, COUNT(*) AS bad_reports,
       SUM(COALESCE(cash.amt,0) - COALESCE(cin.amt,0)) AS net_not_credited
FROM structured_reports r
LEFT JOIN cash ON cash.report_id=r.id
LEFT JOIN cin  ON cin.report_id=r.id
LEFT JOIN users u ON u.telegram_id = r.submitted_by
WHERE COALESCE(cash.amt,0) <> COALESCE(cin.amt,0)
GROUP BY u.full_name ORDER BY 3 DESC;

-- ═══════════════════════════════════════════════════════════════════
-- 4. WHICH KIND of income line is missing its CASH_IN
-- ═══════════════════════════════════════════════════════════════════
\echo ''
\echo '=== 4. HER CASH INCOME BY SOURCE TYPE (last 60 days) ==='
WITH me AS (
  SELECT telegram_id FROM users
  WHERE full_name ILIKE '%аргиз%' OR full_name ILIKE '%аргис%' OR full_name ILIKE '%argi%'
)
SELECT
  CASE WHEN e.minibar_item_id IS NOT NULL THEN 'MINIBAR'
       WHEN e.spa_appointment_id IS NOT NULL THEN 'SPA (appointment)'
       WHEN e.service_item_id IS NOT NULL THEN 'SERVICE'
       WHEN e.property_id IS NOT NULL THEN 'ACCOMMODATION'
       WHEN e.restaurant_category IS NOT NULL THEN 'RESTAURANT'
       ELSE 'OTHER' END AS source,
  e.payment_method, COUNT(*) AS n, SUM(e.amount) AS total
FROM income_entries e
JOIN structured_reports r ON r.id = e.report_id
WHERE r.submitted_by IN (SELECT telegram_id FROM me)
  AND r.report_date >= CURRENT_DATE - 60
GROUP BY 1,2 ORDER BY 1,2;

-- ═══════════════════════════════════════════════════════════════════
-- 5. SPA: appointments she was paid for, and whether cash hit a wallet
-- ═══════════════════════════════════════════════════════════════════
\echo ''
\echo '=== 5. SPA PAYMENTS (last 60 days) — who got the wallet credit ==='
SELECT e.id AS income_id, r.report_date, e.amount, e.payment_method,
       us.full_name AS report_owner,
       (SELECT COUNT(*) FROM wallet_transactions w
          WHERE w.report_id = r.id AND w.transaction_type='CASH_IN'
            AND w.amount = e.amount) AS matching_cash_in_tx
FROM income_entries e
JOIN structured_reports r ON r.id = e.report_id
LEFT JOIN users us ON us.telegram_id = r.submitted_by
WHERE e.spa_appointment_id IS NOT NULL AND r.report_date >= CURRENT_DATE - 60
ORDER BY r.report_date DESC, e.id DESC LIMIT 100;

-- ═══════════════════════════════════════════════════════════════════
-- 6. What she actually paid OUT (this is what drives it negative)
-- ═══════════════════════════════════════════════════════════════════
\echo ''
\echo '=== 6. HER LAST 60 WALLET MOVEMENTS ==='
WITH me AS (
  SELECT telegram_id FROM users
  WHERE full_name ILIKE '%аргиз%' OR full_name ILIKE '%аргис%' OR full_name ILIKE '%argi%'
)
SELECT w.id, w.created_at::date AS d, w.transaction_type, w.status,
       w.amount, w.report_id, w.business_unit, LEFT(COALESCE(w.note,''), 50) AS note,
       ur.full_name AS receiver
FROM wallet_transactions w
LEFT JOIN users ur ON ur.telegram_id = w.receiver_telegram_id
WHERE w.sender_telegram_id IN (SELECT telegram_id FROM me)
   OR w.receiver_telegram_id IN (SELECT telegram_id FROM me)
ORDER BY w.id DESC LIMIT 60;

-- ═══════════════════════════════════════════════════════════════════
-- 7. SPA commission payouts she made (SALARY out of her wallet)
-- ═══════════════════════════════════════════════════════════════════
\echo ''
\echo '=== 7. SPA COMMISSION PAYOUTS SHE PAID ==='
SELECT p.id, p.created_at::date AS d, m.name AS master, p.amount, u.full_name AS paid_by
FROM spa_commission_payouts p
LEFT JOIN spa_masters m ON m.id = p.master_id
LEFT JOIN users u ON u.telegram_id = p.paid_by
ORDER BY p.id DESC LIMIT 40;

-- ═══════════════════════════════════════════════════════════════════
-- 8. Cash prepayments she took (these NEVER create a wallet CASH_IN)
-- ═══════════════════════════════════════════════════════════════════
\echo ''
\echo '=== 8. HER CASH PREPAYMENTS (no wallet credit exists for these) ==='
WITH me AS (
  SELECT telegram_id FROM users
  WHERE full_name ILIKE '%аргиз%' OR full_name ILIKE '%аргис%' OR full_name ILIKE '%argi%'
)
SELECT status, COUNT(*) AS n, SUM(amount) AS total
FROM prepayments
WHERE operator_telegram_id IN (SELECT telegram_id FROM me)
  AND payment_method = 'CASH'
GROUP BY status;
