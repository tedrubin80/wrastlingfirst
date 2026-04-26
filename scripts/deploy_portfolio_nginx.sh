#!/usr/bin/env bash
# Repurpose hookgen.online to serve the static portfolio site.
#
# Replaces /etc/nginx/sites-available/ringside (which previously proxied
# the Next.js + Express + ML stack) with the static portfolio config in
# nginx/portfolio.conf. Reuses the existing letsencrypt SSL cert.
#
# Idempotent: backs up the previous config to ringside.bak.<timestamp>
# before overwriting. Verifies cert and config before reload.
#
# Usage:
#   sudo ./scripts/deploy_portfolio_nginx.sh

set -euo pipefail

REPO=/var/www/wrastling
SRC="$REPO/nginx/portfolio.conf"
DST_AVAIL=/etc/nginx/sites-available/ringside
DST_ENABLED=/etc/nginx/sites-enabled/ringside
DOMAIN=hookgen.online
CERT=/etc/letsencrypt/live/$DOMAIN/fullchain.pem

# ─── Pre-flight ──────────────────────────────────────────────────────
[[ $EUID -eq 0 ]] || { echo "Run as root (sudo)." >&2; exit 1; }
[[ -r "$SRC" ]]   || { echo "Missing $SRC — run from repo root." >&2; exit 1; }

# Check required cert exists; if not, run certbot first
if [[ ! -f "$CERT" ]]; then
    echo ">> No existing cert at $CERT"
    echo ">> Running certbot to issue one (interactive, accepts ToS)"
    if ! command -v certbot >/dev/null; then
        apt-get update && apt-get install -y certbot python3-certbot-nginx
    fi

    # Need a temporary HTTP-only server to satisfy ACME challenge.
    # Use the existing config which already serves on :80.
    certbot --nginx -d "$DOMAIN" -d "www.$DOMAIN" --non-interactive --agree-tos \
            --email ted@theorubin.com --redirect
    echo ">> Cert issued. Continuing."
else
    echo ">> Existing cert found. Will reuse."
fi

# ─── Backup current config ──────────────────────────────────────────
TS=$(date +%Y%m%d-%H%M%S)
if [[ -f "$DST_AVAIL" ]]; then
    BACKUP="$DST_AVAIL.bak.$TS"
    echo ">> Backing up current config to $BACKUP"
    cp "$DST_AVAIL" "$BACKUP"
fi

# ─── Install new config ─────────────────────────────────────────────
echo ">> Installing portfolio config"
cp "$SRC" "$DST_AVAIL"

# Ensure symlink in sites-enabled
if [[ ! -L "$DST_ENABLED" ]]; then
    ln -sf "$DST_AVAIL" "$DST_ENABLED"
fi

# ─── Validate + reload ──────────────────────────────────────────────
echo ">> Testing nginx config"
nginx -t

echo ">> Reloading nginx"
systemctl reload nginx

# ─── Verify ─────────────────────────────────────────────────────────
echo ">> Verifying live response"
sleep 1
HTTP_CODE=$(curl -ks -o /dev/null -w "%{http_code}" "https://$DOMAIN/")
echo "   https://$DOMAIN/ -> $HTTP_CODE"

if [[ "$HTTP_CODE" == "200" ]]; then
    echo
    echo "✓ Portfolio is live at https://$DOMAIN/"
    echo "✓ Paper:   https://$DOMAIN/paper.html"
    echo "✓ PDF:     https://$DOMAIN/paper.pdf"
    echo
    echo "Old config saved at $BACKUP — restore with:"
    echo "    sudo cp $BACKUP $DST_AVAIL && sudo systemctl reload nginx"
else
    echo "!! Unexpected HTTP $HTTP_CODE — check /var/log/nginx/ringside-portfolio-error.log"
    exit 1
fi
