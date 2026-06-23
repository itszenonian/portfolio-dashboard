#!/usr/bin/env python3
"""Tiny static server for the standalone Kive Agents dashboard."""
from __future__ import annotations

import http.server
from pathlib import Path

PORT = 8766
BASE = Path(__file__).parent

class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        path = self.path.split('?', 1)[0]
        if path in ('/', '/index.html'):
            p = BASE / 'index.html'
            if not p.exists():
                self.send_error(404, 'Agents dashboard not built')
                return
            body = p.read_bytes()
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_error(404)

    def log_message(self, fmt, *args):
        print(f"{self.address_string()} - {fmt % args}")

if __name__ == '__main__':
    print(f'Serving Kive Agents on 0.0.0.0:{PORT}')
    http.server.ThreadingHTTPServer(('0.0.0.0', PORT), Handler).serve_forever()
