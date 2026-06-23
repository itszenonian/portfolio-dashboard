#!/usr/bin/env python3
"""Build a standalone Agents dashboard from the portfolio dashboard output.

This intentionally keeps the Agents site separate from the main portfolio
navigation so mobile users can open a smaller, focused page.
"""
from __future__ import annotations

import os
from pathlib import Path

# Build from the full dashboard (which still contains the Agents page + LP data).
# The served main dashboard is now slimmed and no longer includes #page-agents.
SRC = Path(os.environ.get('AGENTS_SRC', '/opt/portfolio/.full_dashboard.html'))
OUT = Path('/opt/agents-dashboard/index.html')


def extract_balanced_div(html: str, start: int) -> str:
    """Return the complete <div ...>...</div> block starting at start."""
    i = start
    depth = 0
    while i < len(html):
        n_open = html.find('<div', i)
        n_close = html.find('</div>', i)
        if n_close == -1:
            raise RuntimeError('unclosed div while extracting page-agents')
        if n_open != -1 and n_open < n_close:
            depth += 1
            i = n_open + 4
            continue
        depth -= 1
        i = n_close + len('</div>')
        if depth == 0:
            return html[start:i]
    raise RuntimeError('failed to extract balanced div')


def main() -> None:
    html = SRC.read_text()
    head = html[html.find('<head>') + len('<head>'):html.find('</head>')]
    # Keep the original CSS/script dependencies, but retitle the standalone app.
    head = head.replace('<title>Portfolio Dashboard</title>', '<title>Kive Agents</title>')

    start = html.find('<div id="page-agents"')
    if start == -1:
        raise RuntimeError('page-agents not found')
    agents_block = extract_balanced_div(html, start).replace('id="page-agents" class="page"', 'id="page-agents" class="page active"', 1)

    lp_start = html.find('const LP_BACKTEST_DATA')
    if lp_start == -1:
        raise RuntimeError('LP_BACKTEST_DATA not found')
    script_open = html.rfind('<script', 0, lp_start)
    script_close = html.find('</script>', lp_start) + len('</script>')
    lp_script = html[script_open:script_close]

    nav_script = """
<script>
const AGENT_TABS = ['overview', 'lp', 'usdc'];
function selectAgentTab(tab, pushHash = true) {
  if (!AGENT_TABS.includes(tab)) tab = 'overview';
  document.querySelectorAll('.agent-panel').forEach(p => p.classList.remove('active'));
  const panel = document.getElementById('agents-' + tab);
  if (panel) panel.classList.add('active');
  document.querySelectorAll('.agent-subtab').forEach(b => {
    const on = b.dataset.agentTab === tab;
    b.classList.toggle('active', on);
    b.setAttribute('aria-selected', on ? 'true' : 'false');
  });
  if (pushHash) {
    const next = tab === 'overview' ? '' : tab;
    if (location.hash.replace(/^#/, '') !== next) location.hash = next ? '#' + next : '#';
  }
  if (tab === 'lp' && typeof renderLpBacktest === 'function') setTimeout(renderLpBacktest, 60);
}
function routeAgentHash() {
  const h = (location.hash || '').replace(/^#/, '');
  if (h === 'lp' || h === 'agents-lp' || h === 'backtest') selectAgentTab('lp', false);
  else if (h === 'usdc' || h === 'agents-usdc') selectAgentTab('usdc', false);
  else selectAgentTab('overview', false);
}
window.addEventListener('hashchange', routeAgentHash);
window.addEventListener('DOMContentLoaded', routeAgentHash);
</script>
"""

    shell = f"""<!DOCTYPE html>
<html lang="en">
<head>
{head}
<style>
/* Standalone Agents site polish */
.top-nav {{ max-width: 1440px; margin: 0 auto; padding: 24px 28px 8px; }}
.agent-home-link {{ color: var(--text2); text-decoration: none; font-size: .82rem; }}
.agent-home-link:hover {{ color: var(--text); }}
@media(max-width:700px) {{ .top-nav {{ padding: calc(18px + env(safe-area-inset-top,0px)) 16px 10px; }} }}
</style>
</head>
<body>
<nav class="top-nav">
  <div class="nav-left">
    <a class="nav-brand" href="/" style="text-decoration:none">Kive <span style="color:var(--text3)">Agents</span></a>
    <a class="agent-home-link" href="https://zenonian.duckdns.org">← Portfolio</a>
  </div>
</nav>
{agents_block}
{nav_script}
{lp_script}
</body>
</html>
"""
    OUT.write_text(shell)
    print(f'wrote {OUT} ({OUT.stat().st_size:,} bytes)')


if __name__ == '__main__':
    main()
