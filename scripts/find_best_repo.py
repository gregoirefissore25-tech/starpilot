#!/usr/bin/env python3
"""
find_best_repo.py - Trouve les meilleurs repos GitHub pour un besoin donne.

Usage:
    python3 find_best_repo.py "pdf parsing" --language python --top 5
    python3 find_best_repo.py "swipe ui component" --language javascript
    python3 find_best_repo.py "backtesting trading" --min-stars 500

Score = etoiles ponderees par la fraicheur de maintenance.
Un repo a 50k etoiles abandonne depuis 3 ans peut perdre face
a un repo a 8k etoiles pousse la semaine derniere.
"""

import argparse
import json
import sys
import urllib.request
from datetime import datetime, timezone

API = "https://api.github.com/search/repositories"


def months_since(iso_date: str) -> float:
    dt = datetime.fromisoformat(iso_date.replace("Z", "+00:00"))
    return (datetime.now(timezone.utc) - dt).days / 30.44


def freshness_factor(months: float) -> float:
    """1.0 si pousse ce mois-ci, decroit ensuite. Plancher a 0.15."""
    if months <= 1:
        return 1.0
    if months <= 6:
        return 0.9
    if months <= 12:
        return 0.7
    if months <= 24:
        return 0.4
    return 0.15


def search(query: str, language: str | None, min_stars: int, top: int):
    q = query
    if language:
        q += f" language:{language}"
    if min_stars:
        q += f" stars:>={min_stars}"
    url = f"{API}?q={urllib.parse.quote(q)}&sort=stars&order=desc&per_page={max(top * 3, 15)}"
    req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json",
                                               "User-Agent": "claude-skill-github-autopilot"})
    with urllib.request.urlopen(req, timeout=20) as r:
        data = json.load(r)

    results = []
    for item in data.get("items", []):
        months = months_since(item["pushed_at"])
        score = item["stargazers_count"] * freshness_factor(months)
        results.append({
            "full_name": item["full_name"],
            "stars": item["stargazers_count"],
            "score": round(score),
            "last_push_months_ago": round(months, 1),
            "license": (item.get("license") or {}).get("spdx_id", "NONE"),
            "language": item.get("language"),
            "description": (item.get("description") or "")[:140],
            "clone_url": item["clone_url"],
            "html_url": item["html_url"],
            "archived": item.get("archived", False),
        })

    # Exclure les repos archives, trier par score
    results = [r for r in results if not r["archived"]]
    results.sort(key=lambda r: r["score"], reverse=True)
    return results[:top]


if __name__ == "__main__":
    import urllib.parse
    p = argparse.ArgumentParser()
    p.add_argument("query")
    p.add_argument("--language", default=None)
    p.add_argument("--min-stars", type=int, default=0)
    p.add_argument("--top", type=int, default=5)
    args = p.parse_args()

    try:
        results = search(args.query, args.language, args.min_stars, args.top)
    except Exception as e:
        print(json.dumps({"error": str(e)}), file=sys.stderr)
        sys.exit(1)

    print(json.dumps(results, indent=2, ensure_ascii=False))
