#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
extras.py — Statistiques, graphiques textuels et exportation du bilan.

Fonctionnalités :
    F13 : afficher_statistiques() — total par membre (payé et part due),
          par catégorie (avec %), par mois ; graphiques en barres textuelles.
    F14 : generer_bilan_texte()  — synthèse complète (soldes + virements)
          afficher_bilan()       — affichage à l'écran
          exporter_bilan_txt()   — export en fichier .txt
          exporter_bilan_csv()   — export en fichier .csv (UTF-8 avec BOM,
                                   pour un affichage correct des accents dans Excel)

Dépend uniquement de noyau.py (aucune entrée utilisateur ici).
"""

import csv
from collections import defaultdict

from noyau import (
    Groupe,
    calculer_soldes,
    format_montant,
    regler,
    repartir_depense,
    trouver_membre,
    verifier_soldes,
)


# ==============================================================================
# F13 — STATISTIQUES ET GRAPHIQUES TEXTUELS
# ==============================================================================

def dessiner_barre(valeur: int, valeur_max: int, largeur_max: int = 20) -> str:
    """Génère une jauge fine et élégante (style barre de progression)

    Utilise des blocs calibrés ('▰' rempli, '▱' vide) qui ne fusionnent pas
    verticalement d'une ligne à l'autre dans le terminal.
    """
    if valeur_max <= 0 or valeur <= 0:
        return "▱" * largeur_max
    nb = min(largeur_max, max(1, (valeur * largeur_max) // valeur_max))
    reste = largeur_max - nb
    return "▰" * nb + "▱" * reste


def afficher_statistiques(groupe: Groupe) -> None:
    """F13 : Affiche les statistiques détaillées avec graphiques en barres texte.

    Les statistiques portent sur TOUTES les dépenses (soldées ou non).
    Affiche :
      - Par membre : montant payé (avancé), % du total, et part due
      - Total par catégorie (montant + % du total global)
      - Total par mois AAAA-MM (montant + % du total global)
    """
    if not groupe.depenses:
        print("\nAucune dépense enregistrée. Statistiques indisponibles.")
        return

    total_general = sum(d.montant for d in groupe.depenses)

    # --- 1. Par membre : payé (avancé) et dû (part de chaque dépense) ---
    total_par_membre: dict[str, int] = {m.nom: 0 for m in groupe.membres}
    du_par_membre: dict[str, int] = {m.nom: 0 for m in groupe.membres}
    for d in groupe.depenses:
        m_p = trouver_membre(groupe, d.payeur)
        nom = m_p.nom if m_p else d.payeur.nom
        total_par_membre[nom] = total_par_membre.get(nom, 0) + d.montant
        du_par_membre.setdefault(nom, 0)

        for nom_b, part in repartir_depense(d.montant, d.beneficiaires).items():
            m_b = trouver_membre(groupe, nom_b)
            nom_c = m_b.nom if m_b else nom_b
            du_par_membre[nom_c] = du_par_membre.get(nom_c, 0) + part
            total_par_membre.setdefault(nom_c, 0)

    # --- 2. Par catégorie ---
    total_par_cat: dict[str, int] = defaultdict(int)
    for d in groupe.depenses:
        cat = d.categorie.strip().capitalize() or "Général"
        total_par_cat[cat] += d.montant

    # --- 3. Par mois (AAAA-MM) ---
    total_par_mois: dict[str, int] = defaultdict(int)
    for d in groupe.depenses:
        total_par_mois[d.date[:7]] += d.montant

    def pct_str(montant: int) -> str:
        """Calcule le pourcentage du total avec 1 décimale (sans float)."""
        if total_general <= 0:
            return "  0.0%"
        dixieme = (montant * 1000) // total_general
        return f"{dixieme // 10}.{dixieme % 10}%"

    print("\n" + "=" * 78)
    print(f"  STATISTIQUES — GROUPE : {groupe.nom.upper()}")
    print("=" * 78)
    print(f"  Nombre de dépenses : {len(groupe.depenses)}")
    print(f"  Montant total      : {format_montant(total_general)}")

    # Affichage par membre
    print("\n  ── TOTAL PAR MEMBRE (payé = avancé ; dû = part de chaque dépense) ──")
    max_m = max(total_par_membre.values(), default=0)
    for nom, m in sorted(total_par_membre.items(), key=lambda x: (-x[1], x[0].casefold())):
        barre = dessiner_barre(m, max_m, 20)
        du = du_par_membre.get(nom, 0)
        print(f"  {nom:<12} payé {format_montant(m):>12} ({pct_str(m):>6})  "
              f"dû {format_montant(du):>12}  {barre}")

    # Affichage par catégorie
    print("\n  ── TOTAL PAR CATÉGORIE ────────────────────────────────────")
    max_c = max(total_par_cat.values(), default=0)
    for cat, m in sorted(total_par_cat.items(), key=lambda x: (-x[1], x[0].casefold())):
        barre = dessiner_barre(m, max_c, 22)
        print(f"  {cat:<15} {format_montant(m):>12}  ({pct_str(m):>6})  {barre}")

    # Affichage par mois
    print("\n  ── TOTAL PAR MOIS ─────────────────────────────────────────")
    max_mois = max(total_par_mois.values(), default=0)
    for mois in sorted(total_par_mois):
        m = total_par_mois[mois]
        barre = dessiner_barre(m, max_mois, 22)
        print(f"  {mois:<15} {format_montant(m):>12}  ({pct_str(m):>6})  {barre}")

    print("=" * 78)


# ==============================================================================
# F14 — BILAN DE RÈGLEMENT (texte, TXT, CSV)
# ==============================================================================

def generer_bilan_texte(groupe: Groupe) -> str:
    """Génère la synthèse complète des soldes individuels et du plan de règlement.

    Les soldes portent sur les dépenses non soldées uniquement.
    """
    soldes = calculer_soldes(groupe)
    equilibre = verifier_soldes(soldes)
    virements = regler(soldes)
    nb_non_soldees = sum(1 for d in groupe.depenses if not d.soldee)

    lignes = [
        "=" * 62,
        f"  BILAN DE RÈGLEMENT — {groupe.nom.upper()}",
        "=" * 62,
        f"  Dépenses non soldées prises en compte : {nb_non_soldees} "
        f"sur {len(groupe.depenses)}",
        "",
        "  ── SOLDES INDIVIDUELS ──────────────────────────────────────",
    ]

    for nom, solde in sorted(soldes.items(), key=lambda x: x[0].casefold()):
        statut = "Créditeur ✚" if solde > 0 else ("Débiteur  ✖" if solde < 0 else "Équilibré ○")
        lignes.append(f"  {nom:<15} {format_montant(solde):>12}   {statut}")

    somme = sum(soldes.values())
    lignes.append(f"\n  Somme de contrôle : {format_montant(somme)}  "
                  f"{'✔ Équilibrée' if equilibre else '✖ DÉSÉQUILIBRÉE'}")

    lignes.append("\n  ── PLAN DE RÈGLEMENT (VIREMENTS SUGGÉRÉS) ───────────────")
    if not virements:
        lignes.append("  Aucun virement nécessaire (tous les membres sont à l'équilibre).")
    else:
        for i, v in enumerate(virements, 1):
            debiteur, crediteur, montant_v = v   # tuple (débiteur, créditeur, montant)
            lignes.append(
                f"  {i}. {debiteur} → {crediteur}  :  {format_montant(montant_v)}"
            )
        max_v = max(0, len(groupe.membres) - 1)
        lignes.append(f"\n  Nombre de virements : {len(virements)} (≤ {max_v})")

    lignes.append("=" * 62)
    return "\n".join(lignes)


def afficher_bilan(groupe: Groupe) -> None:
    """Affiche le bilan de règlement à l'écran."""
    print("\n" + generer_bilan_texte(groupe))


def exporter_bilan_txt(groupe: Groupe, chemin: str = "bilan.txt") -> str:
    """F14 : Exporte le bilan complet au format texte brut (.txt)."""
    with open(chemin, "w", encoding="utf-8") as f:
        f.write(generer_bilan_texte(groupe))
    return chemin


def exporter_bilan_csv(groupe: Groupe, chemin: str = "bilan.csv") -> str:
    """F14 : Exporte soldes et virements au format CSV.

    Encodage UTF-8 avec BOM (utf-8-sig) : Excel affiche ainsi correctement
    les accents (Débiteur, Créditeur...).
    """
    soldes = calculer_soldes(groupe)
    virements = regler(soldes)

    with open(chemin, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(["Section", "Membre / Débiteur", "Créditeur",
                         "Montant (millimes)", "Montant formaté"])
        for nom, solde in sorted(soldes.items(), key=lambda x: x[0].casefold()):
            writer.writerow(["Solde", nom, "", solde, format_montant(solde)])
        for v in virements:
            debiteur, crediteur, montant_v = v
            writer.writerow(["Virement", debiteur, crediteur,
                             montant_v, format_montant(montant_v)])
    return chemin


# ==============================================================================
# F14 BONUS — TABLEAU DE BORD WEB (délégué au module dédié web.py)
# ==============================================================================

# Re-export pour compatibilité
from web import exporter_dashboard_html, generer_dashboard_html
