#!/usr/bin/env python3
"""
Fetches real GitHub data for GITHUB_USER via the GraphQL API and regenerates
stats.svg, langs.svg, trophies.svg and streak.svg in place, using the same
animated, self-hosted SVG style as the rest of the profile.

Requires a PAT with `read:user` scope in the PAT_GITHUB secret/env var —
the default Actions GITHUB_TOKEN cannot read another account's personal
contribution data via the `viewer` field, so a personal token is required.
See the comment block in .github/workflows/update-stats.yml for setup.
"""
import os
import sys
import json
import datetime
import urllib.request

GITHUB_USER = os.environ.get("GITHUB_USER", "Piyush1gupta")
TOKEN = os.environ.get("PAT_GITHUB") or os.environ.get("GITHUB_TOKEN")
OUT_DIR = os.environ.get("OUT_DIR", ".")

if not TOKEN:
    print("No token found (PAT_GITHUB / GITHUB_TOKEN). Skipping live update.", file=sys.stderr)
    sys.exit(0)

BG1, BG2 = "#000000", "#0b1530"
PINK, PINK2, PURPLE, PURPLE2 = "#2f8dff", "#7fc4ff", "#1e4fd6", "#123a9c"
TEXT, DIM, FAINT = "#eaf2ff", "#a9c0e6", "#5b78a8"
CARD_BORDER = "#20335f"
TRACK = "#101d3d"

COMMON_DEFS = f'''
  <linearGradient id="bgGrad" x1="0%" y1="0%" x2="100%" y2="100%">
    <stop offset="0%" stop-color="{BG1}"/><stop offset="100%" stop-color="{BG2}"/>
  </linearGradient>
  <linearGradient id="barGrad" x1="0%" y1="0%" x2="100%" y2="0%">
    <stop offset="0%" stop-color="{PINK}"/><stop offset="100%" stop-color="{PURPLE}"/>
  </linearGradient>
  <linearGradient id="ringGrad" x1="0%" y1="0%" x2="100%" y2="100%">
    <stop offset="0%" stop-color="{PINK}"/><stop offset="100%" stop-color="{PURPLE}"/>
  </linearGradient>
  <filter id="glow" x="-60%" y="-60%" width="220%" height="220%">
    <feGaussianBlur stdDeviation="4" result="b"/>
    <feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>
  </filter>
'''

COMMON_STYLE = f'''
  .slideIn {{ opacity: 0; animation: slideInA 0.6s ease forwards; }}
  @keyframes slideInA {{ from {{ opacity:0; transform: translateX(-16px);}} to {{ opacity:1; transform: translateX(0);}} }}
  .popIn {{ opacity: 0; animation: popA 0.55s cubic-bezier(.2,1.4,.4,1) forwards; }}
  @keyframes popA {{ 0%{{opacity:0; transform:scale(.4);}} 70%{{opacity:1; transform:scale(1.08);}} 100%{{opacity:1; transform:scale(1);}} }}
  .fadeIn {{ opacity: 0; animation: fadeA 0.7s ease forwards; }}
  @keyframes fadeA {{ to {{ opacity:1; }} }}
'''


def esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def card_shell(w, h, title):
    return (
        f'<rect x="1" y="1" width="{w-2}" height="{h-2}" rx="16" fill="url(#bgGrad)" '
        f'stroke="{CARD_BORDER}" stroke-width="1.4"/>\n'
        f'<text x="24" y="34" font-family="Verdana, Geneva, sans-serif" font-size="16" font-weight="700" '
        f'fill="{TEXT}" class="fadeIn">{esc(title)}</text>'
    )


def gh_graphql(query, variables=None):
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": query, "variables": variables or {}}).encode(),
        headers={
            "Authorization": f"bearer {TOKEN}",
            "Content-Type": "application/json",
            "User-Agent": GITHUB_USER,
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


QUERY = '''
query($login: String!) {
  user(login: $login) {
    followers { totalCount }
    contributionsCollection {
      totalCommitContributions
      totalPullRequestContributions
      totalIssueContributions
      totalRepositoriesWithContributedCommits
      contributionCalendar {
        weeks { contributionDays { date contributionCount } }
      }
    }
    repositories(first: 100, ownerAffiliations: OWNER, isFork: false, privacy: PUBLIC) {
      totalCount
      nodes {
        stargazers { totalCount }
        languages(first: 10, orderBy: {field: SIZE, direction: DESC}) {
          edges { size node { name color } }
        }
      }
    }
  }
}
'''


def fetch():
    data = gh_graphql(QUERY, {"login": GITHUB_USER})
    if "errors" in data:
        print("GraphQL errors:", data["errors"], file=sys.stderr)
        sys.exit(0)
    return data["data"]["user"]


def compute_streaks(weeks):
    days = []
    for w in weeks:
        for d in w["contributionDays"]:
            days.append((d["date"], d["contributionCount"]))
    days.sort()
    longest = cur = 0
    best = 0
    for _, count in days:
        if count > 0:
            cur += 1
            best = max(best, cur)
        else:
            cur = 0
    # current streak = trailing run ending today (or yesterday, to allow for timezone lag)
    current = 0
    for _, count in reversed(days):
        if count > 0:
            current += 1
        else:
            break
    total = sum(c for _, c in days)
    return current, best, total


def rank(value, thresholds):
    # thresholds: list of (min_value, label) sorted descending by min_value
    for minval, label in thresholds:
        if value >= minval:
            return label
    return thresholds[-1][1]


def gen_stats(user):
    stars = sum(r["stargazers"]["totalCount"] for r in user["repositories"]["nodes"])
    cc = user["contributionsCollection"]
    stats = [
        ("Total Stars", stars),
        ("Total Commits (last year)", cc["totalCommitContributions"]),
        ("Total PRs", cc["totalPullRequestContributions"]),
        ("Total Issues", cc["totalIssueContributions"]),
        ("Contributed to", cc["totalRepositoriesWithContributedCommits"]),
    ]
    score = min(100, stars * 2 + cc["totalCommitContributions"] * 0.1 + cc["totalPullRequestContributions"] * 1.5)
    grade = rank(score, [(85, "A+"), (70, "A"), (55, "B+"), (40, "B"), (25, "C+"), (0, "C")])

    W, H = 440, 190
    import math
    r = 42
    circumference = 2 * math.pi * r
    rows, ry = [], 58
    for i, (label, val) in enumerate(stats):
        delay = 0.5 + i * 0.15
        rows.append(f'''
    <g transform="translate(24,{ry})">
    <g class="slideIn" style="animation-delay:{delay:.2f}s">
      <circle cx="0" cy="-5" r="3.4" fill="url(#barGrad)"/>
      <text x="14" y="0" font-family="Verdana, sans-serif" font-size="13" fill="{DIM}">{esc(label)}</text>
      <text x="255" y="0" text-anchor="end" font-family="Verdana, sans-serif" font-size="13" font-weight="700" fill="{TEXT}">{val}</text>
    </g>
    </g>''')
        ry += 26

    svg = f'''<svg width="{W}" height="{H}" viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="{GITHUB_USER} GitHub stats">
<title>GitHub Stats - {GITHUB_USER}</title>
<defs>{COMMON_DEFS}</defs>
<style>{COMMON_STYLE}</style>
{card_shell(W, H, "GitHub Stats (live)")}
{''.join(rows)}
<g transform="translate({W-98},{H/2+6})">
  <circle r="{r}" fill="none" stroke="{TRACK}" stroke-width="9"/>
  <circle r="{r}" fill="none" stroke="url(#ringGrad)" stroke-width="9" stroke-linecap="round"
    stroke-dasharray="{circumference:.1f}" stroke-dashoffset="{circumference:.1f}" filter="url(#glow)"
    transform="rotate(-90)">
    <animate attributeName="stroke-dashoffset" from="{circumference:.1f}" to="{circumference*(1-score/100):.1f}"
      dur="1.6s" begin="0.4s" fill="freeze" calcMode="spline" keySplines="0.2 0.8 0.2 1" keyTimes="0;1"/>
  </circle>
  <text x="0" y="-2" text-anchor="middle" font-family="Verdana, sans-serif" font-size="20" font-weight="700" fill="{TEXT}" class="fadeIn" style="animation-delay:1.6s">{grade}</text>
  <text x="0" y="16" text-anchor="middle" font-family="Verdana, sans-serif" font-size="9.5" fill="{FAINT}" class="fadeIn" style="animation-delay:1.6s">RANK</text>
</g>
</svg>'''
    open(os.path.join(OUT_DIR, "stats.svg"), "w").write(svg)
    return stats, stars, grade


def gen_langs(user):
    totals = {}
    for repo in user["repositories"]["nodes"]:
        for edge in repo["languages"]["edges"]:
            name = edge["node"]["name"]
            totals[name] = totals.get(name, {"size": 0, "color": edge["node"]["color"] or DIM})
            totals[name]["size"] += edge["size"]
    total_size = sum(v["size"] for v in totals.values()) or 1
    top = sorted(totals.items(), key=lambda kv: -kv[1]["size"])[:5]
    langs = [(name, round(v["size"] * 100 / total_size, 1), v["color"] or DIM) for name, v in top]
    if not langs:
        langs = [("No public repos found", 0, DIM)]

    W, H = 440, 56 + len(langs) * 30 + 20
    rows, ry = [], 56
    for i, (name, pct, col) in enumerate(langs):
        bw = 300 * pct / 100
        delay = 0.4 + i * 0.15
        rows.append(f'''
    <g transform="translate(24,{ry})">
      <text y="-6" font-family="Verdana, sans-serif" font-size="12.5" fill="{DIM}">{esc(name)}</text>
      <text x="300" y="-6" text-anchor="end" font-family="Verdana, sans-serif" font-size="11.5" fill="{FAINT}">{pct}%</text>
      <rect y="0" width="300" height="8" rx="4" fill="{TRACK}"/>
      <rect y="0" width="0" height="8" rx="4" fill="{col}">
        <animate attributeName="width" values="0;{bw:.1f}" dur="1.2s" begin="{delay:.2f}s" fill="freeze"
          calcMode="spline" keySplines="0.2 0.8 0.2 1" keyTimes="0;1"/>
      </rect>
    </g>''')
        ry += 30

    svg = f'''<svg width="{W}" height="{H}" viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="{GITHUB_USER} most used languages">
<title>Most Used Languages - {GITHUB_USER}</title>
<defs>{COMMON_DEFS}</defs>
<style>{COMMON_STYLE}</style>
{card_shell(W, H, "Most Used Languages (live)")}
{''.join(rows)}
</svg>'''
    open(os.path.join(OUT_DIR, "langs.svg"), "w").write(svg)


def gen_streak(current, longest, total):
    W, H = 440, 150
    cols = [("Current Streak", current), ("Longest Streak", longest), ("Total Contributions", total)]
    cells = []
    cw = (W - 48) / 3
    for i, (label, val) in enumerate(cols):
        cx = 24 + i * cw
        delay = 0.4 + i * 0.18
        cells.append(f'''
    <g transform="translate({cx:.1f},58)">
    <g class="popIn" style="animation-delay:{delay:.2f}s">
      <text x="{cw/2-12:.1f}" y="0" text-anchor="middle" font-family="Verdana, sans-serif" font-size="26" font-weight="700" fill="url(#ringGrad)" filter="url(#glow)">{val}</text>
      <text x="{cw/2-12:.1f}" y="24" text-anchor="middle" font-family="Verdana, sans-serif" font-size="11" fill="{DIM}">{esc(label)}</text>
    </g>
    </g>''')
    dividers = "".join(
        f'<line x1="{24+cw*i-6:.1f}" y1="30" x2="{24+cw*i-6:.1f}" y2="100" stroke="{CARD_BORDER}" stroke-width="1"/>'
        for i in (1, 2)
    )
    svg = f'''<svg width="{W}" height="{H}" viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="{GITHUB_USER} contribution streak">
<title>Contribution Streak - {GITHUB_USER}</title>
<defs>{COMMON_DEFS}</defs>
<style>{COMMON_STYLE}</style>
{card_shell(W, H, "Contribution Streak (live)")}
{dividers}
{''.join(cells)}
</svg>'''
    open(os.path.join(OUT_DIR, "streak.svg"), "w").write(svg)


def gen_trophies(stars, cc, followers):
    trophies = [
        ("Stars", stars, [(50, "A+"), (25, "A"), (10, "B+"), (3, "B"), (1, "C+"), (0, "C")]),
        ("Commits", cc["totalCommitContributions"], [(1000, "A+"), (500, "A"), (200, "B+"), (50, "B"), (10, "C+"), (0, "C")]),
        ("PRs", cc["totalPullRequestContributions"], [(50, "A+"), (25, "A"), (10, "B+"), (3, "B"), (1, "C+"), (0, "C")]),
        ("Issues", cc["totalIssueContributions"], [(30, "A+"), (15, "A"), (6, "B+"), (2, "B"), (1, "C+"), (0, "C")]),
        ("Repositories", None, None),
        ("Followers", followers, [(100, "A+"), (50, "A"), (20, "B+"), (5, "B"), (1, "C+"), (0, "C")]),
    ]

    W, H = 700, 220
    cell_w, gap = 104, 12
    total_w = len(trophies) * cell_w + (len(trophies) - 1) * gap
    start_x = (W - total_w) / 2
    cells, shine_defs = [], []
    for i, (label, val, thresholds) in enumerate(trophies):
        rank_label = rank(val, thresholds) if thresholds else "—"
        x = start_x + i * (cell_w + gap)
        delay = 0.3 + i * 0.14
        shine_defs.append(
            f'<linearGradient id="shine{i}" x1="0%" y1="0%" x2="100%" y2="100%">'
            f'<stop offset="0%" stop-color="#fff" stop-opacity="0"/>'
            f'<stop offset="50%" stop-color="#fff" stop-opacity="0.35"/>'
            f'<stop offset="100%" stop-color="#fff" stop-opacity="0"/></linearGradient>'
        )
        cells.append(f'''
    <g transform="translate({x:.1f},60)">
    <g class="popIn" style="animation-delay:{delay:.2f}s">
      <rect width="{cell_w}" height="130" rx="14" fill="{BG2}" stroke="{CARD_BORDER}" stroke-width="1.2"/>
      <clipPath id="tclip{i}"><rect width="{cell_w}" height="130" rx="14"/></clipPath>
      <g clip-path="url(#tclip{i})">
        <rect x="-40" y="0" width="30" height="140" fill="url(#shine{i})" transform="skewX(-18)">
          <animate attributeName="x" values="-40;{cell_w+40}" dur="2.6s" begin="{1.4+i*0.15:.2f}s" repeatCount="indefinite"/>
        </rect>
      </g>
      <text x="{cell_w/2}" y="46" text-anchor="middle" font-family="Verdana, sans-serif" font-size="22" font-weight="700" fill="url(#ringGrad)" filter="url(#glow)">{rank_label}</text>
      <text x="{cell_w/2}" y="78" text-anchor="middle" font-family="Verdana, sans-serif" font-size="11.5" fill="{TEXT}">{esc(label)}</text>
      <circle cx="{cell_w/2}" cy="104" r="14" fill="none" stroke="url(#ringGrad)" stroke-width="2.4" opacity="0.7"/>
    </g>
    </g>''')

    svg = f'''<svg width="{W}" height="{H}" viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="{GITHUB_USER} GitHub trophies">
<title>GitHub Trophies - {GITHUB_USER}</title>
<defs>{COMMON_DEFS}{"".join(shine_defs)}</defs>
<style>{COMMON_STYLE}</style>
{card_shell(W, H, "Trophy Case (live)")}
{''.join(cells)}
</svg>'''
    open(os.path.join(OUT_DIR, "trophies.svg"), "w").write(svg)


def main():
    user = fetch()
    stats, stars, grade = gen_stats(user)
    gen_langs(user)
    weeks = user["contributionsCollection"]["contributionCalendar"]["weeks"]
    current, longest, total = compute_streaks(weeks)
    gen_streak(current, longest, total)
    gen_trophies(stars, user["contributionsCollection"], user["followers"]["totalCount"])
    print(f"Updated stats.svg / langs.svg / streak.svg / trophies.svg for {GITHUB_USER} "
          f"(stars={stars}, rank={grade}, streak={current}/{longest})")


if __name__ == "__main__":
    main()
