"""
EMGS Visa Application Tracker
=============================

Reads a list of international students from a Google Sheet, looks up each
student's visa application on the public EMGS (Education Malaysia Global
Services) status page, and writes the current progress back to the sheet.

Built to replace a manual routine of checking applications one by one.

Usage:
    python emgs_tracker.py              # check all tabs in config.json, write results
    python emgs_tracker.py --dry-run    # check, but print results instead of writing
    python emgs_tracker.py --headless   # run Chrome without opening a window

Setup: see README.md.
"""

import argparse
import json
import os
import sys
import time

import gspread
from dotenv import load_dotenv
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select, WebDriverWait

from nationality_codes import to_country_code

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Anchor every path to this script's own folder, so double-clicking, a
# terminal, or a startup shortcut all behave the same.
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(SCRIPT_DIR, ".env"))

EMGS_SEARCH_URL = "https://visa.educationmalaysia.gov.my/emgs/application/searchForm/"

# Words that mean an application was rejected / failed. EMGS only draws a
# rejection on a <canvas>, so the text near the "Application Status" label
# is the only readable signal.
REJECT_WORDS = ("REJECT", "FAIL", "UNSUCCESSFUL", "DECLINE")

# Rows whose status already contains one of these are finished; skip them.
FINISHED_MARKERS = ("CLOSED", "REJECTED", "100%")

HEADER_ROW = 2          # row number holding the column headers
POLITE_DELAY_SECS = 1   # pause between lookups so we don't hammer the EMGS server


def load_config():
    """Read secrets from .env and tab layout from config.json."""
    sheet_id = os.getenv("SHEET_ID")
    creds_file = os.getenv("GOOGLE_CREDENTIALS_FILE", "credentials.json")
    if not sheet_id:
        sys.exit("SHEET_ID is not set. Copy .env.example to .env and fill it in.")

    creds_path = os.path.join(SCRIPT_DIR, creds_file)
    if not os.path.exists(creds_path):
        sys.exit(f"Credentials file not found: {creds_path}")

    config_path = os.path.join(SCRIPT_DIR, "config.json")
    if not os.path.exists(config_path):
        sys.exit("config.json not found. Copy config.example.json to config.json.")
    with open(config_path, encoding="utf-8") as f:
        config = json.load(f)

    return sheet_id, creds_path, config["tabs"]


# ---------------------------------------------------------------------------
# Scraping
# ---------------------------------------------------------------------------

def read_progress(driver, timeout=10):
    """
    Return the application's progress after a search has been submitted.

    - A percentage ("85%") is real text in an <h2>, and always wins.
    - Otherwise, look only at the text right after each "Application Status"
      label for rejection words. The whole page is never scanned, so a valid
      application can't be misread as rejected.
    - "No record found" returns an empty string.
    """
    def check(d):
        try:
            for el in d.find_elements(By.XPATH, "//h2"):
                if "%" in el.text:
                    return el.text.strip()
            body = d.find_element(By.TAG_NAME, "body").text.upper()
            for segment in body.split("APPLICATION STATUS")[1:]:
                if any(word in segment[:80] for word in REJECT_WORDS):
                    return "REJECTED"
            if "NO RECORD FOUND" in body:
                return "__NONE__"
        except Exception:
            return False
        return False

    try:
        result = WebDriverWait(driver, timeout).until(check)
    except Exception:
        return ""
    return "" if result == "__NONE__" else result


def read_application_type(driver):
    """Return the 'Application Type' value on the results page (e.g. NEW, RENEWAL)."""
    try:
        body = driver.find_element(By.TAG_NAME, "body").text.upper()
        if "APPLICATION TYPE" not in body:
            return ""
        after = body.split("APPLICATION TYPE", 1)[1].lstrip(" :\n\t\r")
        parts = after.split()
        return parts[0].strip(",.;:") if parts else ""
    except Exception:
        return ""


def lookup(driver, passport, country_code):
    """Submit one search on the EMGS page and return (progress, application_type)."""
    driver.get(EMGS_SEARCH_URL)
    wait = WebDriverWait(driver, 10)
    passport_input = wait.until(
        EC.presence_of_element_located((By.NAME, "travel_doc_no"))
    )
    passport_input.send_keys(passport)
    Select(driver.find_element(By.ID, "nationality")).select_by_value(country_code)
    driver.execute_script("arguments[0].click();", driver.find_element(By.ID, "agreement"))
    driver.find_element(By.XPATH, "//button[@type='submit']").click()

    progress = read_progress(driver, 10)
    return progress, read_application_type(driver)


# ---------------------------------------------------------------------------
# Sheet processing
# ---------------------------------------------------------------------------

def find_columns(headers, default_status_col):
    """Locate the passport, nationality and status columns by header text."""
    passport_key = nationality_key = status_key = ""
    status_col = default_status_col
    for i, header in enumerate(headers):
        h = str(header).upper()
        if "PASSPORT" in h:
            passport_key = header
        elif "NATIONALITY" in h:
            nationality_key = header
        elif "PERCENTAGE" in h:
            status_key = header
            status_col = i + 1
    return passport_key, nationality_key, status_key, status_col


def process_tab(sheet, driver, tab, dry_run=False):
    students = sheet.get_all_records(head=HEADER_ROW)
    headers = sheet.row_values(HEADER_ROW)
    passport_key, nationality_key, status_key, status_col = find_columns(
        headers, tab["default_status_col"]
    )

    checked = updated = errors = 0
    for index, student in enumerate(students):
        sheet_row = index + HEADER_ROW + 1

        passport = "".join(str(student.get(passport_key, "")).split())
        nationality = " ".join(str(student.get(nationality_key, "")).split()).upper()
        current = str(student.get(status_key, "")).upper()

        if not passport or not nationality:
            continue
        if any(marker in current for marker in FINISHED_MARKERS):
            continue

        country_code = to_country_code(nationality)
        if not country_code:
            print(f"Row {sheet_row}: unknown nationality '{nationality}', skipped")
            continue

        checked += 1
        try:
            progress, app_type = lookup(driver, passport, country_code)

            # The renewal tab should only record genuine renewals.
            if tab.get("renewal_only") and app_type == "NEW":
                progress = ""
                print(f"Row {sheet_row}: application type is NEW, not a renewal; cleared")

            print(f"Row {sheet_row}: {progress or '(no record)'}")
            if not dry_run:
                sheet.update_cell(sheet_row, status_col, progress)
            updated += 1
        except Exception as e:
            errors += 1
            print(f"Row {sheet_row}: error - {e}")
            if not dry_run:
                sheet.update_cell(sheet_row, status_col, "Scrape Error")

        time.sleep(POLITE_DELAY_SECS)

    return checked, updated, errors


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Track EMGS visa application progress.")
    parser.add_argument("--dry-run", action="store_true",
                        help="look up applications but don't write to the sheet")
    parser.add_argument("--headless", action="store_true",
                        help="run Chrome without a visible window")
    args = parser.parse_args()

    sheet_id, creds_path, tabs = load_config()

    print("Connecting to Google Sheets...")
    spreadsheet = gspread.service_account(filename=creds_path).open_by_key(sheet_id)

    options = webdriver.ChromeOptions()
    if args.headless:
        options.add_argument("--headless=new")
    driver = webdriver.Chrome(options=options)

    totals = [0, 0, 0]
    try:
        for tab in tabs:
            title = tab.get("title")
            try:
                sheet = spreadsheet.sheet1 if not title else spreadsheet.worksheet(title)
            except Exception as e:
                print(f"Could not open tab {title!r}: {e}")
                print("Available tabs:", [w.title for w in spreadsheet.worksheets()])
                continue

            print(f"\n===== {title or 'First tab'} =====")
            for i, n in enumerate(process_tab(sheet, driver, tab, args.dry_run)):
                totals[i] += n
    finally:
        driver.quit()

    checked, updated, errors = totals
    mode = " (dry run, nothing written)" if args.dry_run else ""
    print(f"\nDone{mode}: {checked} checked, {updated} updated, {errors} errors.")


if __name__ == "__main__":
    main()
