-- ═══════════════════════════════════════════════════════════════════════════
-- FIX 3 — PREVIEW ONLY. Nothing is modified by this file.
--
-- api/routers/reservations.py delete_payment / edit_payment post their wallet
-- reversal with sender_telegram_id = report.submitted_by. When the payment sat
-- in a bot-created (orphaned) report, the reversal landed on the ghost id while
-- the ORIGINAL CASH_IN went to the real person. Result: real wallets kept
-- credits for payments that were later deleted.
--
-- Ghost account 4 is holding 8 ADJUSTMENT rows totalling -61,712,000.
--
-- Applying this makes real balances DROP. Read the preview, decide per person,
-- then run the UPDATE at the bottom only if you agree.
-- ═══════════════════════════════════════════════════════════════════════════

\pset border 2

\echo '--- Wallet transactions sitting on a ghost id ---'
SELECT w.sender_telegram_id AS ghost_id,
       u.full_name AS should_belong_to,
       w.transaction_type, w.status,
       COUNT(*) AS n, SUM(w.amount) AS total
FROM wallet_transactions w
LEFT JOIN users u ON u.id = w.sender_telegram_id
WHERE NOT EXISTS (SELECT 1 FROM users u2 WHERE u2.telegram_id = w.sender_telegram_id)
GROUP BY 1,2,3,4 ORDER BY 1,3;

\echo ''
\echo '--- Line by line ---'
SELECT w.id, w.created_at::date AS d, w.sender_telegram_id AS ghost_id,
       u.full_name AS should_belong_to, w.transaction_type, w.amount, w.report_id, w.note
FROM wallet_transactions w
LEFT JOIN users u ON u.id = w.sender_telegram_id
WHERE NOT EXISTS (SELECT 1 FROM users u2 WHERE u2.telegram_id = w.sender_telegram_id)
ORDER BY w.id;

\echo ''
\echo '--- Effect on each real balance IF applied ---'
SELECT u.full_name, SUM(w.amount) AS balance_change
FROM wallet_transactions w
JOIN users u ON u.id = w.sender_telegram_id
WHERE NOT EXISTS (SELECT 1 FROM users u2 WHERE u2.telegram_id = w.sender_telegram_id)
  AND w.transaction_type = 'ADJUSTMENT'
GROUP BY 1 ORDER BY 2;

-- ═══════════════════════════════════════════════════════════════════════════
-- TO APPLY (uncomment and run separately, only after reading the preview):
--
-- BEGIN;
-- UPDATE wallet_transactions w
--    SET sender_telegram_id = u.telegram_id
--   FROM users u
--  WHERE w.sender_telegram_id = u.id
--    AND NOT EXISTS (SELECT 1 FROM users u2 WHERE u2.telegram_id = w.sender_telegram_id);
-- COMMIT;
-- ═══════════════════════════════════════════════════════════════════════════
