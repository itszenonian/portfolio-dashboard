#!/usr/bin/env python3
"""
Weekly update script — run every Wednesday 23:45 Thai time.
Usage: python update_weekly.py --main 114.20 --mm 13.18

Steps:
  1. Fetches live portfolio data (crypto + stocks) via generate_dashboard
  2. Calculates Ann. Yield from provided Main + MM
  3. Appends new row to Google Sheet
  4. Appends to interest_data.json (feeds Cashflow tab)
  5. Regenerates dashboard HTML
"""

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

import gspread
from google.oauth2.service_account import Credentials
from dotenv import load_dotenv

BASE        = Path(__file__).parent
SHEET_ID    = "1KQJO0GdZN-uFfmwoLB-4noebyNzAC1Eq0rZZ84yxtQw"
KEY_FILE    = BASE / "sheets-key.json"
DATA_FILE   = BASE / "interest_data.json"
HISTORY_FILE = BASE / "history.json"

load_dotenv(BASE / ".env")

THAI_TZ = timezone(timedelta(hours=7))


def get_latest_portfolio():
    """Read the most recent history.json entry for portfolio values."""
    if not HISTORY_FILE.exists():
        return None
    history = json.loads(HISTORY_FILE.read_text())
    if not history:
        return None
    return history[-1]


def save_history(history: list) -> None:
    HISTORY_FILE.write_text(json.dumps(history, indent=2))


def load_interest_data():
    if DATA_FILE.exists():
        return json.loads(DATA_FILE.read_text())
    return []


def save_interest_data(data):
    DATA_FILE.write_text(json.dumps(data, indent=2))


def connect_sheet():
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = Credentials.from_service_account_file(str(KEY_FILE), scopes=scopes)
    gc    = gspread.authorize(creds)
    return gc.open_by_key(SHEET_ID)


def read_main_mm_from_sheet(sh, date_str):
    """Read Main and MM from the 'interest' tab for the given date.
    Columns: A=Date, B=Main, C=MM, D=Total, E=Daily, F=Cumulative"""
    ws = sh.worksheet('interest')
    all_vals = ws.get_all_values(value_render_option='FORMATTED_VALUE')
    for row in all_vals:
        if not row or row[0].strip() != date_str:
            continue
        try:
            main = float(str(row[1]).replace(',', '')) if len(row) > 1 and row[1] else 0
            mm   = float(str(row[2]).replace(',', '')) if len(row) > 2 and row[2] else 0
            if main > 0 or mm > 0:
                return main, mm
        except ValueError:
            continue
    return None, None


def sync_interest_from_sheet(sh):
    """Rebuild interest_data.json from interest + 2025 + 2026 sheet tabs."""
    def parse_date(s):
        for fmt in ('%m/%d/%Y', '%m/%d/%y'):
            try:
                from datetime import datetime as _dt
                return _dt.strptime(s.strip(), fmt)
            except Exception:
                pass
        return None

    # Earnings from interest tab
    earnings = {}
    ws_int = sh.worksheet('interest')
    for row in ws_int.get_all_values(value_render_option='FORMATTED_VALUE')[1:]:
        if not row[0] or not row[1]:
            continue
        d = parse_date(row[0])
        if not d:
            continue
        try:
            earnings[d.strftime('%Y-%m-%d')] = {
                'main': float(row[1].replace(',', '')),
                'mm':   float(row[2].replace(',', '')) if row[2] else 0.0,
            }
        except Exception:
            pass

    # Portfolio snapshots from 2025 + 2026 tabs
    snapshots = {}
    for tab in ('2025', '2026'):
        ws = sh.worksheet(tab)
        for row in ws.get_all_values(value_render_option='FORMATTED_VALUE')[1:]:
            if not row[0] or not row[1]:
                continue
            d = parse_date(row[0])
            if not d:
                continue
            try:
                crypto = float(row[1].replace(',', ''))
                stock  = float(row[2].replace(',', '')) if row[2] else 0
                total  = float(row[3].replace(',', '')) if len(row) > 3 and row[3] else 0
                yld    = float(row[9].replace('%', '').replace(',', '')) if len(row) > 9 and row[9] and '%' in row[9] else None
                snapshots[d.strftime('%Y-%m-%d')] = {'crypto': crypto, 'stock': stock, 'total': total, 'yield': yld}
            except Exception:
                pass

    all_dates = sorted(set(list(earnings.keys()) + list(snapshots.keys())))
    from datetime import datetime as _dt
    merged = []
    for dt in all_dates:
        e = earnings.get(dt, {})
        s = snapshots.get(dt, {})
        merged.append({
            'label': _dt.strptime(dt, '%Y-%m-%d').strftime('%-m/%-d/%y'),
            'sort':  dt,
            'main':  e.get('main', 0),
            'mm':    e.get('mm', 0),
            'yield': s.get('yield'),
            'crypto': s.get('crypto'),
            'stock':  s.get('stock'),
            'total':  s.get('total'),
        })

    if merged:
        DATA_FILE.write_text(json.dumps(merged, indent=2))
        print(f"  interest_data.json synced — {len(merged)} entries ({merged[0]['sort']} → {merged[-1]['sort']})")


def sync_history_from_sheet(sh):
    """Rebuild history.json from the 2025 + 2026 sheet tabs so the chart matches exactly."""
    history = []
    for tab in ('2025', '2026'):
        try:
            ws = sh.worksheet(tab)
            rows = ws.get_all_values(value_render_option='FORMATTED_VALUE')
            for row in rows:
                if not row or not row[0].strip():
                    continue
                date_str = row[0].strip()
                # Skip header row
                if date_str.lower() in ('date', ''):
                    continue
                try:
                    crypto = float(str(row[1]).replace(',', '')) if len(row) > 1 and row[1] else 0
                    stock  = float(str(row[2]).replace(',', '')) if len(row) > 2 and row[2] else 0
                    total  = float(str(row[3]).replace(',', '')) if len(row) > 3 and row[3] else 0
                except ValueError:
                    continue
                if crypto > 0 or total > 0:
                    # Normalize date to YYYY-MM-DD
                    try:
                        from datetime import datetime as _dt
                        d = _dt.strptime(date_str, '%m/%d/%Y')
                        history.append({"date": d.strftime('%Y-%m-%d'), "crypto": crypto, "stock": stock, "total": total})
                    except ValueError:
                        pass
        except Exception as e:
            print(f"  WARNING: Could not read {tab} tab: {e}")

    if history:
        history.sort(key=lambda x: x['date'])
        save_history(history)
        print(f"  history.json synced from sheet — {len(history)} entries")


def update_portfolio_row(sh, date_str, crypto_val, stock_val):
    """Write Total crypto + Stock into the '2026' tab for the given date.
    Columns: A=date, B=Total crypto, C=Total stock, D+=formulas"""
    ws = sh.worksheet('2026')
    all_vals = ws.get_all_values(value_render_option='FORMATTED_VALUE')
    for i, row in enumerate(all_vals):
        if not row or row[0].strip() != date_str:
            continue
        row_num = i + 1  # 1-indexed
        try:
            ws.update_cell(row_num, 2, crypto_val)   # Column B = Total crypto
            ws.update_cell(row_num, 3, stock_val)    # Column C = Total stock
            print(f"  Sheet updated — {date_str}: crypto={crypto_val}, stock={stock_val}")
            return True
        except Exception as e:
            print(f"  WARNING: Failed updating row {row_num}: {e}")
    return False


def week_label(dt):
    return dt.strftime("%-m/%-d'%y").replace("'2025", "'25").replace("'2026", "'26")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--main", type=float, help="Main DeFi earnings this week (USD)")
    parser.add_argument("--mm",   type=float, help="MM earnings this week (USD)")
    parser.add_argument("--read-sheet", action="store_true", help="Read Main+MM from Google Sheet automatically")
    parser.add_argument("--date", type=str, help="Override date for testing (e.g. 6/3/2026)")
    args = parser.parse_args()

    now_thai  = datetime.now(THAI_TZ)
    date_str  = args.date if args.date else now_thai.strftime("%-m/%-d/%Y")

    if args.read_sheet or (args.main is None and args.mm is None):
        print("[0/4] Reading Main + MM from Google Sheet...")
        try:
            sh = connect_sheet()
            main_earn, mm_earn = read_main_mm_from_sheet(sh, date_str)
            if main_earn is None:
                print(f"  ERROR: No earnings data found for {date_str} in the sheet. Please fill in Main and MM first.")
                sys.exit(1)
            print(f"  Found — Main: ${main_earn:.2f}  MM: ${mm_earn:.2f}")
        except Exception as e:
            print(f"  ERROR reading sheet: {e}")
            sys.exit(1)
    else:
        main_earn = args.main
        mm_earn   = args.mm or 0.0
    weekly    = main_earn + mm_earn
    lbl       = week_label(now_thai)
    sort_key  = now_thai.strftime("%Y-%m-%d")

    print(f"\n{'='*50}")
    print(f"  Weekly Update — {date_str}")
    print(f"  Main: ${main_earn:.2f}  MM: ${mm_earn:.2f}  Total: ${weekly:.2f}")
    print(f"{'='*50}\n")

    # 1. Regenerate dashboard to get fresh portfolio data
    print("[1/4] Regenerating dashboard (fetching live data)...")
    result = subprocess.run(
        [sys.executable, str(BASE / "generate_dashboard.py")],
        capture_output=True, text=True, timeout=300
    )
    if result.returncode != 0:
        print(f"  ERROR: {result.stderr[-300:]}")
        sys.exit(1)
    print("  Dashboard regenerated.")

    # 2. Read fresh portfolio values from history
    snap = get_latest_portfolio()
    if not snap:
        print("  ERROR: No history data found after regeneration.")
        sys.exit(1)

    crypto_val  = snap["crypto"]
    stock_val   = snap["stock"]
    total_val   = snap["total"]
    ann_yield   = round((weekly / crypto_val) * 52 * 100, 2) if crypto_val > 0 else 0.0

    print(f"  Crypto: ${crypto_val:,.2f}  Stock: ${stock_val:,.2f}  Total: ${total_val:,.2f}")
    print(f"  Ann. Yield: {ann_yield:.2f}%")

    # Load previous entry to calculate % changes
    interest_data = load_interest_data()
    prev_crypto = interest_data[-1]["crypto"] if interest_data else crypto_val
    prev_stock  = interest_data[-1]["stock"]  if interest_data else stock_val
    prev_total  = interest_data[-1]["total"]  if interest_data else total_val
    pct_crypto  = round((crypto_val - prev_crypto) / prev_crypto * 100, 2) if prev_crypto else 0
    pct_stock   = round((stock_val  - prev_stock)  / prev_stock  * 100, 2) if prev_stock  else 0
    pct_total   = round((total_val  - prev_total)  / prev_total  * 100, 2) if prev_total  else 0

    # 3. Append to interest_data.json
    print("[2/4] Updating interest_data.json...")
    new_entry = {
        "label":    lbl,
        "sort":     sort_key,
        "main":     main_earn,
        "mm":       mm_earn,
        "yield":    ann_yield,
        "crypto":   crypto_val,
        "stock":    stock_val,
        "total":    total_val,
    }
    interest_data.append(new_entry)
    save_interest_data(interest_data)
    print(f"  Saved {len(interest_data)} entries to interest_data.json")

    # 4. Update Google Sheet — write only Total crypto + Stock into the existing date row
    print("[3/4] Writing to Google Sheet...")
    try:
        sh = connect_sheet()
        ok = update_portfolio_row(sh, date_str, round(crypto_val, 2), round(stock_val, 2))
        if not ok:
            print(f"  WARNING: Could not find row for {date_str} in portfolio snapshot table.")
        sync_interest_from_sheet(sh)
        sync_history_from_sheet(sh)
    except Exception as e:
        print(f"  WARNING: Sheet write failed — {e}")

    # 5. Regenerate dashboard again to include new Cashflow row
    print("[4/4] Regenerating dashboard with new Cashflow entry...")
    subprocess.run(
        [sys.executable, str(BASE / "generate_dashboard.py")],
        capture_output=True, timeout=300
    )
    print("  Done.\n")
    print(f"  Weekly: ${weekly:.2f}  Yield: {ann_yield:.2f}%  Crypto: ${crypto_val:,.2f}")
    print(f"{'='*50}\n")


if __name__ == "__main__":
    main()
