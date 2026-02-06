# Olyos Capital - Portfolio Terminal

Systeme de gestion de portefeuille pour hedge fund utilisant la methodologie William Higgons (Quality Value).

## Fonctionnalites

- **Dashboard Bloomberg-style** - Interface terminal professionnelle
- **Screener Higgons** - Filtrage des actions europeennes small/mid caps
- **Backtesting** - Simulation de strategies sur donnees historiques
- **Scoring multi-factoriel** - Higgons + Piotroski F-Score
- **Gestion de portefeuille** - Suivi des positions et P&L

## Installation

```bash
pip install -r requirements.txt
```

## Configuration

Definir la variable d'environnement pour l'API EOD:
```bash
set EOD_API_KEY=votre_cle_api
```

## Lancement

```bash
python -m olyos.app
```

Ouvrir http://localhost:8080 dans le navigateur.

## Structure du projet

```
olyos-capital/
├── olyos/              # Package principal
│   ├── app.py          # Point d'entree HTTP
│   ├── config.py       # Configuration centralisee
│   ├── handlers/       # Routes HTTP
│   ├── services/       # Logique metier
│   ├── models/         # Modeles de donnees
│   └── templates/      # Templates HTML (Jinja2)
├── static/             # CSS, JS, images
├── tests/              # Tests unitaires
└── data/               # Donnees (portfolio.xlsx, caches)
```

## Methodologie Higgons

Criteres de selection:
- **PE** < 12 (valorisation attractive)
- **ROE** > 10% (rentabilite)
- **Dette/EBITDA** < 3x (solidite financiere)
- **FCF Yield** > 5% (generation de cash)

## License

Proprietary - Olyos Capital
