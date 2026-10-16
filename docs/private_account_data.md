# Private account data model

## Storage boundary

- Keep account exports, transaction ledgers, snapshots and any account-specific portfolio JSON under the local `account_private/` directory.
- `account_private/` is ignored by Git. Do not upload its contents to the public repository or GitHub Pages.
- Public `site/data/latest.json` is market/valuation-only. Public history may contain market observations and data-quality metadata only.
- No Tencent Licaitong API adapter is enabled. Add one only after an official API and its authorization scope are confirmed.

## One-time migration from the legacy file

Before merging the privacy-removal change, preserve the currently tracked `portfolio.json` privately:
1. In a local checkout of the current main branch, copy `portfolio.json` to `account_private/portfolio.json`.
2. Verify the copy locally; do not upload it, attach it to a public issue, or paste its contents into chat.
3. Then update to the privacy branch and confirm `account_private/portfolio.json` remains present locally and is ignored by Git.
4. The legacy `data/dashboard_history.json` and public `site/data/history.json` are reset because they contain historical account-level values. Market valuation history under `data/history/*.csv` is preserved.

If you only use GitHub's web interface and cannot make a local copy, do not merge the deletion yet; first download the legacy file to a private device/location. Removing a file from the latest commit does not erase old Git history. A separate history purge is needed to remove historical copies from the repository's reachable history.

## First-stage CSV import

Use `account_import.py transactions <file.csv>` or `account_import.py snapshots <file.csv>`.

Transactions CSV canonical columns:
`transaction_id,date,action,code,name,amount,shares,nav,fee,status,source,raw_description`

Holdings snapshot CSV canonical columns:
`as_of,account_id,cash_balance,total_assets,code,name,shares,unit_cost,nav,market_value,unrealized_pnl,source`

Unknown source headers are not guessed. The importer accepts canonical names plus a small explicit alias list, rejects rows with missing required keys, and writes normalized records locally as JSON Lines. It reports counts and errors only, not row contents.

## Integrity and reconciliation

- Transactions are idempotent: prefer source transaction ID; otherwise use a deterministic fingerprint of date, action, code, amount, shares, NAV and status.
- Snapshot identity is `as_of + account_id + code`; a later import replaces the same identity rather than duplicating it.
- Blank source fields remain blank/null. No synthetic cash balance, NAV, shares, historical trades or missing dates are created.
- Imported values are source facts; computed values must be labelled as computed and retain the valuation date.
- Keep original exports in private storage if retention is needed. Never log full rows or account identifiers.

## Deployment note

The public workflow intentionally runs in valuation-only mode when no local private ledger is available. A GitHub-hosted workflow cannot read a local ignored directory. If future account automation is required, use a dedicated private data store and narrowly scoped authorization; do not put private records in the public repository or publish them as workflow artifacts.
