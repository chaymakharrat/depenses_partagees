#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Application de gestion de dépenses partagées (colocation, voyage, association).
Conforme aux spécifications Python 3.10+ en utilisant uniquement la bibliothèque standard.

Auteur : Antigravity (Google DeepMind)
Fichier : depenses.py
"""

from collections import defaultdict, namedtuple
import csv
from dataclasses import dataclass, field
from datetime import datetime
import json
import os
import sys
from typing import Callable


# ==============================================================================
# MODÈLE DE DONNÉES (3 entités, rien d'autre n'est stocké)
# ==============================================================================

@dataclass
class Membre:
    """Entité représentant un membre du groupe.
    
    L'égalité et le hachage sont insensibles à la casse ('ali' et 'Ali' sont identiques).
    """
    nom: str

    def __post_init__(self) -> None:
        self.nom = self.nom.strip()

    def __str__(self) -> str:
        return self.nom

    def __repr__(self) -> str:
        return f"Membre({self.nom!r})"

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Membre):
            return self.nom.casefold() == other.nom.casefold()
        if isinstance(other, str):
            return self.nom.casefold() == other.casefold()
        return False

    def __hash__(self) -> int:
        return hash(self.nom.casefold())

    def casefold(self) -> str:
        return self.nom.casefold()

    def lower(self) -> str:
        return self.nom.lower()


@dataclass
class Depense:
    """Entité représentant une dépense partagée.
    
    id            : identifiant entier unique
    date          : texte au format AAAA-MM-JJ
    montant       : entier en millimes (1 TND = 1000 millimes)
    payeur        : membre ayant effectué le paiement
    beneficiaires : liste d'au moins un membre bénéficiaire
    categorie     : catégorie de la dépense (ex: courses, transport)
    description   : description libre
    """
    id: int
    date: str
    montant: int
    payeur: Membre
    beneficiaires: list[Membre]
    categorie: str = "Général"
    description: str = ""

    def __post_init__(self) -> None:
        if isinstance(self.payeur, str):
            self.payeur = Membre(self.payeur)
        self.beneficiaires = [
            Membre(b) if isinstance(b, str) else b for b in self.beneficiaires
        ]


@dataclass
class Groupe:
    """Entité représentant un groupe de partage de dépenses.
    
    nom         : nom non vide du groupe
    membres     : liste des membres enregistrés
    depenses    : liste des dépenses enregistrées
    prochain_id : compteur d'identifiant auto-incrémenté
    """
    nom: str
    membres: list[Membre] = field(default_factory=list)
    depenses: list[Depense] = field(default_factory=list)
    prochain_id: int = 1

    def __post_init__(self) -> None:
        self.membres = [
            Membre(m) if isinstance(m, str) else m for m in self.membres
        ]


# Structure immuable pour les virements calculés (non stockés)
Virement = namedtuple("Virement", ["debiteur", "crediteur", "montant"])


class SoldesDict(dict):
    """Dictionnaire de soldes avec accès insensible à la casse et support de Membre."""

    def __getitem__(self, key):
        cle_str = key.nom if isinstance(key, Membre) else str(key)
        for k in self.keys():
            if k.casefold() == cle_str.casefold():
                return super().__getitem__(k)
        return super().__getitem__(key)

    def __contains__(self, key):
        cle_str = key.nom if isinstance(key, Membre) else str(key)
        for k in self.keys():
            if k.casefold() == cle_str.casefold():
                return True
        return super().__contains__(key)


# ==============================================================================
# GESTION DES MONTANTS (Entiers en millimes, aucun float)
# ==============================================================================

def parse_montant(texte: str) -> int:
    """Convertit une chaîne en millimes (entier). Accepte '.' et ',', max 3 décimales.
    
    Exemples :
        parse_montant("12.5") -> 12500
        parse_montant("12,50") -> 12500
        parse_montant("100") -> 100000
    """
    if not isinstance(texte, str):
        raise ValueError("Le montant doit être fourni sous forme de chaîne de caractères.")
    
    nettoye = texte.strip().replace(" ", "").replace(",", ".")
    if not nettoye:
        raise ValueError("Le montant ne peut pas être vide.")
    
    if nettoye.startswith("-"):
        raise ValueError("Le montant doit être positif.")

    parties = nettoye.split(".")
    if len(parties) == 1:
        if not parties[0].isdigit():
            raise ValueError(f"Format de montant invalide : '{texte}'.")
        return int(parties[0]) * 1000
    elif len(parties) == 2:
        entier_str, dec_str = parties
        if (entier_str and not entier_str.isdigit()) or (dec_str and not dec_str.isdigit()):
            raise ValueError(f"Format de montant invalide : '{texte}'.")
        if len(dec_str) > 3:
            raise ValueError("Le montant ne peut pas comporter plus de 3 décimales (précision au millime).")
        dec_pad = dec_str.ljust(3, "0")
        partie_entiere = int(entier_str) if entier_str else 0
        return partie_entiere * 1000 + int(dec_pad)
    else:
        raise ValueError(f"Format de montant invalide (plusieurs points décimaux) : '{texte}'.")


def format_montant(millimes: int) -> str:
    """Formate un montant en millimes en 'X,YYY TND'. Utilisé uniquement pour l'affichage."""
    signe = "-" if millimes < 0 else ""
    valeur = abs(millimes)
    entier = valeur // 1000
    reste = valeur % 1000
    return f"{signe}{entier},{reste:03d} TND"


# ==============================================================================
# RÈGLES DE VALIDATION (R1 à R6)
# ==============================================================================

def valider_date(date_str: str) -> str:
    """R1 : Vérifie que la date respecte le format AAAA-MM-JJ avec datetime.strptime."""
    if not isinstance(date_str, str):
        raise ValueError("La date doit être une chaîne de caractères.")
    nettoye = date_str.strip()
    try:
        dt = datetime.strptime(nettoye, "%Y-%m-%d")
        return dt.strftime("%Y-%m-%d")
    except ValueError:
        raise ValueError(f"Date invalide : '{date_str}'. Le format attendu est AAAA-MM-JJ (ex: 2026-11-01).")


def valider_montant(montant: int) -> int:
    """R2 : Vérifie que le montant en millimes est strictement positif."""
    if montant <= 0:
        raise ValueError(f"Le montant doit être strictement positif (> 0). Reçu : {montant} millimes.")
    return montant


def trouver_membre(groupe: Groupe, nom_ou_membre: str | Membre) -> Membre | None:
    """Recherche un membre dans le groupe de façon insensible à la casse."""
    nom_cherche = (nom_ou_membre.nom if isinstance(nom_ou_membre, Membre) else str(nom_ou_membre)).strip().casefold()
    for m in groupe.membres:
        if m.nom.casefold() == nom_cherche:
            return m
    return None


def valider_membres_depense(
    groupe: Groupe,
    payeur: str | Membre,
    beneficiaires: list[str | Membre]
) -> tuple[Membre, list[Membre]]:
    """R3 : Vérifie que le payeur et les bénéficiaires sont membres ; au moins un bénéficiaire."""
    m_payeur = trouver_membre(groupe, payeur)
    if not m_payeur:
        raise ValueError(f"Payeur inconnu : '{payeur}'. Il doit faire partie des membres du groupe.")

    if not beneficiaires:
        raise ValueError("Une dépense doit comporter au moins un bénéficiaire.")

    m_beneficiaires: list[Membre] = []
    vus = set()
    for b in beneficiaires:
        m_b = trouver_membre(groupe, b)
        if not m_b:
            raise ValueError(f"Bénéficiaire inconnu : '{b}'. Il doit faire partie des membres du groupe.")
        if m_b.nom.casefold() not in vus:
            vus.add(m_b.nom.casefold())
            m_beneficiaires.append(m_b)

    return m_payeur, m_beneficiaires


def valider_nom_membre(groupe: Groupe, nom: str) -> str:
    """R4 : Vérifie que le nom de membre est non vide et unique (casse ignorée)."""
    if not isinstance(nom, str):
        raise ValueError("Le nom du membre doit être une chaîne de caractères.")
    nettoye = nom.strip()
    if not nettoye:
        raise ValueError("Le nom du membre ne peut pas être vide.")
    if trouver_membre(groupe, nettoye) is not None:
        raise ValueError(f"Le membre '{nettoye}' existe déjà dans le groupe (la casse est ignorée).")
    return nettoye


def verifier_suppression_membre(groupe: Groupe, nom: str | Membre) -> Membre:
    """R5 : Vérifie qu'un membre n'apparaît dans aucune dépense avant suppression."""
    membre = trouver_membre(groupe, nom)
    if not membre:
        raise ValueError(f"Membre '{nom}' introuvable dans le groupe.")

    cf = membre.nom.casefold()
    for d in groupe.depenses:
        if d.payeur.nom.casefold() == cf:
            raise ValueError(
                f"Impossible de supprimer '{membre.nom}' : il apparaît comme payeur "
                f"dans la dépense #{d.id} ({d.description or d.categorie})."
            )
        for b in d.beneficiaires:
            if b.nom.casefold() == cf:
                raise ValueError(
                    f"Impossible de supprimer '{membre.nom}' : il apparaît comme bénéficiaire "
                    f"dans la dépense #{d.id} ({d.description or d.categorie})."
                )
    return membre


def verifier_soldes(soldes: dict[str, int]) -> bool:
    """R6 & F11 : Vérifie que la somme des soldes est nulle (tolérance de 10 millimes)."""
    somme = sum(soldes.values())
    return abs(somme) <= 10


# ==============================================================================
# FONCTIONNALITÉS F1 À F7 (Gestion du groupe, membres et dépenses)
# ==============================================================================

def creer_groupe(nom: str) -> Groupe:
    """F1 : Crée un nouveau groupe avec un nom non vide."""
    if not isinstance(nom, str):
        raise ValueError("Le nom du groupe doit être une chaîne de caractères.")
    nettoye = nom.strip()
    if not nettoye:
        raise ValueError("Le nom du groupe ne peut pas être vide.")
    return Groupe(nom=nettoye, membres=[], depenses=[], prochain_id=1)


def ajouter_membre(groupe: Groupe, nom: str | Membre) -> Membre:
    """F2 : Ajoute un membre au groupe après validation R4."""
    nom_str = nom.nom if isinstance(nom, Membre) else str(nom)
    nom_valide = valider_nom_membre(groupe, nom_str)
    nouveau_membre = Membre(nom=nom_valide)
    groupe.membres.append(nouveau_membre)
    return nouveau_membre


def supprimer_membre(groupe: Groupe, nom: str | Membre) -> Membre:
    """F3 : Supprime un membre du groupe en appliquant la règle R5."""
    membre = verifier_suppression_membre(groupe, nom)
    groupe.membres = [m for m in groupe.membres if m.nom.casefold() != membre.nom.casefold()]
    return membre


def lister_membres(groupe: Groupe) -> list[str]:
    """F4 : Renvoie la liste des noms des membres."""
    return [m.nom for m in groupe.membres]


def repartir_depense(montant: int, beneficiaires: list[str | Membre]) -> dict[str, int]:
    """Répartit un montant équitablement entre bénéficiaires en millimes.
    
    Pour un montant M et n bénéficiaires : chacun doit M // n.
    Le reste (M % n) est réparti à raison de 1 millime en plus pour les premiers
    bénéficiaires dans l'ORDRE ALPHABÉTIQUE (insensible à la casse).
    La somme des parts est exactement égale à M.
    """
    if not beneficiaires:
        raise ValueError("La liste des bénéficiaires ne peut pas être vide.")

    noms = [b.nom if isinstance(b, Membre) else str(b) for b in beneficiaires]
    n = len(noms)
    base = montant // n
    reste = montant % n

    # Tri alphabétique insensible à la casse pour un résultat déterministe
    noms_tries = sorted(noms, key=lambda s: s.casefold())

    repartition: dict[str, int] = {}
    for i, nom in enumerate(noms_tries):
        repartition[nom] = base + (1 if i < reste else 0)

    return repartition


def ajouter_depense(
    groupe: Groupe,
    date: str,
    montant: int | str,
    payeur: str | Membre,
    beneficiaires: list[str | Membre] | None = None,
    categorie: str = "Général",
    description: str = "",
) -> Depense:
    """F5 : Ajoute une dépense au groupe avec validations R1, R2, R3.
    
    Par défaut, tous les membres actuels du groupe sont bénéficiaires.
    """
    date_valide = valider_date(date)

    montant_millimes = parse_montant(montant) if isinstance(montant, str) else montant
    valider_montant(montant_millimes)

    if beneficiaires is None:
        if not groupe.membres:
            raise ValueError("Impossible d'ajouter une dépense : le groupe ne contient aucun membre.")
        liste_beneficiaires = list(groupe.membres)
    else:
        if len(beneficiaires) == 0:
            raise ValueError("Une dépense doit comporter au moins un bénéficiaire.")
        liste_beneficiaires = list(beneficiaires)

    m_payeur, m_beneficiaires = valider_membres_depense(groupe, payeur, liste_beneficiaires)

    cat_propre = categorie.strip() if categorie and categorie.strip() else "Général"
    desc_propre = description.strip() if description else ""

    depense = Depense(
        id=groupe.prochain_id,
        date=date_valide,
        montant=montant_millimes,
        payeur=m_payeur,
        beneficiaires=m_beneficiaires,
        categorie=cat_propre,
        description=desc_propre,
    )
    groupe.prochain_id += 1
    groupe.depenses.append(depense)
    return depense


def modifier_depense(
    groupe: Groupe,
    depense_id: int,
    date: str | None = None,
    montant: int | str | None = None,
    payeur: str | Membre | None = None,
    beneficiaires: list[str | Membre] | None = None,
    categorie: str | None = None,
    description: str | None = None,
) -> Depense:
    """F6 : Modifie une dépense existante par son ID avec les mêmes validations."""
    depense = next((d for d in groupe.depenses if d.id == depense_id), None)
    if not depense:
        raise ValueError(f"Dépense #{depense_id} introuvable.")

    nouvelle_date = valider_date(date) if date is not None else depense.date

    if montant is not None:
        nouveau_montant = parse_montant(montant) if isinstance(montant, str) else montant
        valider_montant(nouveau_montant)
    else:
        nouveau_montant = depense.montant

    nouveau_payeur = payeur if payeur is not None else depense.payeur
    nouveaux_benefs = beneficiaires if beneficiaires is not None else depense.beneficiaires

    m_payeur, m_benefs = valider_membres_depense(groupe, nouveau_payeur, nouveaux_benefs)

    nouvelle_cat = categorie.strip() if categorie is not None else depense.categorie
    nouvelle_desc = description.strip() if description is not None else depense.description

    depense.date = nouvelle_date
    depense.montant = nouveau_montant
    depense.payeur = m_payeur
    depense.beneficiaires = m_benefs
    depense.categorie = nouvelle_cat or "Général"
    depense.description = nouvelle_desc

    return depense


def supprimer_depense(groupe: Groupe, depense_id: int) -> Depense:
    """F7 : Supprime une dépense par son identifiant unique."""
    for i, d in enumerate(groupe.depenses):
        if d.id == depense_id:
            return groupe.depenses.pop(i)
    raise ValueError(f"Dépense #{depense_id} introuvable.")


# ==============================================================================
# TRI ET FILTRAGE AVEC FERMETURE (F8 et F9)
# ==============================================================================

def trier_depenses(
    depenses: list[Depense],
    cle: str = "date",
    decroissant: bool = False,
) -> list[Depense]:
    """F8 : Trie les dépenses par date ou par montant (ordre croissant ou décroissant)."""
    cle_normalisee = cle.strip().lower()
    if cle_normalisee == "date":
        return sorted(depenses, key=lambda d: (d.date, d.id), reverse=decroissant)
    elif cle_normalisee == "montant":
        return sorted(depenses, key=lambda d: (d.montant, d.id), reverse=decroissant)
    else:
        raise ValueError("Clé de tri invalide : choisissez 'date' ou 'montant'.")


def creer_filtre(
    categorie: str | None = None,
    membre: str | None = None,
    date_debut: str | None = None,
    date_fin: str | None = None,
) -> Callable[[Depense], bool]:
    """F9 : Crée et renvoie une fermeture filtre(depense) -> bool.
    
    'membre' signifie payeur OU bénéficiaire.
    La période [date_debut, date_fin] est inclusive.
    """
    cat_cible = categorie.strip().casefold() if (categorie and categorie.strip()) else None
    membre_cible = membre.strip().casefold() if (membre and membre.strip()) else None
    debut_cible = date_debut.strip() if (date_debut and date_debut.strip()) else None
    fin_cible = date_fin.strip() if (date_fin and date_fin.strip()) else None

    def filtre(depense: Depense) -> bool:
        # Filtrage par catégorie
        if cat_cible is not None:
            if depense.categorie.strip().casefold() != cat_cible:
                return False

        # Filtrage par membre (payeur OU bénéficiaire)
        if membre_cible is not None:
            est_payeur = depense.payeur.nom.casefold() == membre_cible
            est_benef = any(b.nom.casefold() == membre_cible for b in depense.beneficiaires)
            if not (est_payeur or est_benef):
                return False

        # Filtrage par date de début (inclusive)
        if debut_cible is not None:
            if depense.date < debut_cible:
                return False

        # Filtrage par date de fin (inclusive)
        if fin_cible is not None:
            if depense.date > fin_cible:
                return False

        return True

    return filtre


def filtrer_depenses(
    depenses: list[Depense],
    filtre_fn: Callable[[Depense], bool],
) -> list[Depense]:
    """Applique la fermeture sur la liste de dépenses en utilisant filter()."""
    return list(filter(filtre_fn, depenses))


# ==============================================================================
# CALCUL DES SOLDES ET RÈGLEMENT (F10, F11, F12)
# ==============================================================================

def calculer_soldes(groupe: Groupe) -> dict[str, int]:
    """F10 : Calcule le solde de chaque membre en millimes (total payé - total dû).
    
    Les soldes ne sont jamais stockés, ils sont recalculés à la demande.
    """
    soldes = SoldesDict({m.nom: 0 for m in groupe.membres})

    for depense in groupe.depenses:
        m_payeur = trouver_membre(groupe, depense.payeur)
        nom_payeur = m_payeur.nom if m_payeur else depense.payeur.nom
        soldes[nom_payeur] = soldes.get(nom_payeur, 0) + depense.montant

        parts = repartir_depense(depense.montant, depense.beneficiaires)
        for nom_benef, part in parts.items():
            m_benef = trouver_membre(groupe, nom_benef)
            nom_canonique = m_benef.nom if m_benef else nom_benef
            soldes[nom_canonique] = soldes.get(nom_canonique, 0) - part

    return soldes


def regler(soldes: dict[str, int]) -> list[Virement]:
    """F12 : Calcule un plan de règlement minimal (au plus n-1 virements).
    
    Algorithme :
    1. Séparer créditeurs (solde > 0) et débiteurs (solde < 0) ; ignorer solde == 0.
    2. Tant qu'il reste des débiteurs et des créditeurs :
       a. D = débiteur au plus grand montant dû ; C = créditeur au plus grand montant à recevoir
          (en cas d'égalité, ordre alphabétique pour un résultat déterministe).
       b. montant = min(dû de D, à recevoir de C) ; enregistrer le virement (D, C, montant).
       c. Mettre à jour les deux soldes et retirer ceux qui tombent à 0.
    Ne modifie pas le dictionnaire reçu en argument (travaille sur une copie).
    """
    copie_soldes = dict(soldes)

    # debiteurs stocke des montants positifs dus : montant_du = -solde
    debiteurs = {m: -s for m, s in copie_soldes.items() if s < 0}
    crediteurs = {m: s for m, s in copie_soldes.items() if s > 0}

    virements: list[Virement] = []

    while debiteurs and crediteurs:
        # Sélection déterministe de D : plus grand montant dû, puis ordre alphabétique
        d_nom = min(debiteurs.keys(), key=lambda m: (-debiteurs[m], m.casefold()))
        # Sélection déterministe de C : plus grand montant à recevoir, puis ordre alphabétique
        c_nom = min(crediteurs.keys(), key=lambda m: (-crediteurs[m], m.casefold()))

        montant_virement = min(debiteurs[d_nom], crediteurs[c_nom])
        virements.append(Virement(debiteur=d_nom, crediteur=c_nom, montant=montant_virement))

        debiteurs[d_nom] -= montant_virement
        crediteurs[c_nom] -= montant_virement

        if debiteurs[d_nom] == 0:
            del debiteurs[d_nom]
        if crediteurs[c_nom] == 0:
            del crediteurs[c_nom]

    return virements


# ==============================================================================
# STATISTIQUES ET GRAPHIQUES TEXTUELS (F13)
# ==============================================================================

def dessiner_barre(valeur: int, valeur_max: int, largeur_max: int = 25) -> str:
    """Génère une barre textuelle proportionnelle en blocs pleins ('█')."""
    if valeur_max <= 0 or valeur <= 0:
        return ""
    nb_blocs = (valeur * largeur_max) // valeur_max
    return "█" * max(1, nb_blocs)


def afficher_statistiques(groupe: Groupe) -> None:
    """F13 : Affiche les statistiques détaillées avec graphiques en barres texte.
    
    - Total dépensé par membre (ce qu'il a payé).
    - Total par catégorie avec pourcentage du montant global.
    - Total par mois (AAAA-MM).
    """
    if not groupe.depenses:
        print("\nAucune dépense enregistrée pour le moment. Statistiques indisponibles.")
        return

    total_general = sum(d.montant for d in groupe.depenses)

    # 1. Par membre (ce qu'il a effectivement payé)
    total_par_membre: dict[str, int] = {m.nom: 0 for m in groupe.membres}
    for d in groupe.depenses:
        m_p = trouver_membre(groupe, d.payeur)
        nom = m_p.nom if m_p else d.payeur.nom
        total_par_membre[nom] = total_par_membre.get(nom, 0) + d.montant

    # 2. Par catégorie
    total_par_cat = defaultdict(int)
    for d in groupe.depenses:
        cat = d.categorie.strip().capitalize() or "Général"
        total_par_cat[cat] += d.montant

    # 3. Par mois (AAAA-MM)
    total_par_mois = defaultdict(int)
    for d in groupe.depenses:
        mois = d.date[:7]
        total_par_mois[mois] += d.montant

    print("\n" + "=" * 65)
    print(f" STATISTIQUES GLOBALES DU GROUPE : {groupe.nom.upper()}")
    print("=" * 65)
    print(f"Nombre de dépenses : {len(groupe.depenses)}")
    print(f"Montant total payé : {format_montant(total_general)}")

    # Affichage par membre
    print("\n--- TOTAL PAYÉ PAR MEMBRE ---")
    max_m = max(total_par_membre.values()) if total_par_membre else 0
    for nom, montant in sorted(total_par_membre.items(), key=lambda item: (-item[1], item[0].casefold())):
        pct_dixieme = (montant * 1000) // total_general if total_general > 0 else 0
        pct_str = f"{pct_dixieme // 10}.{pct_dixieme % 10}%"
        barre = dessiner_barre(montant, max_m, largeur_max=22)
        print(f"  {nom:<15} : {format_montant(montant):>12} ({pct_str:>6})  {barre}")

    # Affichage par catégorie
    print("\n--- TOTAL PAR CATÉGORIE ---")
    max_c = max(total_par_cat.values()) if total_par_cat else 0
    for cat, montant in sorted(total_par_cat.items(), key=lambda item: (-item[1], item[0].casefold())):
        pct_dixieme = (montant * 1000) // total_general if total_general > 0 else 0
        pct_str = f"{pct_dixieme // 10}.{pct_dixieme % 10}%"
        barre = dessiner_barre(montant, max_c, largeur_max=22)
        print(f"  {cat:<15} : {format_montant(montant):>12} ({pct_str:>6})  {barre}")

    # Affichage par mois
    print("\n--- TOTAL PAR MOIS ---")
    max_mois = max(total_par_mois.values()) if total_par_mois else 0
    for mois in sorted(total_par_mois.keys()):
        montant = total_par_mois[mois]
        pct_dixieme = (montant * 1000) // total_general if total_general > 0 else 0
        pct_str = f"{pct_dixieme // 10}.{pct_dixieme % 10}%"
        barre = dessiner_barre(montant, max_mois, largeur_max=22)
        print(f"  {mois:<15} : {format_montant(montant):>12} ({pct_str:>6})  {barre}")
    print("=" * 65)


# ==============================================================================
# AFFICHAGE ET EXPORT DU BILAN (F14)
# ==============================================================================

def generer_bilan_texte(groupe: Groupe) -> str:
    """Génère la synthèse textuelle complète des soldes et des virements."""
    soldes = calculer_soldes(groupe)
    equilibre = verifier_soldes(soldes)
    virements = regler(soldes)

    lignes = [
        "=" * 60,
        f" BILAN DE RÈGLEMENT : {groupe.nom.upper()}",
        "=" * 60,
        "",
        "--- SOLDES INDIVIDUELS ---",
    ]

    for nom, solde in sorted(soldes.items(), key=lambda item: item[0].casefold()):
        statut = "Créditeur" if solde > 0 else ("Débiteur" if solde < 0 else "Équilibré")
        lignes.append(f"  {nom:<15} : {format_montant(solde):>12}  ({statut})")

    somme_soldes = sum(soldes.values())
    lignes.append(f"\n  Somme de contrôle : {format_montant(somme_soldes)} (Valide: {'OUI' if equilibre else 'NON'})")

    lignes.append("\n--- PLAN DE RÈGLEMENT (VIREMENTS SUGGÉRÉS) ---")
    if not virements:
        lignes.append("  Aucun virement nécessaire (tous les membres sont à l'équilibre).")
    else:
        for i, v in enumerate(virements, start=1):
            lignes.append(f"  {i}. {v.debiteur} doit verser {format_montant(v.montant)} à {v.crediteur}")
        lignes.append(f"\n  Nombre de virements : {len(virements)} (<= {max(0, len(groupe.membres) - 1)})")

    lignes.append("=" * 60)
    return "\n".join(lignes)


def afficher_bilan(groupe: Groupe) -> None:
    """Affiche le bilan de règlement à l'écran."""
    print("\n" + generer_bilan_texte(groupe))


def exporter_bilan_txt(groupe: Groupe, chemin_fichier: str = "bilan.txt") -> str:
    """F14 : Exporte le bilan au format texte (TXT)."""
    texte = generer_bilan_texte(groupe)
    with open(chemin_fichier, "w", encoding="utf-8") as f:
        f.write(texte)
    return chemin_fichier


def exporter_bilan_csv(groupe: Groupe, chemin_fichier: str = "bilan.csv") -> str:
    """F14 : Exporte le bilan (soldes et virements) au format CSV."""
    soldes = calculer_soldes(groupe)
    virements = regler(soldes)

    with open(chemin_fichier, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Section", "Membre / Debiteur", "Crediteur", "Montant (millimes)", "Montant formate"])
        for membre, solde in sorted(soldes.items(), key=lambda item: item[0].casefold()):
            writer.writerow(["Solde", membre, "", solde, format_montant(solde)])
        for v in virements:
            writer.writerow(["Virement", v.debiteur, v.crediteur, v.montant, format_montant(v.montant)])

    return chemin_fichier


# ==============================================================================
# SAUVEGARDE ET CHARGEMENT JSON (F15)
# ==============================================================================

def sauvegarder_groupe(groupe: Groupe, chemin: str = "groupe.json") -> None:
    """F15 : Sauvegarde toutes les données du groupe dans un fichier JSON (UTF-8, indent=2)."""
    data = {
        "nom": groupe.nom,
        "membres": [m.nom for m in groupe.membres],
        "prochain_id": groupe.prochain_id,
        "depenses": [
            {
                "id": d.id,
                "date": d.date,
                "montant": d.montant,
                "payeur": d.payeur.nom,
                "beneficiaires": [b.nom for b in d.beneficiaires],
                "categorie": d.categorie,
                "description": d.description,
            }
            for d in groupe.depenses
        ],
    }
    with open(chemin, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def charger_groupe(chemin: str = "groupe.json") -> Groupe:
    """F15 : Recharge un groupe depuis un fichier JSON en restaurant le compteur d'id."""
    with open(chemin, "r", encoding="utf-8") as f:
        data = json.load(f)

    nom = data["nom"]
    membres = [Membre(nom=m) if isinstance(m, str) else m for m in data.get("membres", [])]
    prochain_id = data.get("prochain_id", 1)

    depenses: list[Depense] = []
    for d_data in data.get("depenses", []):
        depense = Depense(
            id=d_data["id"],
            date=d_data["date"],
            montant=d_data["montant"],
            payeur=Membre(nom=d_data["payeur"]),
            beneficiaires=[Membre(nom=b) for b in d_data["beneficiaires"]],
            categorie=d_data.get("categorie", "Général"),
            description=d_data.get("description", ""),
        )
        depenses.append(depense)

    # Restauration robuste de l'id
    if depenses:
        max_id = max(d.id for d in depenses)
        if prochain_id <= max_id:
            prochain_id = max_id + 1

    return Groupe(nom=nom, membres=membres, depenses=depenses, prochain_id=prochain_id)


# ==============================================================================
# INTERACTION CONSOLE ET MENU PRINCIPAL (F16)
# ==============================================================================

def afficher_tableau_depenses(depenses: list[Depense]) -> None:
    """Affiche une liste de dépenses sous forme de tableau lisible."""
    if not depenses:
        print("\nAucune dépense trouvée.")
        return

    print("\n" + "-" * 88)
    print(f"{'ID':<4} | {'Date':<10} | {'Montant':<12} | {'Payeur':<12} | {'Catégorie':<12} | {'Bénéficiaires':<15} | {'Description'}")
    print("-" * 88)
    for d in depenses:
        benefs_str = ", ".join(b.nom for b in d.beneficiaires)
        if len(benefs_str) > 15:
            benefs_str = benefs_str[:12] + "..."
        print(f"#{d.id:<3} | {d.date:<10} | {format_montant(d.montant):>12} | {d.payeur.nom:<12} | {d.categorie:<12} | {benefs_str:<15} | {d.description}")
    print("-" * 88)


def menu_ajouter_depense(groupe: Groupe) -> None:
    """Dialogue pour ajouter une dépense."""
    if not groupe.membres:
        print("Erreur : Ajoutez d'abord des membres au groupe avant d'enregistrer une dépense.")
        return

    print("\n--- NOUVELLE DÉPENSE ---")
    date_defaut = datetime.now().strftime("%Y-%m-%d")
    date_saisie = input(f"Date AAAA-MM-JJ [défaut : {date_defaut}] : ").strip()
    date = date_saisie if date_saisie else date_defaut

    montant_str = input("Montant en TND (ex: 12.5 ou 12,500) : ").strip()

    print(f"Membres disponibles : {', '.join(lister_membres(groupe))}")
    payeur = input("Nom du payeur : ").strip()

    benef_str = input("Bénéficiaires séparés par des virgules [défaut : tous] : ").strip()
    if benef_str:
        beneficiaires = [b.strip() for b in benef_str.split(",") if b.strip()]
    else:
        beneficiaires = None

    categorie = input("Catégorie [défaut : Général] : ").strip() or "Général"
    description = input("Description : ").strip()

    dep = ajouter_depense(
        groupe=groupe,
        date=date,
        montant=montant_str,
        payeur=payeur,
        beneficiaires=beneficiaires,
        categorie=categorie,
        description=description,
    )
    print(f"✓ Dépense #{dep.id} enregistrée avec succès ({format_montant(dep.montant)}).")


def menu_modifier_depense(groupe: Groupe) -> None:
    """Dialogue pour modifier une dépense."""
    if not groupe.depenses:
        print("Aucune dépense à modifier.")
        return

    id_str = input("ID de la dépense à modifier : ").strip()
    try:
        dep_id = int(id_str)
    except ValueError:
        print("ID invalide.")
        return

    depense = next((d for d in groupe.depenses if d.id == dep_id), None)
    if not depense:
        print(f"Dépense #{dep_id} introuvable.")
        return

    print(f"\nModification de la dépense #{dep_id} (laisser vide pour conserver la valeur actuelle) :")
    nouvelle_date = input(f"Date [{depense.date}] : ").strip() or None
    nouveau_montant = input(f"Montant [{format_montant(depense.montant)}] : ").strip() or None
    nouveau_payeur = input(f"Payeur [{depense.payeur.nom}] : ").strip() or None

    benef_actuels = ", ".join(b.nom for b in depense.beneficiaires)
    benef_str = input(f"Bénéficiaires [{benef_actuels}] : ").strip()
    nouveaux_benefs = [b.strip() for b in benef_str.split(",") if b.strip()] if benef_str else None

    nouvelle_cat = input(f"Catégorie [{depense.categorie}] : ").strip() or None
    nouvelle_desc = input(f"Description [{depense.description}] : ").strip() or None

    dep = modifier_depense(
        groupe=groupe,
        depense_id=dep_id,
        date=nouvelle_date,
        montant=nouveau_montant,
        payeur=nouveau_payeur,
        beneficiaires=nouveaux_benefs,
        categorie=nouvelle_cat,
        description=nouvelle_desc,
    )
    print(f"✓ Dépense #{dep.id} modifiée avec succès.")


def menu_supprimer_depense(groupe: Groupe) -> None:
    """Dialogue pour supprimer une dépense."""
    id_str = input("ID de la dépense à supprimer : ").strip()
    try:
        dep_id = int(id_str)
    except ValueError:
        print("ID invalide.")
        return

    dep = supprimer_depense(groupe, dep_id)
    print(f"✓ Dépense #{dep.id} ({format_montant(dep.montant)}) supprimée.")


def menu_lister_ou_filtrer_depenses(groupe: Groupe) -> None:
    """Dialogue pour lister, trier ou filtrer les dépenses."""
    if not groupe.depenses:
        print("\nAucune dépense enregistrée.")
        return

    print("\n--- AFFICHAGE DES DÉPENSES ---")
    print("1. Toutes les dépenses")
    print("2. Filtrer les dépenses (fermeture F9)")
    choix_vue = input("Votre choix [1] : ").strip() or "1"

    depenses_a_afficher = groupe.depenses
    if choix_vue == "2":
        cat = input("Catégorie (laisser vide pour ignorer) : ").strip() or None
        mem = input("Membre payeur/bénéficiaire (laisser vide pour ignorer) : ").strip() or None
        d_deb = input("Date de début AAAA-MM-JJ (laisser vide pour ignorer) : ").strip() or None
        d_fin = input("Date de fin AAAA-MM-JJ (laisser vide pour ignorer) : ").strip() or None

        filtre_fn = creer_filtre(categorie=cat, membre=mem, date_debut=d_deb, date_fin=d_fin)
        depenses_a_afficher = filtrer_depenses(groupe.depenses, filtre_fn)
        print(f"Résultat du filtre : {len(depenses_a_afficher)} dépense(s) retenue(s).")

    print("\nTri :")
    print("1. Par date (décroissant, du plus récent au plus ancien)")
    print("2. Par date (croissant)")
    print("3. Par montant (décroissant)")
    print("4. Par montant (croissant)")
    choix_tri = input("Votre choix [1] : ").strip() or "1"

    cle = "date"
    decroissant = True
    if choix_tri == "2":
        cle, decroissant = "date", False
    elif choix_tri == "3":
        cle, decroissant = "montant", True
    elif choix_tri == "4":
        cle, decroissant = "montant", False

    depenses_triees = trier_depenses(depenses_a_afficher, cle=cle, decroissant=decroissant)
    afficher_tableau_depenses(depenses_triees)


def menu_exporter(groupe: Groupe) -> None:
    """Dialogue pour exporter le bilan au format CSV ou TXT."""
    print("\nFormat d'exportation :")
    print("1. Fichier CSV (bilan.csv)")
    print("2. Fichier TXT (bilan.txt)")
    choix = input("Votre choix [1] : ").strip() or "1"

    if choix == "2":
        chemin = input("Chemin du fichier [bilan.txt] : ").strip() or "bilan.txt"
        exporter_bilan_txt(groupe, chemin)
        print(f"✓ Bilan exporté au format TXT avec succès dans '{chemin}'.")
    else:
        chemin = input("Chemin du fichier [bilan.csv] : ").strip() or "bilan.csv"
        exporter_bilan_csv(groupe, chemin)
        print(f"✓ Bilan exporté au format CSV avec succès dans '{chemin}'.")


def boucle_principale() -> None:
    """F16 : Boucle principale interactive avec gestion des exceptions et sauvegarde automatique."""
    chemin_fichier_json = "groupe.json"

    # F15 : Recharger au démarrage si le fichier existe
    if os.path.exists(chemin_fichier_json):
        try:
            groupe = charger_groupe(chemin_fichier_json)
            print(f"Groupe chargé depuis '{chemin_fichier_json}' : '{groupe.nom}' ({len(groupe.membres)} membres, {len(groupe.depenses)} dépenses).")
        except Exception as e:
            print(f"Erreur lors du chargement de '{chemin_fichier_json}' : {e}")
            groupe = creer_groupe("Dépenses")
    else:
        print("=== APPLICATION DE GESTION DE DÉPENSES PARTAGÉES ===")
        nom_initial = input("Nom du nouveau groupe [Colocation] : ").strip() or "Colocation"
        groupe = creer_groupe(nom_initial)
        sauvegarder_groupe(groupe, chemin_fichier_json)
        print(f"Groupe '{groupe.nom}' créé et initialisé dans '{chemin_fichier_json}'.")

    while True:
        try:
            print("\n" + "=" * 55)
            print(f" MENU PRINCIPAL - GROUPE : {groupe.nom.upper()}")
            print("=" * 55)
            print(" 1. Lister les membres")
            print(" 2. Ajouter un membre")
            print(" 3. Supprimer un membre")
            print(" 4. Lister les dépenses (avec tri et filtrage)")
            print(" 5. Ajouter une dépense")
            print(" 6. Modifier une dépense")
            print(" 7. Supprimer une dépense")
            print(" 8. Consulter les soldes et le plan de règlement")
            print(" 9. Statistiques et graphiques textuels")
            print("10. Exporter le bilan (CSV / TXT)")
            print("11. Créer un nouveau groupe / Renommer le groupe")
            print("12. Exécuter la suite de tests unitaires")
            print(" 0. Quitter")
            print("=" * 55)

            choix = input("Choisissez une option (0-12) : ").strip()

            if choix == "0":
                print("\nSauvegarde finale effectuée. Au revoir !")
                sauvegarder_groupe(groupe, chemin_fichier_json)
                break

            if choix == "1":
                membres = lister_membres(groupe)
                if membres:
                    print(f"\nMembres du groupe ({len(membres)}) :")
                    for i, m in enumerate(membres, 1):
                        print(f"  {i}. {m}")
                else:
                    print("\nAucun membre dans ce groupe.")

            elif choix == "2":
                nom = input("Nom du nouveau membre : ").strip()
                nouveau = ajouter_membre(groupe, nom)
                sauvegarder_groupe(groupe, chemin_fichier_json)
                print(f"✓ Membre '{nouveau.nom}' ajouté avec succès.")

            elif choix == "3":
                nom = input("Nom du membre à supprimer : ").strip()
                supprime = supprimer_membre(groupe, nom)
                sauvegarder_groupe(groupe, chemin_fichier_json)
                print(f"✓ Membre '{supprime.nom}' supprimé avec succès.")

            elif choix == "4":
                menu_lister_ou_filtrer_depenses(groupe)

            elif choix == "5":
                menu_ajouter_depense(groupe)
                sauvegarder_groupe(groupe, chemin_fichier_json)

            elif choix == "6":
                menu_modifier_depense(groupe)
                sauvegarder_groupe(groupe, chemin_fichier_json)

            elif choix == "7":
                menu_supprimer_depense(groupe)
                sauvegarder_groupe(groupe, chemin_fichier_json)

            elif choix == "8":
                afficher_bilan(groupe)

            elif choix == "9":
                afficher_statistiques(groupe)

            elif choix == "10":
                menu_exporter(groupe)

            elif choix == "11":
                print("\n1. Renommer le groupe actuel")
                print("2. Créer un tout nouveau groupe")
                sous_choix = input("Votre choix [1] : ").strip() or "1"
                if sous_choix == "2":
                    nouveau_nom = input("Nom du nouveau groupe : ").strip()
                    groupe = creer_groupe(nouveau_nom)
                    sauvegarder_groupe(groupe, chemin_fichier_json)
                    print(f"✓ Nouveau groupe '{groupe.nom}' créé.")
                else:
                    nouveau_nom = input(f"Nouveau nom pour '{groupe.nom}' : ").strip()
                    if not nouveau_nom:
                        raise ValueError("Le nom ne peut pas être vide.")
                    groupe.nom = nouveau_nom
                    sauvegarder_groupe(groupe, chemin_fichier_json)
                    print(f"✓ Groupe renommé en '{groupe.nom}'.")

            elif choix == "12":
                tests()

            else:
                print("Choix invalide, veuillez entrer un numéro entre 0 et 12.")

        except (KeyboardInterrupt, EOFError):
            print("\n\nInterruption détectée. Sauvegarde automatique...")
            sauvegarder_groupe(groupe, chemin_fichier_json)
            print("À bientôt !")
            break
        except ValueError as err:
            # Règle générale : gestion des erreurs sans faire planter le programme
            print(f"\n[!] Erreur de validation : {err}")
        except Exception as err:
            print(f"\n[!] Une erreur inattendue est survenue : {err}")


# ==============================================================================
# TESTS UNITAIRES (assert)
# ==============================================================================

def tests() -> None:
    """Exécute tous les tests unitaires spécifiés avec des assertions.
    
    Peut être lancée depuis le menu principal ou avec l'argument --test.
    """
    print("\n" + "=" * 55)
    print(" DÉMARRAGE DE LA SUITE DE TESTS UNITAIRES")
    print("=" * 55)

    # --------------------------------------------------------------------------
    # 1. Exemple de l'énoncé : Ali paie 90 TND pour Ali, Sara, Omar
    # --------------------------------------------------------------------------
    g1 = creer_groupe("Coloc Énoncé")
    ajouter_membre(g1, "Ali")
    ajouter_membre(g1, "Sara")
    ajouter_membre(g1, "Omar")
    ajouter_depense(g1, "2026-11-01", 90000, "Ali", ["Ali", "Sara", "Omar"], "Courses", "Courses hebdo")

    soldes1 = calculer_soldes(g1)
    assert soldes1["Ali"] == 60000, f"Attendu 60000, obtenu {soldes1['Ali']}"
    assert soldes1["Sara"] == -30000, f"Attendu -30000, obtenu {soldes1['Sara']}"
    assert soldes1["Omar"] == -30000, f"Attendu -30000, obtenu {soldes1['Omar']}"
    assert verifier_soldes(soldes1) is True, "La somme des soldes doit être nulle"

    virements1 = regler(soldes1)
    assert len(virements1) == 2, f"Attendu 2 virements, obtenu {len(virements1)}"
    virements1_set = {(v.debiteur, v.crediteur, v.montant) for v in virements1}
    assert virements1_set == {("Sara", "Ali", 30000), ("Omar", "Ali", 30000)}, f"Virements inattendus : {virements1_set}"
    print("✓ Test 1 : Exemple de l'énoncé (Ali 90 TND -> +60 / -30 / -30, 2 virements) validé.")

    # --------------------------------------------------------------------------
    # 2. Groupe d'un seul membre : solde 0, aucun virement
    # --------------------------------------------------------------------------
    g2 = creer_groupe("Solo")
    ajouter_membre(g2, "Ali")
    ajouter_depense(g2, "2026-11-02", 50000, "Ali", ["Ali"], "Divers", "Dépense solo")

    soldes2 = calculer_soldes(g2)
    assert soldes2["Ali"] == 0, f"Attendu solde 0, obtenu {soldes2['Ali']}"
    assert verifier_soldes(soldes2) is True
    virements2 = regler(soldes2)
    assert len(virements2) == 0, f"Attendu 0 virement, obtenu {len(virements2)}"
    print("✓ Test 2 : Groupe d'un seul membre (solde 0, aucun virement) validé.")

    # --------------------------------------------------------------------------
    # 3. 100 TND entre 3 personnes : parts 33,334 / 33,333 / 33,333
    # --------------------------------------------------------------------------
    # Ali, Omar, Sara : tri alphabétique. Ali reçoit le millime restant.
    parts3 = repartir_depense(100000, ["Sara", "Ali", "Omar"])
    assert parts3["Ali"] == 33334, f"Attendu 33334 pour Ali, obtenu {parts3['Ali']}"
    assert parts3["Omar"] == 33333, f"Attendu 33333 pour Omar, obtenu {parts3['Omar']}"
    assert parts3["Sara"] == 33333, f"Attendu 33333 pour Sara, obtenu {parts3['Sara']}"
    assert sum(parts3.values()) == 100000, "La somme des parts doit faire exactement 100000 millimes"

    g3 = creer_groupe("Trio")
    ajouter_membre(g3, "Ali")
    ajouter_membre(g3, "Omar")
    ajouter_membre(g3, "Sara")
    ajouter_depense(g3, "2026-11-03", 100000, "Ali", ["Ali", "Omar", "Sara"], "Resto", "Dîner")
    soldes3 = calculer_soldes(g3)
    assert soldes3["Ali"] == 100000 - 33334  # +66666
    assert soldes3["Omar"] == -33333
    assert soldes3["Sara"] == -33333
    assert sum(soldes3.values()) == 0
    assert verifier_soldes(soldes3) is True
    print("✓ Test 3 : Répartition 100 TND entre 3 personnes (33,334 / 33,333 / 33,333) validée.")

    # --------------------------------------------------------------------------
    # 4. Nom en double ('ali' puis 'Ali') refusé
    # --------------------------------------------------------------------------
    g4 = creer_groupe("Test Doublon")
    ajouter_membre(g4, "ali")
    try:
        ajouter_membre(g4, "Ali")
        assert False, "L'ajout d'un doublon insensible à la casse aurait dû être refusé"
    except ValueError:
        pass
    print("✓ Test 4 : Nom de membre en double ('ali' puis 'Ali') refusé.")

    # --------------------------------------------------------------------------
    # 5. Suppression d'un membre qui a des dépenses refusée
    # --------------------------------------------------------------------------
    g5 = creer_groupe("Test Suppression")
    ajouter_membre(g5, "Ali")
    ajouter_membre(g5, "Sara")
    ajouter_depense(g5, "2026-11-04", 45000, "Ali", ["Sara"], "Courses", "Lait")

    # Tentative de suppression du payeur
    try:
        supprimer_membre(g5, "Ali")
        assert False, "La suppression du payeur aurait dû être refusée"
    except ValueError:
        pass

    # Tentative de suppression du bénéficiaire
    try:
        supprimer_membre(g5, "Sara")
        assert False, "La suppression du bénéficiaire aurait dû être refusée"
    except ValueError:
        pass

    # Un membre sans dépense peut être supprimé
    ajouter_membre(g5, "Youssef")
    assert "Youssef" in lister_membres(g5)
    supprimer_membre(g5, "Youssef")
    assert "Youssef" not in lister_membres(g5)
    print("✓ Test 5 : Suppression d'un membre apparaissant dans une dépense refusée.")

    # --------------------------------------------------------------------------
    # 6. Date invalide, montant <= 0, payeur inconnu refusés
    # --------------------------------------------------------------------------
    g6 = creer_groupe("Test Validations")
    ajouter_membre(g6, "Ali")
    ajouter_membre(g6, "Sara")

    # Dates invalides (format ou jour inexistant)
    for date_err in ["2026-02-30", "01-11-2026", "2026/11/01", "texte", ""]:
        try:
            ajouter_depense(g6, date_err, 10000, "Ali", ["Ali", "Sara"])
            assert False, f"La date invalide '{date_err}' aurait dû lever une ValueError"
        except ValueError:
            pass

    # Montants négatifs ou nuls
    for montant_err in [0, -1, -50000]:
        try:
            ajouter_depense(g6, "2026-11-01", montant_err, "Ali", ["Ali", "Sara"])
            assert False, f"Le montant invalide '{montant_err}' aurait dû lever une ValueError"
        except ValueError:
            pass

    # Payeur inconnu
    try:
        ajouter_depense(g6, "2026-11-01", 10000, "Inconnu", ["Ali", "Sara"])
        assert False, "Un payeur inconnu aurait dû lever une ValueError"
    except ValueError:
        pass

    # Bénéficiaire inconnu
    try:
        ajouter_depense(g6, "2026-11-01", 10000, "Ali", ["Ali", "Inconnu"])
        assert False, "Un bénéficiaire inconnu aurait dû lever une ValueError"
    except ValueError:
        pass

    # Aucun bénéficiaire
    try:
        ajouter_depense(g6, "2026-11-01", 10000, "Ali", [])
        assert False, "Une liste vide de bénéficiaires aurait dû lever une ValueError"
    except ValueError:
        pass
    print("✓ Test 6 : Rejet des dates invalides, montants <= 0 et membres inconnus validé.")

    # --------------------------------------------------------------------------
    # 7. Filtre par catégorie, par membre, par période (fermeture)
    # --------------------------------------------------------------------------
    g7 = creer_groupe("Test Filtres")
    ajouter_membre(g7, "Ali")
    ajouter_membre(g7, "Sara")
    ajouter_membre(g7, "Omar")
    d1 = ajouter_depense(g7, "2026-10-05", 30000, "Ali", ["Ali", "Sara"], "Courses", "Légumes")
    d2 = ajouter_depense(g7, "2026-10-15", 50000, "Sara", ["Sara", "Omar"], "Transport", "Train")
    d3 = ajouter_depense(g7, "2026-11-02", 40000, "Omar", ["Ali", "Omar"], "Courses", "Supermarché")

    # Filtre par catégorie (Courses) -> d1 et d3
    f_cat = creer_filtre(categorie="courses")
    res_cat = filtrer_depenses(g7.depenses, f_cat)
    assert [d.id for d in res_cat] == [d1.id, d3.id]

    # Filtre par membre ('ali' : payeur dans d1, bénéficiaire dans d3)
    f_mem = creer_filtre(membre="ali")
    res_mem = filtrer_depenses(g7.depenses, f_mem)
    assert [d.id for d in res_mem] == [d1.id, d3.id]

    # Filtre par période inclusive [2026-10-05, 2026-10-15] -> d1 et d2
    f_per = creer_filtre(date_debut="2026-10-05", date_fin="2026-10-15")
    res_per = filtrer_depenses(g7.depenses, f_per)
    assert [d.id for d in res_per] == [d1.id, d2.id]

    # Filtre combiné : Courses + Ali + Octobre -> uniquement d1
    f_comb = creer_filtre(categorie="Courses", membre="Ali", date_debut="2026-10-01", date_fin="2026-10-31")
    res_comb = filtrer_depenses(g7.depenses, f_comb)
    assert [d.id for d in res_comb] == [d1.id]
    print("✓ Test 7 : Filtrage par catégorie, membre et période avec fermeture validé.")

    # --------------------------------------------------------------------------
    # 8. Sauvegarde puis rechargement JSON : données identiques
    # --------------------------------------------------------------------------
    fichier_test = "_test_groupe_temporaire.json"
    sauvegarder_groupe(g7, fichier_test)
    g7_recup = charger_groupe(fichier_test)

    assert g7_recup.nom == g7.nom
    assert g7_recup.prochain_id == g7.prochain_id
    assert [m.nom for m in g7_recup.membres] == [m.nom for m in g7.membres]
    assert len(g7_recup.depenses) == len(g7.depenses)
    for orig, recup in zip(g7.depenses, g7_recup.depenses):
        assert orig.id == recup.id
        assert orig.date == recup.date
        assert orig.montant == recup.montant
        assert orig.payeur.nom == recup.payeur.nom
        assert [b.nom for b in orig.beneficiaires] == [b.nom for b in recup.beneficiaires]
        assert orig.categorie == recup.categorie
        assert orig.description == recup.description

    if os.path.exists(fichier_test):
        os.remove(fichier_test)
    print("✓ Test 8 : Sauvegarde et rechargement JSON (données identiques) validés.")

    # --------------------------------------------------------------------------
    # 9. Plusieurs dépenses croisées (Ali paie 90 pour 3, Sara paie 60 pour 3)
    # --------------------------------------------------------------------------
    g9 = creer_groupe("Dépenses Croisées")
    ajouter_membre(g9, "Ali")
    ajouter_membre(g9, "Sara")
    ajouter_membre(g9, "Omar")
    ajouter_depense(g9, "2026-11-01", 90000, "Ali", ["Ali", "Sara", "Omar"])
    ajouter_depense(g9, "2026-11-02", 60000, "Sara", ["Ali", "Sara", "Omar"])

    soldes9 = calculer_soldes(g9)
    # Total payé : Ali 90000, Sara 60000, Omar 0.
    # Total dû   : Ali 30000 + 20000 = 50000 -> Solde = +40000
    #              Sara 30000 + 20000 = 50000 -> Solde = +10000
    #              Omar 30000 + 20000 = 50000 -> Solde = -50000
    assert soldes9["Ali"] == 40000
    assert soldes9["Sara"] == 10000
    assert soldes9["Omar"] == -50000
    assert verifier_soldes(soldes9) is True

    virements9 = regler(soldes9)
    assert len(virements9) == 2, f"Attendu 2 virements, obtenu {len(virements9)}"
    virements9_set = {(v.debiteur, v.crediteur, v.montant) for v in virements9}
    assert virements9_set == {("Omar", "Ali", 40000), ("Omar", "Sara", 10000)}
    print("✓ Test 9 : Plusieurs dépenses croisées avec résolution des soldes validées.")

    # --------------------------------------------------------------------------
    # 10. Parsing et formatage des montants
    # --------------------------------------------------------------------------
    assert parse_montant("12.5") == 12500
    assert parse_montant("12,5") == 12500
    assert parse_montant("12") == 12000
    assert parse_montant("0.001") == 1
    assert parse_montant("100") == 100000
    assert format_montant(12500) == "12,500 TND"
    assert format_montant(0) == "0,000 TND"
    assert format_montant(-30000) == "-30,000 TND"

    # Erreurs de parsing attendues
    for p_err in ["12.1234", "abc", "-5", "12.3.4", ""]:
        try:
            parse_montant(p_err)
            assert False, f"parse_montant('{p_err}') aurait dû lever une ValueError"
        except ValueError:
            pass
    print("✓ Test 10 : Parsing exact et formatage des montants validés.")

    print("=" * 55)
    print("TOUS LES TESTS ONT ÉTÉ EXÉCUTÉS AVEC SUCCÈS (10/10) !")
    print("=" * 55 + "\n")


# ==============================================================================
# POINT D'ENTRÉE DU SCRIPT
# ==============================================================================

if __name__ == "__main__":
    if "--test" in sys.argv:
        tests()
        sys.exit(0)
    else:
        boucle_principale()
