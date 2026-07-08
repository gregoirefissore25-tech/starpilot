# ⭐ StarPilot

**Your Claude finds, ranks and integrates the best open source tool for the job. Automatically.**

StarPilot is a [Claude Skill](https://docs.claude.com) that turns Claude into a build-vs-reuse reflex machine. Before writing anything non-trivial from scratch, Claude checks whether a well-maintained, battle-tested open source library already does the job (GitHub, npm or crates.io, whichever fits the ecosystem), then installs it and keeps working. No prompt needed.

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
2. **Searches** the right source for the job, ranks candidates by weighted score
3. **Selects** the winner (license check, overkill check, relevance floor)
4. **Integrates** immediately: `pip install`, `npm install` or shallow clone, runs a smoke test, falls back to #2 if it breaks
5. **Continues your task** with the tool in place, telling you in one line what it picked and why

## Ecosystem-aware scoring

GitHub stars are a biased signal for ecosystems that have their own registry with real usage numbers, a library can be massively used in production and never get starred. StarPilot picks the source that actually reflects adoption:

| `--language` | Source | Metric |
|---|---|---|
| `javascript` / `typescript` | npm | real weekly downloads |
| `rust` | crates.io | total downloads |
| anything else | GitHub | stars |

Force a specific source with `--registry {auto,github,npm,crates}`.

## Built to keep working

- **Higher GitHub quota, automatically.** Unauthenticated search is capped at 60 requests/hour. Set `GITHUB_TOKEN` (or `GH_TOKEN`), or just have the `gh` CLI authenticated, and StarPilot picks it up on its own for a 5000/hour quota.
- **Transient network errors** (timeout, brief outage, 5xx) are retried with backoff, invisibly.
- **If npm or crates.io is unreachable** (restricted network), StarPilot falls back to GitHub silently and tells you why on stderr.
- **If nothing is reachable at all**, it fails with a clear, structured error instead of a raw stack trace, so the calling agent can propose a well-known library from general knowledge (flagged as unverified) instead of getting stuck.

## Install

Download [`starpilot.skill`](../../releases/latest) and upload it in Claude → Settings → Capabilities → Skills. Or grab the folder and zip `SKILL.md` + `scripts/` yourself.

## Use it standalone

The scoring engine works outside Claude too:

```bash
python3 scripts/find_best_repo.py "backtesting" --language python --top 5
```

```json
{
  "source": "github",
  "results": [
    {
      "full_name": "hummingbot/hummingbot",
      "metric": "github_stars",
      "stars": 19090,
      "score": 19090,
      "last_push_months_ago": 0.2,
      "license": "Apache-2.0"
    }
  ]
}
```

No API key required by default (60 unauthenticated GitHub requests/hour, plenty for the use case). Set `GITHUB_TOKEN` for 5000/hour, or point `--language` at `javascript`/`typescript`/`rust` to use npm/crates.io instead, which have no such cap.

## Philosophy

StarPilot is not a destination, it's an accelerator. One search per need, one line of justification, then back to work. It never overrides a library you already chose.

---

## 🇫🇷 En bref

StarPilot est un skill Claude qui détecte automatiquement le meilleur outil pour la tâche en cours (score = métrique d'adoption pondérée par la fraîcheur de maintenance), l'installe et continue le travail. Zéro prompt, zéro repo zombie. Il interroge la source la plus pertinente par écosystème (npm pour JS/TS, crates.io pour Rust, GitHub sinon), avec repli automatique si une source est injoignable.

## License

MIT
