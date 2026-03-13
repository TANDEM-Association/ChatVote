"""Seed fake chat sessions into prod Firestore for demo/testing purposes.

Usage:
    ENV=prod poetry run python scripts/seed_prod_chats.py
"""
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone
import random

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.utils import load_env

# Preserve ENV from shell — load_env uses override=True which clobbers it
_target_env = os.getenv("ENV")
load_env()
if _target_env:
    os.environ["ENV"] = _target_env

from src.firebase_service import db

PARTY_IDS = [
    "europe-ecologie-les-verts",
    "lfi",
    "ps",
    "reconquete",
    "union_centre",
]

ASSISTANT_ID = "assistant"

MUNICIPALITY_CODES = ["75056", "69123", "13055", "31555", "33063"]  # Paris, Lyon, Marseille, Toulouse, Bordeaux
MUNICIPALITY_NAMES = {
    "75056": "Paris",
    "69123": "Lyon",
    "13055": "Marseille",
    "31555": "Toulouse",
    "33063": "Bordeaux",
}

FAKE_CONVERSATIONS = [
    {
        "title": "Programme environnement",
        "party_ids": ["europe-ecologie-les-verts", "ps"],
        "municipality_code": "75056",
        "messages": [
            {
                "role": "user",
                "content": "Quelles sont les propositions des partis pour l'environnement et le climat ?",
            },
            {
                "role": "assistant",
                "party_id": "europe-ecologie-les-verts",
                "content": "Les Écologistes proposent un plan ambitieux pour le climat avec l'objectif de neutralité carbone en 2050. Ils veulent investir massivement dans les énergies renouvelables, interdire les nouveaux forages pétroliers, et instaurer une taxe carbone aux frontières de l'UE [0].\n\nIls défendent aussi la création d'une Garantie Universelle d'Assurance Climatique pour protéger les citoyens face aux risques climatiques [1].",
                "sources": [
                    {"source": "Les Écologistes - Programme électoral", "page": 7, "content_preview": "Atteindre la neutralité carbone...", "url": "https://chatvote-public-assets.s3.fr-par.scw.cloud/public/europe-ecologie-les-verts/programme.pdf", "source_type": "manifesto", "party_id": "europe-ecologie-les-verts"},
                    {"source": "Les Écologistes - Programme électoral", "page": 28, "content_preview": "Instaurer une Garantie Universelle...", "url": "https://chatvote-public-assets.s3.fr-par.scw.cloud/public/europe-ecologie-les-verts/programme.pdf", "source_type": "manifesto", "party_id": "europe-ecologie-les-verts"},
                ],
            },
            {
                "role": "assistant",
                "party_id": "ps",
                "content": "Place Publique met l'écologie au cœur de son programme avec une grande loi Climat engageant tous les ministères. Ils proposent une trajectoire de -90% d'émissions en 2040 et la neutralité climat en 2050 [0].\n\nIls souhaitent aussi adopter un bouclier législatif pour la sobriété : loi contre la fast-fashion, score carbone obligatoire sur les produits, et fin des plastiques à usage unique d'ici 2030 [1].",
                "sources": [
                    {"source": "Place Publique - Programme électoral", "page": 28, "content_preview": "Faire une grande loi Climat...", "url": "https://chatvote-public-assets.s3.fr-par.scw.cloud/public/ps/programme.pdf", "source_type": "manifesto", "party_id": "ps"},
                    {"source": "Place Publique - Programme électoral", "page": 29, "content_preview": "Adopter un bouclier législatif...", "url": "https://chatvote-public-assets.s3.fr-par.scw.cloud/public/ps/programme.pdf", "source_type": "manifesto", "party_id": "ps"},
                ],
            },
        ],
    },
    {
        "title": "Logement et urbanisme",
        "party_ids": ["union_centre", "lfi"],
        "municipality_code": "69123",
        "messages": [
            {
                "role": "user",
                "content": "Que proposent les partis en matière de logement ?",
            },
            {
                "role": "assistant",
                "party_id": "union_centre",
                "content": "Renaissance propose de relancer la construction de logements neufs, avec un objectif de 500 000 logements par an. Le parti souhaite simplifier les normes de construction et accélérer les permis de construire pour fluidifier le marché immobilier.",
                "sources": [],
            },
            {
                "role": "assistant",
                "party_id": "lfi",
                "content": "La France Insoumise propose un plan ambitieux pour le logement, incluant l'encadrement des loyers dans toutes les zones tendues, la construction de 200 000 logements sociaux par an, et la réquisition des logements vacants pour lutter contre la crise du logement [0].",
                "sources": [
                    {"source": "La France Insoumise - Programme électoral", "page": 15, "content_preview": "Encadrement des loyers...", "url": "https://chatvote-public-assets.s3.fr-par.scw.cloud/public/lfi/programme.pdf", "source_type": "manifesto", "party_id": "lfi"},
                ],
            },
        ],
    },
    {
        "title": "Sécurité et justice",
        "party_ids": ["reconquete"],
        "municipality_code": "13055",
        "messages": [
            {
                "role": "user",
                "content": "Quelle est la position de Reconquête sur la sécurité ?",
            },
            {
                "role": "assistant",
                "party_id": "reconquete",
                "content": "Reconquête propose un renforcement significatif des forces de l'ordre avec le recrutement de 30 000 policiers et gendarmes supplémentaires. Le parti souhaite instaurer des peines plancher pour les récidivistes et supprimer les remises de peine automatiques.",
                "sources": [],
            },
        ],
    },
    {
        "title": "Éducation nationale",
        "party_ids": ["ps", "lfi", "europe-ecologie-les-verts"],
        "municipality_code": "31555",
        "messages": [
            {
                "role": "user",
                "content": "Quelles réformes de l'éducation proposent les différents partis de gauche ?",
            },
            {
                "role": "assistant",
                "party_id": "ps",
                "content": "Place Publique défend une école républicaine inclusive. Le parti propose d'augmenter le budget de l'Éducation nationale, de limiter les classes à 20 élèves en zones prioritaires, et de revaloriser les salaires des enseignants de 20% sur le quinquennat.",
                "sources": [],
            },
            {
                "role": "assistant",
                "party_id": "lfi",
                "content": "La France Insoumise souhaite une refonte complète du système éducatif avec la gratuité totale de l'école (fournitures, cantine, transport), le recrutement massif d'enseignants, et la fin du tri social via Parcoursup.",
                "sources": [],
            },
            {
                "role": "assistant",
                "party_id": "europe-ecologie-les-verts",
                "content": "Les Écologistes veulent intégrer l'éducation à l'environnement dans les programmes scolaires dès le primaire, rénover énergétiquement les bâtiments scolaires, et développer les cantines bio et locales dans tous les établissements.",
                "sources": [],
            },
        ],
    },
    {
        "title": "Transport et mobilité",
        "party_ids": ["europe-ecologie-les-verts"],
        "municipality_code": "33063",
        "messages": [
            {
                "role": "user",
                "content": "Que proposent les écologistes pour les transports ?",
            },
            {
                "role": "assistant",
                "party_id": "europe-ecologie-les-verts",
                "content": "Les Écologistes proposent un plan massif d'investissement dans les transports en commun et les mobilités douces. Ils souhaitent développer le réseau ferroviaire avec la réouverture de lignes abandonnées, instaurer un pass transport à 50€/mois, et créer des zones à faibles émissions dans toutes les grandes villes [0].",
                "sources": [
                    {"source": "Les Écologistes - Programme électoral", "page": 12, "content_preview": "Investir dans le ferroviaire...", "url": "https://chatvote-public-assets.s3.fr-par.scw.cloud/public/europe-ecologie-les-verts/programme.pdf", "source_type": "manifesto", "party_id": "europe-ecologie-les-verts"},
                ],
            },
        ],
    },
    {
        "title": "Économie et emploi",
        "party_ids": ["union_centre", "reconquete"],
        "municipality_code": "75056",
        "messages": [
            {
                "role": "user",
                "content": "Comparez les programmes économiques de Renaissance et Reconquête.",
            },
            {
                "role": "assistant",
                "party_id": "union_centre",
                "content": "Renaissance mise sur la continuité de la politique macroéconomique avec la poursuite de la réindustrialisation, la baisse des impôts de production, et le soutien à l'innovation technologique. Le parti défend le plein emploi comme objectif prioritaire.",
                "sources": [],
            },
            {
                "role": "assistant",
                "party_id": "reconquete",
                "content": "Reconquête propose une politique économique protectionniste avec la relocalisation industrielle, la préférence nationale pour les marchés publics, et une baisse massive de la fiscalité pour les PME. Le parti souhaite aussi réduire la dette publique en diminuant les dépenses sociales.",
                "sources": [],
            },
        ],
    },
    {
        "title": "Santé publique",
        "party_ids": ["lfi", "ps"],
        "municipality_code": "69123",
        "messages": [
            {
                "role": "user",
                "content": "Quelles sont les propositions pour améliorer le système de santé ?",
            },
            {
                "role": "assistant",
                "party_id": "lfi",
                "content": "La France Insoumise propose le remboursement intégral des soins de santé par la Sécurité sociale (100% Sécu), la régulation de l'installation des médecins pour lutter contre les déserts médicaux, et la création de centres de santé publics dans chaque canton.",
                "sources": [],
            },
            {
                "role": "assistant",
                "party_id": "ps",
                "content": "Place Publique défend un grand plan de lutte contre les déserts médicaux avec des maisons de santé pluridisciplinaires, la revalorisation des métiers du soin, et un investissement massif dans l'hôpital public pour rattraper le retard accumulé.",
                "sources": [],
            },
        ],
    },
    {
        "title": "Immigration et intégration",
        "party_ids": ["reconquete", "union_centre"],
        "municipality_code": "13055",
        "messages": [
            {
                "role": "user",
                "content": "Quelles sont les positions sur l'immigration ?",
            },
            {
                "role": "assistant",
                "party_id": "reconquete",
                "content": "Reconquête propose une politique d'immigration très restrictive : moratoire sur l'immigration légale, fin du regroupement familial, suppression du droit du sol, et expulsion systématique des étrangers en situation irrégulière.",
                "sources": [],
            },
            {
                "role": "assistant",
                "party_id": "union_centre",
                "content": "Renaissance défend une immigration maîtrisée avec le renforcement des contrôles aux frontières européennes via Frontex, l'accélération du traitement des demandes d'asile, et des accords bilatéraux pour faciliter les retours. Le parti soutient aussi l'intégration par la langue et l'emploi.",
                "sources": [],
            },
        ],
    },
]

FAKE_USER_IDS = [
    "demo_user_" + str(i) for i in range(1, 9)
]


def create_timestamp(dt: datetime):
    """Create a Firestore-compatible timestamp."""
    from google.cloud.firestore_v1 import _helpers
    return dt


def seed_chat_sessions():
    batch = db.batch()
    created = 0

    for i, conv in enumerate(FAKE_CONVERSATIONS):
        session_id = str(uuid.uuid4())
        user_id = FAKE_USER_IDS[i % len(FAKE_USER_IDS)]
        municipality_code = conv.get("municipality_code")

        # Randomize date within last 7 days
        days_ago = random.randint(0, 6)
        hours_ago = random.randint(0, 23)
        base_time = datetime.now(timezone.utc) - timedelta(days=days_ago, hours=hours_ago)

        # Create session document
        session_ref = db.collection("chat_sessions").document(session_id)
        session_data = {
            "user_id": user_id,
            "party_ids": conv["party_ids"],
            "created_at": base_time,
            "updated_at": base_time + timedelta(seconds=30),
            "title": conv["title"],
        }
        if municipality_code:
            session_data["municipality_code"] = municipality_code
        batch.set(session_ref, session_data)

        # Create grouped messages
        msg_time = base_time
        user_group_id = None

        for msg in conv["messages"]:
            msg_time = msg_time + timedelta(seconds=random.randint(2, 8))

            if msg["role"] == "user":
                # User messages get their own grouped message doc
                user_group_id = str(uuid.uuid4())
                msg_ref = session_ref.collection("messages").document(user_group_id)
                batch.set(msg_ref, {
                    "id": user_group_id,
                    "messages": [{
                        "id": str(uuid.uuid4()),
                        "content": msg["content"],
                        "sources": [],
                        "created_at": msg_time,
                        "role": "user",
                    }],
                    "quick_replies": [],
                    "role": "user",
                    "created_at": msg_time,
                })
            else:
                # Assistant messages: create a new grouped message
                group_id = str(uuid.uuid4())
                msg_ref = session_ref.collection("messages").document(group_id)
                batch.set(msg_ref, {
                    "id": group_id,
                    "messages": [{
                        "id": str(uuid.uuid4()),
                        "content": msg["content"],
                        "sources": msg.get("sources", []),
                        "party_id": msg.get("party_id", ASSISTANT_ID),
                        "created_at": msg_time,
                        "role": "assistant",
                    }],
                    "created_at": msg_time,
                })

        created += 1
        print(f"  [{created}] {conv['title']} ({municipality_code or 'national'}) — {len(conv['messages'])} messages")

    print(f"\nCommitting {created} chat sessions to Firestore...")
    batch.commit()
    print(f"Done! Created {created} fake chat sessions.")


if __name__ == "__main__":
    env = os.getenv("ENV", "dev")
    print(f"Seeding fake chats into Firestore (ENV={env})")
    if env == "prod":
        print("WARNING: Writing to PRODUCTION Firestore!")
        response = input("Continue? [y/N] ")
        if response.lower() != "y":
            print("Aborted.")
            sys.exit(0)
    seed_chat_sessions()
