# Deployment Guide — Structured Reports Update

## What's New
- Button-driven report entry (no more free-text daily reports)
- 16 properties, 8 services, 6 minibar items, 5 staff members preloaded
- New expense flow with staff attribution
- Auto-daily-report at 21:00 Tashkent time
- New API endpoints at `/api/v1/structured/`
- React dashboard components (to be built separately)

## Deployment Steps

### 1. SCP the archive to VPS
```bash
scp deploy-structured-reports.tar.gz root@83.69.135.27:/opt/projects/analytics/
```

### 2. SSH into VPS and run the migration
```bash
ssh root@83.69.135.27
cd /opt/projects/analytics

# Run the SQL migration to create new enum types and tables
docker compose exec db psql -U balandda -d balandda -f /dev/stdin < scripts/migrate_new_tables.sql
```

If the above doesn't work (file not mounted), copy the SQL in:
```bash
docker compose cp scripts/migrate_new_tables.sql db:/tmp/migrate.sql
docker compose exec db psql -U balandda -d balandda -f /tmp/migrate.sql
```

### 3. Extract the archive
```bash
tar xzf deploy-structured-reports.tar.gz
```

### 4. Rebuild and restart
```bash
docker compose build --no-cache bot api
docker compose up -d
```

### 5. Verify
```bash
docker compose logs -f bot --tail=50
```

Look for:
- "Database tables ready"
- "New structured report tables seeded"
- "Scheduler configured: daily report at 21:00"
- "Bot is running"

### 6. Test in Telegram
1. Send `/start` to the bot
2. Select "Курорт"
3. Tap "Новый отчёт" button (should be at top of main menu)
4. Try adding an accommodation entry
5. Try adding a service/massage
6. Preview and finalize

## Rollback
If something breaks, the old handlers still work (Приход/Расход/История/Отчёт).
The new "Новый отчёт" button is additive — it doesn't break existing functionality.
