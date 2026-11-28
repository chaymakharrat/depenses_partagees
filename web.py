#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
web.py — Module dédié au Tableau de Bord Web interactif Multi-Groupes (HTML / CSS / JS).

Fonctionnalités :
  - Support multi-groupes : vue d'ensemble comparative + onglet dédié par groupe.
  - Bascule de thème instantanée : Mode Sombre / Mode Clair avec mémorisation.
  - Statistiques comparatives et graphiques Chart.js (par catégorie, mois et inter-groupes).
  - Filtrage et recherche en temps réel sans rechargement.
  - Palette sobre orientée comptabilité (bleu marine, aplats, vert/rouge réservés aux soldes).
  - Design responsive (mobile/tablette/PC) et optimisé pour l'impression PDF.
  - Icônes vectorielles SVG intégrées (style Feather / Lucide, sans émojis).
"""

from collections import defaultdict
from datetime import datetime
from html import escape as esc
import json
import os
import webbrowser

from noyau import (
    Groupe,
    calculer_soldes,
    charger_groupe,
    format_montant,
    lister_groupes_disponibles,
    regler,
    repartir_depense,
    trouver_membre,
    verifier_soldes,
)


# ---------------------------------------------------------------------------
# Icônes vectorielles SVG épurées
# ---------------------------------------------------------------------------
def _svg(contenu: str) -> str:
    return ('<svg class="icon" viewBox="0 0 24 24" aria-hidden="true">'
            + contenu + '</svg>')


IC_DOLLAR = _svg('<line x1="12" y1="1" x2="12" y2="23"/>'
                 '<path d="M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/>')
IC_CHECK = _svg('<path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/>'
                '<polyline points="22 4 12 14.01 9 11.01"/>')
IC_X = _svg('<circle cx="12" cy="12" r="10"/>'
            '<line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/>')
IC_SEARCH = _svg('<circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>')
IC_ARROW = _svg('<line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/>')
IC_PRINT = _svg('<polyline points="6 9 6 2 18 2 18 9"/>'
                '<path d="M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2"/>'
                '<rect x="6" y="14" width="12" height="8"/>')
IC_LAYERS = _svg('<polygon points="12 2 2 7 12 12 22 7 12 2"/>'
                 '<polyline points="2 17 12 22 22 17"/><polyline points="2 12 12 17 22 12"/>')
IC_USERS = _svg('<path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/>'
                '<circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/>'
                '<path d="M16 3.13a4 4 0 0 1 0 7.75"/>')
IC_BARS = _svg('<line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/>'
               '<line x1="6" y1="20" x2="6" y2="14"/>')
IC_SUN = _svg('<circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/>'
              '<line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/>'
              '<line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/>'
              '<line x1="21" y1="12" x2="23" y2="12"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/>'
              '<line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/>')
IC_MOON = _svg('<path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/>')


# ---------------------------------------------------------------------------
# Utilitaires de présentation
# ---------------------------------------------------------------------------
# Tons discrets, tous assez sombres pour un texte blanc lisible
_COULEURS_AVATAR = ["#1f3a5f", "#2f6f6a", "#6b5b95", "#8a6d3b", "#475569", "#7a3e4d", "#3f6b4f"]


def _avatar(nom: str) -> str:
    """Génère une pastille ronde avec initiales colorées de façon déterministe."""
    nom = str(nom)
    mots = nom.split()
    ini = (mots[0][0] + mots[1][0]) if len(mots) >= 2 else nom[:2]
    couleur = _COULEURS_AVATAR[sum(ord(c) for c in nom) % len(_COULEURS_AVATAR)]
    return f'<span class="avatar" style="--av:{couleur}" aria-hidden="true">{esc(ini.upper())}</span>'


def _fmt_date(s: str) -> str:
    s = str(s)
    if len(s) >= 10 and s[4] == "-" and s[7] == "-":
        return f"{s[8:10]}/{s[5:7]}/{s[0:4]}"
    return s


def _fmt_mois(s: str) -> str:
    s = str(s)
    if len(s) >= 7 and s[4] == "-":
        return f"{s[5:7]}/{s[0:4]}"
    return s


# ---------------------------------------------------------------------------
# Feuille de styles sobre (Comptabilité, Mode Sombre & Clair)
# ---------------------------------------------------------------------------
_CSS = """
:root {
    color-scheme: light dark;
    --bg: #f4f6f8;
    --surface: #ffffff;
    --surface-elevated: #ffffff;
    --soft: #eef1f5;
    --soft-hover: #e2e7ee;
    --ink: #1a2433;
    --muted: #5b6778;
    --line: #d9dfe7;
    --brand: #1f3a5f;
    --brand-ink: #ffffff;
    --brand-soft: #e8eef6;
    --plan-bg: #1f3a5f;
    --pos: #1b7f5c;
    --pos-bg: #e6f4ee;
    --neg: #b42318;
    --neg-bg: #fdecea;
    --warn: #9a6700;
    --warn-bg: #fff6e0;
    --shadow-sm: 0 1px 2px rgba(15, 23, 42, 0.06);
    --shadow-md: 0 3px 8px rgba(15, 23, 42, 0.08);
    --shadow-lg: 0 8px 16px rgba(15, 23, 42, 0.10);
    --gutter: clamp(16px, 3vw, 32px);
    --radius: 12px;
    --radius-sm: 8px;
}

[data-theme="dark"] {
    --bg: #0f1620;
    --surface: #161f2c;
    --surface-elevated: #1d2838;
    --soft: #1d2838;
    --soft-hover: #283548;
    --ink: #e8edf4;
    --muted: #93a0b3;
    --line: #2a384b;
    --brand: #7aa2d6;
    --brand-ink: #0f1620;
    --brand-soft: #1c2f4a;
    --plan-bg: #24476f;
    --pos: #4cc38a;
    --pos-bg: #11332a;
    --neg: #f2766b;
    --neg-bg: #3d1a17;
    --warn: #e0a93b;
    --warn-bg: #382a0c;
    --shadow-sm: 0 1px 2px rgba(0, 0, 0, 0.4);
    --shadow-md: 0 3px 8px rgba(0, 0, 0, 0.5);
    --shadow-lg: 0 8px 16px rgba(0, 0, 0, 0.6);
}

@media (prefers-color-scheme: dark) {
    :root:not([data-theme="light"]) {
        --bg: #0f1620;
        --surface: #161f2c;
        --surface-elevated: #1d2838;
        --soft: #1d2838;
        --soft-hover: #283548;
        --ink: #e8edf4;
        --muted: #93a0b3;
        --line: #2a384b;
        --brand: #7aa2d6;
        --brand-ink: #0f1620;
        --brand-soft: #1c2f4a;
        --plan-bg: #24476f;
        --pos: #4cc38a;
        --pos-bg: #11332a;
        --neg: #f2766b;
        --neg-bg: #3d1a17;
        --warn: #e0a93b;
        --warn-bg: #382a0c;
    }
}

* { box-sizing: border-box; margin: 0; padding: 0; }
body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
    font-size: 15px;
    line-height: 1.5;
    background: var(--bg);
    color: var(--ink);
    padding-bottom: 60px;
    transition: background 0.2s ease, color 0.2s ease;
}

[hidden] { display: none !important; }
.icon { width: 1.15em; height: 1.15em; stroke: currentColor; fill: none; stroke-width: 2; stroke-linecap: round; stroke-linejoin: round; flex-shrink: 0; }
.sr-only { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); }

/* Navigation Bar */
.navbar {
    background: var(--surface);
    border-bottom: 1px solid var(--line);
    position: sticky;
    top: 0;
    z-index: 50;
    box-shadow: var(--shadow-sm);
}
.nav-wrap {
    width: min(1200px, 100% - 2 * var(--gutter));
    margin-inline: auto;
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 12px 0;
    gap: 16px;
}
.brand {
    display: flex;
    align-items: center;
    gap: 12px;
    text-decoration: none;
    color: var(--ink);
}
.brand-logo {
    width: 38px;
    height: 38px;
    border-radius: 8px;
    background: var(--brand);
    color: var(--brand-ink);
    display: grid;
    place-items: center;
}
.brand-name {
    font-size: 1.1rem;
    font-weight: 700;
    letter-spacing: -0.01em;
}
.brand-tag {
    font-size: 0.75rem;
    color: var(--muted);
}
.nav-tools {
    display: flex;
    align-items: center;
    gap: 10px;
}
.btn-icon {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 38px;
    height: 38px;
    border-radius: 8px;
    border: 1px solid var(--line);
    background: var(--surface);
    color: var(--ink);
    cursor: pointer;
    transition: background 0.15s, border-color 0.15s;
}
.btn-icon:hover {
    background: var(--soft);
}
.btn-text {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    padding: 0 14px;
    height: 38px;
    border-radius: 8px;
    border: 1px solid var(--line);
    background: var(--surface);
    color: var(--ink);
    font: inherit;
    font-size: 0.85rem;
    font-weight: 600;
    cursor: pointer;
    transition: all 0.15s ease;
}
.btn-text:hover {
    background: var(--soft);
}

/* Tab Bar */
.tabs-container {
    width: min(1200px, 100% - 2 * var(--gutter));
    margin-inline: auto;
    margin-top: 24px;
}
.tabs-list {
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 4px;
    border-radius: 10px;
    background: var(--soft);
    overflow-x: auto;
    scrollbar-width: none;
}
.tabs-list::-webkit-scrollbar { display: none; }
.tab-btn {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    padding: 8px 16px;
    border: 0;
    border-radius: 7px;
    background: transparent;
    color: var(--muted);
    font: inherit;
    font-size: 0.875rem;
    font-weight: 600;
    cursor: pointer;
    white-space: nowrap;
    transition: all 0.15s ease;
}
.tab-btn:hover {
    color: var(--ink);
}
.tab-btn[aria-selected="true"] {
    background: var(--surface);
    color: var(--brand);
    box-shadow: var(--shadow-sm);
}
.tab-btn .badge-count {
    padding: 2px 7px;
    border-radius: 999px;
    font-size: 0.725rem;
    background: var(--surface);
    color: var(--muted);
}
.tab-btn[aria-selected="true"] .badge-count {
    background: var(--brand-soft);
    color: var(--brand);
}

/* Conteneur principal */
.main-wrap {
    width: min(1200px, 100% - 2 * var(--gutter));
    margin-inline: auto;
    margin-top: 24px;
    display: flex;
    flex-direction: column;
    gap: 24px;
}

/* En-tête de page */
.page-header {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: space-between;
    gap: 16px;
}
.page-title {
    font-size: clamp(1.4rem, 1.1rem + 1.2vw, 1.85rem);
    font-weight: 800;
    letter-spacing: -0.02em;
}
.page-subtitle {
    color: var(--muted);
    font-size: 0.875rem;
    margin-top: 3px;
}
.pill {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 6px 14px;
    border-radius: 999px;
    font-size: 0.8125rem;
    font-weight: 700;
}
.pill.ok { background: var(--pos-bg); color: var(--pos); }
.pill.ko { background: var(--neg-bg); color: var(--neg); }
.pill.neutral { background: var(--soft); color: var(--muted); }

/* Cartes KPI (Stats) */
.kpis {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
    gap: 16px;
}
.kpi {
    background: var(--surface);
    border: 1px solid var(--line);
    border-radius: var(--radius);
    padding: 20px 22px;
    box-shadow: var(--shadow-sm);
}
.kpi-label {
    display: flex;
    align-items: center;
    gap: 8px;
    color: var(--muted);
    font-size: 0.8rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.04em;
}
.kpi-value {
    font-size: clamp(1.4rem, 1.1rem + 1vw, 1.85rem);
    font-weight: 800;
    letter-spacing: -0.02em;
    margin-top: 8px;
    font-variant-numeric: tabular-nums;
}
.kpi-sub {
    color: var(--muted);
    font-size: 0.8125rem;
    margin-top: 4px;
}

/* Grille de comparaison des groupes */
.groups-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
    gap: 20px;
}
.group-card {
    background: var(--surface);
    border: 1px solid var(--line);
    border-radius: var(--radius);
    padding: 22px;
    box-shadow: var(--shadow-sm);
    display: flex;
    flex-direction: column;
    justify-content: space-between;
    transition: border-color 0.2s ease, box-shadow 0.2s ease;
}
.group-card:hover {
    border-color: var(--brand);
    box-shadow: var(--shadow-md);
}
.group-card-head {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    gap: 12px;
}
.group-card-name {
    font-size: 1.15rem;
    font-weight: 700;
}
.group-card-members {
    color: var(--muted);
    font-size: 0.85rem;
    margin-top: 4px;
}
.group-card-body {
    margin-top: 18px;
    padding-top: 16px;
    border-top: 1px solid var(--line);
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 12px;
}
.group-card-stat-label {
    color: var(--muted);
    font-size: 0.775rem;
    text-transform: uppercase;
    font-weight: 600;
}
.group-card-stat-val {
    font-size: 1.05rem;
    font-weight: 700;
    margin-top: 2px;
    font-variant-numeric: tabular-nums;
}
.group-card-footer {
    margin-top: 20px;
    display: flex;
    justify-content: flex-end;
}
.btn-open-group {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 8px 14px;
    border-radius: 8px;
    border: 1px solid var(--line);
    background: var(--soft);
    color: var(--ink);
    font: inherit;
    font-size: 0.825rem;
    font-weight: 600;
    cursor: pointer;
    transition: all 0.15s;
}
.btn-open-group:hover {
    background: var(--brand);
    color: var(--brand-ink);
    border-color: var(--brand);
}

/* Sections & Panneaux */
.panel {
    background: var(--surface);
    border: 1px solid var(--line);
    border-radius: var(--radius);
    padding: clamp(18px, 2.5vw, 28px);
    box-shadow: var(--shadow-sm);
}
.panel-head {
    display: flex;
    flex-wrap: wrap;
    justify-content: space-between;
    align-items: baseline;
    gap: 8px 16px;
    margin-bottom: 20px;
}
.panel-title {
    font-size: 1.1rem;
    font-weight: 700;
    letter-spacing: -0.01em;
}
.panel-lede {
    color: var(--muted);
    font-size: 0.85rem;
    margin-top: 2px;
}

/* Plan de règlement (aplat, sans dégradé) */
.layout-two {
    display: grid;
    grid-template-columns: minmax(0, 1.1fr) minmax(0, 1fr);
    gap: 24px;
    align-items: start;
}
@media (max-width: 960px) { .layout-two { grid-template-columns: 1fr; } }

.plan-card {
    background: var(--plan-bg);
    border-radius: var(--radius);
    padding: clamp(20px, 3vw, 28px);
    color: #fff;
    box-shadow: var(--shadow-md);
}
.plan-card .panel-title { color: #fff; }
.plan-card .panel-lede { color: rgba(255, 255, 255, 0.8); }
.virements-list {
    list-style: none;
    display: flex;
    flex-direction: column;
    gap: 10px;
    margin-top: 14px;
}
.virement-item {
    display: grid;
    grid-template-columns: minmax(0, 1fr) auto minmax(0, 1fr) auto;
    align-items: center;
    gap: 12px;
    padding: 13px 16px;
    border-radius: 10px;
    background: rgba(255, 255, 255, 0.10);
    border: 1px solid rgba(255, 255, 255, 0.18);
}
.actor {
    display: flex;
    align-items: center;
    gap: 10px;
    min-width: 0;
    font-weight: 600;
}
.actor span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.v-montant {
    text-align: right;
    font-size: 1.15rem;
    font-weight: 800;
    font-variant-numeric: tabular-nums;
    white-space: nowrap;
}
@media (max-width: 580px) {
    .virement-item {
        grid-template-columns: 1fr auto 1fr;
    }
    .v-montant {
        grid-column: 1 / -1;
        text-align: right;
        padding-top: 8px;
        border-top: 1px solid rgba(255, 255, 255, 0.18);
    }
}

/* Soldes individuels */
.avatar {
    width: 32px;
    height: 32px;
    border-radius: 50%;
    background: var(--av, var(--brand));
    color: #fff;
    display: grid;
    place-items: center;
    font-size: 0.75rem;
    font-weight: 700;
    flex-shrink: 0;
}
.soldes-list { list-style: none; }
.solde-item {
    display: grid;
    grid-template-columns: minmax(110px, 1fr) minmax(0, 1.4fr) auto;
    grid-template-areas: "id track val" "det det det";
    align-items: center;
    gap: 6px 14px;
    padding: 14px 0;
    border-top: 1px solid var(--line);
}
.solde-item:first-child { border-top: 0; padding-top: 0; }
.solde-track {
    grid-area: track;
    position: relative;
    height: 8px;
    border-radius: 99px;
    background: var(--soft);
}
.solde-track::before {
    content: "";
    position: absolute;
    left: 50%;
    top: -3px;
    bottom: -3px;
    width: 2px;
    margin-left: -1px;
    background: var(--muted);
    opacity: 0.5;
}
.solde-bar { position: absolute; top: 0; bottom: 0; }
.solde-bar.pos { left: 50%; background: var(--pos); border-radius: 0 99px 99px 0; }
.solde-bar.neg { right: 50%; background: var(--neg); border-radius: 99px 0 0 99px; }
.solde-val {
    grid-area: val;
    text-align: right;
    font-weight: 700;
    font-variant-numeric: tabular-nums;
    white-space: nowrap;
}
.solde-val.pos { color: var(--pos); }
.solde-val.neg { color: var(--neg); }
.solde-val.zero { color: var(--muted); }
.solde-detail { grid-area: det; color: var(--muted); font-size: 0.8125rem; }

/* Graphiques */
.charts-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(360px, 1fr));
    gap: 24px;
}
.chart-box {
    position: relative;
    height: 280px;
    width: 100%;
}

/* Outils & Tableau */
.tools {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 12px;
    margin-bottom: 16px;
}
.search-box {
    position: relative;
    flex: 1 1 260px;
}
.search-box .icon {
    position: absolute;
    left: 12px;
    top: 50%;
    translate: 0 -50%;
    color: var(--muted);
    pointer-events: none;
}
.search-input {
    width: 100%;
    height: 40px;
    padding: 0 14px 0 38px;
    border-radius: 8px;
    border: 1px solid var(--line);
    background: var(--bg);
    color: var(--ink);
    font: inherit;
    font-size: 0.875rem;
}
.seg {
    display: inline-flex;
    gap: 2px;
    padding: 3px;
    border-radius: 8px;
    background: var(--soft);
}
.seg button {
    height: 34px;
    padding: 0 12px;
    border: 0;
    border-radius: 6px;
    background: transparent;
    color: var(--muted);
    font: inherit;
    font-size: 0.825rem;
    font-weight: 600;
    cursor: pointer;
    transition: all 0.15s;
}
.seg button[aria-pressed="true"] {
    background: var(--surface);
    color: var(--ink);
    box-shadow: var(--shadow-sm);
}

.table-wrap { overflow-x: auto; }
table { width: 100%; border-collapse: collapse; font-size: 0.875rem; }
th {
    text-align: left;
    padding: 12px 14px;
    color: var(--muted);
    font-size: 0.775rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    border-bottom: 2px solid var(--line);
    white-space: nowrap;
}
td {
    padding: 12px 14px;
    border-bottom: 1px solid var(--line);
    vertical-align: middle;
}
tbody tr:last-child td { border-bottom: 0; }
tbody tr:nth-child(even) td { background: var(--soft); }
tbody tr:hover td { background: var(--soft-hover); }
th.num, td.num { text-align: right; }
td.num {
    font-family: ui-monospace, "SF Mono", Consolas, "Liberation Mono", monospace;
    font-weight: 700;
    font-variant-numeric: tabular-nums;
    white-space: nowrap;
}
.tag {
    display: inline-block;
    padding: 3px 10px;
    border-radius: 999px;
    background: var(--brand-soft);
    color: var(--brand);
    font-size: 0.8rem;
    font-weight: 600;
}
.status-pill {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    font-size: 0.8rem;
    font-weight: 600;
    white-space: nowrap;
}
.status-pill::before {
    content: "";
    width: 7px;
    height: 7px;
    border-radius: 50%;
    background: currentColor;
}
.status-pill.ok { color: var(--pos); }
.status-pill.warn { color: var(--warn); }

@media print {
    body { background: #fff !important; color: #000 !important; }
    .navbar, .tabs-container, .tools, .btn-open-group { display: none !important; }
    .panel, .kpi { break-inside: avoid; border: 1px solid #ccc !important; box-shadow: none !important; }
    .plan-card { background: #fff !important; color: #000 !important; border: 1px solid #999 !important; box-shadow: none !important; }
    .plan-card .panel-title, .plan-card .panel-lede { color: #000 !important; }
    .virement-item { background: #f8f8f8 !important; border-color: #ddd !important; border-left: 3px solid #1f3a5f !important; }
    .virement-item .actor, .virement-item .v-montant { color: #000 !important; }
    tbody tr:nth-child(even) td { background: #f3f4f6 !important; }
}
"""

# ---------------------------------------------------------------------------
# JavaScript Client (Gestion des onglets, Chart.js et Thème)
# ---------------------------------------------------------------------------
_JS = """
(function () {
    const root = document.documentElement;
    const css = function (n) { return getComputedStyle(root).getPropertyValue(n).trim(); };

    function isDark() {
        const t = root.getAttribute('data-theme');
        if (t) return t === 'dark';
        return !!(window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches);
    }

    // Palettes sobres, sans rouge ni vert vif (réservés aux soldes)
    const PALETTE_CLAIR = ['#1f3a5f', '#2a9d8f', '#c8963e', '#6b7fa3', '#8a5a83', '#5c9ead', '#a3a380', '#7d8597'];
    const PALETTE_SOMBRE = ['#7aa2d6', '#5cc4b5', '#e0b366', '#a3b3d1', '#c08fb8', '#8cc7d6', '#c9c9a0', '#a8b0c0'];
    function palette() { return isDark() ? PALETTE_SOMBRE : PALETTE_CLAIR; }

    // 1. Registre des graphiques (reconstruits à chaque changement de thème)
    const registre = [];
    function themeCharts() {
        if (typeof Chart === 'undefined') return;
        Chart.defaults.color = css('--muted');
        Chart.defaults.borderColor = css('--line');
    }
    function rendre(id, fabrique) {
        const el = document.getElementById(id);
        if (!el || typeof Chart === 'undefined') return;
        const ancien = Chart.getChart(el);
        if (ancien) ancien.destroy();
        new Chart(el, fabrique());
    }
    function mk(id, fabrique) {
        registre.push([id, fabrique]);
        rendre(id, fabrique);
    }
    function reconstruireGraphiques() {
        themeCharts();
        registre.forEach(function (r) { rendre(r[0], r[1]); });
    }

    // 2. Thème Sombre / Clair avec mémorisation localStorage
    const themeBtn = document.getElementById('themeToggle');
    function setTheme(t) {
        root.setAttribute('data-theme', t);
        try { localStorage.setItem('depenses_theme', t); } catch (e) {}
        if (themeBtn) {
            themeBtn.title = t === 'dark' ? 'Basculer vers le mode clair' : 'Basculer vers le mode sombre';
        }
    }
    let savedTheme = null;
    try { savedTheme = localStorage.getItem('depenses_theme'); } catch (e) {}
    if (savedTheme) {
        setTheme(savedTheme);
    } else if (isDark()) {
        setTheme('dark');
    }
    if (themeBtn) {
        themeBtn.addEventListener('click', function () {
            setTheme(isDark() ? 'light' : 'dark');
            reconstruireGraphiques();
        });
    }

    // 3. Gestion des onglets multi-groupes
    const tabBtns = document.querySelectorAll('.tab-btn');
    const tabPanes = document.querySelectorAll('.tab-pane');

    window.activerOnglet = function (id) {
        tabBtns.forEach(function (btn) {
            btn.setAttribute('aria-selected', btn.dataset.tab === id ? 'true' : 'false');
        });
        tabPanes.forEach(function (pane) {
            pane.hidden = pane.id !== id;
        });
        window.dispatchEvent(new Event('resize'));
    };

    tabBtns.forEach(function (btn) {
        btn.addEventListener('click', function () {
            activerOnglet(btn.dataset.tab);
        });
    });

    // 4. Initialisation des graphiques Chart.js
    if (typeof Chart !== 'undefined') {
        Chart.defaults.font.family = '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif';
        themeCharts();

        // Graphiques comparatifs
        mk('compBarChart', function () {
            return {
                type: 'bar',
                data: {
                    labels: __COMP_LABELS__,
                    datasets: [{
                        label: 'Total dépensé (TND)',
                        data: __COMP_DATA__,
                        backgroundColor: css('--brand'),
                        borderRadius: 6
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: { legend: { display: false } },
                    scales: {
                        y: { beginAtZero: true },
                        x: { grid: { display: false } }
                    }
                }
            };
        });

        mk('compPieChart', function () {
            return {
                type: 'doughnut',
                data: {
                    labels: __COMP_LABELS__,
                    datasets: [{
                        data: __COMP_DATA__,
                        backgroundColor: palette(),
                        borderColor: css('--surface'),
                        borderWidth: 2
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: { legend: { position: 'bottom' } }
                }
            };
        });

        // Graphiques individuels par groupe
        __GROUP_CHARTS_INIT__
    }

    // 5. Recherche et filtrage en direct dans chaque groupe
    document.querySelectorAll('.tab-pane').forEach(function (pane) {
        const search = pane.querySelector('.search-input');
        const rows = pane.querySelectorAll('tbody tr');
        const buttons = pane.querySelectorAll('.seg button');
        const compteur = pane.querySelector('.compteur-texte');
        let filtreStatut = 'all';

        if (search && rows.length > 0) {
            function filtrer() {
                const q = search.value.trim().toLowerCase();
                let count = 0;
                rows.forEach(function (tr) {
                    const matchFiltre = (filtreStatut === 'all' || tr.dataset.statut === filtreStatut);
                    const matchSearch = !q || (tr.dataset.search && tr.dataset.search.indexOf(q) !== -1);
                    const ok = matchFiltre && matchSearch;
                    tr.hidden = !ok;
                    if (ok) count++;
                });
                if (compteur) {
                    compteur.textContent = count + ' sur ' + rows.length + ' dépense(s) affichée(s)';
                }
            }

            search.addEventListener('input', filtrer);
            buttons.forEach(function (b) {
                b.addEventListener('click', function () {
                    filtreStatut = b.dataset.filtre;
                    buttons.forEach(function (x) { x.setAttribute('aria-pressed', x === b ? 'true' : 'false'); });
                    filtrer();
                });
            });
            filtrer();
        }
    });
})();
"""


# ---------------------------------------------------------------------------
# Génération HTML
# ---------------------------------------------------------------------------

def charger_tous_les_groupes(dossier_groupes: str = "groupes", groupe_actif: Groupe = None) -> list[Groupe]:
    """Charge l'ensemble des groupes disponibles dans le dossier et ajoute le groupe actif."""
    groupes_dict = {}
    if os.path.exists(dossier_groupes):
        for nom_g, chemin in lister_groupes_disponibles(dossier_groupes):
            try:
                g = charger_groupe(chemin)
                groupes_dict[g.nom.casefold()] = g
            except Exception:
                continue

    if groupe_actif:
        groupes_dict[groupe_actif.nom.casefold()] = groupe_actif

    return sorted(groupes_dict.values(), key=lambda g: g.nom.casefold())


def generer_dashboard_html(groupe_ou_liste, nom_groupe_actif: str = "", dossier_groupes: str = "groupes") -> str:
    """Génère un tableau de bord Web complet avec vue comparative multi-groupes et onglets détaillés."""
    if isinstance(groupe_ou_liste, Groupe):
        nom_groupe_actif = groupe_ou_liste.nom
        groupes = charger_tous_les_groupes(dossier_groupes, groupe_actif=groupe_ou_liste)
    elif isinstance(groupe_ou_liste, list) and groupe_ou_liste:
        groupes = groupe_ou_liste
        if not nom_groupe_actif:
            nom_groupe_actif = groupes[0].nom
    else:
        groupes = charger_tous_les_groupes(dossier_groupes)
        nom_groupe_actif = groupes[0].nom if groupes else "Groupe"

    maintenant = datetime.now().strftime("%d/%m/%Y à %H:%M")

    # Statistiques globales (inter-groupes)
    total_global_millimes = sum(sum(d.montant for d in g.depenses) for g in groupes)
    nb_global_depenses = sum(len(g.depenses) for g in groupes)
    nb_global_membres = sum(len(g.membres) for g in groupes)
    nb_global_virements = 0

    group_labels = []
    group_totals_tnd = []
    cards_comparatif_html = ""
    table_comparatif_html = ""

    for idx, g in enumerate(groupes):
        soldes_g = calculer_soldes(g)
        virements_g = regler(soldes_g)
        nb_global_virements += len(virements_g)
        total_g = sum(d.montant for d in g.depenses)
        non_soldees_g = sum(1 for d in g.depenses if not d.soldee)
        equilibre_g = verifier_soldes(soldes_g)
        badge_eq = ('<span class="pill ok">' + IC_CHECK + ' Équilibré</span>'
                    if equilibre_g else '<span class="pill ko">' + IC_X + ' Déséquilibré</span>')

        group_labels.append(g.nom)
        group_totals_tnd.append(total_g / 1000)

        membres_str = ", ".join(m.nom for m in g.membres) if g.membres else "Aucun membre"

        cards_comparatif_html += f"""
        <div class="group-card">
            <div>
                <div class="group-card-head">
                    <div>
                        <div class="group-card-name">{esc(g.nom)}</div>
                        <div class="group-card-members">{len(g.membres)} membre(s) : {esc(membres_str)}</div>
                    </div>
                    {badge_eq}
                </div>
                <div class="group-card-body">
                    <div>
                        <div class="group-card-stat-label">Total Dépensé</div>
                        <div class="group-card-stat-val">{format_montant(total_g)}</div>
                    </div>
                    <div>
                        <div class="group-card-stat-label">Dépenses</div>
                        <div class="group-card-stat-val">{len(g.depenses)} ({non_soldees_g} à solder)</div>
                    </div>
                </div>
            </div>
            <div class="group-card-footer">
                <button type="button" class="btn-open-group" onclick="activerOnglet('pane_group_{idx}')">
                    Voir les détails {IC_ARROW}
                </button>
            </div>
        </div>"""

        table_comparatif_html += f"""
        <tr>
            <td><strong>{esc(g.nom)}</strong></td>
            <td>{badge_eq}</td>
            <td>{len(g.membres)} membre(s)</td>
            <td>{len(g.depenses)} dépense(s)</td>
            <td class="num">{format_montant(total_g)}</td>
            <td class="num">
                <button type="button" class="btn-open-group" onclick="activerOnglet('pane_group_{idx}')">
                    Ouvrir
                </button>
            </td>
        </tr>"""

    # Onglets Navigation
    tabs_html = f"""
    <button type="button" class="tab-btn" data-tab="pane_overview" aria-selected="{'true' if len(groupes) > 1 else 'false'}">
        {IC_LAYERS} Comparatif ({len(groupes)} groupes)
    </button>"""

    group_panes_html = ""
    group_charts_js = []

    for idx, g in enumerate(groupes):
        is_active = (len(groupes) == 1 or g.nom.casefold() == nom_groupe_actif.casefold())
        badge_actif = ' <span class="badge-count">Actif</span>' if g.nom.casefold() == nom_groupe_actif.casefold() else ""
        tabs_html += f"""
        <button type="button" class="tab-btn" data-tab="pane_group_{idx}" aria-selected="{'true' if is_active and len(groupes) == 1 else 'false'}">
            {IC_USERS} {esc(g.nom)}{badge_actif}
        </button>"""

        # Données détaillées du groupe
        soldes = calculer_soldes(g)
        equilibre = verifier_soldes(soldes)
        virements = regler(soldes)
        total_g = sum(d.montant for d in g.depenses)
        nb_non_soldees = sum(1 for d in g.depenses if not d.soldee)
        nb_soldees = len(g.depenses) - nb_non_soldees

        # Catégories & Mois
        par_cat = defaultdict(int)
        for d in g.depenses:
            par_cat[d.categorie.strip().capitalize() or "Général"] += d.montant

        par_mois = defaultdict(int)
        for d in g.depenses:
            par_mois[d.date[:7]] += d.montant

        # Payé / Dû
        paye_membre = {m.nom: 0 for m in g.membres}
        du_membre = {m.nom: 0 for m in g.membres}
        for d in g.depenses:
            m_p = trouver_membre(g, d.payeur)
            nom_p = m_p.nom if m_p else d.payeur.nom
            paye_membre[nom_p] = paye_membre.get(nom_p, 0) + d.montant
            for nom_b, part in repartir_depense(d.montant, d.beneficiaires).items():
                m_b = trouver_membre(g, nom_b)
                nom_c = m_b.nom if m_b else nom_b
                du_membre[nom_c] = du_membre.get(nom_c, 0) + part

        # Soldes HTML
        max_abs = max((abs(v) for v in soldes.values()), default=0)
        soldes_html = ""
        for nom, solde in sorted(soldes.items(), key=lambda x: (-x[1], x[0].casefold())):
            paye = paye_membre.get(nom, 0)
            du = du_membre.get(nom, 0)
            if solde > 0:
                classe, signe = "pos", "+"
            elif solde < 0:
                classe, signe = "neg", ""
            else:
                classe, signe = "zero", ""
            largeur = (abs(solde) / max_abs * 50) if max_abs else 0
            barre = f'<span class="solde-bar {classe}" style="width:{largeur:.1f}%"></span>' if classe != "zero" else ""
            soldes_html += f"""
            <li class="solde-item">
                <div class="actor">{_avatar(nom)}<span>{esc(str(nom))}</span></div>
                <div class="solde-track">{barre}</div>
                <div class="solde-val {classe}">{signe}{format_montant(solde)}</div>
                <div class="solde-detail">A avancé {format_montant(paye)} et doit {format_montant(du)}.</div>
            </li>"""

        # Plan de règlement HTML
        if not virements:
            plan_html = f"""
            <div style="text-align:center; padding: 24px; color: rgba(255,255,255,0.85);">
                {IC_CHECK}
                <p style="margin-top:8px;">Tous les comptes sont à l'équilibre. Aucun virement nécessaire.</p>
            </div>"""
            plan_lede = "Équilibre parfait."
        else:
            lignes_v = ""
            for debiteur, crediteur, montant in virements:
                lignes_v += f"""
                <li class="virement-item">
                    <div class="actor">{_avatar(debiteur)}<span>{esc(str(debiteur))}</span></div>
                    <span style="opacity:0.8;">{IC_ARROW}</span>
                    <div class="actor">{_avatar(crediteur)}<span>{esc(str(crediteur))}</span></div>
                    <div class="v-montant">{format_montant(montant)}</div>
                </li>"""
            plan_html = f'<ul class="virements-list">{lignes_v}</ul>'
            plan_lede = f"{len(virements)} virement(s) suffisent pour tout solder."

        # Tableau des dépenses du groupe
        tableau_depenses = ""
        for d in sorted(g.depenses, key=lambda x: x.date, reverse=True):
            benefs_str = ", ".join(b.nom for b in d.beneficiaires)
            desc = d.description or "—"
            cat = d.categorie.strip().capitalize() or "Général"
            stat_pill = ('<span class="status-pill ok">Soldée</span>' if d.soldee
                         else '<span class="status-pill warn">Non soldée</span>')
            stat_key = "soldee" if d.soldee else "non"
            search_str = f"{d.id} {d.date} {_fmt_date(d.date)} {cat} {desc} {d.payeur.nom} {benefs_str}".lower()
            tableau_depenses += f"""
            <tr data-statut="{stat_key}" data-search="{esc(search_str, quote=True)}">
                <td>#{d.id}</td>
                <td>{esc(_fmt_date(d.date))}</td>
                <td><span class="tag">{esc(cat)}</span></td>
                <td>{esc(desc)}</td>
                <td><strong>{esc(d.payeur.nom)}</strong></td>
                <td style="color:var(--muted); font-size:0.8rem;">{esc(benefs_str)}</td>
                <td class="num">{format_montant(d.montant)}</td>
                <td>{stat_pill}</td>
            </tr>"""

        # JS Graphiques du groupe
        cat_labels = list(par_cat.keys())
        cat_values = [v / 1000 for v in par_cat.values()]
        mois_labels = sorted(par_mois.keys())
        mois_values = [par_mois[m] / 1000 for m in mois_labels]

        group_charts_js.append(f"""
        mk('catChart_{idx}', function () {{
            return {{
                type: 'doughnut',
                data: {{
                    labels: {json.dumps(cat_labels, ensure_ascii=False)},
                    datasets: [{{ data: {json.dumps(cat_values)}, backgroundColor: palette(), borderColor: css('--surface'), borderWidth: 2 }}]
                }},
                options: {{ responsive: true, maintainAspectRatio: false, plugins: {{ legend: {{ position: 'bottom' }} }} }}
            }};
        }});
        mk('moisChart_{idx}', function () {{
            return {{
                type: 'bar',
                data: {{
                    labels: {json.dumps([_fmt_mois(m) for m in mois_labels], ensure_ascii=False)},
                    datasets: [{{ label: 'Dépensé', data: {json.dumps(mois_values)}, backgroundColor: css('--brand'), borderRadius: 6 }}]
                }},
                options: {{
                    responsive: true, maintainAspectRatio: false, plugins: {{ legend: {{ display: false }} }},
                    scales: {{ y: {{ beginAtZero: true }}, x: {{ grid: {{ display: false }} }} }}
                }}
            }};
        }});""")

        badge_groupe_eq = ('<span class="pill ok">' + IC_CHECK + ' Équilibré</span>'
                           if equilibre else '<span class="pill ko">' + IC_X + ' Déséquilibré</span>')

        group_panes_html += f"""
        <section class="tab-pane" id="pane_group_{idx}" {'hidden' if not (is_active and len(groupes) == 1) else ''}>
            <header class="page-header">
                <div>
                    <h1 class="page-title">{esc(g.nom)}</h1>
                    <p class="page-subtitle">{len(g.membres)} membres • {len(g.depenses)} dépenses</p>
                </div>
                <div>{badge_groupe_eq}</div>
            </header>

            <div class="kpis" style="margin-top:20px;">
                <div class="kpi">
                    <div class="kpi-label">{IC_DOLLAR} Total Dépensé</div>
                    <div class="kpi-value">{format_montant(total_g)}</div>
                    <div class="kpi-sub">{len(g.depenses)} dépense(s) au total</div>
                </div>
                <div class="kpi">
                    <div class="kpi-label">{IC_ARROW} Virements à effectuer</div>
                    <div class="kpi-value">{len(virements)}</div>
                    <div class="kpi-sub">Plan optimisé (≤ {max(0, len(g.membres)-1)})</div>
                </div>
                <div class="kpi">
                    <div class="kpi-label">{IC_BARS} Non Soldées</div>
                    <div class="kpi-value" style="color: {'var(--warn)' if nb_non_soldees > 0 else 'var(--pos)'};">
                        {nb_non_soldees}
                    </div>
                    <div class="kpi-sub">sur {len(g.depenses)} enregistrées</div>
                </div>
                <div class="kpi">
                    <div class="kpi-label">{IC_USERS} Membres</div>
                    <div class="kpi-value">{len(g.membres)}</div>
                    <div class="kpi-sub">{esc(", ".join(m.nom for m in g.membres))}</div>
                </div>
            </div>

            <div class="layout-two" style="margin-top:24px;">
                <div class="plan-card">
                    <div class="panel-head">
                        <div>
                            <h2 class="panel-title">Qui paie qui</h2>
                            <p class="panel-lede">{plan_lede}</p>
                        </div>
                    </div>
                    {plan_html}
                </div>

                <div class="panel">
                    <div class="panel-head">
                        <div>
                            <h2 class="panel-title">Soldes individuels</h2>
                            <p class="panel-lede">Vert (+) : à recevoir | Rouge : à payer</p>
                        </div>
                    </div>
                    <ul class="soldes-list">{soldes_html}</ul>
                </div>
            </div>

            <div class="charts-grid" style="margin-top:24px;">
                <div class="panel">
                    <div class="panel-head"><h2 class="panel-title">Dépenses par catégorie</h2></div>
                    <div class="chart-box"><canvas id="catChart_{idx}"></canvas></div>
                </div>
                <div class="panel">
                    <div class="panel-head"><h2 class="panel-title">Évolution par mois</h2></div>
                    <div class="chart-box"><canvas id="moisChart_{idx}"></canvas></div>
                </div>
            </div>

            <div class="panel" style="margin-top:24px;">
                <div class="panel-head"><h2 class="panel-title">Historique des dépenses</h2></div>
                <div class="tools">
                    <div class="search-box">
                        {IC_SEARCH}
                        <input type="search" class="search-input" placeholder="Rechercher une description, un payeur, une date…" autocomplete="off">
                    </div>
                    <div class="seg" role="group">
                        <button type="button" data-filtre="all" aria-pressed="true">Toutes ({len(g.depenses)})</button>
                        <button type="button" data-filtre="non" aria-pressed="false">Non soldées ({nb_non_soldees})</button>
                        <button type="button" data-filtre="soldee" aria-pressed="false">Soldées ({nb_soldees})</button>
                    </div>
                </div>
                <p class="compteur-texte" style="color:var(--muted); font-size:0.825rem; margin-bottom:12px;"></p>
                <div class="table-wrap">
                    <table>
                        <thead>
                            <tr>
                                <th>N°</th>
                                <th>Date</th>
                                <th>Catégorie</th>
                                <th>Description</th>
                                <th>Payeur</th>
                                <th>Bénéficiaires</th>
                                <th class="num">Montant</th>
                                <th>Statut</th>
                            </tr>
                        </thead>
                        <tbody>{tableau_depenses}</tbody>
                    </table>
                </div>
            </div>
        </section>"""

    # Assemblage JavaScript
    js_content = (_JS
                  .replace("__COMP_LABELS__", json.dumps(group_labels, ensure_ascii=False))
                  .replace("__COMP_DATA__", json.dumps(group_totals_tnd))
                  .replace("__GROUP_CHARTS_INIT__", "\n".join(group_charts_js)))

    # Vue Comparatif (si plusieurs groupes ou par défaut)
    overview_pane_html = f"""
    <section class="tab-pane" id="pane_overview" {'hidden' if len(groupes) == 1 else ''}>
        <header class="page-header">
            <div>
                <h1 class="page-title">Synthèse Multi-Groupes</h1>
                <p class="page-subtitle">Vue d'ensemble et comparatif financier de vos {len(groupes)} groupes</p>
            </div>
            <div class="pill neutral">{len(groupes)} Groupes Enregistrés</div>
        </header>

        <div class="kpis" style="margin-top:20px;">
            <div class="kpi">
                <div class="kpi-label">{IC_DOLLAR} Total Cumulé Tous Groupes</div>
                <div class="kpi-value">{format_montant(total_global_millimes)}</div>
                <div class="kpi-sub">{nb_global_depenses} dépenses au total</div>
            </div>
            <div class="kpi">
                <div class="kpi-label">{IC_LAYERS} Groupes Actifs</div>
                <div class="kpi-value">{len(groupes)}</div>
                <div class="kpi-sub">Colocation, voyages, événements...</div>
            </div>
            <div class="kpi">
                <div class="kpi-label">{IC_USERS} Total Membres</div>
                <div class="kpi-value">{nb_global_membres}</div>
                <div class="kpi-sub">Participants enregistrés</div>
            </div>
            <div class="kpi">
                <div class="kpi-label">{IC_ARROW} Virements Restants</div>
                <div class="kpi-value">{nb_global_virements}</div>
                <div class="kpi-sub">Sur tous les groupes</div>
            </div>
        </div>

        <div class="charts-grid" style="margin-top:24px;">
            <div class="panel">
                <div class="panel-head"><h2 class="panel-title">Dépenses par Groupe (TND)</h2></div>
                <div class="chart-box"><canvas id="compBarChart"></canvas></div>
            </div>
            <div class="panel">
                <div class="panel-head"><h2 class="panel-title">Part de chaque Groupe</h2></div>
                <div class="chart-box"><canvas id="compPieChart"></canvas></div>
            </div>
        </div>

        <div style="margin-top:24px;">
            <div class="panel-head"><h2 class="panel-title">Détail des Groupes</h2></div>
            <div class="groups-grid">{cards_comparatif_html}</div>
        </div>

        <div class="panel" style="margin-top:24px;">
            <div class="panel-head"><h2 class="panel-title">Tableau Comparatif Global</h2></div>
            <div class="table-wrap">
                <table>
                    <thead>
                        <tr>
                            <th>Groupe</th>
                            <th>État Soldes</th>
                            <th>Membres</th>
                            <th>Dépenses</th>
                            <th class="num">Montant Total</th>
                            <th class="num">Action</th>
                        </tr>
                    </thead>
                    <tbody>{table_comparatif_html}</tbody>
                </table>
            </div>
        </div>
    </section>"""

    html = f"""<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <meta name="color-scheme" content="light dark">
    <title>Dépenses Partagées — Tableau de Bord</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
    <style>{_CSS}</style>
</head>
<body>
    <nav class="navbar">
        <div class="nav-wrap">
            <a href="#" class="brand">
                <div class="brand-logo">{IC_DOLLAR}</div>
                <div>
                    <div class="brand-name">Dépenses Partagées</div>
                    <div class="brand-tag">Tableau de Bord Multi-Groupes • {maintenant}</div>
                </div>
            </a>
            <div class="nav-tools">
                <button type="button" class="btn-icon" id="themeToggle" title="Basculer le mode sombre / clair">
                    {IC_MOON}
                </button>
                <button type="button" class="btn-text" onclick="window.print()">
                    {IC_PRINT} Imprimer / PDF
                </button>
            </div>
        </div>
    </nav>

    <div class="tabs-container">
        <div class="tabs-list" role="tablist">
            {tabs_html}
        </div>
    </div>

    <main class="main-wrap">
        {overview_pane_html}
        {group_panes_html}
    </main>

    <script>{js_content}</script>
</body>
</html>
"""
    return html


def exporter_dashboard_html(groupe_ou_liste, chemin: str = "dashboard.html", ouvrir: bool = True, dossier_groupes: str = "groupes") -> str:
    """F14 BONUS : Exporte le dashboard HTML multi-groupes et l'ouvre dans le navigateur web."""
    html = generer_dashboard_html(groupe_ou_liste, dossier_groupes=dossier_groupes)
    with open(chemin, "w", encoding="utf-8") as f:
        f.write(html)
    if ouvrir:
        webbrowser.open("file://" + os.path.abspath(chemin))
    return chemin