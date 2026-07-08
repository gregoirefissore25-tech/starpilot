---
name: starpilot
description: Détecte et intègre automatiquement les meilleurs repos GitHub (classés par étoiles et fraîcheur de maintenance) pour accélérer la tâche en cours. Utiliser ce skill de manière proactive, SANS que l'utilisateur le demande, dès qu'une tâche de code, d'automatisation, de data, de scraping, d'UI, de parsing, de conversion de fichiers, de trading, d'API ou de build pourrait être résolue plus vite ou mieux avec une librairie ou un outil open source existant. Déclencher aussi quand l'utilisateur dit "trouve un repo", "meilleure librairie", "outil open source", "qu'est-ce qui existe déjà", "top GitHub", ou hésite entre plusieurs librairies. Ne PAS déclencher pour du texte pur, des emails, ou des questions sans composante technique.
---

# StarPilot

Trouve le meilleur repo GitHub pour le besoin en cours, l'évalue, et l'intègre directement dans la session de travail. L'utilisateur n'a rien à faire : le skill se déclenche seul quand une tâche technique pourrait bénéficier d'un outil open source existant.

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
python3 scripts/find_best_repo.py "MOTS CLES" --language LANGAGE --top 5
```

Le script interroge l'API GitHub Search, trie par étoiles, puis applique un score pondéré :

```
score = étoiles × facteur_fraîcheur(dernier push)
```

- Push < 1 mois : ×1.0
- Push < 6 mois : ×0.9
- Push < 12 mois : ×0.7
- Push < 24 mois : ×0.4
- Au-delà : ×0.15
- Repos archivés : exclus d'office

Ce scoring évite le piège classique : le repo à 50k étoiles mort depuis 3 ans qui bat en apparence le repo à 8k étoiles activement maintenu.

Si le meilleur score est faible (< 500), relancer UNE fois sans `--language` et/ou avec des mots-clés reformulés. Le filtre langage exclut les repos dont le langage principal déclaré diffère, ce qui rate parfois les gros repos.

### 3. Sélectionner

Choisir le repo #1 par score, sauf si :
- **Licence incompatible** : NONE, GPL sur un projet commercial fermé → prendre le suivant (MIT, Apache-2.0, BSD sont sûrs)
- **Overkill** : un framework de 200k lignes pour un besoin de 30 lignes → coder soi-même
- **Pas de match réel** : si le meilleur score est faible (< 500) ou hors sujet, coder from scratch et le dire

Annoncer le choix en une ligne : nom, étoiles, licence, dernier push, pourquoi lui.

### 4. Intégrer immédiatement

Selon le type de repo :

**Librairie packagée** (le plus fréquent) :
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

Seuls github.com, api.github.com, raw.githubusercontent.com, pypi.org, npmjs.com (et miroirs) sont accessibles. Un repo dont l'installation exige un domaine hors liste : passer au suivant.
