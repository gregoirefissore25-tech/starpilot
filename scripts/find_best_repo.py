#!/usr/bin/env python3
"""
find_best_repo.py - Trouve le meilleur outil (repo GitHub ou paquet de
l'ecosysteme natif) pour un besoin donne.

Usage:
    python3 find_best_repo.py "pdf parsing" --language python --top 5
    python3 find_best_repo.py "swipe ui component" --language javascript
    python3 find_best_repo.py "date formatting" --language rust
    python3 find_best_repo.py "backtesting trading" --min-stars 500
    python3 find_best_repo.py "http client" --registry npm --top 3
    python3 find_best_repo.py "date formatting" --auto   # detecte le langage/gestionnaire du projet en cours

Score = metrique d'adoption ponderee par la fraicheur de maintenance.
Un repo a 50k etoiles abandonne depuis 3 ans peut perdre face
a un repo a 8k etoiles pousse la semaine derniere.

Adaptation par ecosysteme : GitHub (etoiles) est la source par defaut,
mais npm (telechargements hebdo) et crates.io (telechargements totaux)
sont des signaux d'adoption plus fiables que les etoiles pour leurs
ecosystemes respectifs (une etoile ne veut pas dire "utilise en prod").
--language javascript/typescript/node -> npm ; --language rust -> crates.io ;
tout le reste -> GitHub. Forcer avec --registry {auto,github,npm,crates}.

Resilience ("marcher dans n'importe quelle condition") :
- Jeton GitHub optionnel (env GITHUB_TOKEN ou GH_TOKEN, ou `gh auth token`
  si le CLI gh est authentifie) : fait passer le quota de 60 a 5000 req/h.
- Nouvelles tentatives automatiques (avec delai croissant) sur les erreurs
  reseau transitoires (timeout, coupure, 5xx) ; jamais sur les erreurs
  definitives (quota depasse, requete invalide).
- Si la source native de l'ecosysteme (npm/crates) est injoignable
  (reseau restreint, domaine bloque), repli silencieux et signale sur
  GitHub, qui reste la source universelle.
- Si meme GitHub est injoignable, erreur structuree et explicite
  (pas de trace Python brute) pour que l'appelant sache exactement quoi
  faire : proposer une librairie connue en le signalant comme non verifie,
  plutot que de bloquer la tache en cours.
"""

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

GITHUB_API = "https://api.github.com/search/repositories"
NPM_API = "https://registry.npmjs.org/-/v1/search"
NPM_DOWNLOADS_API = "https://api.npmjs.org/downloads/point/last-week"
CRATES_API = "https://crates.io/api/v1/crates"

USER_AGENT = "claude-skill-starpilot"


class RateLimitError(Exception):
    """Quota de l'API depasse (source et delai d'attente inclus dans le message)."""


class SourceUnavailableError(Exception):
    """Source d'un ecosysteme injoignable (reseau, DNS, timeout, 5xx persistant)."""

    def __init__(self, source: str, reason: str):
        self.source = source
        self.reason = reason
        super().__init__(f"{source} indisponible : {reason}")


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


def github_token() -> str | None:
    """Jeton optionnel pour passer de 60 a 5000 requetes/heure.
    Cherche GITHUB_TOKEN, GH_TOKEN, puis `gh auth token` si le CLI est present."""
    tok = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if tok:
        return tok.strip()
    try:
        import subprocess
        out = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True, timeout=3)
        if out.returncode == 0 and out.stdout.strip():
            return out.stdout.strip()
    except Exception:
        pass
    return None


def fetch_json(url: str, source: str, headers: dict, retries: int = 2, timeout: int = 20):
    """GET JSON avec nouvelles tentatives sur erreurs transitoires uniquement.
    Leve RateLimitError (definitif, GitHub) ou SourceUnavailableError (reseau/5xx persistant)."""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, **headers})
    delay = 0.6
    last_reason = "raison inconnue"
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code == 403 and source == "github" and e.headers and e.headers.get("X-RateLimit-Remaining") == "0":
                reset = e.headers.get("X-RateLimit-Reset")
                wait_s = max(0, int(reset) - int(datetime.now(timezone.utc).timestamp())) if reset else None
                msg = "Quota GitHub API depasse (60 requetes/heure sans jeton, 5000 avec)."
                if wait_s is not None:
                    msg += f" Reessayer dans ~{wait_s // 60} min, ou definir GITHUB_TOKEN."
                else:
                    msg += " Definir GITHUB_TOKEN pour un quota plus large."
                raise RateLimitError(msg) from e
            if e.code >= 500 and attempt < retries:
                last_reason = f"HTTP {e.code}"
                time.sleep(delay); delay *= 2.5
                continue
            raise SourceUnavailableError(source, f"HTTP {e.code} {e.reason}") from e
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            if attempt < retries:
                last_reason = str(getattr(e, "reason", e)) or str(e)
                time.sleep(delay); delay *= 2.5
                continue
            raise SourceUnavailableError(source, str(getattr(e, "reason", e)) or str(e)) from e
    # Ne devrait pas etre atteint (la derniere iteration leve toujours), filet de securite :
    raise SourceUnavailableError(source, last_reason)


def search_github(query: str, language: str | None, min_stars: int, top: int):
    q = query
    if language:
        q += f" language:{language}"
    if min_stars:
        q += f" stars:>={min_stars}"
    url = f"{GITHUB_API}?q={urllib.parse.quote(q)}&sort=stars&order=desc&per_page={max(top * 4, 20)}"
    headers = {"Accept": "application/vnd.github+json"}
    token = github_token()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = fetch_json(url, "github", headers)

    results = []
    for item in data.get("items", []):
        if item.get("archived"):
            continue
        months = months_since(item["pushed_at"])
        stars = item["stargazers_count"]
        results.append({
            "full_name": item["full_name"],
            "metric": "github_stars",
            "stars": stars,
            "score": round(stars * freshness_factor(months)),
            "last_push_months_ago": round(months, 1),
            "license": (item.get("license") or {}).get("spdx_id", "NONE"),
            "language": item.get("language"),
            "description": (item.get("description") or "")[:140],
            "clone_url": item["clone_url"],
            "html_url": item["html_url"],
            "archived": False,
            "source": "github",
        })
    results.sort(key=lambda r: r["score"], reverse=True)
    return results[:top]


def npm_weekly_downloads(names: list[str]) -> dict:
    """Vrais telechargements hebdo (nombre absolu), pas un score relatif.
    L'API bulk ne supporte pas les paquets scopes (@scope/nom) : ils sont
    recuperes individuellement. Un paquet introuvable vaut 0 (jamais un echec
    global : voir le test empirique en commentaire de fetch_json)."""
    unscoped = [n for n in names if not n.startswith("@")]
    scoped = [n for n in names if n.startswith("@")]
    out = {}
    if unscoped:
        url = f"{NPM_DOWNLOADS_API}/{','.join(urllib.parse.quote(n, safe='') for n in unscoped)}"
        try:
            data = fetch_json(url, "npm", {"Accept": "application/json"})
            if isinstance(data, dict) and "downloads" in data and len(unscoped) == 1:
                data = {unscoped[0]: data}
            for n in unscoped:
                v = data.get(n) if isinstance(data, dict) else None
                out[n] = (v or {}).get("downloads", 0)
        except SourceUnavailableError:
            for n in unscoped:
                out[n] = 0
    for n in scoped:
        try:
            v = fetch_json(f"{NPM_DOWNLOADS_API}/{urllib.parse.quote(n, safe='')}", "npm", {"Accept": "application/json"})
            out[n] = v.get("downloads", 0) if isinstance(v, dict) else 0
        except SourceUnavailableError:
            out[n] = 0
    return out


def search_npm(query: str, min_stars: int, top: int):
    """npm : les telechargements hebdo reels sont un signal d'adoption bien
    plus fiable que des etoiles GitHub pour un paquet JS/TS : une lib peut
    etre tres utilisee en production sans jamais avoir ete "starred"."""
    url = f"{NPM_API}?text={urllib.parse.quote(query)}&size={max(top * 4, 20)}"
    data = fetch_json(url, "npm", {"Accept": "application/json"})

    candidates = []
    for obj in data.get("objects", []):
        pkg = obj.get("package", {})
        if pkg.get("name"):
            candidates.append(pkg)
    downloads = npm_weekly_downloads([p["name"] for p in candidates])

    results = []
    for pkg in candidates:
        weekly = downloads.get(pkg["name"], 0)
        if weekly < min_stars:
            continue
        date = pkg.get("date")
        months = months_since(date) if date else 999
        repo = ((pkg.get("links") or {}).get("repository")) or pkg.get("links", {}).get("npm", "")
        results.append({
            "full_name": pkg["name"],
            "metric": "npm_weekly_downloads",
            "stars": weekly,
            "score": round(weekly * freshness_factor(months)),
            "last_push_months_ago": round(months, 1),
            "license": pkg.get("license", "NONE") or "NONE",
            "language": "javascript",
            "description": (pkg.get("description") or "")[:140],
            "clone_url": repo,
            "html_url": pkg.get("links", {}).get("npm", repo),
            "archived": False,
            "source": "npm",
        })
    results.sort(key=lambda r: r["score"], reverse=True)
    return results[:top]


def search_crates(query: str, min_stars: int, top: int):
    """crates.io : le nombre de telechargements total est le signal natif
    de l'ecosysteme Rust, publie directement par le registre officiel.
    Tri par pertinence (defaut de l'API) puis re-classement par notre propre
    score : `sort=downloads` a ete teste et elargit le filtrage textuel
    (des crates hors-sujet mais tres telecharges remontent, ex. "regex"
    sur une recherche "date time"), on garde donc le tri par defaut."""
    url = f"{CRATES_API}?q={urllib.parse.quote(query)}&per_page={max(top * 4, 20)}"
    data = fetch_json(url, "crates", {"Accept": "application/json"})

    results = []
    for c in data.get("crates", []):
        downloads = c.get("downloads", 0)
        if downloads < min_stars:
            continue
        updated = c.get("updated_at")
        months = months_since(updated) if updated else 999
        repo = c.get("repository") or f"https://crates.io/crates/{c.get('name')}"
        results.append({
            "full_name": c.get("name"),
            "metric": "crates_downloads",
            "stars": downloads,
            "score": round(downloads * freshness_factor(months)),
            "last_push_months_ago": round(months, 1),
            "license": c.get("license", "NONE") or "NONE",
            "language": "rust",
            "description": (c.get("description") or "")[:140],
            "clone_url": repo,
            "html_url": f"https://crates.io/crates/{c.get('name')}",
            "archived": False,
            "source": "crates",
        })
    results.sort(key=lambda r: r["score"], reverse=True)
    return results[:top]


def _read(path: str) -> str:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except OSError:
        return ""


def _parse_json_deps(path: str, keys: tuple) -> list:
    try:
        data = json.loads(_read(path) or "{}")
    except json.JSONDecodeError:
        return []
    names = []
    for k in keys:
        names.extend((data.get(k) or {}).keys())
    return names


def _parse_requirements_txt(path: str) -> list:
    names = []
    for line in _read(path).splitlines():
        line = line.strip()
        if not line or line.startswith(("#", "-")):
            continue
        name = re.split(r"[<>=!~\[; ]", line, 1)[0].strip()
        if name:
            names.append(name)
    return names


def _parse_pyproject_toml(path: str) -> list:
    text = _read(path)
    names = []
    m = re.search(r"dependencies\s*=\s*\[(.*?)\]", text, re.S)
    if m:
        for item in re.findall(r'"([^"]*)"', m.group(1)):
            name = re.split(r"[<>=!~\[; ]", item, 1)[0].strip()
            if name:
                names.append(name)
    m = re.search(r"\[tool\.poetry\.dependencies\](.*?)(?=\n\[|\Z)", text, re.S)
    if m:
        for line in m.group(1).splitlines():
            key = line.split("=", 1)[0].strip().strip('"')
            if key and key.lower() != "python":
                names.append(key)
    return names


def _pyproject_uses_poetry(path: str) -> bool:
    return "[tool.poetry]" in _read(path)


def _parse_cargo_toml(path: str) -> list:
    text = _read(path)
    names = []
    for section in re.findall(r"\[dependencies(?:\.\S+)?\](.*?)(?=\n\[|\Z)", text, re.S):
        for line in section.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            key = line.split("=", 1)[0].strip().strip('"')
            if key:
                names.append(key)
    return names


def _parse_go_mod(path: str) -> list:
    names = []
    in_block = False
    for line in _read(path).splitlines():
        line = line.strip()
        if line.startswith("require ("):
            in_block = True
            continue
        if in_block and line == ")":
            in_block = False
            continue
        target = line[len("require "):] if (not in_block and line.startswith("require ")) else (line if in_block else "")
        parts = target.split()
        if parts:
            names.append(parts[0])
    return names


def detect_project(start_dir: str | None = None):
    """Detecte l'ecosysteme du projet EN COURS a partir de ses vrais fichiers
    de manifeste et de verrou (pas d'un --language devine), pour choisir la
    bonne source ET la commande d'installation qui correspond aux outils
    deja utilises par ce projet precis. Remonte jusqu'a 5 dossiers parents,
    au cas ou l'appel se fasse depuis un sous-dossier."""
    d = os.path.abspath(start_dir or os.getcwd())
    for _ in range(5):
        pkg_json = os.path.join(d, "package.json")
        if os.path.isfile(pkg_json):
            if os.path.isfile(os.path.join(d, "bun.lockb")):
                pm = "bun"
            elif os.path.isfile(os.path.join(d, "pnpm-lock.yaml")):
                pm = "pnpm"
            elif os.path.isfile(os.path.join(d, "yarn.lock")):
                pm = "yarn"
            else:
                pm = "npm"
            install_tpl = {"npm": "npm install {name}", "pnpm": "pnpm add {name}",
                           "yarn": "yarn add {name}", "bun": "bun add {name}"}[pm]
            lang = "typescript" if os.path.isfile(os.path.join(d, "tsconfig.json")) else "javascript"
            return {
                "language": lang, "package_manager": pm, "manifest": pkg_json,
                "install_cmd_template": install_tpl,
                "existing_dependencies": sorted(set(_parse_json_deps(pkg_json, ("dependencies", "devDependencies")))),
            }

        cargo_toml = os.path.join(d, "Cargo.toml")
        if os.path.isfile(cargo_toml):
            return {
                "language": "rust", "package_manager": "cargo", "manifest": cargo_toml,
                "install_cmd_template": "cargo add {name}",
                "existing_dependencies": sorted(set(_parse_cargo_toml(cargo_toml))),
            }

        go_mod = os.path.join(d, "go.mod")
        if os.path.isfile(go_mod):
            return {
                "language": "go", "package_manager": "go modules", "manifest": go_mod,
                "install_cmd_template": "go get {name}",
                "existing_dependencies": sorted(set(_parse_go_mod(go_mod))),
            }

        pyproject = os.path.join(d, "pyproject.toml")
        requirements = os.path.join(d, "requirements.txt")
        pipfile = os.path.join(d, "Pipfile")
        if os.path.isfile(pyproject) or os.path.isfile(requirements) or os.path.isfile(pipfile):
            deps = []
            if os.path.isfile(pyproject):
                deps += _parse_pyproject_toml(pyproject)
            if os.path.isfile(requirements):
                deps += _parse_requirements_txt(requirements)
            if os.path.isfile(os.path.join(d, "uv.lock")):
                pm = "uv"
            elif os.path.isfile(pyproject) and _pyproject_uses_poetry(pyproject):
                pm = "poetry"
            elif os.path.isfile(pipfile):
                pm = "pipenv"
            else:
                pm = "pip"
            install_tpl = {"pip": "pip install {name}", "poetry": "poetry add {name}",
                           "uv": "uv add {name}", "pipenv": "pipenv install {name}"}[pm]
            manifest = requirements if os.path.isfile(requirements) else (pyproject if os.path.isfile(pyproject) else pipfile)
            return {
                "language": "python", "package_manager": pm, "manifest": manifest,
                "install_cmd_template": install_tpl,
                "existing_dependencies": sorted(set(deps)),
            }

        composer = os.path.join(d, "composer.json")
        if os.path.isfile(composer):
            return {
                "language": "php", "package_manager": "composer", "manifest": composer,
                "install_cmd_template": "composer require {name}",
                "existing_dependencies": sorted(set(_parse_json_deps(composer, ("require", "require-dev")))),
            }

        gemfile = os.path.join(d, "Gemfile")
        if os.path.isfile(gemfile):
            return {
                "language": "ruby", "package_manager": "bundler", "manifest": gemfile,
                "install_cmd_template": "bundle add {name}",
                "existing_dependencies": [],
            }

        parent = os.path.dirname(d)
        if parent == d:
            break
        d = parent
    return None


def pick_registry(explicit: str, language: str | None) -> str:
    if explicit and explicit != "auto":
        return explicit
    lang = (language or "").lower()
    if lang in ("javascript", "typescript", "js", "ts", "node", "nodejs"):
        return "npm"
    if lang == "rust":
        return "crates"
    return "github"


def search(query: str, language: str | None, min_stars: int, top: int, registry: str = "auto"):
    """Point d'entree unique. Repli automatique et silencieux (signale sur
    stderr) vers GitHub si la source native de l'ecosysteme est injoignable :
    un reseau restreint qui bloque registry.npmjs.org ou crates.io ne doit
    pas empecher l'outil de repondre."""
    chosen = pick_registry(registry, language)

    if chosen == "npm":
        try:
            return search_npm(query, min_stars, top), "npm"
        except SourceUnavailableError as e:
            print(json.dumps({"warning": f"{e}. Repli sur GitHub."}), file=sys.stderr)
    elif chosen == "crates":
        try:
            return search_crates(query, min_stars, top), "crates"
        except SourceUnavailableError as e:
            print(json.dumps({"warning": f"{e}. Repli sur GitHub."}), file=sys.stderr)

    return search_github(query, language, min_stars, top), "github"


if __name__ == "__main__":
    # Certaines consoles (Windows/cp1252) plantent sur les caracteres Unicode
    # que peuvent contenir des descriptions de repos (emoji, fleches, accents rares).
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    p = argparse.ArgumentParser()
    p.add_argument("query")
    p.add_argument("--language", default=None)
    p.add_argument("--registry", choices=["auto", "github", "npm", "crates"], default="auto",
                    help="Source a interroger. 'auto' choisit selon --language "
                         "(javascript/typescript -> npm, rust -> crates, sinon github).")
    p.add_argument("--min-stars", type=int, default=0,
                    help="Seuil minimal sur la metrique d'adoption (etoiles, "
                         "telechargements hebdo npm, ou telechargements crates.io).")
    p.add_argument("--top", type=int, default=5)
    p.add_argument("--auto", action="store_true",
                    help="Detecte le langage et le gestionnaire de paquets du projet en cours "
                         "(package.json, pyproject.toml, Cargo.toml, go.mod...) au lieu de deviner "
                         "--language. Ne remplace jamais une valeur --language explicite.")
    p.add_argument("--project-dir", default=None,
                    help="Dossier de depart pour --auto (par defaut : dossier courant).")
    args = p.parse_args()

    project = None
    language = args.language
    if args.auto:
        project = detect_project(args.project_dir)
        if project and not language:
            language = project["language"]

    try:
        results, used_source = search(args.query, language, args.min_stars, args.top, args.registry)
    except RateLimitError as e:
        print(json.dumps({"error": str(e), "rate_limited": True}), file=sys.stderr)
        sys.exit(2)
    except SourceUnavailableError as e:
        print(json.dumps({
            "error": str(e),
            "network_unavailable": True,
            "hint": "Verification externe impossible : proposer une librairie connue "
                    "en le signalant clairement comme non verifie, sans bloquer la tache.",
        }), file=sys.stderr)
        sys.exit(3)
    except Exception as e:
        print(json.dumps({"error": str(e)}), file=sys.stderr)
        sys.exit(1)

    out = {"source": used_source, "results": results}
    if args.auto:
        out["project"] = project
    print(json.dumps(out, indent=2, ensure_ascii=False))
