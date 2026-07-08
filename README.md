# ⭐ StarPilot

**Your Claude finds, ranks and integrates the best GitHub repos. Automatically.**

StarPilot is a [Claude Skill](https://docs.claude.com) that turns Claude into a build-vs-reuse reflex machine. Before writing anything non-trivial from scratch, Claude checks whether a well-maintained, battle-tested open source repo already does the job, then installs it and keeps working. No prompt needed.

## Why

GitHub stars lie. A 50k-star repo abandoned three years ago will outrank an 8k-star repo pushed last week on every naive search. StarPilot fixes this with freshness-weighted scoring:

```
score = stars × freshness_factor(last_push)
```

| Last push | Factor |
|---|---|
| < 1 month | ×1.0 |
| < 6 months | ×0.9 |
| < 12 months | ×0.7 |
| < 24 months | ×0.4 |
| older | ×0.15 |

Archived repos are excluded. Licenses are checked (MIT/Apache/BSD preferred, GPL flagged for closed commercial projects).

## What it does

1. **Auto-triggers** on any coding, automation, data, scraping, UI, parsing or API task where an existing library could help
2. **Searches** the GitHub API, ranks candidates by weighted score
3. **Selects** the winner (license check, overkill check, relevance floor)
4. **Integrates** immediately: `pip install`, `npm install` or shallow clone, runs a smoke test, falls back to #2 if it breaks
5. **Continues your task** with the tool in place, telling you in one line what it picked and why

## Install

Download [`starpilot.skill`](../../releases/latest) and upload it in Claude → Settings → Capabilities → Skills. Or grab the folder and zip `SKILL.md` + `scripts/` yourself.

## Use it standalone

The scoring engine works outside Claude too:

```bash
python3 scripts/find_best_repo.py "backtesting" --language python --top 5
```

```json
[
  {
    "full_name": "hummingbot/hummingbot",
    "stars": 19090,
    "score": 19090,
    "last_push_months_ago": 0.2,
    "license": "Apache-2.0"
  }
]
```

No API key required (60 unauthenticated requests/hour, plenty for the use case).

## Philosophy

StarPilot is not a destination, it's an accelerator. One search per need, one line of justification, then back to work. It never overrides a library you already chose.

---

## 🇫🇷 En bref

StarPilot est un skill Claude qui détecte automatiquement le meilleur repo GitHub pour la tâche en cours (score = étoiles pondérées par la fraîcheur de maintenance), l'installe et continue le travail. Zéro prompt, zéro repo zombie.

## License

MIT
