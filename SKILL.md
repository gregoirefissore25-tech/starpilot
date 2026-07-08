---
name: starpilot
description: Détecte et intègre automatiquement le meilleur outil open source (repo GitHub, paquet npm ou crate Rust selon l'écosystème) pour accélérer la tâche en cours, en s'adaptant au projet réel en cours (langage, gestionnaire de paquets, dépendances déjà installées détectés depuis package.json/pyproject.toml/Cargo.toml/go.mod...) plutôt qu'à une recherche générique. Utiliser ce skill de manière proactive, SANS que l'utilisateur le demande, dès qu'une tâche de code, d'automatisation, de data, de scraping, d'UI, de parsing, de conversion de fichiers, de trading, d'API ou de build pourrait être résolue plus vite ou mieux avec une librairie ou un outil open source existant. Déclencher aussi quand l'utilisateur dit "trouve un repo", "meilleure librairie", "outil open source", "qu'est-ce qui existe déjà", "top GitHub", ou hésite entre plusieurs librairies. Ne PAS déclencher pour du texte pur, des emails, ou des questions sans composante technique.
---

# StarPilot

Trouve le meilleur outil open source pour le besoin en cours (GitHub, npm ou crates.io selon l'écosystème du projet réel), l'évalue, et l'intègre directement dans la session de travail avec la commande d'installation qui correspond aux outils déjà en place. L'utilisateur n'a rien à faire : le skill se déclenche seul quand une tâche technique pourrait bénéficier d'un outil open source existant.

## Principe

Avant de coder quoi que ce soit de non trivial from scratch, vérifier si un repo bien maintenu et populaire fait déjà le travail. Réflexe : "build vs. reuse", avec biais vers reuse quand un repo à fort score existe.

## Workflow (4 étapes)

### 1. Détecter le besoin

Extraire de la tâche en cours un besoin en 2-4 mots-clés anglais (l'index GitHub est anglophone). Exemples :
- "convertis ce PDF en markdown" → `pdf to markdown`
- "je veux un swipe deck dans mon app React" → `swipe cards react`
- "backtester ma stratégie XAUUSD" → `backtesting trading`

### 2. Chercher et scorer

```bash
python3 scripts/find_best_repo.py "MOTS CLES" --auto --top 5
```

`--auto` est la forme par défaut : il lit les vrais fichiers du projet en cours (`package.json`, `pyproject.toml`, `Cargo.toml`, `go.mod`, `composer.json`, `Gemfile`, et leurs lockfiles) pour connaître le langage, le gestionnaire de paquets exact (pnpm/yarn/bun/npm, poetry/uv/pipenv/pip, cargo, go modules, composer, bundler) et les dépendances déjà installées, au lieu de deviner `--language` depuis le contexte de la tâche. Il remonte jusqu'à 5 dossiers parents si l'appel se fait depuis un sous-dossier. Utiliser `--project-dir CHEMIN` si le dossier courant n'est pas la racine du projet, et `--language LANGAGE` en explicite uniquement quand `--auto` ne trouve rien (projet vide, prototype sans manifeste) ou pour forcer un langage différent de celui détecté.

Le script choisit automatiquement la source la plus fiable pour l'écosystème détecté (voir « Sources par écosystème » ci-dessous), puis applique un score pondéré :

```
score = métrique d'adoption × facteur_fraîcheur(dernière mise à jour)
```

où la métrique d'adoption est les étoiles GitHub, les téléchargements hebdo npm, ou les téléchargements crates.io selon la source utilisée (voir plus bas).

- Mise à jour < 1 mois : ×1.0
- < 6 mois : ×0.9
- < 12 mois : ×0.7
- < 24 mois : ×0.4
- Au-delà : ×0.15
- Repos/paquets archivés : exclus d'office

Ce scoring évite le piège classique : le repo à 50k étoiles mort depuis 3 ans qui bat en apparence le repo à 8k étoiles activement maintenu.

La sortie JSON contient un champ `source` (registre effectivement utilisé) et chaque résultat porte un champ `metric` (`github_stars`, `npm_weekly_downloads` ou `crates_downloads`) : reprendre ce libellé exact en une ligne à l'utilisateur plutôt que de toujours dire « étoiles ».

Si le meilleur score est faible (< 500), relancer UNE fois sans `--language` et/ou avec des mots-clés reformulés. Le filtre langage exclut les repos dont le langage principal déclaré diffère, ce qui rate parfois les gros repos.

### Sources par écosystème (optimisation par outil)

Les étoiles GitHub sont un signal biaisé pour les écosystèmes qui ont leur propre registre avec de vrais chiffres d'usage : une lib peut être massivement utilisée en production sans jamais avoir été « starred ». Le script s'adapte donc :

| `--language` | Source utilisée | Métrique |
|---|---|---|
| `javascript`, `typescript`, `js`, `ts`, `node` | npm | téléchargements hebdomadaires réels |
| `rust` | crates.io | téléchargements totaux |
| tout le reste (`python`, `go`, `java`...) | GitHub | étoiles |

Forcer une source précise avec `--registry {auto,github,npm,crates}` (utile si `--language` n'est pas fourni ou si on veut comparer). Si la source native de l'écosystème est injoignable (réseau restreint), le script bascule seul sur GitHub et le signale sur stderr : ne pas s'en inquiéter, le résultat reste utilisable, juste avec une métrique différente (`metric` dans la sortie le précise).

### 3. Sélectionner

**D'abord, vérifier qu'on ne réinvente pas ce qui existe déjà** : la sortie de `--auto` inclut `project.existing_dependencies`, la liste réelle des dépendances déjà déclarées dans le projet. Si l'une d'elles couvre déjà le besoin (ex. `axios` déjà présent alors qu'on cherche un client HTTP), le dire et la réutiliser directement, sans chercher ni installer quoi que ce soit de nouveau.

Sinon, choisir le repo #1 par score, sauf si :
- **Licence incompatible** : NONE, GPL sur un projet commercial fermé → prendre le suivant (MIT, Apache-2.0, BSD sont sûrs)
- **Overkill** : un framework de 200k lignes pour un besoin de 30 lignes → coder soi-même
- **Pas de match réel** : si le meilleur score est faible (< 500) ou hors sujet, coder from scratch et le dire

Annoncer le choix en une ligne : nom, métrique d'adoption (étoiles ou téléchargements, voir `metric`), licence, dernier push, pourquoi lui.

### 4. Intégrer immédiatement

Utiliser le `install_cmd_template` de `project` (sortie de `--auto`) pour respecter exactement le gestionnaire de paquets déjà en place dans le projet, plutôt qu'une commande générique :

```bash
# install_cmd_template = "pnpm add {name}" -> pnpm add axios
# install_cmd_template = "poetry add {name}" -> poetry add requests
# install_cmd_template = "cargo add {name}" -> cargo add serde
```

Si `--auto` n'a rien détecté (pas de manifeste trouvé), retomber sur la commande générique de l'écosystème :

```bash
pip install NOM --break-system-packages   # Python
npm install NOM                            # Node
```

**Repo à cloner** (outil, template, code à adapter) :
```bash
git clone --depth 1 https://github.com/OWNER/REPO /home/claude/vendor/REPO
```
Puis lire le README et les fichiers clés avant usage.

**Vérification obligatoire** : exécuter un test minimal (import, --help, ou mini exemple) avant de bâtir dessus. Si ça casse, basculer sur le repo #2 sans demander.

Ensuite, continuer la tâche de l'utilisateur avec l'outil intégré. Le skill n'est pas la destination, c'est un accélérateur en cours de route.

## Règles

- Une seule recherche par besoin. Ne pas transformer la tâche en revue de littérature.
- Toujours mentionner à l'utilisateur quel repo a été intégré et pourquoi (une phrase suffit).
- Ne jamais cloner un repo pour du code malveillant, du scraping abusif de données personnelles, ou du contournement de protections.
- Si l'utilisateur a déjà choisi sa librairie, respecter son choix : ne pas la remettre en cause avec ce skill.
- L'environnement se réinitialise entre les sessions : les installations sont valables pour la session en cours uniquement. Le skill se recharge et réintègre automatiquement à chaque nouvelle session où le besoin apparaît.

## Limites réseau

Domaines utilisés : github.com, api.github.com, raw.githubusercontent.com, pypi.org, npmjs.com, registry.npmjs.org, api.npmjs.org, crates.io (et miroirs). Un repo dont l'installation exige un domaine hors liste : passer au suivant.

## Marcher dans n'importe quelle condition

Le script est conçu pour ne jamais bloquer la tâche en cours, même en environnement contraint :

- **Quota GitHub dépassé** (60 requêtes/heure sans jeton) : le script le détecte explicitement et le dit (au lieu d'une erreur réseau confuse). Si `GITHUB_TOKEN` ou `GH_TOKEN` est présent dans l'environnement, ou si le CLI `gh` est authentifié (`gh auth token`), le quota passe à 5000/heure automatiquement, sans rien à faire de plus. Si une recherche échoue pour cette raison et qu'aucun jeton n'est disponible, proposer à l'utilisateur d'en configurer un, ou attendre le délai indiqué.
- **Source de l'écosystème injoignable** (registry.npmjs.org ou crates.io bloqué par le réseau) : repli automatique et silencieux sur GitHub, signalé sur stderr. Ne pas s'interrompre pour ça.
- **Panne réseau totale ou GitHub injoignable** (sandbox sans accès internet, domaine bloqué au niveau plateforme) : le script sort avec un code 3 et un message structuré (`network_unavailable: true`). Dans ce cas précis, **ne jamais bloquer la tâche de l'utilisateur** : le dire en une ligne, proposer la librairie la plus réputée de sa connaissance générale en la signalant explicitement comme non vérifiée (pas de score, pas de garantie de fraîcheur), et continuer le travail avec ce choix par défaut.
- **Erreurs transitoires** (timeout, coupure momentanée, 5xx) : nouvelles tentatives automatiques avec délai croissant, invisibles pour l'appelant. Aucune action à prendre.
