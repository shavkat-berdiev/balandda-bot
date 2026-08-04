\pset pager off
\pset border 2

-- Наргис
\set me 0

\echo '=== A. THE "ХАТОЛИК" EXPENSE + all big expenses last 10 days ==='
WITH me AS (SELECT telegram_id FROM users WHERE full_name ILIKE '%аргис%')
SELECT w.id AS tx_id, w.created_at::date AS d, w.amount, w.report_id, w.note,
       (SELECT e.id FROM expense_entries e
         WHERE e.report_id = w.report_id AND e.amount = w.amount LIMIT 1) AS expense_entry_id
FROM wallet_transactions w
WHERE w.sender_telegram_id IN (SELECT telegram_id FROM me)
  AND w.transaction_type IN ('EXPENSE','SALARY')
  AND w.created_at >= CURRENT_DATE - 10
ORDER BY w.amount DESC;

\echo ''
\echo '=== B. CASH PREPAYMENTS split by origin (the real uncredited pile) ==='
WITH me AS (SELECT telegram_id FROM users WHERE full_name ILIKE '%аргис%')
SELECT p.status,
       CASE WHEN p.income_entry_id IS NULL THEN 'BOT/WEB prepayment -> NO wallet credit'
            ELSE 'calendar-mirrored -> credited' END AS origin,
       COUNT(*) AS n, SUM(p.amount) AS total,
       MIN(p.created_at)::date AS first, MAX(p.created_at)::date AS last
FROM prepayments p
WHERE p.operator_telegram_id IN (SELECT telegram_id FROM me)
  AND p.payment_method = 'CASH'
GROUP BY 1,2 ORDER BY 1,2;

\echo ''
\echo '=== C. PROOF: orphan CASH_IN vs cash income on her mismatched reports ==='
SELECT r.id AS report, r.report_date,
       (SELECT COUNT(*) FROM income_entries e WHERE e.report_id=r.id AND e.payment_method='CASH') AS cash_rows,
       (SELECT COUNT(*) FROM wallet_transactions w WHERE w.report_id=r.id AND w.transaction_type='CASH_IN') AS cashin_rows,
       (SELECT string_agg(e.amount::bigint::text, ' | ' ORDER BY e.id)
          FROM income_entries e WHERE e.report_id=r.id AND e.payment_method='CASH') AS income_cash_amounts,
       (SELECT string_agg(w.amount::bigint::text, ' | ' ORDER BY w.id)
          FROM wallet_transactions w WHERE w.report_id=r.id AND w.transaction_type='CASH_IN') AS wallet_cashin_amounts
FROM structured_reports r
WHERE r.id IN (320, 333, 458, 486, 498, 523, 547)
ORDER BY r.report_date;

\echo ''
\echo '=== D. Commission-style expenses she pays in cash (фоиз / massage / hammam) ==='
WITH me AS (SELECT telegram_id FROM users WHERE full_name ILIKE '%аргис%')
SELECT r.report_date, e.expense_category, e.amount, e.description
FROM expense_entries e
JOIN structured_reports r ON r.id = e.report_id
WHERE r.submitted_by IN (SELECT telegram_id FROM me)
  AND r.report_date >= CURRENT_DATE - 45
  AND (e.description ILIKE '%фоиз%' OR e.description ILIKE '%фои%' OR e.description ILIKE '%масса%'
       OR e.description ILIKE '%хамм%' OR e.description ILIKE '%хамом%' OR e.description ILIKE '%спа%'
       OR e.description ILIKE '%калян%')
ORDER BY r.report_date DESC, e.amount DESC;

\echo ''
\echo '=== E. WHERE hammam / massage / SPA revenue is actually recorded ==='
SELECT COALESCE(u.full_name,'(none)') AS report_owner,
       COALESCE(s.name_ru, m.name_ru, 'accommodation/other') AS item,
       e.payment_method, COUNT(*) AS n, SUM(e.amount) AS total
FROM income_entries e
JOIN structured_reports r ON r.id = e.report_id
LEFT JOIN users u ON u.telegram_id = r.submitted_by
LEFT JOIN service_items s ON s.id = e.service_item_id
LEFT JOIN minibar_items m ON m.id = e.minibar_item_id
WHERE r.report_date >= CURRENT_DATE - 45
  AND (s.name_ru ILIKE '%масс%' OR s.name_ru ILIKE '%хам%' OR s.name_ru ILIKE '%spa%'
       OR s.name_ru ILIKE '%спа%' OR s.name_ru ILIKE '%калян%' OR s.name_ru ILIKE '%сауна%')
GROUP BY 1,2,3 ORDER BY 5 DESC;

\echo ''
\echo '=== F. The 12 owner ADJUSTMENTs on her wallet ==='
WITH me AS (SELECT telegram_id FROM users WHERE full_name ILIKE '%аргис%')
SELECT w.id, w.created_at::date AS d, w.amount, w.report_id, w.note
FROM wallet_transactions w
WHERE w.sender_telegram_id IN (SELECT telegram_id FROM me)
  AND w.transaction_type='ADJUSTMENT'
ORDER BY w.id;

\echo ''
\echo '=== G. Her 26 PENDING outgoing transfers (deducted, never accepted) ==='
WITH me AS (SELECT telegram_id FROM users WHERE full_name ILIKE '%аргис%')
SELECT w.id, w.created_at::date AS d, w.amount, ur.full_name AS waiting_on, w.note
FROM wallet_transactions w
LEFT JOIN users ur ON ur.telegram_id = w.receiver_telegram_id
WHERE w.sender_telegram_id IN (SELECT telegram_id FROM me)
  AND w.status='PENDING'
ORDER BY w.id;
