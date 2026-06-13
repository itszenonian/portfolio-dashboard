#!/usr/bin/env python3
"""
Portfolio Dashboard Server — cloud-ready.
Serves portfolio_dashboard.html, handles /refresh, and stock edits.
Viewing (GET) is open to anyone with the URL. Data-mutating actions (POST)
are protected by HTTP Basic Auth (set DASHBOARD_USER / DASHBOARD_PASS in .env).

Usage:
    python server.py
Then open http://<your-vm-ip>:8765 in your browser.
"""

import base64
import hmac
import http.server
import json
import os
import subprocess
import sys
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

PORT = 8765
BASE = Path(__file__).parent
AUTH_USER = os.getenv("DASHBOARD_USER", "admin")
AUTH_PASS = os.getenv("DASHBOARD_PASS", "changeme")

# Tracks the background `generate_dashboard.py` run kicked off by /refresh,
# so /refresh can return immediately and the page can poll for completion
# (a long-held request can get silently dropped by NAT/proxy idle timeouts).
_refresh_state = {'proc': None, 'log': BASE / 'refresh.log'}


class Handler(http.server.BaseHTTPRequestHandler):
    def _auth_ok(self):
        auth = self.headers.get("Authorization", "")
        if not auth.startswith("Basic "):
            return False
        try:
            decoded = base64.b64decode(auth[6:]).decode()
            user, pw = decoded.split(":", 1)
            return (hmac.compare_digest(user, AUTH_USER) and
                    hmac.compare_digest(pw, AUTH_PASS))
        except Exception:
            return False

    def _require_auth(self):
        self.send_response(401)
        self.send_header("WWW-Authenticate", 'Basic realm="Portfolio Dashboard"')
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self):
        if self.path in ('/', '/index.html'):
            html_path = BASE / 'portfolio_dashboard.html'
            if not html_path.exists():
                self.send_error(404, 'Dashboard not found — run generate_dashboard.py first')
                return
            content = html_path.read_bytes()
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(content)))
            self.end_headers()
            self.wfile.write(content)
        elif self.path == '/market/notes':
            notes_path = BASE / 'market_notes.json'
            notes = json.loads(notes_path.read_text()) if notes_path.exists() else []
            body  = json.dumps(notes).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif self.path == '/refresh-status':
            proc = _refresh_state['proc']
            if proc is None:
                body = json.dumps({'done': True, 'ok': True}).encode()
            else:
                rc = proc.poll()
                if rc is None:
                    body = json.dumps({'done': False}).encode()
                elif rc == 0:
                    body = json.dumps({'done': True, 'ok': True}).encode()
                else:
                    log_path = _refresh_state['log']
                    err = log_path.read_text()[-500:] if log_path.exists() else ''
                    body = json.dumps({'done': True, 'ok': False, 'error': err}).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_error(404)

    def do_POST(self):
        if not self._auth_ok():
            self._require_auth()
            return
        if self.path == '/refresh':
            try:
                proc = _refresh_state['proc']
                if proc is not None and proc.poll() is None:
                    body = json.dumps({'ok': True, 'already_running': True}).encode()
                else:
                    log_f = open(_refresh_state['log'], 'w')
                    _refresh_state['proc'] = subprocess.Popen(
                        [sys.executable, str(BASE / 'generate_dashboard.py')],
                        stdout=log_f, stderr=subprocess.STDOUT
                    )
                    log_f.close()  # child keeps its own dup'd fd
                    body = json.dumps({'ok': True, 'started': True}).encode()
            except Exception as e:
                body = json.dumps({'ok': False, 'error': str(e)}).encode()

        elif self.path == '/stocks/update':
            try:
                length = int(self.headers.get('Content-Length', 0))
                payload = json.loads(self.rfile.read(length))
                stocks_path = BASE / 'stocks.json'
                stocks = json.loads(stocks_path.read_text()) if stocks_path.exists() else []
                for s in stocks:
                    if s['ticker'] == payload['ticker']:
                        s['shares']   = float(payload['shares'])
                        s['avg_cost'] = float(payload['avg_cost'])
                        if s.get('price', 0) > 0 and s['avg_cost'] > 0:
                            s['pct_chg'] = round((s['price'] - s['avg_cost']) / s['avg_cost'] * 100, 1)
                        break
                stocks_path.write_text(json.dumps(stocks, indent=2))
                body = json.dumps({'ok': True}).encode()
            except Exception as e:
                body = json.dumps({'ok': False, 'error': str(e)}).encode()

        elif self.path == '/stocks/add':
            try:
                length = int(self.headers.get('Content-Length', 0))
                payload = json.loads(self.rfile.read(length))
                stocks_path = BASE / 'stocks.json'
                stocks = json.loads(stocks_path.read_text()) if stocks_path.exists() else []
                ticker = payload['ticker'].strip().upper()
                if any(s['ticker'] == ticker for s in stocks):
                    body = json.dumps({'ok': False, 'error': f'{ticker} already exists'}).encode()
                else:
                    stocks.append({
                        'ticker':       ticker,
                        'name':         ticker,   # auto-filled by fetch_stock_prices on next refresh
                        'exchange':     '',        # auto-filled by fetch_stock_prices
                        'shares':       float(payload['shares']),
                        'avg_cost':     float(payload['avg_cost']),
                        'price':        0.0,
                        'market_value': 0.0,
                        'pct_chg':      0.0,
                        'daily_chg':    0.0,
                        'currency':     'USD',     # auto-corrected by fetch_stock_prices
                    })
                    stocks_path.write_text(json.dumps(stocks, indent=2))
                    body = json.dumps({'ok': True}).encode()
            except Exception as e:
                body = json.dumps({'ok': False, 'error': str(e)}).encode()

        elif self.path == '/market/note':
            try:
                length  = int(self.headers.get('Content-Length', 0))
                payload = json.loads(self.rfile.read(length))
                notes_path = BASE / 'market_notes.json'
                notes = json.loads(notes_path.read_text()) if notes_path.exists() else []
                entry = {
                    'date':    payload['date'],
                    'title':   payload.get('title', '').strip(),
                    'content': payload.get('content', '').strip(),
                    'saved_at': payload.get('saved_at', ''),
                }
                # Replace existing entry for same date or prepend
                notes = [n for n in notes if n['date'] != entry['date']]
                notes.insert(0, entry)
                notes = notes[:90]  # keep last 90 days
                notes_path.write_text(json.dumps(notes, indent=2, ensure_ascii=False))
                body = json.dumps({'ok': True}).encode()
            except Exception as e:
                body = json.dumps({'ok': False, 'error': str(e)}).encode()

        elif self.path == '/market/note/delete':
            try:
                length  = int(self.headers.get('Content-Length', 0))
                payload = json.loads(self.rfile.read(length))
                notes_path = BASE / 'market_notes.json'
                notes = json.loads(notes_path.read_text()) if notes_path.exists() else []
                notes = [n for n in notes if n['date'] != payload['date']]
                notes_path.write_text(json.dumps(notes, indent=2, ensure_ascii=False))
                body = json.dumps({'ok': True}).encode()
            except Exception as e:
                body = json.dumps({'ok': False, 'error': str(e)}).encode()

        elif self.path == '/weekly-update':
            try:
                result  = subprocess.run(
                    [sys.executable, str(BASE / 'update_weekly.py'), '--read-sheet'],
                    capture_output=True, text=True, timeout=360
                )
                if result.returncode == 0:
                    body = json.dumps({'ok': True, 'log': result.stdout[-500:]}).encode()
                else:
                    body = json.dumps({'ok': False, 'error': result.stderr[-400:]}).encode()
            except Exception as e:
                body = json.dumps({'ok': False, 'error': str(e)}).encode()

        else:
            self.send_error(404)
            return

        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        if args and str(args[1]) not in ('200', '304'):
            super().log_message(fmt, *args)


if __name__ == '__main__':
    server = http.server.HTTPServer(('0.0.0.0', PORT), Handler)
    print(f'Portfolio Dashboard → http://0.0.0.0:{PORT}')
    print(f'Viewing is open. POST auth user: {AUTH_USER}')
    print('Press Ctrl+C to stop.\n')
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\nServer stopped.')
