#!/bin/bash
set -e

echo "=== Swapping domains ==="
echo "  hookgen.online → Ringside Analytics"
echo "  moviea.net     → Movie Rec (was hookgen.online)"
echo ""

# Copy configs
echo "[1/5] Copying nginx configs..."
sudo cp /var/www/wrastling/nginx/ringside.conf /etc/nginx/sites-available/ringside
sudo cp /var/www/wrastling/nginx/moviea.conf /etc/nginx/sites-available/moviea

# Swap symlinks
echo "[2/5] Swapping symlinks..."
sudo rm -f /etc/nginx/sites-enabled/movierec
sudo ln -sf /etc/nginx/sites-available/ringside /etc/nginx/sites-enabled/ringside
sudo ln -sf /etc/nginx/sites-available/moviea /etc/nginx/sites-enabled/moviea

# Test config
echo "[3/5] Testing nginx config..."
sudo nginx -t

# Reload
echo "[4/5] Reloading nginx..."
sudo systemctl reload nginx

echo "[5/5] Getting SSL cert for moviea.net..."
sudo certbot --nginx -d moviea.net -d www.moviea.net

echo ""
echo "=== Done ==="
echo "  https://hookgen.online  → Ringside Analytics (port 3000/3001)"
echo "  https://moviea.net      → Movie Rec (port 8001)"
