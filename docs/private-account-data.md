# Private account data setup

This repository is public. Personal balances, fund shares, transaction records, cost basis and account performance history must live in a separate **private** repository.

## Before merging the security branch

1. Create a new private GitHub repository, for example `OWNER/investment-dashboard-private`.
2. From the current public repository's `main` branch, copy `portfolio.json` and `data/dashboard_history.json` into the private repository root as `portfolio.json` and `dashboard_history.json`. Do this **before** merging the security branch so the existing ledger is preserved. Do not paste these files into issues, pull-request comments or chat.
3. Confirm the new repository is private and contains both JSON files. Keep the history file even if some older shares were estimates; do not silently convert estimates into verified account facts.
4. Create a fine-grained GitHub token restricted to this private repository with **Contents: Read and write**. Do not commit the token.
5. In the public `investment-dashboard` repository, open **Settings → Secrets and variables → Actions → New repository secret** and add:
   - `PRIVATE_DATA_REPO`: `OWNER/investment-dashboard-private`
   - `PRIVATE_DATA_TOKEN`: the fine-grained token from step 4.
6. Only then merge the security branch and run **Actions → Daily investment dashboard update → Run workflow**. If the private repository or secrets are missing, the workflow fails closed rather than reading a public account file.

## Data flow after setup

- `portfolio.json` and full `dashboard_history.json` are loaded from and persisted to the private repository.
- The public repository stores valuation data and a sanitized history projection only.
- The public Pages bundle excludes the private portfolio, holding rows, account-level summary, fund-code list and the per-fund NAV map associated with the personal portfolio.
- `account_import.py` imports official CSV/JSON exports into a local directory outside the repository by default. Example:

  ```bash
  python account_import.py --type transactions --input /path/to/export.csv
  python account_import.py --type snapshots --input /path/to/holdings.csv
  ```

  Use only files exported or otherwise obtained through an authorized official channel. Field names are mapped when recognized; missing values remain missing. Review the import report and reconcile totals before treating data as authoritative.

## Tencent Licaitong integration status

No public, individual-user official API has been confirmed. This branch therefore does **not** log in to Licaitong, scrape its pages, or fabricate transactions. File import is the first supported path. An API adapter should be added only after Tencent confirms the official interface, authorization method, available fields and permitted use.

## Important limitations

- Removing files from the current branch does not erase them from earlier public Git commits, forks, caches or clones. If account data has been exposed, consider repository history rewriting and GitHub cache removal after the private copy is verified. Coordinate history rewriting because it changes commit SHAs.
- GitHub Actions secrets are for credentials, not durable account storage. The private repository is the persistent source of truth.
- Do not use this workflow until the private repository is created and the existing ledger is copied over. The workflow intentionally stops if the private data source is unavailable.
