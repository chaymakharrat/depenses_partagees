#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_noyau.py — Suite de tests unitaires pour le module noyau.py.

Chaque fonction test_*() est indépendante et peut être lancée avec :
    python test_noyau.py          (exécution directe)
    python -m pytest test_noyau.py -v  (avec pytest)

Cas couverts :
    1. Exemple du cahier des charges (Ali 90 TND → +60/−30/−30, 2 virements)
    2. Groupe d'un seul membre (solde 0, aucun virement)
    3. Répartition 100 TND entre 3 (arrondi documenté : +1 millime à Ali)
    4. Nom de membre en doublon refusé (insensible à la casse)
    5. Suppression refusée si le membre figure dans une dépense non soldée ★
    6. Suppression autorisée une fois les dépenses soldées ★
    7. Validations : dates invalides, montants ≤ 0, membres inconnus
    8. Fermetures : filtrage par catégorie, membre, période, combiné + filtres nommés
    9. Sauvegarde et rechargement JSON (données identiques, champ soldee compris)
   10. Parsing et formatage des montants (dont chiffres non ASCII refusés)
   11. Plusieurs dépenses croisées (règlement minimal)
   12. verifier_soldes : somme nulle avec tolérance 10 millimes
   13. marquer_soldees : les soldes repassent à 0, aucun virement
   14. Méthodes de la classe Groupe (façades du diagramme de classes)
"""

import os

from noyau import (
    ajouter_depense,
    ajouter_membre,
    calculer_soldes,
    charger_groupe,
    creer_filtre,
    creer_groupe,
    filtre_categorie,
    filtre_membre,
    filtre_periode,
    filtrer_depenses,
    format_montant,
    marquer_soldees,
    parse_montant,
    repartir_depense,
    regler,
    sauvegarder_groupe,
    supprimer_depense,
    supprimer_membre,
    trier_depenses,
    verifier_soldes,
)


# ==============================================================================
# TESTS
# ==============================================================================

def test_exemple_cahier_des_charges():
    """Test 1 : Ali paie 90 TND pour Ali, Sara, Omar → +60/−30/−30, 2 virements."""
    g = creer_groupe("Coloc Test")
    ajouter_membre(g, "Ali")
    ajouter_membre(g, "Sara")
    ajouter_membre(g, "Omar")
    ajouter_depense(g, "2026-11-01", 90000, "Ali", ["Ali", "Sara", "Omar"], "Courses")

    s = calculer_soldes(g)
    assert s["Ali"]  ==  60000, f"Ali : attendu +60000, obtenu {s['Ali']}"
    assert s["Sara"] == -30000, f"Sara : attendu -30000, obtenu {s['Sara']}"
    assert s["Omar"] == -30000, f"Omar : attendu -30000, obtenu {s['Omar']}"
    assert verifier_soldes(s)

    v = regler(s)
    assert len(v) == 2, f"Attendu 2 virements, obtenu {len(v)}"
    # Chaque virement est un tuple (débiteur, créditeur, montant)
    paires = {(vi[0], vi[1], vi[2]) for vi in v}
    assert paires == {("Sara", "Ali", 30000), ("Omar", "Ali", 30000)}
    print("✔ Test 1 : Exemple du cahier des charges validé.")


def test_groupe_un_seul_membre():
    """Test 2 : Groupe d'un seul membre — solde 0, aucun virement."""
    g = creer_groupe("Solo")
    ajouter_membre(g, "Ali")
    ajouter_depense(g, "2026-11-02", 50000, "Ali", ["Ali"], "Divers")

    s = calculer_soldes(g)
    assert s["Ali"] == 0, f"Ali solo : attendu 0, obtenu {s['Ali']}"
    assert verifier_soldes(s)
    assert regler(s) == []
    print("✔ Test 2 : Groupe d'un seul membre validé.")


def test_repartition_arrondi_100_entre_3():
    """Test 3 : 100 TND entre 3 → Ali +1 millime (ordre alphabétique)."""
    parts = repartir_depense(100000, ["Sara", "Ali", "Omar"])
    # Tri alpha : Ali, Omar, Sara → Ali reçoit le millime restant
    assert parts["Ali"]  == 33334, f"Ali : attendu 33334, obtenu {parts['Ali']}"
    assert parts["Omar"] == 33333, f"Omar : attendu 33333, obtenu {parts['Omar']}"
    assert parts["Sara"] == 33333, f"Sara : attendu 33333, obtenu {parts['Sara']}"
    assert sum(parts.values()) == 100000, "Somme des parts ≠ 100000"

    # Vérification via le groupe complet
    g = creer_groupe("Trio")
    ajouter_membre(g, "Ali"); ajouter_membre(g, "Omar"); ajouter_membre(g, "Sara")
    ajouter_depense(g, "2026-11-03", 100000, "Ali", ["Ali", "Omar", "Sara"])
    s = calculer_soldes(g)
    assert sum(s.values()) == 0, "La somme des soldes doit être nulle"
    assert verifier_soldes(s)
    print("✔ Test 3 : Répartition 100 TND entre 3 avec arrondi validée.")


def test_doublon_nom_refuse():
    """Test 4 : Le même nom (casse différente) est refusé."""
    g = creer_groupe("Test Doublon")
    ajouter_membre(g, "ali")
    try:
        ajouter_membre(g, "Ali")
        assert False, "Doublon aurait dû lever ValueError"
    except ValueError:
        pass
    print("✔ Test 4 : Doublon de nom refusé.")


def test_suppression_refusee_si_depense_non_soldee():
    """Test 5 ★ : Suppression refusée si le membre figure dans une dépense non soldée.

    Ali (payeur) et Sara (bénéficiaire) figurent dans la dépense #1 (soldee=False)
    → ni l'un ni l'autre ne peut être supprimé. Omar, absent de toute dépense,
    peut l'être.
    """
    g = creer_groupe("Test Non Soldée")
    ajouter_membre(g, "Ali")
    ajouter_membre(g, "Sara")
    ajouter_membre(g, "Omar")
    dep = ajouter_depense(g, "2026-11-04", 90000, "Ali", ["Ali", "Sara"])
    assert dep.soldee is False, "Une dépense est non soldée à la création"

    try:
        supprimer_membre(g, "Ali")
        assert False, "Ali (payeur, dépense non soldée) → suppression aurait dû être refusée"
    except ValueError as e:
        assert "non soldée" in str(e), f"Message d'erreur inattendu : {e}"

    try:
        supprimer_membre(g, "Sara")
        assert False, "Sara (bénéficiaire, dépense non soldée) → suppression aurait dû être refusée"
    except ValueError:
        pass

    # Omar ne figure dans aucune dépense : suppression autorisée
    assert supprimer_membre(g, "Omar").nom == "Omar"
    print("✔ Test 5 : Suppression refusée si dépense non soldée (R5).")


def test_suppression_autorisee_apres_reglement():
    """Test 6 ★ : Suppression autorisée une fois les dépenses soldées.

    Youssef paie 60 TND pour lui seul : la dépense est non soldée → refus.
    Après marquer_soldees() (« J'ai réglé les virements ») → suppression autorisée,
    et les soldes ne contiennent aucun membre fantôme.
    """
    g = creer_groupe("Test Après Règlement")
    ajouter_membre(g, "Ali")
    ajouter_membre(g, "Youssef")
    ajouter_depense(g, "2026-11-05", 60000, "Youssef", ["Youssef"])

    try:
        supprimer_membre(g, "Youssef")
        assert False, "Dépense non soldée → suppression aurait dû être refusée"
    except ValueError:
        pass

    assert marquer_soldees(g) == 1

    supprime = supprimer_membre(g, "Youssef")
    assert supprime.nom == "Youssef"
    assert "Youssef" not in [m.nom for m in g.membres]
    assert "Youssef" not in calculer_soldes(g), "Pas de membre fantôme dans les soldes"
    print("✔ Test 6 : Suppression autorisée après règlement des dépenses.")


def test_validations_date_montant_membres():
    """Test 7 : Rejet des dates invalides, montants ≤ 0 et membres inconnus."""
    g = creer_groupe("Test Validations")
    ajouter_membre(g, "Ali"); ajouter_membre(g, "Sara")

    # Dates invalides
    for date_err in ["2026-02-30", "01-11-2026", "2026/11/01", "texte", ""]:
        try:
            ajouter_depense(g, date_err, 10000, "Ali", ["Ali"])
            assert False, f"Date '{date_err}' aurait dû lever ValueError"
        except ValueError:
            pass

    # Montants invalides
    for m_err in [0, -1, -50000]:
        try:
            ajouter_depense(g, "2026-11-01", m_err, "Ali", ["Ali"])
            assert False, f"Montant {m_err} aurait dû lever ValueError"
        except ValueError:
            pass

    # parse_montant : valeurs invalides
    for p_err in ["12.1234", "abc", "-5", "12.3.4", ""]:
        try:
            parse_montant(p_err)
            assert False, f"parse_montant('{p_err}') aurait dû lever ValueError"
        except ValueError:
            pass

    # Payeur inconnu
    try:
        ajouter_depense(g, "2026-11-01", 10000, "Inconnu", ["Ali"])
        assert False, "Payeur inconnu → ValueError attendue"
    except ValueError:
        pass

    # Bénéficiaire inconnu
    try:
        ajouter_depense(g, "2026-11-01", 10000, "Ali", ["Inconnu"])
        assert False, "Bénéficiaire inconnu → ValueError attendue"
    except ValueError:
        pass

    # Aucun bénéficiaire
    try:
        ajouter_depense(g, "2026-11-01", 10000, "Ali", [])
        assert False, "Liste vide → ValueError attendue"
    except ValueError:
        pass

    print("✔ Test 7 : Toutes les validations rejettent les entrées invalides.")


def test_fermetures_filtrage():
    """Test 8 : Filtrage par catégorie, membre, période et combiné (closure)."""
    g = creer_groupe("Test Filtres")
    ajouter_membre(g, "Ali"); ajouter_membre(g, "Sara"); ajouter_membre(g, "Omar")
    d1 = ajouter_depense(g, "2026-10-05", 30000, "Ali",  ["Ali",  "Sara"],        "Courses",   "Légumes")
    d2 = ajouter_depense(g, "2026-10-15", 50000, "Sara", ["Sara", "Omar"],        "Transport", "Train")
    d3 = ajouter_depense(g, "2026-11-02", 40000, "Omar", ["Ali",  "Omar"],        "Courses",   "Supermarché")

    # Par catégorie
    res = filtrer_depenses(g.depenses, creer_filtre(categorie="courses"))
    assert [d.id for d in res] == [d1.id, d3.id]

    # Par membre
    res = filtrer_depenses(g.depenses, creer_filtre(membre="ali"))
    assert [d.id for d in res] == [d1.id, d3.id]

    # Par période inclusive
    res = filtrer_depenses(g.depenses, creer_filtre(date_debut="2026-10-05", date_fin="2026-10-15"))
    assert [d.id for d in res] == [d1.id, d2.id]

    # Filtre combiné
    res = filtrer_depenses(g.depenses,
          creer_filtre(categorie="Courses", membre="Ali",
                       date_debut="2026-10-01", date_fin="2026-10-31"))
    assert [d.id for d in res] == [d1.id]

    # Filtres à critère unique (noms du cahier des charges)
    assert [d.id for d in filtrer_depenses(g.depenses, filtre_categorie("transport"))] == [d2.id]
    assert [d.id for d in filtrer_depenses(g.depenses, filtre_membre("omar"))] == [d2.id, d3.id]
    assert [d.id for d in filtrer_depenses(g.depenses, filtre_periode("2026-11-01"))] == [d3.id]

    # Tri par date décroissant
    tries = trier_depenses(g.depenses, cle="date", decroissant=True)
    assert tries[0].id == d3.id

    print("✔ Test 8 : Fermetures de filtrage (catégorie, membre, période, combiné) validées.")


def test_sauvegarde_chargement_json():
    """Test 9 : Sauvegarde puis rechargement JSON — données identiques (soldee compris)."""
    g = creer_groupe("Test JSON")
    ajouter_membre(g, "Ali"); ajouter_membre(g, "Sara")
    ajouter_depense(g, "2026-11-10", 45000, "Ali", ["Ali", "Sara"], "Loyer", "Loyer nov.")
    ajouter_depense(g, "2026-11-11", 12500, "Sara", ["Ali", "Sara"], "Courses", "Pain")
    g.depenses[0].soldee = True   # une dépense soldée, l'autre non

    fichier = "_test_tmp.json"
    sauvegarder_groupe(g, fichier)
    g2 = charger_groupe(fichier)

    assert g2.nom == g.nom
    assert g2.prochain_id == g.prochain_id
    assert [m.nom for m in g2.membres] == [m.nom for m in g.membres]
    assert len(g2.depenses) == len(g.depenses)
    for orig, recup in zip(g.depenses, g2.depenses):
        assert orig.id == recup.id
        assert orig.date == recup.date
        assert orig.montant == recup.montant
        assert orig.payeur.nom == recup.payeur.nom
        assert [b.nom for b in orig.beneficiaires] == [b.nom for b in recup.beneficiaires]
        assert orig.categorie == recup.categorie
        assert orig.soldee == recup.soldee

    if os.path.exists(fichier):
        os.remove(fichier)
    print("✔ Test 9 : Sauvegarde et rechargement JSON validés.")


def test_parsing_formatage_montants():
    """Test 10 : parse_montant() et format_montant() corrects."""
    assert parse_montant("12.5")  == 12500
    assert parse_montant("12,5")  == 12500
    assert parse_montant("12")    == 12000
    assert parse_montant("0.001") == 1
    assert parse_montant("100")   == 100000
    assert format_montant(12500)  == "12,500 TND"
    assert format_montant(0)      == "0,000 TND"
    assert format_montant(-30000) == "-30,000 TND"

    # Chiffres non ASCII : refusés proprement (ValueError, pas de plantage obscur)
    for p_err in ["²", "1²", "١٢", "12.٥"]:
        try:
            parse_montant(p_err)
            assert False, f"parse_montant('{p_err}') aurait dû lever ValueError"
        except ValueError:
            pass
    print("✔ Test 10 : Parsing et formatage des montants validés.")


def test_depenses_croisees():
    """Test 11 : Plusieurs dépenses croisées → règlement minimal correct."""
    g = creer_groupe("Croisé")
    ajouter_membre(g, "Ali"); ajouter_membre(g, "Sara"); ajouter_membre(g, "Omar")
    ajouter_depense(g, "2026-11-01", 90000, "Ali",  ["Ali", "Sara", "Omar"])
    ajouter_depense(g, "2026-11-02", 60000, "Sara", ["Ali", "Sara", "Omar"])

    s = calculer_soldes(g)
    # Ali  : payé 90000, dû 30000+20000=50000 → solde +40000
    # Sara : payé 60000, dû 30000+20000=50000 → solde +10000
    # Omar : payé 0,     dû 30000+20000=50000 → solde -50000
    assert s["Ali"]  == 40000
    assert s["Sara"] == 10000
    assert s["Omar"] == -50000
    assert verifier_soldes(s)

    v = regler(s)
    assert len(v) == 2
    # Chaque virement est un tuple (débiteur, créditeur, montant)
    paires = {(vi[0], vi[1], vi[2]) for vi in v}
    assert paires == {("Omar", "Ali", 40000), ("Omar", "Sara", 10000)}
    print("✔ Test 11 : Dépenses croisées et règlement minimal validés.")


def test_verifier_soldes_tolerance():
    """Test 12 : verifier_soldes() accepte une somme ≤ 10 millimes (tolérance 0,01 TND)."""
    assert verifier_soldes({"Ali": 5,  "Sara": -5})   is True
    assert verifier_soldes({"Ali": 10, "Sara": -10})  is True
    # somme = 10 → exactement dans la tolérance → valide
    assert verifier_soldes({"Ali": 10, "Sara": 0})    is True
    # somme = 11 → dépasse la tolérance → invalide
    assert verifier_soldes({"Ali": 11, "Sara": 0})    is False
    # somme = -11 → dépasse la tolérance → invalide
    assert verifier_soldes({"Ali": -11, "Sara": 0})   is False
    # soldes tous nuls
    assert verifier_soldes({"Ali": 0,  "Sara": 0})    is True
    print("✔ Test 12 : verifier_soldes() avec tolérance 10 millimes validé.")


def test_marquer_soldees():
    """Test 13 : « J'ai réglé les virements » → soldes à 0, aucun virement, historique conservé."""
    g = creer_groupe("Test Règlement")
    ajouter_membre(g, "Ali"); ajouter_membre(g, "Sara"); ajouter_membre(g, "Omar")
    ajouter_depense(g, "2026-11-01", 90000, "Ali", ["Ali", "Sara", "Omar"])
    assert regler(calculer_soldes(g)) != []

    assert marquer_soldees(g) == 1
    assert marquer_soldees(g) == 0, "Deuxième appel : rien de nouveau à marquer"

    s = calculer_soldes(g)
    assert all(v == 0 for v in s.values()), f"Soldes attendus à 0, obtenu {dict(s)}"
    assert regler(s) == []

    # L'historique reste consultable
    assert calculer_soldes(g, inclure_soldees=True)["Ali"] == 60000

    # Une nouvelle dépense repart à non soldée et réapparaît dans les soldes
    nouvelle = ajouter_depense(g, "2026-11-02", 30000, "Sara", ["Ali", "Sara", "Omar"])
    assert nouvelle.soldee is False
    assert calculer_soldes(g)["Sara"] == 20000
    print("✔ Test 13 : marquer_soldees() validé.")


def test_methodes_groupe():
    """Test 14 : Les méthodes de Groupe (diagramme de classes) délèguent au noyau."""
    g = creer_groupe("Façade")
    g.ajouter_membre("Ali"); g.ajouter_membre("Sara")
    assert g.lister_membres() == ["Ali", "Sara"]

    d1 = g.ajouter_depense("2026-11-01", "30", "Ali", ["Ali", "Sara"], "Courses")
    d2 = g.ajouter_depense("2026-11-02", "50", "Sara", ["Ali", "Sara"], "Transport")
    assert [d.id for d in g.lister_depenses("montant", decroissant=True)] == [d2.id, d1.id]

    g.modifier_depense(d1.id, montant="40")
    assert g.depenses[0].montant == 40000

    s = g.calculer_soldes()
    assert s["Ali"] == 40000 - 20000 - 25000 and g.somme_nulle()

    g.supprimer_depense(d2.id)
    assert len(g.depenses) == 1
    assert g.marquer_soldees() == 1
    g.supprimer_membre("Sara")
    assert g.lister_membres() == ["Ali"]
    print("✔ Test 14 : Méthodes de la classe Groupe validées.")


# ==============================================================================
# LANCEMENT DIRECT
# ==============================================================================

def lancer_tous_les_tests() -> None:
    """Exécute tous les tests et affiche un bilan final."""
    tests = [
        test_exemple_cahier_des_charges,
        test_groupe_un_seul_membre,
        test_repartition_arrondi_100_entre_3,
        test_doublon_nom_refuse,
        test_suppression_refusee_si_depense_non_soldee,
        test_suppression_autorisee_apres_reglement,
        test_validations_date_montant_membres,
        test_fermetures_filtrage,
        test_sauvegarde_chargement_json,
        test_parsing_formatage_montants,
        test_depenses_croisees,
        test_verifier_soldes_tolerance,
        test_marquer_soldees,
        test_methodes_groupe,
    ]

    print("\n" + "=" * 60)
    print("  SUITE DE TESTS — noyau.py")
    print("=" * 60)
    echecs = 0
    for test_fn in tests:
        try:
            test_fn()
        except AssertionError as e:
            print(f"✖ ÉCHEC {test_fn.__name__} : {e}")
            echecs += 1
        except Exception as e:
            print(f"✖ ERREUR {test_fn.__name__} : {type(e).__name__}: {e}")
            echecs += 1

    print("=" * 60)
    if echecs == 0:
        print(f"  TOUS LES TESTS PASSÉS ({len(tests)}/{len(tests)}) ✔")
    else:
        print(f"  {echecs} ÉCHEC(S) sur {len(tests)} tests ✖")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    lancer_tous_les_tests()