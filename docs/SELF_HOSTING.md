# Self-hosting deskstack

Deploy your own copy on a free Cloudflare account, so you don't share the public service's daily capacity.
You need Node.js 24+ and a free Cloudflare account.

## In one command

```bash
git clone https://github.com/joaquimmj/deskstack && cd deskstack
scripts/self-host.sh
```

The script:

1. asks for your SEC contact;
2. signs you in to Cloudflare;
3. creates your daily-cap database and writes its id into your `server/wrangler.jsonc`;
4. builds the data for 10 large US companies, Damodaran's valuation inputs, the European issuers and the Brazilian
   companies;
5. deploys and prints your connector URL.

The European build takes 10-20 minutes the first time. Options:

- `--bulk`: every SEC company (downloads 2-3 GB);
- `--tickers AAPL,MSFT`: only these companies;
- `--no-eu`: skip the European issuers;
- `--dry-run`: print the steps and run nothing.

## Step by step

```bash
git clone https://github.com/joaquimmj/deskstack && cd deskstack/server
npm ci
npx wrangler login
```

1. **Set your SEC contact.** SEC's fair-access policy requires a User-Agent naming you. Store it as a Worker secret
   (it never goes in the repo): `printf '%s' "<your app name> <your email>" | npx wrangler secret put SEC_USER_AGENT`.
   Run this after the first deploy (step 3), or let Wrangler create the Worker when you run it.
2. **Build the snapshot.** This is optional but recommended: without it, every request fetches SEC live, which is slower and can hit the free plan's CPU limit on large filers.
   - A few companies: `SEC_USER_AGENT="..." npm run snapshot -- --tickers AAPL,MSFT,NVDA`
   - All of them: `SEC_USER_AGENT="..." npm run snapshot -- --bulk` (downloads 2–3 GB)
   - **Valuation inputs** (Damodaran, about 1.5 MB): `npx tsx scripts/build-damodaran.ts`. Without it,
     `valuation_inputs` is unavailable.
   - **European issuers** (ESEF and UKSEF reports, 10-20 minutes): `npx tsx scripts/build-esef.ts`. Without it,
     European companies are missing.
   - **Brazilian companies** (CVM open data, a few minutes): `npx tsx scripts/build-cvm.ts`. The data is under the
     ODbL: keep the attribution, and keep `v1/br/dataset.json` downloadable.
3. **Deploy:** `npm run deploy`. Wrangler prints your URL, `https://deskstack.<you>.workers.dev`.
4. **Connect it in Claude:** Customize → Connectors → Add custom connector. Paste `https://deskstack.<you>.workers.dev/mcp`, with no sign-in.

**Daily cap and per-IP limit.** `wrangler.jsonc` binds both: a rate limiter (`IP_LIMITER`, 60 requests a minute
per IP and Cloudflare location) and a D1 counter (`USAGE`) that enforces `DAILY_CAP`. The D1 `database_id` in the file
is the public service's, so create your own and replace it:

```bash
npx wrangler d1 create deskstack-usage
npx wrangler d1 execute deskstack-usage --remote --file migrations/0001_usage.sql
```

If you share your copy, keep both. Without them one client can spend the Free plan's 100k requests/day for everyone
(Cloudflare then returns error 1027 until 00:00 UTC; nothing is billed). For a private copy you can remove the two
blocks.

**Nightly refresh.** Fork the repo and set the Actions secrets `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ACCOUNT_ID` and `SEC_USER_AGENT`. `.github/workflows/snapshot-deploy.yml` then rebuilds and deploys daily.
