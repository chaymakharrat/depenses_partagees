#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
main.py — Point d'entrée et menu interactif de l'application Dépenses Partagées.

Structure du projet :
    noyau.py      → Classes de données + toute la logique métier
    extras.py     → Statistiques, graphiques en barres, export CSV/TXT
    test_noyau.py → Suite de tests unitaires (14 tests)
    main.py       → Menu interactif (ce fichier)

Lancement :
    python main.py          → démarre l'application
    python test_noyau.py    → lance les tests
"""

import os
from datetime import datetime

from noyau import (
    Groupe,
    ajouter_depense,
    ajouter_membre,
    calculer_soldes,
    charger_groupe,
    creer_filtre,
    creer_groupe,
    filtrer_depenses,
    format_montant,
    lister_membres,
    marquer_soldees,
    modifier_depense,
    sauvegarder_groupe,
    supprimer_depense,
    supprimer_membre,
    trier_depenses,
    verifier_soldes,
)
from extras import (
    afficher_bilan,
    afficher_statistiques,
    exporter_bilan_csv,
    exporter_bilan_txt,
)

FICHIER_JSON = "groupe.json"


# ==============================================================================
# AFFICHAGE
# ==============================================================================

def afficher_tableau_depenses(depenses: list) -> None:
    """Affiche une liste de dépenses sous forme de tableau lisible."""
    if not depenses:
        print("\n  Aucune dépense trouvée.")
        return
    sep = "-" * 100
    print(f"\n{sep}")
    print(f"  {'ID':<4} {'Date':<12} {'Montant':>13} {'Payeur':<13} "
          f"{'Catégorie':<13} {'Bénéficiaires':<18} Description")
    print(sep)
    for d in depenses:
        benefs = ", ".join(b.nom for b in d.beneficiaires)
        if len(benefs) > 18:
            benefs = benefs[:15] + "..."
        marque = " [soldée]" if d.soldee else ""
        print(f"  #{d.id:<3} {d.date:<12} {format_montant(d.montant):>13} "
              f"{d.payeur.nom:<13} {d.categorie:<13} {benefs:<18} {d.description}{marque}")
    print(sep)


# ==============================================================================
# DIALOGUES DE SAISIE (un par fonctionnalité)
# ==============================================================================

def dialogue_ajouter_membre(groupe: Groupe) -> None:
    """Dialogue pour ajouter un membre."""
    nom = input("  Nom du nouveau membre : ").strip()
    nouveau = ajouter_membre(groupe, nom)
    sauvegarder_groupe(groupe, FICHIER_JSON)
    print(f"  ✔ Membre '{nouveau.nom}' ajouté.")


def dialogue_supprimer_membre(groupe: Groupe) -> None:
    """Dialogue pour supprimer un membre (refusé s'il a des dépenses non soldées)."""
    membres = lister_membres(groupe)
    if not membres:
        print("  Aucun membre dans ce groupe.")
        return
    print(f"  Membres : {', '.join(membres)}")
    nom = input("  Nom du membre à supprimer : ").strip()
    supprime = supprimer_membre(groupe, nom)   # lève ValueError si dépense non soldée
    sauvegarder_groupe(groupe, FICHIER_JSON)
    print(f"  ✔ Membre '{supprime.nom}' supprimé.")


def dialogue_ajouter_depense(groupe: Groupe) -> None:
    """Dialogue pour saisir et enregistrer une dépense."""
    if not groupe.membres:
        print("  Ajoutez d'abord des membres avant d'enregistrer une dépense.")
        return

    print(f"\n  Membres disponibles : {', '.join(lister_membres(groupe))}")
    date_def = datetime.now().strftime("%Y-%m-%d")
    date_s   = input(f"  Date AAAA-MM-JJ [défaut : {date_def}] : ").strip() or date_def
    montant_s = input("  Montant en TND (ex: 12.5 ou 12,500) : ").strip()
    payeur    = input("  Nom du payeur : ").strip()

    benef_s = input("  Bénéficiaires (virgule) [défaut : tous] : ").strip()
    beneficiaires = [b.strip() for b in benef_s.split(",") if b.strip()] if benef_s else None

    categorie   = input("  Catégorie [défaut : Général] : ").strip() or "Général"
    description = input("  Description : ").strip()

    dep = ajouter_depense(groupe, date_s, montant_s, payeur,
                          beneficiaires, categorie, description)
    sauvegarder_groupe(groupe, FICHIER_JSON)
    print(f"  ✔ Dépense #{dep.id} enregistrée ({format_montant(dep.montant)}).")


def dialogue_modifier_depense(groupe: Groupe) -> None:
    """Dialogue pour modifier une dépense existante."""
    if not groupe.depenses:
        print("  Aucune dépense à modifier.")
        return
    afficher_tableau_depenses(groupe.depenses)
    try:
        dep_id = int(input("  ID de la dépense à modifier : ").strip())
    except ValueError:
        print("  ID invalide.")
        return

    dep = next((d for d in groupe.depenses if d.id == dep_id), None)
    if not dep:
        print(f"  Dépense #{dep_id} introuvable.")
        return

    print("  (Laisser vide = conserver la valeur actuelle)")
    new_date     = input(f"  Date [{dep.date}] : ").strip() or None
    new_montant  = input(f"  Montant [{format_montant(dep.montant)}] : ").strip() or None
    new_payeur   = input(f"  Payeur [{dep.payeur.nom}] : ").strip() or None
    benef_act    = ", ".join(b.nom for b in dep.beneficiaires)
    benef_s      = input(f"  Bénéficiaires [{benef_act}] : ").strip()
    new_benefs   = [b.strip() for b in benef_s.split(",") if b.strip()] if benef_s else None
    new_cat      = input(f"  Catégorie [{dep.categorie}] : ").strip() or None
    new_desc     = input(f"  Description [{dep.description}] : ").strip() or None

    dep = modifier_depense(groupe, dep_id, new_date, new_montant,
                           new_payeur, new_benefs, new_cat, new_desc)
    sauvegarder_groupe(groupe, FICHIER_JSON)
    print(f"  ✔ Dépense #{dep.id} modifiée.")


def dialogue_supprimer_depense(groupe: Groupe) -> None:
    """Dialogue pour supprimer une dépense."""
    afficher_tableau_depenses(groupe.depenses)
    try:
        dep_id = int(input("  ID de la dépense à supprimer : ").strip())
    except ValueError:
        print("  ID invalide.")
        return
    dep = supprimer_depense(groupe, dep_id)
    sauvegarder_groupe(groupe, FICHIER_JSON)
    print(f"  ✔ Dépense #{dep.id} ({format_montant(dep.montant)}) supprimée.")


def dialogue_lister_depenses(groupe: Groupe) -> None:
    """Dialogue pour lister, filtrer et trier les dépenses."""
    if not groupe.depenses:
        print("  Aucune dépense enregistrée.")
        return

    # --- Filtrage (fermeture / closure) ---
    print("\n  Filtrer les dépenses (laisser vide = pas de filtre) :")
    cat   = input("  Catégorie : ").strip() or None
    mem   = input("  Membre (payeur ou bénéficiaire) : ").strip() or None
    debut = input("  Date de début AAAA-MM-JJ : ").strip() or None
    fin   = input("  Date de fin   AAAA-MM-JJ : ").strip() or None

    filtre_fn = creer_filtre(categorie=cat, membre=mem, date_debut=debut, date_fin=fin)
    depenses_filtrees = filtrer_depenses(groupe.depenses, filtre_fn)
    print(f"  → {len(depenses_filtrees)} dépense(s) retenue(s).")

    # --- Tri ---
    print("\n  Tri : 1=date↓  2=date↑  3=montant↓  4=montant↑  [1]")
    choix_tri = input("  Votre choix : ").strip() or "1"
    cle, dec = "date", True
    if choix_tri == "2": cle, dec = "date",    False
    elif choix_tri == "3": cle, dec = "montant", True
    elif choix_tri == "4": cle, dec = "montant", False

    afficher_tableau_depenses(trier_depenses(depenses_filtrees, cle=cle, decroissant=dec))


def dialogue_marquer_soldees(groupe: Groupe) -> None:
    """« J'ai réglé les virements » : passe toutes les dépenses à soldée (après confirmation)."""
    nb = sum(1 for d in groupe.depenses if not d.soldee)
    if nb == 0:
        print("  Aucune dépense non soldée.")
        return
    afficher_bilan(groupe)
    rep = input(f"\n  Confirmer : marquer {nb} dépense(s) comme soldées ? (o/N) : ").strip().lower()
    if rep in ("o", "oui"):
        marquer_soldees(groupe)
        sauvegarder_groupe(groupe, FICHIER_JSON)
        print(f"  ✔ {nb} dépense(s) marquée(s) comme soldées. Tous les soldes sont à 0.")
    else:
        print("  Annulé.")


def dialogue_exporter(groupe: Groupe) -> None:
    """Dialogue pour exporter le bilan (CSV ou TXT)."""
    print("\n  Format : 1=CSV  2=TXT  [1]")
    choix = input("  Votre choix : ").strip() or "1"
    if choix == "2":
        chemin = input("  Chemin [bilan.txt] : ").strip() or "bilan.txt"
        exporter_bilan_txt(groupe, chemin)
        print(f"  ✔ Bilan TXT exporté dans '{chemin}'.")
    else:
        chemin = input("  Chemin [bilan.csv] : ").strip() or "bilan.csv"
        exporter_bilan_csv(groupe, chemin)
        print(f"  ✔ Bilan CSV exporté dans '{chemin}'.")


def dialogue_creer_groupe() -> Groupe:
    """Dialogue pour créer un nouveau groupe vide (F1)."""
    nom = input("  Nom du nouveau groupe (ex: Colocation, Voyage...) : ").strip()
    nouveau_groupe = creer_groupe(nom)
    sauvegarder_groupe(nouveau_groupe, FICHIER_JSON)
    print(f"  ✔ Nouveau groupe '{nouveau_groupe.nom}' créé et sauvegardé.")
    return nouveau_groupe


def dialogue_renommer_groupe(groupe: Groupe) -> None:
    """Dialogue pour renommer le groupe actuel."""
    nom = input(f"  Nouveau nom pour '{groupe.nom}' : ").strip()
    if not nom:
        raise ValueError("Le nom ne peut pas être vide.")
    groupe.nom = nom
    sauvegarder_groupe(groupe, FICHIER_JSON)
    print(f"  ✔ Groupe renommé en '{groupe.nom}'.")


# ==============================================================================
# MENU PRINCIPAL
# ==============================================================================

def afficher_menu(groupe: Groupe) -> None:
    """Affiche le menu principal avec toutes les fonctionnalités F1 à F16."""
    soldes = calculer_soldes(groupe)
    equilibre = "✔ Équilibré" if verifier_soldes(soldes) else "✖ Déséquilibré"
    nb_non_soldees = sum(1 for d in groupe.depenses if not d.soldee)
    print("\n" + "=" * 58)
    print(f"  DÉPENSES PARTAGÉES — GROUPE : {groupe.nom.upper()}")
    print(f"  {len(groupe.membres)} membre(s) | "
          f"{len(groupe.depenses)} dépense(s) ({nb_non_soldees} non soldée(s)) | {equilibre}")
    print("=" * 58)
    print("  GESTION DU GROUPE")
    print("   1. Créer / Ajouter un nouveau groupe")
    print("   2. Renommer le groupe actuel")
    print("  MEMBRES")
    print("   3. Lister les membres")
    print("   4. Ajouter un membre")
    print("   5. Supprimer un membre")
    print("  DÉPENSES")
    print("   6. Lister / filtrer / trier les dépenses")
    print("   7. Ajouter une dépense")
    print("   8. Modifier une dépense")
    print("   9. Supprimer une dépense")
    print("  BILAN & RÈGLEMENT")
    print("  10. Consulter soldes et plan de règlement")
    print("  11. Statistiques et graphiques textuels")
    print("  12. Marquer les dépenses comme réglées (soldées)")
    print("  EXPORT & TESTS")
    print("  13. Exporter le bilan (CSV / TXT)")
    print("  14. Lancer la suite de tests unitaires")
    print("   0. Quitter")
    print("=" * 58)


def boucle_principale() -> None:
    """Boucle principale : charge les données, affiche le menu, gère les actions."""
    # Chargement ou création du groupe
    if os.path.exists(FICHIER_JSON):
        try:
            groupe = charger_groupe(FICHIER_JSON)
            print(f"\n  Groupe '{groupe.nom}' chargé "
                  f"({len(groupe.membres)} membres, {len(groupe.depenses)} dépenses).")
        except Exception as e:
            print(f"  Erreur de chargement : {e} → nouveau groupe créé.")
            groupe = creer_groupe("Colocation")
            sauvegarder_groupe(groupe, FICHIER_JSON)
    else:
        print("=== APPLICATION DÉPENSES PARTAGÉES ===")
        nom = input("Nom du groupe [Colocation] : ").strip() or "Colocation"
        groupe = creer_groupe(nom)
        sauvegarder_groupe(groupe, FICHIER_JSON)
        print(f"  Groupe '{groupe.nom}' créé.")

    while True:
        try:
            afficher_menu(groupe)
            choix = input("  Votre choix (0–14) : ").strip()

            if choix == "0":
                sauvegarder_groupe(groupe, FICHIER_JSON)
                print("  Données sauvegardées. Au revoir !")
                break

            elif choix == "1":
                groupe = dialogue_creer_groupe()

            elif choix == "2":
                dialogue_renommer_groupe(groupe)

            elif choix == "3":
                membres = lister_membres(groupe)
                if membres:
                    soldes = calculer_soldes(groupe)
                    print(f"\n  Membres du groupe '{groupe.nom}' ({len(membres)}) :")
                    for i, m in enumerate(membres, 1):
                        print(f"    {i}. {m:<15} ({format_montant(soldes.get(m, 0))})")
                else:
                    print("  Aucun membre dans ce groupe.")

            elif choix == "4":
                dialogue_ajouter_membre(groupe)

            elif choix == "5":
                dialogue_supprimer_membre(groupe)

            elif choix == "6":
                dialogue_lister_depenses(groupe)

            elif choix == "7":
                dialogue_ajouter_depense(groupe)

            elif choix == "8":
                dialogue_modifier_depense(groupe)

            elif choix == "9":
                dialogue_supprimer_depense(groupe)

            elif choix == "10":
                afficher_bilan(groupe)

            elif choix == "11":
                afficher_statistiques(groupe)

            elif choix == "12":
                dialogue_marquer_soldees(groupe)

            elif choix == "13":
                dialogue_exporter(groupe)

            elif choix == "14":
                from test_noyau import lancer_tous_les_tests
                lancer_tous_les_tests()

            else:
                print("  Choix invalide. Entrez un numéro entre 0 et 14.")

        except (KeyboardInterrupt, EOFError):
            print("\n\n  Interruption. Sauvegarde automatique...")
            sauvegarder_groupe(groupe, FICHIER_JSON)
            print("  À bientôt !")
            break
        except ValueError as e:
            print(f"\n  [!] {e}")
        except Exception as e:
            print(f"\n  [!] Erreur inattendue : {type(e).__name__}: {e}")


# ==============================================================================
# POINT D'ENTRÉE
# ==============================================================================

if __name__ == "__main__":
    boucle_principale()