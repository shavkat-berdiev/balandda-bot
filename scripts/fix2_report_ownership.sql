-- ═══════════════════════════════════════════════════════════════════════════
-- FIX 2 — repair reports orphaned by the user.id / telegram_id bug
--
-- bot/handlers/new_report.py stored users.id (primary key) in submitted_by
-- instead of users.telegram_id. Every report created via «📝 Новый отчёт»
-- landed under a ghost owner (4, 1, ...) that matches no user.
--
-- RUN THE CODE FIX FIRST (deploy), otherwise the bot immediately creates new
-- orphans and you will have to run this again.
--
-- This script does NOT touch any wallet balance. It only re-attributes reports
-- and merges the duplicate same-day drafts the bug created.
-- ═══════════════════════════════════════════════════════════════════════════

\pset border 2

\echo '--- PREVIEW: reports that will be re-attributed ---'
SELECT r.submitted_by AS ghost_id, u.telegram_id AS real_id, u.full_name,
       COUNT(*) AS reports, MIN(r.report_date) AS from_date, MAX(r.report_date) AS to_date
FROM structured_reports r
JOIN users u ON u.id = r.submitted_by
WHERE NOT EXISTS (SELECT 1 FROM users u2 WHERE u2.telegram_id = r.submitted_by)
GROUP BY 1,2,3 ORDER BY 4 DESC;

\echo ''
\echo '--- PREVIEW: orphans with NO matching users row (need manual attention) ---'
SELECT r.submitted_by AS unknown_id, COUNT(*) AS reports,
       MIN(r.report_date) AS from_date, MAX(r.report_date) AS to_date
FROM structured_reports r
WHERE NOT EXISTS (SELECT 1 FROM users u2 WHERE u2.telegram_id = r.submitted_by)
  AND NOT EXISTS (SELECT 1 FROM users u  WHERE u.id          = r.submitted_by)
GROUP BY 1 ORDER BY 2 DESC;

BEGIN;

-- ── 1. Re-attribute: users.id → users.telegram_id ─────────────────────────
--    Guard: only rows whose current submitted_by is NOT already a valid
--    telegram_id. Telegram ids are 9-10 digits, PKs are small, so there is no
--    realistic collision, but the guard makes that explicit.
UPDATE structured_reports r
   SET submitted_by = u.telegram_id
  FROM users u
 WHERE r.submitted_by = u.id
   AND NOT EXISTS (SELECT 1 FROM users u2 WHERE u2.telegram_id = r.submitted_by);

-- ── 2. Merge duplicate DRAFT reports ──────────────────────────────────────
--    The bug produced two drafts per person per day: one from the bot (ghost
--    id) and one from the booking calendar / SPA payments (real id). After
--    step 1 they collide. Keep the lowest id, move everything into it.
CREATE TEMP TABLE _merge AS
SELECT id AS dup_id,
       MIN(id) OVER (PARTITION BY submitted_by, report_date, business_unit) AS keep_id
FROM structured_reports
WHERE status = 'DRAFT';

DELETE FROM _merge WHERE dup_id = keep_id;

\echo ''
\echo '--- duplicate drafts being merged ---'
SELECT COUNT(*) AS reports_to_merge FROM _merge;

UPDATE income_entries e       SET report_id          = m.keep_id FROM _merge m WHERE e.report_id          = m.dup_id;
UPDATE expense_entries e      SET report_id          = m.keep_id FROM _merge m WHERE e.report_id          = m.dup_id;
UPDATE wallet_transactions w  SET report_id          = m.keep_id FROM _merge m WHERE w.report_id          = m.dup_id;
UPDATE prepayments p          SET settled_in_report_id = m.keep_id FROM _merge m WHERE p.settled_in_report_id = m.dup_id;

DELETE FROM structured_reports WHERE id IN (SELECT dup_id FROM _merge);

-- ── 3. Recompute totals from the entries themselves ───────────────────────
UPDATE structured_reports r SET
  total_income  = COALESCE((SELECT SUM(amount) FROM income_entries  WHERE report_id = r.id), 0),
  total_expense = COALESCE((SELECT SUM(amount) FROM expense_entries WHERE report_id = r.id), 0);

COMMIT;

\echo ''
\echo '--- AFTER: any report still owned by nobody? (expect 0 rows) ---'
SELECT r.submitted_by, COUNT(*) AS reports
FROM structured_reports r
WHERE NOT EXISTS (SELECT 1 FROM users u WHERE u.telegram_id = r.submitted_by)
GROUP BY 1;

\echo ''
\echo '--- AFTER: SPA / massage revenue now has a real owner ---'
SELECT COALESCE(u.full_name,'(still none)') AS owner, COUNT(e.id) AS rows, SUM(e.amount) AS total
FROM income_entries e
JOIN structured_reports r ON r.id = e.report_id
JOIN service_items s ON s.id = e.service_item_id
LEFT JOIN users u ON u.telegram_id = r.submitted_by
WHERE s.name_ru ILIKE '%масс%' OR s.name_ru ILIKE '%хам%' OR s.name_ru ILIKE '%spa%' OR s.name_ru ILIKE '%спа%'
GROUP BY 1 ORDER BY 3 DESC;

\echo ''
\echo '--- AFTER: no person should have two drafts for the same day/unit (expect 0) ---'
SELECT submitted_by, report_date, business_unit, COUNT(*)
FROM structured_reports WHERE status='DRAFT'
GROUP BY 1,2,3 HAVING COUNT(*) > 1;
