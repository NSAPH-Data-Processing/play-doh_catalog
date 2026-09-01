# Play-Doh Catalog

The Play-Doh Catalog is a public website that documents datasets imported into the NSAPH ReD shared space. It's generated — not hand-edited — from a Google
Form/Sheet that the  data team uses to track dataset
intake. This repo is the code that turns Sheet rows into that website.

## The big picture

```text
Researcher fills out   Google Form
Google Form                │
                            ▼
                     Google Sheet  ← internal source of truth
                            │
                Reviewer sets review_status = Approved
                Reviewer sets publish_to_catalog = TRUE
                            │
                            ▼
              Publishing script (this repo, GitHub Actions)
                 reads the Sheet, applies eligibility +
                 privacy rules, builds one metadata record
                 per approved dataset
                            │
                            ▼
                  Static catalog website (site/)
                            │
                            ▼
              PR against main → human review → merge
                            │
                            ▼
                Netlify auto-deploys the live site
```

Two things to hold onto:

1. **The Sheet is never read directly by the website.** The website only
   ever sees what the publishing script decides to hand it. This matters
   because the Sheet contains private information (submitter emails,
   internal file paths, restricted-import approvals) mixed in with the
   information that's safe to publish.
2. **A human always reviews the rebuild before it goes live** — the
   pipeline opens a pull request, it never pushes straight to `main`.

## Who can see what: the three publicity tiers

Every dataset row in the Sheet lands in one of three tiers, based on how
the submitter answered the Sheet's sharing questions:

| Tier | Meaning | What the catalog shows |
|---|---|---|
| **Public** | Fully shareable, no restrictions | Full description, keywords, coverage/resolution, and its actual location in ReD/Cannon |
| **Consent** | Shareable, but only with the PI's/owner's permission | Same description-level fields, plus instructions for requesting access — but **not** its file locations |
| **Restricted** | Not shareable at all | Nothing. The dataset does not appear in the catalog, at all — not even a stub entry |

A dataset only reaches one of the first two tiers — and therefore only
appears in the catalog — once **both** of these are true in the Sheet:

- `review_status` = `Approved` (a human checked the submission is valid)
- `publish_to_catalog` = `TRUE` (a human decided it should be advertised
  publicly, as distinct from being approved for import)

**The publishing script works off an explicit whitelist of fields.** A new
column added to the Sheet is invisible to the catalog until someone
deliberately teaches the script about it. This is intentional — it means a
mistake (forgetting to update the code) fails *closed* (nothing new gets
published) rather than *open* (a new private column leaks by default).

## Repository layout

```text
play_doh_catalog/       the publishing pipeline (this is the code you'll edit)
  sheets.py                reads raw rows from the Google Sheet
  fields.py                maps the Sheet's raw column headers → stable field names
  eligibility.py            decides: is this row publishable, and in which tier?
  catalog_record.py         builds one catalog JSON record from an eligible row
  build_site.py             orchestrates all of the above + calls datalad-catalog

tests/                   one test file per module above, run with pytest

site/                    the generated static website — do not hand-edit;
                          it's overwritten by every rebuild
config.json              catalog branding: name, logo, link colors, social links
sheet_config.yaml        which Sheet/tab the script reads (not secret — see below)
environment.yaml         conda environment definition
credentials/             gitignored — your local Google service-account key goes here

.github/workflows/
  rebuild-catalog.yml    the GitHub Actions workflow that runs the pipeline in CI

docs/
  google_sheets_setup.md  one-time setup for Google Sheets API access
```

### How a row becomes a catalog entry — reading order

If you want to understand the pipeline, read the modules under
`play_doh_catalog/` in this order; each one is a step in the pipeline and
takes the previous step's output as its input:

1. **`sheets.py`** — `read_sheet_rows()` calls the Google Sheets API and
   returns each Sheet row as a plain `dict` keyed by the *literal* column
   header text (e.g. `"Is the dataset publicly shareable? (...)"`).
2. **`fields.py`** — `normalize_row()` re-keys that dict using
   `HEADER_MAP`, converting long/awkward header text into short stable
   names like `publicly_shareable` or `review_status`. Any header **not**
   in `HEADER_MAP` is silently dropped — this is the whitelist in action.
3. **`eligibility.py`** — `evaluate_eligibility()` takes a normalized row
   and returns whether it's eligible to publish, and which tier
   (`PUBLIC` / `CONSENT` / `RESTRICTED`) it falls into.
4. **`catalog_record.py`** — `build_catalog_record()` takes an eligible
   row + its tier and builds the actual JSON record that
   [`datalad-catalog`](https://github.com/datalad/datalad-catalog) (the
   library that renders the website) expects. This is the second place
   the whitelist is enforced: only fields explicitly copied here ever
   reach the website.
5. **`build_site.py`** — ties it all together: reads every Sheet row,
   filters to eligible ones, groups them by `Domain` (so the site shows
   folders like "Health" / "Climate" rather than one flat list), and
   drives `datalad-catalog`'s CLI (`catalog-create` / `catalog-validate` /
   `catalog-add` / `catalog-set`) to regenerate `site/` from scratch.

Each rebuild is a **full regeneration**, not an incremental patch —
`datalad-catalog`'s output is deterministic, so an unchanged dataset
produces a zero-diff commit and a changed one shows up cleanly in the PR
diff.

## Running it locally

### 1. Set up the environment

```bash
conda env create -f environment.yaml
conda activate play_doh_catalog
```

### 2. Get Google Sheets access

Follow `docs/google_sheets_setup.md` to create a service account and
download its JSON key. Save it locally as
`credentials/service-account.json` (this path is gitignored — never
commit it). Then set:

```bash
export GOOGLE_APPLICATION_CREDENTIALS=credentials/service-account.json
```

`sheet_config.yaml` at the repo root already points at the right
spreadsheet/tab — it's committed because a spreadsheet ID and tab name
don't grant access on their own (only the service-account key does).

### 3. Rebuild the site

```bash
python -m play_doh_catalog.build_site
```

This overwrites `site/` with a freshly generated catalog and updates
`catalog_state.json` (a small bookkeeping file — not read by the website
itself — used only to report what changed since the last run).

### 4. Run the tests

```bash
pytest
```

Each module in `play_doh_catalog/` has a matching test file in `tests/`.
Notably, `tests/test_fields.py` checks `HEADER_MAP` against the real
Sheet's headers as captured on a known date — if the Google Form's
questions get reworded, this is the test that will catch the drift.

## How it runs in production

The pipeline also runs as a GitHub Actions workflow
(`.github/workflows/rebuild-catalog.yml`), triggered manually from the
Actions tab (`workflow_dispatch`) — there's no automatic trigger on Sheet
edits by design; this is treated as a low-frequency, human-initiated
process. Each run:

1. Reads the Sheet and rebuilds `site/`, using a `GOOGLE_SERVICE_ACCOUNT_JSON`
   repository secret for credentials.
2. If anything changed, opens a GitHub Issue describing what changed
   (datasets added/removed/modified) and commits the rebuilt `site/` to a
   fresh branch (`catalog-update-<run number>`).
3. A human then opens a pull request from that branch (GitHub prompts for
   this — the workflow doesn't do it automatically) and reviews Netlify's
   deploy preview before merging.
4. Merging to `main` triggers Netlify's production deploy.

## Where to go for more detail

- **`docs/google_sheets_setup.md`** — step-by-step Google Cloud / service
  account setup.
- Docstrings at the top of each `play_doh_catalog/*.py` file explain that
  module's specific role and any non-obvious edge cases (e.g. why DOIs of
  literally `"N/A"` are treated as absent, or why PI name doesn't go in
  the catalog's structured `authors` field).
