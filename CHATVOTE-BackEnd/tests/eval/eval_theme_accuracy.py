"""
Labeled evaluation set for theme classifier accuracy.

Run: poetry run python tests/eval/eval_theme_accuracy.py

Reports per-theme precision/recall/F1 and overall accuracy.
Target: >95% accuracy on keyword fast-path (for chunks it claims to classify).
Note: In production, most chunks go through LLM — this tests the keyword
fast-path quality on obvious cases only.
"""

import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.services.theme_classifier import _keyword_scores, classify_theme_keywords


@dataclass
class LabeledSample:
    text: str
    expected_theme: Optional[str]
    expected_sub_theme: Optional[str] = None


EVAL_SET: list[LabeledSample] = [
    # ---- economie (5) ----
    LabeledSample("Le budget de l'État prévoit une réduction de la dette publique de 3%", "economie", "dette publique"),
    LabeledSample("Augmenter le salaire minimum pour renforcer le pouvoir d'achat", "economie", "pouvoir d'achat"),
    LabeledSample("Le taux de chômage a baissé de 0.5 points ce trimestre", "economie", "emploi"),
    LabeledSample("Soutenir les entreprises locales par des aides à l'investissement", "economie", "investissement"),
    LabeledSample("La réforme fiscale prévoit un nouvel impôt sur les grandes fortunes", "economie", "fiscalité"),

    # ---- education (4) ----
    LabeledSample("Recrutement de 5000 enseignants pour les écoles primaires", "education", "enseignement primaire"),
    LabeledSample("Réforme de l'université et de l'enseignement supérieur", "education", "enseignement supérieur"),
    LabeledSample("Ouverture de nouvelles crèches municipales pour la petite enfance", "education", "petite enfance"),
    LabeledSample("Le lycée professionnel doit être revalorisé avec plus de formation en apprentissage", "education"),

    # ---- environnement (5) ----
    LabeledSample("Lutter contre le changement climatique et réduire les émissions de carbone", "environnement", "changement climatique"),
    LabeledSample("Installation de panneaux solaires et développement de l'éolien", "environnement", "énergies renouvelables"),
    LabeledSample("Améliorer le recyclage et la gestion des déchets ménagers", "environnement", "gestion des déchets"),
    LabeledSample("Préserver la biodiversité et protéger les espaces naturels", "environnement", "biodiversité"),
    LabeledSample("Lutter contre la pollution de l'air dans les grandes villes", "environnement", "qualité de l'air"),

    # ---- sante (4) ----
    LabeledSample("Moderniser l'hôpital public et recruter des médecins", "sante", "hôpitaux"),
    LabeledSample("Campagne de vaccination contre la grippe dans les EHPAD", "sante"),
    LabeledSample("Créer des maisons de santé en zone rurale pour l'accès aux soins", "sante", "accès aux soins"),
    LabeledSample("Revaloriser le salaire des infirmiers et des soignants", "sante", "personnel soignant"),

    # ---- securite (4) ----
    LabeledSample("Renforcer les effectifs de police et de gendarmerie", "securite", "forces de l'ordre"),
    LabeledSample("Installer des caméras de vidéoprotection dans le centre-ville", "securite", "vidéoprotection"),
    LabeledSample("Lutter contre la délinquance et les cambriolages", "securite", "délinquance"),
    LabeledSample("Plan de prévention contre les violences faites aux femmes", "securite", "violences"),

    # ---- immigration (3) ----
    LabeledSample("Accueillir les migrants et demandeurs d'asile dans la dignité", "immigration", "droit d'asile"),
    LabeledSample("Renforcer le contrôle aux frontières de l'espace Schengen", "immigration", "contrôle des frontières"),
    LabeledSample("Programme d'intégration et de régularisation des étrangers", "immigration", "intégration"),

    # ---- culture (4) ----
    LabeledSample("Rénover le musée municipal et soutenir le patrimoine local", "culture", "patrimoine"),
    LabeledSample("Organiser un festival de théâtre et de spectacle vivant", "culture", "spectacle vivant"),
    LabeledSample("Ouvrir une nouvelle bibliothèque dans le quartier nord", "culture", "bibliothèques"),
    LabeledSample("Développer le pass culture pour les jeunes de 15 à 18 ans", "culture", "pass culture"),

    # ---- logement (4) ----
    LabeledSample("Construire 1000 logements sociaux HLM dans la commune", "logement", "logement social"),
    LabeledSample("Encadrer les loyers pour protéger les locataires", "logement", "encadrement des loyers"),
    LabeledSample("Plan de rénovation thermique des bâtiments anciens", "logement", "rénovation thermique"),
    LabeledSample("Lutter contre l'habitat insalubre et indigne", "logement", "habitat indigne"),

    # ---- transport (4) ----
    LabeledSample("Développer les pistes cyclables et le vélo en ville", "transport", "mobilités douces"),
    LabeledSample("Extension de la ligne de tramway et du métro", "transport", "transports en commun"),
    LabeledSample("Réduire le stationnement payant dans le centre-ville", "transport", "stationnement"),
    LabeledSample("Améliorer le réseau ferroviaire et les lignes de train régional", "transport", "ferroviaire"),

    # ---- numerique (3) ----
    LabeledSample("Déploiement de la fibre optique et de l'internet haut débit", "numerique", "couverture numérique"),
    LabeledSample("Renforcer la cybersécurité des administrations publiques", "numerique", "cybersécurité"),
    LabeledSample("Ouvrir un tiers-lieu numérique pour le télétravail", "numerique", "tiers-lieux"),

    # ---- agriculture (3) ----
    LabeledSample("Soutenir les agriculteurs locaux et développer le circuit court", "agriculture"),
    LabeledSample("Promouvoir l'agriculture biologique et réduire les pesticides", "agriculture", "agriculture biologique"),
    LabeledSample("Créer une épicerie solidaire avec des produits du producteur local", "agriculture", "circuits courts"),

    # ---- justice (3) ----
    LabeledSample("Réformer le tribunal et recruter des magistrats", "justice", "organisation judiciaire"),
    LabeledSample("Améliorer les conditions dans les prisons et la réinsertion", "justice", "système pénitentiaire"),
    LabeledSample("Développer la médiation pour désengorger les tribunaux", "justice", "médiation"),

    # ---- international (3) ----
    LabeledSample("Renforcer la coopération avec l'OTAN et la défense européenne", "international", "défense"),
    LabeledSample("La diplomatie française au service de la paix", "international", "diplomatie"),
    LabeledSample("Position de la France au sein de l'Union européenne", "international", "Union européenne"),

    # ---- institutions (3) ----
    LabeledSample("Instaurer le référendum d'initiative citoyenne (RIC)", "institutions", "démocratie directe"),
    LabeledSample("Le budget participatif permet aux citoyens de décider", "institutions", "démocratie participative"),
    LabeledSample("Réforme du conseil municipal et de la gouvernance locale", "institutions", "gouvernance locale"),

    # ---- null / non-political (4) ----
    LabeledSample("Mentions légales - Tous droits réservés - CGU", None),
    LabeledSample("Cliquez ici pour vous inscrire à la newsletter", None),
    LabeledSample("Copyright 2024 - Plan du site - Contact", None),
    LabeledSample("Lorem ipsum dolor sit amet consectetur adipiscing elit", None),

    # ---- False positive regression cases (5) ----
    LabeledSample("L'ouverture du nouveau centre commercial a été inaugurée", None),  # "vert" in "ouverture"
    LabeledSample("Le business plan de la startup innovante", None),  # "bus" in "business"
    LabeledSample("L'article premier de la Déclaration des droits", None),  # "art" in "article"
]


def run_evaluation() -> None:
    """Run keyword scoring on eval set and report theme detection accuracy.

    Tests whether _keyword_scores correctly identifies the RIGHT theme as
    highest-scoring (even if the fast-path wouldn't fire due to <3 hits).
    This measures keyword quality independent of the fast-path threshold.

    For the full pipeline (LLM-primary), run the LLM eval separately.
    """
    print("=" * 70)
    print("KEYWORD THEME DETECTION ACCURACY REPORT")
    print("(Tests: does the correct theme get the highest keyword score?)")
    print("=" * 70)

    # Track per-theme stats
    tp: dict[str, int] = defaultdict(int)
    fp: dict[str, int] = defaultdict(int)
    fn: dict[str, int] = defaultdict(int)
    correct = 0
    total = 0
    errors: list[str] = []

    for sample in EVAL_SET:
        scores = _keyword_scores(sample.text)
        expected = sample.expected_theme

        if expected is None:
            # Non-political text: should have no keyword matches
            total += 1
            if not scores:
                correct += 1
            else:
                best = max(scores, key=scores.get)  # type: ignore[arg-type]
                errors.append(
                    f"  FALSE POS: expected=None, got={best} ({scores[best]} hits)\n"
                    f"        text: {sample.text[:80]}..."
                )
                fp[best] += 1
        else:
            total += 1
            if not scores:
                fn[expected] += 1
                errors.append(
                    f"  NO MATCH: expected={expected}, got no keywords\n"
                    f"        text: {sample.text[:80]}..."
                )
            else:
                best = max(scores, key=scores.get)  # type: ignore[arg-type]
                if best == expected:
                    correct += 1
                    tp[expected] += 1
                else:
                    fn[expected] += 1
                    fp[best] += 1
                    errors.append(
                        f"  WRONG: expected={expected} ({scores.get(expected, 0)} hits), "
                        f"got={best} ({scores[best]} hits)\n"
                        f"        text: {sample.text[:80]}..."
                    )

    accuracy = correct / total if total > 0 else 0
    print(f"\nKeyword detection: {correct}/{total} = {accuracy:.1%}")
    print()

    all_themes = sorted(set(list(tp.keys()) + list(fp.keys()) + list(fn.keys())))
    print(f"{'Theme':<16} {'Prec':>6} {'Recall':>6} {'F1':>6} {'TP':>4} {'FP':>4} {'FN':>4}")
    print("-" * 56)
    for theme in all_themes:
        t = tp[theme]
        f_p = fp[theme]
        f_n = fn[theme]
        precision = t / (t + f_p) if (t + f_p) > 0 else 0
        recall = t / (t + f_n) if (t + f_n) > 0 else 0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0
        print(f"{theme:<16} {precision:>6.1%} {recall:>6.1%} {f1:>6.1%} {t:>4} {f_p:>4} {f_n:>4}")

    if errors:
        print(f"\n--- ISSUES ({len(errors)}) ---")
        for err in errors:
            print(err)
    else:
        print("\nNo issues!")

    print("\n" + "=" * 70)
    print(
        f"Note: In production, LLM classifies most chunks. Keywords are a\n"
        f"fast-path optimization only (requires 3+ hits with clear margin)."
    )


if __name__ == "__main__":
    run_evaluation()
