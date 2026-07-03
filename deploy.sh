#!/bin/bash
# Balandda Analytics — Full deploy script
# Usage: ./deploy.sh
# Run this on the VPS from /opt/projects/analytics

set -e

DEPLOY_DIR="/opt/projects/analytics"
WEB_PUBLIC="/var/www/analytics"

echo "🚀 Starting Balandda Analytics deployment..."

# 1. Pull latest code
echo "📥 Pulling latest code..."
cd "$DEPLOY_DIR"
git pull origin main

# 2. Build frontend
echo "🔨 Building frontend..."
cd "$DEPLOY_DIR/web"
sudo rm -rf dist node_modules/.vite-temp
npm run build

# 3. Copy built files to nginx public dir
echo "📂 Copying frontend to $WEB_PUBLIC..."
sudo rm -rf "$WEB_PUBLIC/assets"
sudo cp -r "$DEPLOY_DIR/web/dist/"* "$WEB_PUBLIC/"

# 4. Rebuild and restart API + Bot containers
# (cache is fine: the source COPY layer invalidates on code changes; avoids
#  --no-cache disk bloat. Old images are pruned afterwards to reclaim space.)
echo "🐳 Rebuilding Docker containers..."
cd "$DEPLOY_DIR"
docker compose build api bot
docker compose up -d
docker image prune -f >/dev/null 2>&1 || true

# 5. Restart nginx-proxy if it exists (host nginx serves static files otherwise)
echo "🔄 Reloading web server..."
docker restart nginx-proxy 2>/dev/null || echo "ℹ️  no nginx-proxy container — host nginx serves static files, skipping"

# 6. Verify
echo ""
echo "✅ Deployment complete!"
echo ""
echo "Checking deployed assets:"
ls -la "$WEB_PUBLIC/assets/"
echo ""
echo "Container status:"
docker ps --format 'table {{.Names}}\t{{.Status}}' | grep -E 'balandda|nginx'
echo ""
echo "Verifying HTML serves correct bundle:"
curl -s http://localhost:8000/ | grep -o 'index-[^"]*\.js'
