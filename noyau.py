#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
noyau.py — Noyau métier de l'application Dépenses Partagées.

Contient :
  - Les classes de données : Membre, Depense, Groupe
  - La gestion des montants en millimes (entiers, sans float)
  - Toutes les validations (R1 à R6)
  - Les fonctionnalités F1 à F15 (sans interface utilisateur)

Choix technique : montants stockés en entiers (millimes, 1 TND = 1 000 millimes).
Justification : évite toute erreur d'arrondi flottant ; les affichages se font
uniquement via format_montant().

Règle d'arrondi documentée : lorsque M millimes ne se divisent pas exactement
entre n bénéficiaires, le reste r < n millimes est distribué à raison de +1 millime
aux r premiers bénéficiaires dans l'ordre ALPHABÉTIQUE insensible à la casse.
La somme des parts est toujours exactement M.

Dépense « soldée » (conforme au cahier des charges) :
  - chaque dépense a un champ `soldee` (False à la création) ;
  - marquer_soldees() (« J'ai réglé les virements ») passe toutes les dépenses à True ;
  - un membre présent (payeur ou bénéficiaire) dans au moins une dépense NON soldée
    ne peut pas être supprimé (R5) ;
  - les soldes (F10) ne tiennent compte que des dépenses non soldées : une fois les
    virements effectués, tous les soldes repassent à 0.
"""

from dataclasses import dataclass, field
from datetime import datetime
import json
from typing import Callable


# ==============================================================================
# MODÈLE DE DONNÉES — 3 classes (+ tuples pour les virements)
# ==============================================================================

@dataclass
class Membre:
    """Représente un membre du groupe.

    L'égalité et le hachage sont insensibles à la casse ('ali' == 'Ali').
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
    """Représente une dépense partagée.

    Champs :
        id            : identifiant entier unique (auto-incrémenté par Groupe)
        date          : chaîne au format AAAA-MM-JJ
        montant       : entier en millimes (ex: 90 TND = 90 000 millimes)
        payeur        : membre ayant avancé la somme
        beneficiaires : liste d'au moins un membre bénéficiaire
        categorie     : catégorie libre (ex: Courses, Transport)
        description   : texte libre facultatif
        soldee        : False à la création ; True une fois les virements effectués
    """
    id: int
    date: str
    montant: int
    payeur: Membre
    beneficiaires: list[Membre]
    categorie: str = "Général"
    description: str = ""
    soldee: bool = False

    def __post_init__(self) -> None:
        # Normalisation : accepte str en entrée pour faciliter les tests
        if isinstance(self.payeur, str):
            self.payeur = Membre(self.payeur)
        self.beneficiaires = [
            Membre(b) if isinstance(b, str) else b
            for b in self.beneficiaires
        ]


@dataclass
class Groupe:
    """Représente le groupe de partage de dépenses.

    Champs :
        nom         : nom non vide du groupe
        membres     : liste des membres enregistrés
        depenses    : liste des dépenses enregistrées
        prochain_id : compteur auto-incrémenté pour les IDs de dépenses

    Les méthodes ci-dessous (ajouter_membre, calculer_soldes, ...) sont de fines
    façades vers les fonctions du module : elles correspondent aux méthodes du
    diagramme de classes du cahier des charges.
    """
    nom: str
    membres: list[Membre] = field(default_factory=list)
    depenses: list[Depense] = field(default_factory=list)
    prochain_id: int = 1

    def __post_init__(self) -> None:
        self.membres = [
            Membre(m) if isinstance(m, str) else m
            for m in self.membres
        ]

    # --- Membres ---
    def ajouter_membre(self, nom):
        return ajouter_membre(self, nom)

    def supprimer_membre(self, nom):
        return supprimer_membre(self, nom)

    def lister_membres(self):
        return lister_membres(self)

    # --- Dépenses ---
    def ajouter_depense(self, *args, **kwargs):
        return ajouter_depense(self, *args, **kwargs)

    def modifier_depense(self, *args, **kwargs):
        return modifier_depense(self, *args, **kwargs)

    def supprimer_depense(self, depense_id):
        return supprimer_depense(self, depense_id)

    def lister_depenses(self, cle: str = "date", decroissant: bool = False):
        return trier_depenses(self.depenses, cle=cle, decroissant=decroissant)

    # --- Soldes ---
    def calculer_soldes(self, inclure_soldees: bool = False):
        return calculer_soldes(self, inclure_soldees)

    def somme_nulle(self) -> bool:
        return verifier_soldes(calculer_soldes(self))

    def marquer_soldees(self) -> int:
        return marquer_soldees(self)


# Un virement est un tuple simple (débiteur, créditeur, montant_en_millimes)
# Pas de classe dédiée : regler() retourne une list[tuple[str, str, int]]


class SoldesDict(dict):
    """Dictionnaire de soldes avec accès insensible à la casse."""

    def __getitem__(self, key):
        cle = key.nom if isinstance(key, Membre) else str(key)
        for k in self.keys():
            if k.casefold() == cle.casefold():
                return super().__getitem__(k)
        return super().__getitem__(key)

    def __contains__(self, key):
        cle = key.nom if isinstance(key, Membre) else str(key)
        for k in self.keys():
            if k.casefold() == cle.casefold():
                return True
        return False

    def get(self, key, default=None):
        try:
            return self[key]
        except KeyError:
            return default


# ==============================================================================
# GESTION DES MONTANTS
# ==============================================================================

def _est_entier_ascii(s: str) -> bool:
    """Vrai si s est non vide et composée uniquement de chiffres ASCII 0-9."""
    return s.isascii() and s.isdigit()


def parse_montant(texte: str) -> int:
    """Convertit une chaîne saisie par l'utilisateur en millimes (entier).

    Accepte '.' ou ',' comme séparateur décimal ; maximum 3 décimales.
    Exemples :
        '90'     -> 90 000
        '12.5'   -> 12 500
        '12,500' -> 12 500
        '0.001'  ->      1
    """
    if not isinstance(texte, str):
        raise ValueError("Le montant doit être une chaîne de caractères.")
    nettoye = texte.strip().replace(" ", "").replace(",", ".")
    if not nettoye:
        raise ValueError("Le montant ne peut pas être vide.")
    if nettoye.startswith("-"):
        raise ValueError("Le montant doit être positif.")

    parties = nettoye.split(".")
    if len(parties) == 1:
        if not _est_entier_ascii(parties[0]):
            raise ValueError(f"Format invalide : '{texte}'.")
        return int(parties[0]) * 1000
    elif len(parties) == 2:
        entier_str, dec_str = parties
        if (entier_str and not _est_entier_ascii(entier_str)) or \
           (dec_str and not _est_entier_ascii(dec_str)):
            raise ValueError(f"Format invalide : '{texte}'.")
        if len(dec_str) > 3:
            raise ValueError("Maximum 3 décimales (précision au millime).")
        dec_pad = dec_str.ljust(3, "0")
        return (int(entier_str) if entier_str else 0) * 1000 + int(dec_pad)
    else:
        raise ValueError(f"Format invalide (plusieurs points) : '{texte}'.")


def format_montant(millimes: int) -> str:
    """Formate un montant en millimes pour l'affichage : '-12,500 TND'."""
    signe = "-" if millimes < 0 else ""
    valeur = abs(millimes)
    return f"{signe}{valeur // 1000},{valeur % 1000:03d} TND"


# ==============================================================================
# FONCTIONS UTILITAIRES (sans validation)
# ==============================================================================

def trouver_membre(groupe: Groupe, nom_ou_membre: str | Membre) -> Membre | None:
    """Recherche un membre dans le groupe (insensible à la casse)."""
    cherche = (
        nom_ou_membre.nom if isinstance(nom_ou_membre, Membre) else str(nom_ou_membre)
    ).strip().casefold()
    for m in groupe.membres:
        if m.nom.casefold() == cherche:
            return m
    return None


def repartir_depense(montant: int, beneficiaires: list[str | Membre]) -> dict[str, int]:
    """Répartit un montant équitablement entre les bénéficiaires (en millimes).

    Règle d'arrondi documentée :
        base = montant // n  ;  reste = montant % n
        Les 'reste' premiers bénéficiaires (ordre alphabétique insensible à la casse)
        reçoivent base + 1 millime. La somme des parts vaut exactement montant.
    """
    if not beneficiaires:
        raise ValueError("La liste des bénéficiaires est vide.")
    noms = [b.nom if isinstance(b, Membre) else str(b) for b in beneficiaires]
    n = len(noms)
    base, reste = divmod(montant, n)
    noms_tries = sorted(noms, key=str.casefold)
    repartition: dict[str, int] = {}
    for i, nom in enumerate(noms_tries):
        repartition[nom] = base + (1 if i < reste else 0)
    assert sum(repartition.values()) == montant  # invariant de somme exacte
    return repartition


# ==============================================================================
# CALCUL DES SOLDES
# ==============================================================================

def calculer_soldes(groupe: Groupe, inclure_soldees: bool = False) -> dict[str, int]:
    """F10 : Calcule le solde de chaque membre en millimes.

    Solde = total payé par le membre − total dû par le membre.
    Un solde positif signifie que le membre est créditeur (on lui doit de l'argent).
    Un solde négatif signifie que le membre est débiteur (il doit de l'argent).

    Par défaut, seules les dépenses NON soldées sont prises en compte : une fois
    les virements effectués (marquer_soldees), tous les soldes repassent à 0.
    inclure_soldees=True calcule le solde sur tout l'historique.
    Les soldes sont recalculés à la demande ; ils ne sont jamais stockés.
    """
    soldes = SoldesDict({m.nom: 0 for m in groupe.membres})

    for depense in groupe.depenses:
        if depense.soldee and not inclure_soldees:
            continue

        # Le payeur a avancé le montant total → crédit
        m_payeur = trouver_membre(groupe, depense.payeur)
        nom_payeur = m_payeur.nom if m_payeur else depense.payeur.nom
        soldes[nom_payeur] = soldes.get(nom_payeur, 0) + depense.montant

        # Chaque bénéficiaire doit sa part → débit
        parts = repartir_depense(depense.montant, depense.beneficiaires)
        for nom_benef, part in parts.items():
            m_b = trouver_membre(groupe, nom_benef)
            nom_canon = m_b.nom if m_b else nom_benef
            soldes[nom_canon] = soldes.get(nom_canon, 0) - part

    return soldes


def verifier_soldes(soldes: dict[str, int]) -> bool:
    """R6 / F11 : Vérifie que la somme des soldes est nulle (tolérance : 10 millimes = 0,01 TND)."""
    return abs(sum(soldes.values())) <= 10


def marquer_soldees(groupe: Groupe) -> int:
    """« J'ai réglé les virements » : passe toutes les dépenses à soldee = True.

    Retourne le nombre de dépenses nouvellement marquées.
    """
    nb = 0
    for d in groupe.depenses:
        if not d.soldee:
            d.soldee = True
            nb += 1
    return nb


# ==============================================================================
# VALIDATIONS R1 À R5
# ==============================================================================

def valider_date(date_str: str) -> str:
    """R1 : Vérifie le format AAAA-MM-JJ avec datetime.strptime()."""
    if not isinstance(date_str, str):
        raise ValueError("La date doit être une chaîne de caractères.")
    nettoye = date_str.strip()
    try:
        return datetime.strptime(nettoye, "%Y-%m-%d").strftime("%Y-%m-%d")
    except ValueError:
        raise ValueError(
            f"Date invalide : '{date_str}'. Format attendu : AAAA-MM-JJ (ex: 2026-11-01)."
        )


def valider_montant(montant: int) -> int:
    """R2 : Vérifie que le montant en millimes est strictement positif."""
    if montant <= 0:
        raise ValueError(f"Le montant doit être > 0. Reçu : {montant} millimes.")
    return montant


def valider_membres_depense(
    groupe: Groupe,
    payeur: str | Membre,
    beneficiaires: list[str | Membre],
) -> tuple[Membre, list[Membre]]:
    """R3 : Vérifie que le payeur et les bénéficiaires sont membres du groupe."""
    m_payeur = trouver_membre(groupe, payeur)
    if not m_payeur:
        raise ValueError(f"Payeur inconnu : '{payeur}'. Il doit être membre du groupe.")
    if not beneficiaires:
        raise ValueError("Une dépense doit comporter au moins un bénéficiaire.")
    m_benefs: list[Membre] = []
    vus: set[str] = set()
    for b in beneficiaires:
        m_b = trouver_membre(groupe, b)
        if not m_b:
            raise ValueError(f"Bénéficiaire inconnu : '{b}'. Il doit être membre du groupe.")
        if m_b.nom.casefold() not in vus:
            vus.add(m_b.nom.casefold())
            m_benefs.append(m_b)
    return m_payeur, m_benefs


def valider_nom_membre(groupe: Groupe, nom: str) -> str:
    """R4 : Vérifie que le nom est non vide et unique dans le groupe (casse ignorée)."""
    if not isinstance(nom, str):
        raise ValueError("Le nom doit être une chaîne de caractères.")
    nettoye = nom.strip()
    if not nettoye:
        raise ValueError("Le nom du membre ne peut pas être vide.")
    if trouver_membre(groupe, nettoye) is not None:
        raise ValueError(f"Le membre '{nettoye}' existe déjà (la casse est ignorée).")
    return nettoye


def verifier_suppression_membre(groupe: Groupe, nom: str | Membre) -> Membre:
    """R5 : Un membre présent dans une dépense non soldée ne peut pas être supprimé.

    Conforme au cahier des charges : on regarde le champ `soldee` des dépenses.
    Si le membre est payeur OU bénéficiaire d'au moins une dépense dont
    soldee == False, la suppression est refusée. Il faut d'abord régler les
    virements (marquer_soldees), après quoi le membre peut être retiré.

    Avantage : après suppression, aucune dépense non soldée ne référence un
    membre disparu, donc les soldes ne contiennent jamais de « membre fantôme ».
    """
    membre = trouver_membre(groupe, nom)
    if not membre:
        raise ValueError(f"Membre '{nom}' introuvable dans le groupe.")

    for d in groupe.depenses:
        if d.soldee:
            continue
        if d.payeur == membre or any(b == membre for b in d.beneficiaires):
            raise ValueError(
                f"Impossible de supprimer '{membre.nom}' : il figure dans la dépense "
                f"non soldée #{d.id}. Réglez d'abord les virements "
                f"(« J'ai réglé les virements »)."
            )
    return membre


# ==============================================================================
# F1 À F9 — GESTION DU GROUPE, MEMBRES, DÉPENSES, TRI ET FILTRAGE
# ==============================================================================

def creer_groupe(nom: str) -> Groupe:
    """F1 : Crée un nouveau groupe vide."""
    if not isinstance(nom, str) or not nom.strip():
        raise ValueError("Le nom du groupe ne peut pas être vide.")
    return Groupe(nom=nom.strip(), membres=[], depenses=[], prochain_id=1)


def ajouter_membre(groupe: Groupe, nom: str | Membre) -> Membre:
    """F2 : Ajoute un membre après validation R4 (unicité, non vide)."""
    nom_str = nom.nom if isinstance(nom, Membre) else str(nom)
    nom_valide = valider_nom_membre(groupe, nom_str)
    nouveau = Membre(nom=nom_valide)
    groupe.membres.append(nouveau)
    return nouveau


def supprimer_membre(groupe: Groupe, nom: str | Membre) -> Membre:
    """F3 : Supprime un membre après contrôle R5 (aucune dépense non soldée)."""
    membre = verifier_suppression_membre(groupe, nom)
    groupe.membres = [m for m in groupe.membres if m.nom.casefold() != membre.nom.casefold()]
    return membre


def lister_membres(groupe: Groupe) -> list[str]:
    """F4 : Retourne la liste des noms des membres du groupe."""
    return [m.nom for m in groupe.membres]


def ajouter_depense(
    groupe: Groupe,
    date: str,
    montant: int | str,
    payeur: str | Membre,
    beneficiaires: list[str | Membre] | None = None,
    categorie: str = "Général",
    description: str = "",
) -> Depense:
    """F5 : Ajoute une dépense avec validations R1, R2, R3 (soldee = False).

    Par défaut, tous les membres du groupe sont bénéficiaires (parts égales).
    """
    date_v = valider_date(date)
    montant_m = parse_montant(montant) if isinstance(montant, str) else montant
    valider_montant(montant_m)

    if beneficiaires is None:
        if not groupe.membres:
            raise ValueError("Le groupe ne contient aucun membre.")
        liste_benef = list(groupe.membres)
    else:
        if len(beneficiaires) == 0:
            raise ValueError("Au moins un bénéficiaire est requis.")
        liste_benef = list(beneficiaires)

    m_payeur, m_benefs = valider_membres_depense(groupe, payeur, liste_benef)
    cat = categorie.strip() if categorie and categorie.strip() else "Général"
    desc = description.strip() if description else ""

    dep = Depense(
        id=groupe.prochain_id,
        date=date_v,
        montant=montant_m,
        payeur=m_payeur,
        beneficiaires=m_benefs,
        categorie=cat,
        description=desc,
        soldee=False,
    )
    groupe.prochain_id += 1
    groupe.depenses.append(dep)
    return dep


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
    """F6 : Modifie une dépense existante par son ID."""
    dep = next((d for d in groupe.depenses if d.id == depense_id), None)
    if not dep:
        raise ValueError(f"Dépense #{depense_id} introuvable.")

    new_date = valider_date(date) if date is not None else dep.date

    if montant is not None:
        new_montant = parse_montant(montant) if isinstance(montant, str) else montant
        valider_montant(new_montant)
    else:
        new_montant = dep.montant

    new_payeur = payeur if payeur is not None else dep.payeur
    new_benefs = beneficiaires if beneficiaires is not None else dep.beneficiaires
    m_payeur, m_benefs = valider_membres_depense(groupe, new_payeur, new_benefs)

    dep.date = new_date
    dep.montant = new_montant
    dep.payeur = m_payeur
    dep.beneficiaires = m_benefs
    dep.categorie = (categorie.strip() if categorie is not None else dep.categorie) or "Général"
    dep.description = description.strip() if description is not None else dep.description
    return dep


def supprimer_depense(groupe: Groupe, depense_id: int) -> Depense:
    """F7 : Supprime une dépense par son identifiant."""
    for i, d in enumerate(groupe.depenses):
        if d.id == depense_id:
            return groupe.depenses.pop(i)
    raise ValueError(f"Dépense #{depense_id} introuvable.")


def trier_depenses(
    depenses: list[Depense],
    cle: str = "date",
    decroissant: bool = False,
) -> list[Depense]:
    """F8 : Trie les dépenses par 'date' ou 'montant'."""
    cle_n = cle.strip().lower()
    if cle_n == "date":
        return sorted(depenses, key=lambda d: (d.date, d.id), reverse=decroissant)
    elif cle_n == "montant":
        return sorted(depenses, key=lambda d: (d.montant, d.id), reverse=decroissant)
    raise ValueError("Clé de tri invalide : choisissez 'date' ou 'montant'.")


def creer_filtre(
    categorie: str | None = None,
    membre: str | None = None,
    date_debut: str | None = None,
    date_fin: str | None = None,
) -> Callable[[Depense], bool]:
    """F9 : Crée et retourne une fermeture (closure) filtre(depense) -> bool.

    'membre' signifie payeur OU bénéficiaire.
    La période [date_debut, date_fin] est inclusive.
    Tous les critères non fournis sont ignorés (filtre passe-tout).
    """
    cat_c   = categorie.strip().casefold()   if (categorie   and categorie.strip())   else None
    mem_c   = membre.strip().casefold()      if (membre      and membre.strip())      else None
    debut_c = date_debut.strip()             if (date_debut  and date_debut.strip())  else None
    fin_c   = date_fin.strip()               if (date_fin    and date_fin.strip())    else None

    def filtre(dep: Depense) -> bool:
        if cat_c is not None and dep.categorie.strip().casefold() != cat_c:
            return False
        if mem_c is not None:
            est_payeur = dep.payeur.nom.casefold() == mem_c
            est_benef  = any(b.nom.casefold() == mem_c for b in dep.beneficiaires)
            if not (est_payeur or est_benef):
                return False
        if debut_c is not None and dep.date < debut_c:
            return False
        if fin_c   is not None and dep.date > fin_c:
            return False
        return True

    return filtre


# Filtres à critère unique (noms utilisés dans le cahier des charges, section 10)
def filtre_categorie(categorie: str) -> Callable[[Depense], bool]:
    """Fermeture filtrant sur une seule catégorie."""
    return creer_filtre(categorie=categorie)


def filtre_membre(membre: str) -> Callable[[Depense], bool]:
    """Fermeture filtrant sur un membre (payeur ou bénéficiaire)."""
    return creer_filtre(membre=membre)


def filtre_periode(date_debut: str | None = None,
                   date_fin: str | None = None) -> Callable[[Depense], bool]:
    """Fermeture filtrant sur une période inclusive."""
    return creer_filtre(date_debut=date_debut, date_fin=date_fin)


def filtrer_depenses(
    depenses: list[Depense],
    filtre_fn: Callable[[Depense], bool],
) -> list[Depense]:
    """Applique la fermeture de filtrage sur une liste de dépenses."""
    return list(filter(filtre_fn, depenses))


# ==============================================================================
# F12 — RÈGLEMENT (algorithme glouton)
# ==============================================================================

def regler(soldes: dict[str, int]) -> list[tuple]:
    """F12 : Calcule la liste minimale de virements pour solder tous les comptes.

    Retourne une liste de tuples (débiteur, créditeur, montant_en_millimes).
    Algorithme glouton (au plus n − 1 virements) :
        À chaque étape, le plus grand débiteur rembourse le plus grand créditeur
        du montant minimum(dû, à recevoir). En cas d'égalité, ordre alphabétique.
    Ne modifie pas le dictionnaire reçu (travaille sur une copie).
    """
    debiteurs  = {m: -s for m, s in soldes.items() if s < 0}
    crediteurs = {m:  s for m, s in soldes.items() if s > 0}
    virements: list[tuple] = []

    while debiteurs and crediteurs:
        d_nom = min(debiteurs,  key=lambda m: (-debiteurs[m],  m.casefold()))
        c_nom = min(crediteurs, key=lambda m: (-crediteurs[m], m.casefold()))
        montant = min(debiteurs[d_nom], crediteurs[c_nom])
        virements.append((d_nom, c_nom, montant))       # tuple (débiteur, créditeur, montant)
        debiteurs[d_nom]  -= montant
        crediteurs[c_nom] -= montant
        if debiteurs[d_nom]  == 0: del debiteurs[d_nom]
        if crediteurs[c_nom] == 0: del crediteurs[c_nom]

    return virements


# ==============================================================================
# F15 — SAUVEGARDE ET CHARGEMENT JSON
# ==============================================================================

def sauvegarder_groupe(groupe: Groupe, chemin: str = "groupe.json") -> None:
    """F15 : Sauvegarde toutes les données du groupe dans un fichier JSON (UTF-8)."""
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
                "soldee": d.soldee,
            }
            for d in groupe.depenses
        ],
    }
    with open(chemin, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def charger_groupe(chemin: str = "groupe.json") -> Groupe:
    """F15 : Recharge un groupe depuis un fichier JSON.

    Compatible avec les anciens fichiers sans champ « soldee » (→ False).
    """
    with open(chemin, "r", encoding="utf-8") as f:
        data = json.load(f)

    membres = [Membre(m) for m in data.get("membres", [])]
    prochain_id = data.get("prochain_id", 1)
    depenses: list[Depense] = []

    for d in data.get("depenses", []):
        depenses.append(Depense(
            id=d["id"],
            date=d["date"],
            montant=d["montant"],
            payeur=Membre(d["payeur"]),
            beneficiaires=[Membre(b) for b in d["beneficiaires"]],
            categorie=d.get("categorie", "Général"),
            description=d.get("description", ""),
            soldee=bool(d.get("soldee", False)),
        ))

    # Restauration robuste de l'id
    if depenses:
        max_id = max(d.id for d in depenses)
        if prochain_id <= max_id:
            prochain_id = max_id + 1

    return Groupe(nom=data["nom"], membres=membres, depenses=depenses, prochain_id=prochain_id)