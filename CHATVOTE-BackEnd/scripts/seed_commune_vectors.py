#!/usr/bin/env python3
"""
Seed script for Paris commune (75056) mock vectors in Qdrant.

Creates theme-classified mock chunks for the 9 Paris electoral lists in the
`candidates_websites_dev` collection. Vectors are random 3072-dimensional
floats (no real embeddings needed — this is for testing the commune dashboard).

Usage:
    cd CHATVOTE-BackEnd
    poetry run python scripts/seed_commune_vectors.py
    poetry run python scripts/seed_commune_vectors.py --dry-run   # print summary only
    poetry run python scripts/seed_commune_vectors.py --recreate  # drop existing Paris points first
"""

import argparse
import logging
import os
import sys
import uuid
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

from dotenv import load_dotenv

_env_path = PROJECT_ROOT / ".env"
if _env_path.exists():
    load_dotenv(_env_path, override=False)

os.environ.setdefault("QDRANT_URL", "http://localhost:6333")

QDRANT_URL = os.environ["QDRANT_URL"]
COLLECTION_NAME = "candidates_websites_dev"
MUNICIPALITY_CODE = "75056"
MUNICIPALITY_NAME = "Paris"
VECTOR_DIM = 3072

ALL_THEMES = [
    "economie",
    "education",
    "environnement",
    "sante",
    "securite",
    "immigration",
    "culture",
    "logement",
    "transport",
    "numerique",
    "agriculture",
    "justice",
    "international",
    "institutions",
]

# Sub-themes per theme (used for payload variety)
SUB_THEMES: dict[str, list[str]] = {
    "economie": ["fiscalite", "emploi", "industrie", "commerce", "tourisme"],
    "education": ["ecoles", "universites", "cantine", "periscolaire", "creches"],
    "environnement": ["biodiversite", "pollution", "dechets", "seine", "ilots_chaleur"],
    "sante": ["hopitaux", "medecins", "prevention", "sante_mentale", "sport"],
    "securite": ["police", "videosurveillance", "incivilites", "delinquance", "pompiers"],
    "immigration": ["integration", "asile", "regularisation", "langues", "nationalite"],
    "culture": ["patrimoine", "musees", "nuit_parisienne", "festivals", "bibliotheques"],
    "logement": ["logement_social", "airbnb", "renovation", "loyers", "construction"],
    "transport": ["metro", "velo", "velo_voiture", "peripherique", "grand_paris"],
    "numerique": ["services_publics", "ia", "inclusion_numerique", "open_data", "smart_city"],
    "agriculture": ["jardins_partages", "circuits_courts", "marches", "alimentation", "bio"],
    "justice": ["tribunaux", "aide_juridictionnelle", "egalite", "discriminations", "droits"],
    "international": ["cooperation", "diplomatie", "europe", "aide_internationale", "diaspora"],
    "institutions": ["democratie_locale", "budget_participatif", "arrondissements", "conseils_quartier", "transparence"],
}

# Each list: (panel_number, list_label, head_first_name, head_last_name, theme_profile)
# theme_profile: dict mapping theme -> number of chunks (strong=9, medium=5, weak=1)
PARIS_LISTS = [
    (
        1,
        "Lutte ouvrière - le camp des travailleurs",
        "Marielle",
        "SAULNIER",
        {
            "economie": 9,
            "justice": 9,
            "logement": 5,
            "education": 5,
            "sante": 4,
            "institutions": 3,
            "transport": 2,
            "culture": 2,
            "numerique": 1,
            "securite": 1,
            "immigration": 1,
            "environnement": 2,
            "agriculture": 1,
            "international": 1,
        },
    ),
    (
        2,
        "RETROUVONS PARIS",
        "Thierry",
        "MARIANI",
        {
            "securite": 10,
            "immigration": 9,
            "institutions": 5,
            "economie": 4,
            "logement": 3,
            "transport": 2,
            "education": 2,
            "culture": 1,
            "sante": 1,
            "justice": 1,
            "numerique": 1,
            "environnement": 1,
            "agriculture": 1,
            "international": 1,
        },
    ),
    (
        3,
        "Paris est à vous! avec Emmanuel Grégoire L'union de la gauche et des écologistes",
        "Emmanuel",
        "GRÉGOIRE",
        {
            "logement": 9,
            "transport": 9,
            "environnement": 8,
            "education": 5,
            "culture": 4,
            "sante": 3,
            "economie": 3,
            "institutions": 2,
            "numerique": 2,
            "agriculture": 2,
            "justice": 1,
            "immigration": 1,
            "securite": 1,
            "international": 1,
        },
    ),
    (
        4,
        "NPA Révolutionnaires - PARIS, ouvrière et révolutionnaire",
        "Blandine",
        "CHAUVEL",
        {
            "economie": 9,
            "justice": 8,
            "logement": 8,
            "education": 5,
            "sante": 4,
            "environnement": 3,
            "culture": 2,
            "institutions": 2,
            "transport": 2,
            "numerique": 1,
            "agriculture": 1,
            "securite": 1,
            "immigration": 1,
            "international": 1,
        },
    ),
    (
        5,
        "SARAH KNAFO POUR PARIS - UNE VILLE HEUREUSE",
        "Sarah",
        "KNAFO",
        {
            "securite": 9,
            "economie": 9,
            "immigration": 8,
            "institutions": 5,
            "logement": 3,
            "transport": 3,
            "education": 2,
            "justice": 2,
            "sante": 2,
            "numerique": 1,
            "culture": 1,
            "environnement": 1,
            "agriculture": 1,
            "international": 1,
        },
    ),
    (
        6,
        "PARIS APAISE AVEC PIERRE-YVES BOURNAZEL",
        "Pierre-Yves",
        "BOURNAZEL",
        {
            "transport": 9,
            "environnement": 9,
            "culture": 8,
            "logement": 5,
            "numerique": 4,
            "sante": 3,
            "education": 2,
            "economie": 2,
            "institutions": 2,
            "agriculture": 2,
            "justice": 1,
            "securite": 1,
            "immigration": 1,
            "international": 1,
        },
    ),
    (
        7,
        "CHANGER PARIS AVEC RACHIDA DATI",
        "Rachida",
        "DATI",
        {
            "securite": 10,
            "economie": 8,
            "logement": 7,
            "transport": 5,
            "education": 4,
            "culture": 3,
            "sante": 2,
            "institutions": 2,
            "numerique": 2,
            "justice": 2,
            "environnement": 2,
            "immigration": 1,
            "agriculture": 1,
            "international": 1,
        },
    ),
    (
        8,
        "LE NOUVEAU PARIS POPULAIRE",
        "Sophia",
        "CHIKIROU",
        {
            "logement": 9,
            "economie": 9,
            "justice": 8,
            "education": 5,
            "sante": 5,
            "culture": 3,
            "transport": 2,
            "environnement": 2,
            "institutions": 2,
            "numerique": 1,
            "agriculture": 1,
            "securite": 1,
            "immigration": 1,
            "international": 1,
        },
    ),
    (
        9,
        "Les coupes budgétaires à Paris ça suffit !",
        "Mahel",
        "PIEROT-GUIMBAUD",
        {
            "economie": 9,
            "education": 9,
            "sante": 8,
            "institutions": 5,
            "logement": 4,
            "culture": 3,
            "transport": 2,
            "justice": 2,
            "environnement": 2,
            "numerique": 1,
            "agriculture": 1,
            "securite": 1,
            "immigration": 1,
            "international": 1,
        },
    ),
]

# French content templates per theme for realistic page_content
CONTENT_TEMPLATES: dict[str, list[str]] = {
    "economie": [
        "Notre programme économique pour Paris vise à soutenir les TPE et PME locales face à la concurrence internationale.",
        "Nous proposons une fiscalité locale plus juste, avec des exonérations ciblées pour les petits commerçants de proximité.",
        "Le tourisme représente un pilier de l'économie parisienne. Nous voulons mieux redistribuer ses bénéfices aux habitants.",
        "Face à la désindustrialisation, nous défendons la création de zones artisanales protégées dans les arrondissements périphériques.",
        "Notre vision pour l'emploi à Paris : accompagner les transitions professionnelles et lutter contre le chômage des jeunes.",
    ],
    "education": [
        "L'éducation est notre priorité. Nous investirons massivement dans la rénovation des écoles parisiennes.",
        "Nous voulons des cantines scolaires avec 100 % de produits locaux et bio d'ici 2030.",
        "Le périscolaire doit être accessible à tous les enfants parisiens, quelle que soit la situation financière de leur famille.",
        "Nous proposons d'ouvrir 5 000 nouvelles places en crèche sur le mandat, priorité aux quartiers sous-dotés.",
        "L'université parisienne est un trésor. Nous soutenons le logement étudiant abordable dans la capitale.",
    ],
    "environnement": [
        "Paris doit devenir une ville véritablement verte. Nous plantons 170 000 arbres supplémentaires d'ici 2030.",
        "La qualité de l'air reste un enjeu de santé publique majeur. Nous renforçons les contrôles sur les émissions polluantes.",
        "La Seine doit redevenir un espace de baignade pour tous les Parisiens. Notre plan Baignade Seine 2027 est chiffré et réaliste.",
        "Nous luttons contre les îlots de chaleur urbains en végétalisant toits et façades dans tous les arrondissements.",
        "La biodiversité urbaine est en danger. Nous créons des corridors écologiques entre les parcs et jardins parisiens.",
    ],
    "sante": [
        "Les déserts médicaux touchent aussi Paris. Nous créons des centres de santé municipaux dans les quartiers sous-dotés.",
        "La santé mentale des Parisiens est une priorité méconnue. Nous finançons des psychologues dans les centres communautaires.",
        "Nous défendons un accès universel au sport et à l'activité physique, avec des équipements ouverts gratuitement.",
        "Face aux épidémies et aux risques sanitaires, Paris doit renforcer son réseau de prévention et de veille.",
        "Nous voulons que chaque Parisien ait un médecin traitant. Fin des files d'attente aux urgences par le développement de la médecine de ville.",
    ],
    "securite": [
        "La sécurité des Parisiens n'est pas négociable. Nous renforçons les effectifs de la police municipale.",
        "Les quartiers sensibles comme la Goutte d'Or et la porte de la Chapelle méritent une présence policière renforcée.",
        "Nous déployons 2 000 caméras supplémentaires dans les zones à risque, avec un centre de supervision modernisé.",
        "La lutte contre les pickpockets dans le métro et près des sites touristiques est une priorité absolue.",
        "Nous voulons une police de proximité qui connaît les habitants de chaque quartier et y tisse des liens de confiance.",
    ],
    "immigration": [
        "L'intégration républicaine passe par la maîtrise de la langue française. Nous finançons des cours de français pour tous.",
        "Paris accueille des réfugiés dans la dignité. Nous renforçons les centres d'hébergement d'urgence.",
        "La politique d'asile doit être humaine et efficace. Nous défendons des délais de traitement raccourcis.",
        "L'immigration non maîtrisée crée des tensions dans les quartiers. Nous demandons une politique nationale plus ferme.",
        "La diversité parisienne est une richesse. Nous luttons contre toutes les formes de discrimination à l'embauche et au logement.",
    ],
    "culture": [
        "Paris est la capitale mondiale de la culture. Nous défendons son réseau de musées, théâtres et bibliothèques.",
        "La vie nocturne parisienne souffre. Nous créons un statut protecteur pour les lieux de musique et de fête.",
        "Notre-Dame rouvre : nous voulons que ce trésor reste accessible aux Parisiens et pas seulement aux touristes.",
        "Les festivals d'été enrichissent la vie culturelle. Nous doublons les subventions aux festivals de quartier.",
        "Chaque arrondissement doit avoir sa médiathèque ouverte 7 jours sur 7. C'est un enjeu démocratique.",
    ],
    "logement": [
        "La crise du logement à Paris est structurelle. Nous construisons 10 000 logements sociaux supplémentaires sur le mandat.",
        "Airbnb vide les quartiers de leurs habitants. Nous plafonnons les locations courte durée à 60 nuits par an.",
        "La rénovation thermique du parc immobilier ancien est urgente. Nous créons un fonds municipal d'aide à la rénovation.",
        "Les loyers sont devenus inaccessibles. Nous défendons un encadrement strict des loyers dans toute la métropole.",
        "Les copropriétés dégradées sont un problème croissant. Nous intervenons plus tôt pour éviter les situations catastrophiques.",
    ],
    "transport": [
        "Le métro parisien est saturé aux heures de pointe. Nous demandons à la RATP d'augmenter les fréquences sur les lignes surchargées.",
        "Le réseau cyclable doit couvrir l'ensemble de Paris, y compris les arrondissements périphériques encore peu desservis.",
        "Le Grand Paris Express doit avancer sans nouveaux retards. Paris doit porter ce dossier au plus haut niveau.",
        "Le périphérique ne doit pas devenir un boulevard urbain : la circulation est nécessaire pour les travailleurs des banlieues.",
        "Nous proposons un abonnement transport gratuit pour les moins de 18 ans et les seniors à faibles revenus.",
    ],
    "numerique": [
        "La dématérialisation des services publics exclut les seniors. Nous maintenons des guichets physiques dans chaque mairie d'arrondissement.",
        "Paris doit devenir une smart city sobre et inclusive. Nous développons des outils numériques au service des habitants.",
        "L'open data municipal doit être étendu pour permettre aux citoyens de contrôler la gestion de la ville.",
        "Nous déployons la fibre optique dans les dernières zones non couvertes et améliorons le WiFi dans les espaces publics.",
        "L'intelligence artificielle peut améliorer les services publics. Nous l'utilisons avec éthique et transparence.",
    ],
    "agriculture": [
        "Les jardins partagés sont des oasis de biodiversité et de lien social. Nous en créons 200 nouveaux sur le mandat.",
        "Les circuits courts doivent alimenter les cantines scolaires et les marchés parisiens. Nous structurons la filière.",
        "Les marchés parisiens (Aligre, Belleville, Raspail) sont un patrimoine vivant que nous protégeons et soutenons.",
        "L'agriculture urbaine en toiture représente un potentiel inexploité. Nous facilitons son développement par des aides à l'installation.",
        "Nous voulons que Paris devienne un modèle d'alimentation durable : moins de viande dans les cantines, plus de bio local.",
    ],
    "justice": [
        "L'accès à la justice est un droit fondamental. Nous renforçons les Maisons de Justice et du Droit dans les quartiers populaires.",
        "Les discriminations dans le logement et l'emploi sont encore trop fréquentes à Paris. Nous renforçons les dispositifs de testing.",
        "La justice doit être plus rapide. Nous demandons des moyens supplémentaires pour les tribunaux parisiens.",
        "Nous défendons l'égalité réelle entre les femmes et les hommes dans l'espace public et professionnel parisien.",
        "La protection des droits des personnes vulnérables — sans-abri, migrants, personnes âgées — est une priorité de justice sociale.",
    ],
    "international": [
        "Paris est une ville monde. Nous renforçons ses partenariats avec les métropoles du réseau C40 pour le climat.",
        "La coopération décentralisée avec les villes du Sud global doit être développée et mieux financée.",
        "Paris accueille de nombreuses institutions internationales. Nous voulons que la ville en tire davantage de bénéfices économiques.",
        "L'Europe se construit aussi à l'échelle des villes. Nous défendons une Europe des territoires plus solidaire.",
        "Paris doit jouer un rôle actif dans l'aide internationale aux populations en détresse, au-delà des déclarations symboliques.",
    ],
    "institutions": [
        "Le budget participatif est une réussite. Nous le portons à 100 millions d'euros par an et simplifions les procédures.",
        "Les conseils de quartier doivent être redynamisés avec de vrais pouvoirs consultatifs et des budgets propres.",
        "La transparence dans la gestion de la ville est une exigence démocratique. Nous publions tous les contrats publics en open data.",
        "Nous réformons la gouvernance des arrondissements pour leur donner plus d'autonomie et de moyens d'action.",
        "La démocratie locale passe aussi par une meilleure représentation de la diversité sociale au conseil de Paris.",
    ],
}


def build_points_for_list(
    panel_number: int,
    list_label: str,
    head_first_name: str,
    head_last_name: str,
    theme_profile: dict[str, int],
) -> list:
    """Build PointStruct objects for a single Paris electoral list."""
    from qdrant_client.models import PointStruct

    namespace = f"paris-list-{panel_number}"
    candidate_name = f"{head_first_name} {head_last_name}"
    total_chunks = sum(theme_profile.values())

    points = []
    chunk_index = 0

    for theme, count in theme_profile.items():
        sub_themes = SUB_THEMES.get(theme, [theme])
        content_options = CONTENT_TEMPLATES.get(theme, [f"Programme sur le thème {theme} pour {list_label}."])

        for i in range(count):
            sub_theme = sub_themes[i % len(sub_themes)]
            content_base = content_options[i % len(content_options)]
            page_content = f"{content_base} — Position de la liste « {list_label} » (tête de liste : {candidate_name})."

            payload = {
                "page_content": page_content,
                "metadata": {
                    "namespace": namespace,
                    "source_document": "candidate_website",
                    "party_name": list_label,
                    "municipality_code": MUNICIPALITY_CODE,
                    "municipality_name": MUNICIPALITY_NAME,
                    "theme": theme,
                    "sub_theme": sub_theme,
                    "fiabilite": 2,
                    "candidate_name": candidate_name,
                    "chunk_index": chunk_index,
                    "page": 1,
                    "total_chunks": total_chunks,
                },
            }

            random_vector = np.random.rand(VECTOR_DIM).tolist()

            points.append(
                PointStruct(
                    id=str(uuid.uuid4()),
                    vector={"dense": random_vector},
                    payload=payload,
                )
            )
            chunk_index += 1

    return points


def ensure_collection_exists(client) -> None:
    """Create candidates_websites_dev if it doesn't exist with 3072-dim dense vectors."""
    from qdrant_client.models import Distance, VectorParams

    existing = {c.name for c in client.get_collections().collections}
    if COLLECTION_NAME in existing:
        logger.info(f"Collection '{COLLECTION_NAME}' already exists — will upsert into it.")
        return

    logger.info(f"Creating collection '{COLLECTION_NAME}' ({VECTOR_DIM}d COSINE)...")
    client.create_collection(
        collection_name=COLLECTION_NAME,
        vectors_config={
            "dense": VectorParams(size=VECTOR_DIM, distance=Distance.COSINE)
        },
    )
    logger.info(f"Collection '{COLLECTION_NAME}' created.")


def delete_existing_paris_points(client) -> None:
    """Delete all points with municipality_code=75056 from the collection."""
    from qdrant_client.models import FieldCondition, Filter, MatchValue

    logger.info("Deleting existing Paris points from collection...")
    client.delete(
        collection_name=COLLECTION_NAME,
        points_selector=Filter(
            must=[
                FieldCondition(
                    key="metadata.municipality_code",
                    match=MatchValue(value=MUNICIPALITY_CODE),
                )
            ]
        ),
    )
    logger.info("Existing Paris points deleted.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed Paris commune mock vectors into Qdrant")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print summary without writing to Qdrant",
    )
    parser.add_argument(
        "--recreate",
        action="store_true",
        help="Delete existing Paris points before inserting new ones",
    )
    args = parser.parse_args()

    logger.info("=== Paris Commune Vector Seeder ===")
    logger.info(f"Qdrant: {QDRANT_URL}")
    logger.info(f"Collection: {COLLECTION_NAME}")
    logger.info(f"Municipality: {MUNICIPALITY_NAME} ({MUNICIPALITY_CODE})")
    logger.info(f"Vector dim: {VECTOR_DIM}")

    if args.dry_run:
        logger.info("\n[DRY RUN] Computing point counts per list:")
        total = 0
        for panel_number, list_label, first, last, profile in PARIS_LISTS:
            count = sum(profile.values())
            total += count
            logger.info(f"  Panel {panel_number} — {list_label[:50]:<50} : {count} chunks")
        logger.info(f"\n  TOTAL: {total} chunks across {len(PARIS_LISTS)} lists")
        return

    from qdrant_client import QdrantClient

    client = QdrantClient(url=QDRANT_URL, check_compatibility=False)

    ensure_collection_exists(client)

    if args.recreate:
        delete_existing_paris_points(client)

    logger.info("\nGenerating and upserting vectors...")
    grand_total = 0

    for panel_number, list_label, first, last, profile in PARIS_LISTS:
        logger.info(f"  Panel {panel_number}: {list_label[:60]}...")
        points = build_points_for_list(panel_number, list_label, first, last, profile)

        # Upsert in batches of 50
        for i in range(0, len(points), 50):
            batch = points[i : i + 50]
            client.upsert(collection_name=COLLECTION_NAME, points=batch)

        count = len(points)
        grand_total += count
        theme_summary = ", ".join(
            f"{t}={n}" for t, n in sorted(profile.items(), key=lambda x: -x[1])[:5]
        )
        logger.info(f"    -> {count} chunks upserted  (top themes: {theme_summary})")

    logger.info(f"\n=== Seeding complete! {grand_total} total chunks for Paris ({MUNICIPALITY_CODE}) ===")

    # Print per-list summary
    logger.info("\nSummary by list:")
    for panel_number, list_label, first, last, profile in PARIS_LISTS:
        count = sum(profile.values())
        logger.info(f"  [{panel_number}] {list_label[:55]:<55} : {count:3d} chunks")


if __name__ == "__main__":
    main()
