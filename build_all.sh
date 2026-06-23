#!/bin/bash
# Rebuild both the slim main dashboard and the standalone Agents site from one
# data fetch. generate_dashboard.py writes portfolio_dashboard.html (slim, served
# on :8765) and .full_dashboard.html (full source); build_agents.py extracts the
# standalone Agents page (served on :8766) from the full source.
set -e
cd /opt/portfolio
/opt/portfolio/venv/bin/python generate_dashboard.py "$@"
/opt/portfolio/venv/bin/python /opt/agents-dashboard/build_agents.py
