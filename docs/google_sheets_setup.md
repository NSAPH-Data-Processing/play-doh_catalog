# Google Sheets API Setup

One-time setup so the publishing script can read the intake Sheet via a
service account, per the "Google Sheets API + service account" decision in
`decisions.md`.

## 1. Create (or choose) a GCP project

Go to the [Google Cloud Console](https://console.cloud.google.com/) and
either select an existing project or create a new one for this catalog.

## 2. Enable the Google Sheets API

In the Cloud Console, go to **APIs & Services → Library**, search for
"Google Sheets API," and enable it for the project.

## 3. Create a service account

**IAM & Admin → Service Accounts → Create Service Account.** Give it a
descriptive name (e.g. `secure-enclave-catalog-reader`). It doesn't need
any project-level IAM role — access is granted per-Sheet in step 5, not via
IAM.

## 4. Create and download a JSON key

On the new service account: **Keys → Add Key → Create new key → JSON**.
This downloads a JSON credentials file.

**This file is a secret.** Save it locally as
`credentials/service-account.json` (already covered by `.gitignore`, see
below) for local development. For CI, store its contents as a GitHub
Actions repository secret instead of a file in the repo.

## 5. Share the intake Sheet with the service account

Open the JSON key file and copy the `client_email` value (looks like
`secure-enclave-catalog-reader@<project>.iam.gserviceaccount.com`). In the
Google Sheet, click **Share** and add that email address with **Viewer**
access — the publishing script only ever needs read access.

## 6. Note the spreadsheet ID and range

The spreadsheet ID is the long token in the Sheet's URL:

```text
https://docs.google.com/spreadsheets/d/SPREADSHEET_ID/edit
```

The read function also needs a range that includes the tab name, e.g.
`Form Responses 1!A1:AZ`. Put both in `sheet_config.yaml` at the repo
root:

```yaml
spreadsheet_id: "<spreadsheet id from step 6>"
range: "<tab name and range from step 6>"
```

This file is committed, not secret — a spreadsheet ID and tab name don't
grant access on their own (see `decisions.md`). Only the service-account
credential itself needs to stay out of git.

## Local development

Set the credential path as an environment variable (e.g. in a gitignored
`.env` file):

```text
GOOGLE_APPLICATION_CREDENTIALS=credentials/service-account.json
```

## CI (GitHub Actions)

Store the JSON key's full contents as a repository secret named
`GOOGLE_SERVICE_ACCOUNT_JSON`, then write it to a temp file at the start
of the workflow job before running the publishing script.
