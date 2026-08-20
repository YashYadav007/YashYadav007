from __future__ import annotations

import datetime as dt
import json
import math
import os
import subprocess
import urllib.request
from collections import Counter
from pathlib import Path

USER = "YashYadav007"
DAYS = 365
CELL = 12
GAP = 4
STEP = CELL + GAP
COLS = 53
ROWS = 7
DURATION = 24.0
OUT = Path("dist")


def today_ist() -> dt.date:
    return (dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=5, minutes=30)).date()


def git_counts(repo: str, start: dt.date, end: dt.date) -> Counter[str]:
    p = subprocess.run(
        ["git", "-C", repo, "log", "--all", "--pretty=%cI"],
        text=True,
        capture_output=True,
        check=True,
    )
    counts: Counter[str] = Counter()
    for line in p.stdout.splitlines():
        if not line.strip():
            continue
        try:
            d = dt.datetime.fromisoformat(line.strip().replace("Z", "+00:00")).date()
        except ValueError:
            continue
        if start <= d <= end:
            counts[d.isoformat()] += 1
    return counts


def graphql_counts(start: dt.date, end: dt.date) -> Counter[str]:
    token = os.getenv("SNAKE_TOKEN", "").strip()
    if not token:
        return Counter()
    query = """
    query($login:String!, $from:DateTime!, $to:DateTime!) {
      user(login:$login) {
        contributionsCollection(from:$from, to:$to) {
          contributionCalendar {
            weeks {
              contributionDays { date contributionCount }
            }
          }
        }
      }
    }
    """
    payload = json.dumps({
        "query": query,
        "variables": {
            "login": USER,
            "from": f"{start.isoformat()}T00:00:00+05:30",
            "to": f"{end.isoformat()}T23:59:59+05:30",
        },
    }).encode()
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=payload,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "YashYadav007-profile-snake",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.load(r)
        weeks = data["data"]["user"]["contributionsCollection"]["contributionCalendar"]["weeks"]
        c: Counter[str] = Counter()
        for w in weeks:
            for day in w["contributionDays"]:
                if start.isoformat() <= day["date"] <= end.isoformat():
                    c[day["date"]] = int(day["contributionCount"])
        return c
    except Exception as e:
        print(f"GraphQL contribution fetch failed: {e}")
        return Counter()


def level(count: int, max_count: int) -> int:
    if count <= 0:
        return 0
    if max_count <= 1:
        return 4
    ratio = math.log1p(count) / math.log1p(max_count)
    if ratio <= 0.25:
        return 1
    if ratio <= 0.5:
        return 2
    if ratio <= 0.75:
        return 3
    return 4


def grid_dates(end: dt.date):
    # GitHub-like rolling calendar: 53 weeks ending in the current week.
    start = end - dt.timedelta(days=DAYS - 1)
    start -= dt.timedelta(days=(start.weekday() + 1) % 7)  # previous Sunday
    cells = []
    for col in range(COLS):
        for row in range(ROWS):
            d = start + dt.timedelta(days=col * 7 + row)
            cells.append((col, row, d))
    return cells


def snake_path_points():
    pts = []
    # Traverse rows in a serpentine path; every grid cell is visited once.
    for row in range(ROWS):
        xs = range(COLS) if row % 2 == 0 else range(COLS - 1, -1, -1)
        for col in xs:
            x = col * STEP + CELL / 2
            y = row * STEP + CELL / 2
            pts.append((x, y, col, row))
    return pts


def build_svg(counts: Counter[str], end: dt.date, dark: bool) -> str:
    colors = ["#161b22", "#0e4429", "#006d32", "#26a641", "#39d353"] if dark else ["#ebedf0", "#9be9a8", "#40c463", "#30a14e", "#216e39"]
    border = "#30363d" if dark else "#d0d7de"
    snake = "#a78bfa" if dark else "#7c3aed"
    text = "#8b949e" if dark else "#57606a"
    cells = grid_dates(end)
    max_count = max(counts.values(), default=1)
    path_pts = snake_path_points()
    visit_index = {(c, r): i for i, (_, _, c, r) in enumerate(path_pts)}
    path_d = " ".join(("M" if i == 0 else "L") + f"{x:.1f},{y:.1f}" for i, (x, y, _, _) in enumerate(path_pts))
    width = COLS * STEP - GAP
    grid_h = ROWS * STEP - GAP
    height = grid_h + 52

    out = [
        f'<svg viewBox="-2 -24 {width+4} {height+26}" width="{width}" height="{height}" xmlns="http://www.w3.org/2000/svg">',
        '<desc>Rolling 365-day contribution snake generated from GitHub data and repository commit history.</desc>',
        f'<rect x="0" y="0" width="{width}" height="{grid_h}" rx="8" fill="none"/>',
    ]

    for col, row, d in cells:
        key = d.isoformat()
        cnt = counts.get(key, 0) if d <= end else 0
        lev = level(cnt, max_count)
        x, y = col * STEP, row * STEP
        fill = colors[lev]
        out.append(f'<rect x="{x}" y="{y}" width="{CELL}" height="{CELL}" rx="2" fill="{fill}" stroke="{border}" stroke-width="0.5">')
        if cnt > 0 and d <= end:
            idx = visit_index[(col, row)]
            p = max(0.001, min(0.999, idx / (len(path_pts) - 1)))
            out.append(f'<animate attributeName="fill" values="{fill};{colors[0]}" keyTimes="0;{p:.5f}" calcMode="discrete" dur="{DURATION}s" repeatCount="indefinite"/>')
        out.append('</rect>')

    # Four-segment snake, offset along the same path.
    for n, opacity in enumerate((1.0, 0.88, 0.72, 0.56)):
        begin = -n * (DURATION / len(path_pts))
        out.append(f'<rect x="{-CELL/2}" y="{-CELL/2}" width="{CELL}" height="{CELL}" rx="3" fill="{snake}" opacity="{opacity}">')
        out.append(f'<animateMotion dur="{DURATION}s" begin="{begin:.4f}s" repeatCount="indefinite" path="{path_d}"/>')
        out.append('</rect>')

    start_real = end - dt.timedelta(days=DAYS - 1)
    total = sum(v for k, v in counts.items() if start_real.isoformat() <= k <= end.isoformat())
    out.append(f'<text x="0" y="{grid_h + 30}" fill="{text}" font-family="ui-monospace,SFMono-Regular,Menlo,monospace" font-size="13">{start_real.strftime("%b %Y")} → {end.strftime("%b %Y")} · {total} contributions · updates daily</text>')
    out.append('</svg>')
    return "".join(out)


def main():
    end = today_ist()
    start = end - dt.timedelta(days=DAYS - 1)

    # GraphQL gives the official profile calendar when available.
    official = graphql_counts(start, end)
    # The synthetic/public gitContribution history is merged as a fallback so
    # the profile snake never collapses to an almost-empty calendar.
    local = git_counts("gitContribution", start, end)

    merged: Counter[str] = Counter()
    for d in set(official) | set(local):
        merged[d] = max(official.get(d, 0), local.get(d, 0))

    print(f"Rolling window: {start} -> {end}")
    print(f"GraphQL total: {sum(official.values())}")
    print(f"gitContribution total: {sum(local.values())}")
    print(f"Rendered total: {sum(merged.values())}")

    OUT.mkdir(exist_ok=True)
    (OUT / "github-snake.svg").write_text(build_svg(merged, end, False), encoding="utf-8")
    (OUT / "github-snake-dark.svg").write_text(build_svg(merged, end, True), encoding="utf-8")


if __name__ == "__main__":
    main()
