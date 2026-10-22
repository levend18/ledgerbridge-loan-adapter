# M8 — Manual UI Acceptance Record

On 22 October 2026, LedgerBridge was checked in the browser against the local
Docker/arm64 stack. Only six-row synthetic scenarios from `tools.make_dirty` were
used for the captured workflow. This is the manual MUST portion of V-22, not an
automated Playwright test suite.

- Signed in as `bank001_user`: [login](screenshots/login.jpg).
- Uploaded compatible credit and payment-plan CSVs through the bank portal.
  Source version 63 showed six credits and six plans: [upload](screenshots/bank-upload.jpg).
- Forced a manual sync, which became SUCCEEDED at published version 63 with 6/6
  rows: [sync](screenshots/sync.jpg).
- The data view showed six credits and normalized 1234.56 amounts, 0.18500000
  rates, ISO dates and booleans: [data](screenshots/data.jpg).
- Profile cards displayed null rates, numeric summaries and categorical charts:
  [profiles](screenshots/profiles.jpg).
- Uploaded the field-error scenario as source version 64. Manual synchronization
  became REJECTED, with 12 ERROR, 2 WARNING and 105 CORRECTED counts. Checked
  REQUIRED, INVALID_NUMBER, OUT_OF_RANGE, UNKNOWN_CODE, MATURITY_AFTER_START and
  ORPHAN_PAYMENT details, including raw values and the ERROR filter:
  [validation](screenshots/validation-rejected.jpg).
- After rejection, the published snapshot remained version 63 with six credits.
- The workspace remained BANK001; no BANK002 records appeared. Automated
  API/RLS isolation evidence is provided separately by V-03/V-04/V-05.

Screenshots represent different stages of this synthetic workflow. Acceptance
and benchmark commands change demo data; `make seed` restores the initial
portfolio. UI labels remain Turkish; the documentation is English.
