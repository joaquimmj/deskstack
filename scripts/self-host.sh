#!/usr/bin/env bash
# Deploys your own deskstack on a free Cloudflare account, in one command. See docs/SELF_HOSTING.md.
#
#   scripts/self-host.sh                      # asks for your SEC contact, builds a small snapshot, deploys
#   scripts/self-host.sh --bulk               # every SEC company (downloads 2-3 GB)
#   scripts/self-host.sh --tickers AAPL,MSFT  # these companies only
#   scripts/self-host.sh --no-eu              # skip the European issuers (their build takes 10-20 minutes)
#   (Brazilian companies from CVM's open data are always built: about 200 MB of downloads, a few minutes.)
#   scripts/self-host.sh --dry-run            # print the steps, run nothing
#
# Needs Node.js 24+ and a free Cloudflare account. Costs nothing: Workers Free, D1 Free.
# Your SEC contact goes to Cloudflare as a Worker secret. It is never written to the repo.

set -euo pipefail

TICKERS="AAPL,MSFT,GOOGL,AMZN,META,NVDA,JPM,KO,CAT,XOM"
SNAPSHOT="tickers"
EU=1
DRY=0
while [ $# -gt 0 ]; do
  case "$1" in
    --bulk) SNAPSHOT="bulk" ;;
    --tickers) TICKERS="${2:?--tickers needs a list, e.g. AAPL,MSFT}"; shift ;;
    --no-snapshot) SNAPSHOT="none" ;;
    --no-eu) EU=0 ;;
    --dry-run) DRY=1 ;;
    -h|--help) sed -n '2,12p' "$0"; exit 0 ;;
    *) echo "Unknown option: $1 (see --help)" >&2; exit 2 ;;
  esac
  shift
done

say() { printf '\n\033[1m%s\033[0m\n' "$*"; }
run() {
  echo "+ $*"
  if [ "$DRY" = 0 ]; then "$@"; fi
}

cd "$(dirname "$0")/../server"

say "1/7  Checking Node.js"
if [ "$DRY" = 0 ]; then
  command -v node >/dev/null || { echo "Node.js is missing. Install Node.js 24 or later from nodejs.org." >&2; exit 1; }
  major="$(node -p 'process.versions.node.split(".")[0]')"
  [ "$major" -ge 24 ] || { echo "Node.js $major found; deskstack needs 24 or later (nodejs.org)." >&2; exit 1; }
fi
run npm ci

say "2/7  Your SEC contact"
# SEC's fair-access policy: requests name an app and a contact. Kept in this shell and sent to Cloudflare as a secret.
if [ -z "${SEC_USER_AGENT:-}" ]; then
  if [ "$DRY" = 1 ]; then
    SEC_USER_AGENT="myapp me@example.com"
  else
    read -r -p "App name and contact email for SEC (e.g. 'mydesk jane@example.com'): " SEC_USER_AGENT
  fi
fi
case "$SEC_USER_AGENT" in
  *@*) ;;
  *) echo "SEC asks for a contact email in the User-Agent, e.g. 'mydesk jane@example.com'." >&2; exit 1 ;;
esac
export SEC_USER_AGENT

say "3/7  Cloudflare sign-in"
# `whoami --json` exits non-zero when signed out.
if [ "$DRY" = 1 ] || ! npx wrangler whoami --json >/dev/null 2>&1; then
  run npx wrangler login
fi

say "4/7  Your daily-cap counter (D1)"
# wrangler.jsonc names the public service's database; your copy needs its own.
if [ "$DRY" = 1 ]; then
  echo "+ npx wrangler d1 create deskstack-usage   (or reuse yours)"
  DB_ID="00000000-0000-0000-0000-000000000000"
else
  DB_ID="$(npx wrangler d1 list --json | node -e 'let s="";process.stdin.on("data",d=>s+=d).on("end",()=>{const d=JSON.parse(s).find(x=>x.name==="deskstack-usage");process.stdout.write(d?d.uuid:"")})')"
  if [ -z "$DB_ID" ]; then
    npx wrangler d1 create deskstack-usage
    DB_ID="$(npx wrangler d1 list --json | node -e 'let s="";process.stdin.on("data",d=>s+=d).on("end",()=>{const d=JSON.parse(s).find(x=>x.name==="deskstack-usage");process.stdout.write(d?d.uuid:"")})')"
  fi
  [ -n "$DB_ID" ] || { echo "Could not find the D1 database deskstack-usage after creating it." >&2; exit 1; }
fi
run node -e '
  const fs = require("fs"); const f = "wrangler.jsonc"; const id = process.argv[1];
  const s = fs.readFileSync(f, "utf8").replace(/("database_id":\s*")[^"]*(")/, `$1${id}$2`);
  fs.writeFileSync(f, s);' "$DB_ID"
run npx wrangler d1 execute deskstack-usage --remote --file migrations/0001_usage.sql

say "5/7  Building the data snapshot"
case "$SNAPSHOT" in
  bulk) run env NODE_OPTIONS=--max-old-space-size=6144 npx tsx scripts/build-snapshot.ts --bulk ;;
  tickers) run npx tsx scripts/build-snapshot.ts --tickers "$TICKERS" ;;
  none) echo "Skipped: every request will fetch SEC live (slower)." ;;
esac
run npx tsx scripts/build-damodaran.ts || echo "Damodaran's datasets didn't build: valuation_inputs will be unavailable. The rest works."
if [ "$EU" = 1 ]; then
  echo "European issuers: about 10-20 minutes the first time (one report every 2 seconds, as filings.xbrl.org asks)."
  run npx tsx scripts/build-esef.ts || echo "The European build failed: European issuers will be missing. The rest works."
fi

echo "Brazilian companies: CVM open data, about 15 ZIPs of 13 MB (ODbL: keep the attribution)."
run npx tsx scripts/build-cvm.ts || echo "The Brazilian build failed: Brazilian companies will be missing. The rest works."

say "6/7  Deploying"
LOG="$(mktemp)"
if [ "$DRY" = 1 ]; then echo "+ npx wrangler deploy"; else npx wrangler deploy | tee "$LOG"; fi
if [ "$DRY" = 1 ]; then
  echo "+ npx wrangler secret put SEC_USER_AGENT   (your contact, from stdin)"
else
  printf '%s' "$SEC_USER_AGENT" | npx wrangler secret put SEC_USER_AGENT
fi

say "7/7  Your connector"
if [ "$DRY" = 1 ]; then
  URL="https://deskstack.<you>.workers.dev"
else
  URL="$(grep -oE 'https://[a-z0-9.-]+\.workers\.dev' "$LOG" | head -1)"
  if [ -n "$URL" ] && curl -fsS "$URL/" >/dev/null 2>&1; then echo "$URL answers."; else URL="${URL:-https://deskstack.<your-subdomain>.workers.dev}"; echo "Check the URL Wrangler printed above."; fi
fi
cat <<EOF

Done. In Claude: Settings > Connectors > Add custom connector, paste
  $URL/mcp
with no sign-in. In Claude Code:
  claude mcp add --transport http deskstack $URL/mcp
Nightly refresh: see docs/SELF_HOSTING.md.
EOF
