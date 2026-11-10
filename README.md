# EMGS Visa Application Tracker

A Python bot that checks Malaysian student visa applications on the
[EMGS](https://visa.educationmalaysia.gov.my/) public status page and writes
each student's progress back to a shared Google Sheet.

## The problem

At a language centre handling international student visas, someone had to
open the EMGS site, type in each student's passport number and nationality,
read the progress percentage, and copy it into the team's spreadsheet, one
student at a time, several times a day. Consultants depended on that sheet
to know when to collect passports or chase missing documents.

## What this does

- Reads the student list straight from Google Sheets (any number of tabs)
- Finds the passport, nationality and status columns by header name, so the
  sheet layout can change without breaking the script
- Converts free-text nationalities ("UK", "SOUTH KOREA", "Turkey") into the
  ISO codes the EMGS form needs
- Submits each lookup with Selenium and reads the result:
  - progress percentage (e.g. `85%`)
  - rejections, which EMGS only draws as an image, detected from the
    status text next to the label instead of scanning the whole page
  - "no record found"
- Skips students who are already finished (closed, rejected, 100%)
- On the renewal tab, ignores results that turn out to be new applications
- Writes results back to the sheet, and marks failed lookups as `Scrape Error`
  so nothing fails silently
- Waits between requests so it doesn't overload the government server

**Result:** a repetitive manual check now runs unattended, and the team's
sheet stays current without anyone retyping status updates.

## Tech

Python · Selenium · Google Sheets API (gspread) · pycountry · python-dotenv

## Setup

1. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```
   You also need Google Chrome installed.

2. **Create a Google service account**
   In Google Cloud Console, create a service account, enable the Google
   Sheets API, and download its JSON key as `credentials.json` into this
   folder. Share your sheet with the service account's email address.

3. **Configure**
   ```bash
   cp .env.example .env                 # then put your SHEET_ID in .env
   cp config.example.json config.json   # then adjust tab names / columns
   ```
   `sample_sheet.csv` shows the expected layout: a title in row 1, headers
   in row 2, students from row 3. Import it into Google Sheets to try the
   bot out.

4. **Run**
   ```bash
   python emgs_tracker.py --dry-run     # check without writing anything
   python emgs_tracker.py               # check and update the sheet
   python emgs_tracker.py --headless    # no browser window
   ```

## Notes

- All data in this repo is fictional. Secrets (`.env`, `credentials.json`)
  are excluded by `.gitignore`.
- This only uses EMGS's public status page, the same one any applicant can
  use, and runs at a deliberately slow pace.
- If EMGS changes its page layout, the selectors in `lookup()` and
  `read_progress()` are the places to update.

## License

MIT
