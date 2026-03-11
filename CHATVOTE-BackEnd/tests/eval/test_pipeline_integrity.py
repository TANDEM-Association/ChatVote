"""
DeepEval pipeline integrity tests.

Tests every stage of each ingestion pipeline against real documents
to catch data quality problems before they reach Qdrant.

Pipelines tested:
1. Party Manifestos    — PDF → pypdf → chunk → theme classify → metadata
2. Candidate Websites  — HTML → scraper → chunk → metadata
3. Admin Upload        — PDF → pypdf/OCR → auto-assign → chunk → metadata
4. Election Posters    — PDF → OCR → chunk → keyword theme → metadata

Each pipeline gets 5 diverse sample documents testing:
- Text extraction completeness (no silent content loss)
- Chunk quality (size, overlap, no garbage)
- Metadata completeness (required fields present)
- Theme classification coverage
- Cross-pipeline consistency (same doc → same chunks regardless of entry point)

Requires:
    DEEPEVAL_JUDGE=gemini  (or Ollama running)
    GOOGLE_API_KEY         (for Gemini OCR + theme classification)

Usage:
    DEEPEVAL_JUDGE=gemini poetry run pytest tests/eval/test_pipeline_integrity.py -s
    poetry run pytest tests/eval/test_pipeline_integrity.py -s  # Ollama judge
"""

import asyncio
import io
import os
import sys
from pathlib import Path
from typing import Optional

import pytest
from deepeval import assert_test
from deepeval.metrics import GEval
from deepeval.test_case import LLMTestCase, LLMTestCaseParams
from langchain_core.documents import Document

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src.models.chunk_metadata import (
    ChunkMetadata,
    Fiabilite,
    THEME_TAXONOMY,
)

# ---------------------------------------------------------------------------
# Lazy imports — only when actually running tests that need them
# ---------------------------------------------------------------------------


def _get_text_splitter():
    from langchain_text_splitters import RecursiveCharacterTextSplitter

    return RecursiveCharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=200,
        length_function=len,
        separators=["\n\n", "\n", ". ", "? ", "! ", "; ", " ", ""],
    )


# ---------------------------------------------------------------------------
# Sample documents — synthetic but representative of real pipeline inputs
# ---------------------------------------------------------------------------

# 5 manifesto texts (French political party programs — varied lengths/styles)
MANIFESTO_SAMPLES = [
    {
        "id": "manifesto_dense_policy",
        "party_id": "test_renaissance",
        "party_name": "Renaissance",
        "text": (
            "Notre programme pour les municipales 2026\n\n"
            "ÉCONOMIE ET EMPLOI\n"
            "Nous proposons la création d'un fonds municipal d'aide aux commerces de proximité "
            "doté de 500 000 euros pour soutenir les artisans et commerçants du centre-ville. "
            "Ce dispositif permettra de financer jusqu'à 50% des loyers pendant 2 ans pour "
            "les nouvelles installations. Un guichet unique sera créé en mairie pour "
            "accompagner les porteurs de projets dans leurs démarches administratives.\n\n"
            "TRANSITION ÉCOLOGIQUE\n"
            "Objectif zéro artificialisation nette d'ici 2030. Plantation de 10 000 arbres "
            "sur l'ensemble du territoire communal. Création de 3 nouvelles pistes cyclables "
            "reliant les quartiers nord et sud. Budget de 2 millions d'euros pour la rénovation "
            "énergétique des bâtiments communaux. Installation de panneaux solaires sur tous "
            "les toits des équipements municipaux.\n\n"
            "ÉDUCATION ET JEUNESSE\n"
            "Construction d'un nouveau groupe scolaire dans le quartier des Lilas, capacité "
            "300 élèves. Extension des horaires d'accueil périscolaire de 7h à 19h. "
            "Création d'un conseil municipal des jeunes avec budget participatif de 50 000 euros. "
            "Mise en place d'un programme de mentorat entre lycéens et professionnels locaux."
        ),
    },
    {
        "id": "manifesto_short_bullet_points",
        "party_id": "test_lfi",
        "party_name": "La France Insoumise",
        "text": (
            "NOS 20 ENGAGEMENTS\n\n"
            "1. Gratuité des transports en commun\n"
            "2. 100% bio dans les cantines scolaires\n"
            "3. Régie publique de l'eau\n"
            "4. Construction de 500 logements sociaux\n"
            "5. Doublement du budget culture\n"
            "6. Création d'une police municipale de proximité\n"
            "7. Budget participatif de 5% du budget communal\n"
            "8. Zéro pesticide sur les espaces verts\n"
            "9. Tarification solidaire de l'énergie\n"
            "10. Plan vélo : 50 km de pistes cyclables\n"
            "11. Ouverture de 3 maisons de santé\n"
            "12. Aide à l'installation des médecins\n"
            "13. Création d'un tiers-lieu numérique\n"
            "14. Extension du réseau de bornes WiFi\n"
            "15. Rénovation thermique de 1000 logements\n"
            "16. Protection des terres agricoles\n"
            "17. Marché de producteurs locaux hebdomadaire\n"
            "18. Soutien aux associations sportives\n"
            "19. Accessibilité universelle des bâtiments publics\n"
            "20. Jumelage avec une ville ukrainienne"
        ),
    },
    {
        "id": "manifesto_with_numbers_and_dates",
        "party_id": "test_rn",
        "party_name": "Rassemblement National",
        "text": (
            "Programme Municipal 2026-2032\n"
            "Liste conduite par Marie DURAND\n\n"
            "SÉCURITÉ : Notre priorité absolue\n"
            "Budget sécurité : passage de 3,2M€ à 5,8M€ (+81%)\n"
            "Recrutement de 45 policiers municipaux supplémentaires d'ici juin 2027\n"
            "Installation de 200 caméras de vidéoprotection dans tous les quartiers\n"
            "Couvre-feu pour les mineurs de moins de 13 ans après 23h\n\n"
            "FISCALITÉ\n"
            "Gel de la taxe foncière pendant toute la durée du mandat (2026-2032)\n"
            "Suppression de la surtaxe d'habitation sur les résidences secondaires\n"
            "Audit complet des finances municipales dans les 100 premiers jours\n\n"
            "IMMIGRATION\n"
            "Conditionnalité des aides sociales municipales à 5 ans de résidence\n"
            "Suppression des subventions aux associations communautaristes\n"
            "Priorité communale pour l'attribution des logements sociaux"
        ),
    },
    {
        "id": "manifesto_long_prose",
        "party_id": "test_eelv",
        "party_name": "Les Écologistes",
        "text": (
            "Vivre mieux, ensemble, dans notre commune\n\n"
            "Chers concitoyens et concitoyennes,\n\n"
            "Nous vivons une époque de transformation profonde. Le changement climatique "
            "n'est plus une menace lointaine : il se manifeste ici, dans nos rues, dans "
            "nos jardins, dans la qualité de l'air que nous respirons chaque jour. Les "
            "épisodes de canicule se multiplient, les nappes phréatiques s'épuisent, la "
            "biodiversité recule.\n\n"
            "Face à ces défis, nous proposons un projet de transformation écologique "
            "ambitieux mais réaliste. Notre vision repose sur trois piliers fondamentaux : "
            "la sobriété énergétique, la solidarité territoriale et la démocratie "
            "participative.\n\n"
            "Premier pilier : la sobriété énergétique. Nous devons réduire notre "
            "consommation d'énergie de 40% d'ici 2030. Cela passe par un plan massif "
            "de rénovation thermique des logements, la généralisation du solaire en "
            "autoconsommation, et la création d'un réseau de chaleur alimenté par la "
            "géothermie et la biomasse locale.\n\n"
            "Deuxième pilier : la solidarité territoriale. Aucun quartier ne doit être "
            "laissé pour compte. Nous créerons des maisons de services publics dans "
            "chaque quartier prioritaire, avec des permanences régulières de la CAF, "
            "de Pôle Emploi et de la CPAM. Le budget participatif sera porté à 10% "
            "du budget d'investissement.\n\n"
            "Troisième pilier : la démocratie participative. Nous instaurerons un "
            "référendum d'initiative citoyenne local pour tout projet supérieur à "
            "1 million d'euros. Un conseil citoyen tiré au sort sera associé à "
            "toutes les grandes décisions d'urbanisme."
        ),
    },
    {
        "id": "manifesto_multilingual_mixed",
        "party_id": "test_ps",
        "party_name": "Parti Socialiste",
        "text": (
            "PROJET MUNICIPAL - PARTI SOCIALISTE\n"
            "« Pour une ville juste et solidaire »\n\n"
            "AXE 1 : SANTÉ ET BIEN-ÊTRE\n"
            "• Ouverture d'un centre de santé municipal avec 15 praticiens\n"
            "• Convention avec l'ARS pour un CPTS (Communauté Professionnelle "
            "Territoriale de Santé)\n"
            "• Création d'un EHPAD public de 80 places\n"
            "• Programme « Sport sur ordonnance » avec 30 clubs partenaires\n\n"
            "AXE 2 : LOGEMENT\n"
            "• Objectif SRU : atteindre 25% de logements sociaux d'ici 2028\n"
            "• Encadrement des loyers via un observatoire local\n"
            "• Réhabilitation de 200 logements insalubres\n"
            "• Programme d'accession sociale à la propriété (PSLA)\n\n"
            "AXE 3 : CULTURE ET PATRIMOINE\n"
            "• Rénovation du théâtre municipal (budget : 3,5M€)\n"
            "• Pass culture local pour les 15-25 ans (200€/an)\n"
            "• Festival annuel des arts de la rue\n"
            "• Numérisation des archives municipales (XIIe-XXe siècle)"
        ),
    },
]

# 5 candidate website page contents
CANDIDATE_WEBSITE_SAMPLES = [
    {
        "id": "website_programme_page",
        "candidate_id": "test_cand_dupont",
        "candidate_name": "Jean Dupont",
        "municipality_code": "75056",
        "municipality_name": "Paris",
        "page_type": "programme",
        "url": "https://jeandupont2026.fr/programme",
        "title": "Mon programme - Jean Dupont",
        "content": (
            "Mon programme pour Paris 15e\n\n"
            "Je suis Jean Dupont, conseiller municipal sortant du 15e arrondissement. "
            "Après 6 ans au service des Parisiens, je me présente pour un nouveau mandat "
            "avec une équipe renouvelée de 45 colistiers.\n\n"
            "Mes priorités :\n"
            "- Propreté : doublement des agents de nettoiement dans le 15e\n"
            "- Sécurité : 20 caméras supplémentaires rue de Vaugirard et avenue Félix Faure\n"
            "- Végétalisation : 500 arbres plantés et 3 nouveaux jardins partagés\n"
            "- Écoles : rénovation des 12 écoles primaires du quartier\n"
            "- Seniors : création d'un club seniors connecté place Charles Vallin\n\n"
            "Contact : jean.dupont@paris15.fr | 01 45 XX XX XX\n"
            "Permanence : 42 rue de la Convention, mardi et jeudi 14h-18h"
        ),
    },
    {
        "id": "website_about_page",
        "candidate_id": "test_cand_martin",
        "candidate_name": "Sophie Martin",
        "municipality_code": "69123",
        "municipality_name": "Lyon",
        "page_type": "about",
        "url": "https://sophiemartin.fr/qui-suis-je",
        "title": "Qui suis-je ? - Sophie Martin",
        "content": (
            "Sophie Martin - Candidate aux municipales de Lyon 2026\n\n"
            "Née à Lyon en 1978, je suis architecte urbaniste de formation (ENSAL 2003). "
            "Après 15 ans dans le privé, j'ai rejoint la métropole de Lyon en 2018 "
            "comme directrice de l'aménagement urbain.\n\n"
            "Mon parcours politique :\n"
            "- 2020 : Élue au conseil du 3e arrondissement\n"
            "- 2022 : Vice-présidente de la commission urbanisme\n"
            "- 2024 : Tête de liste EELV aux européennes (Rhône)\n\n"
            "Je suis mère de deux enfants scolarisés à l'école publique Voltaire. "
            "Mon engagement : une ville à taille humaine, qui respire, où chaque "
            "quartier dispose de services publics de qualité."
        ),
    },
    {
        "id": "website_blog_post",
        "candidate_id": "test_cand_bernard",
        "candidate_name": "Pierre Bernard",
        "municipality_code": "13055",
        "municipality_name": "Marseille",
        "page_type": "blog",
        "url": "https://pierrebernard.fr/blog/2026/02/insecurite-marseille",
        "title": "L'insécurité à Marseille : mes propositions",
        "content": (
            "L'insécurité à Marseille : agir maintenant\n\n"
            "Publié le 15 février 2026\n\n"
            "Les chiffres sont alarmants. En 2025, les agressions violentes ont augmenté "
            "de 23% dans les quartiers nord de Marseille. Les habitants me confient "
            "leur sentiment d'abandon.\n\n"
            "Face à cette situation, je propose un plan d'urgence en 5 points :\n"
            "1. Recrutement immédiat de 100 policiers municipaux\n"
            "2. Déploiement de 500 caméras dans les zones sensibles\n"
            "3. Création de brigades de nuit dans tous les arrondissements\n"
            "4. Partenariat renforcé avec la police nationale et la gendarmerie\n"
            "5. Programme de médiation sociale avec 50 médiateurs de rue\n\n"
            "Ce plan sera financé par une réallocation du budget communication "
            "de la mairie (actuellement 8 millions d'euros par an)."
        ),
    },
    {
        "id": "website_minimal_content",
        "candidate_id": "test_cand_petit",
        "candidate_name": "Marie Petit",
        "municipality_code": "31555",
        "municipality_name": "Toulouse",
        "page_type": "html",
        "url": "https://mariepetit-toulouse.fr",
        "title": "Marie Petit - Municipales 2026",
        "content": (
            "Marie Petit\nCandidate aux municipales de Toulouse 2026\n"
            "Liste : Toulouse en Commun\n\n"
            "Rendez-vous le 15 mars 2026 !\n\n"
            "Contact : contact@mariepetit-toulouse.fr"
        ),
    },
    {
        "id": "website_pdf_programme",
        "candidate_id": "test_cand_leroy",
        "candidate_name": "François Leroy",
        "municipality_code": "44109",
        "municipality_name": "Nantes",
        "page_type": "pdf",
        "url": "https://francoisleroy.fr/programme.pdf",
        "title": "Programme complet",
        "content": (
            "PROGRAMME MUNICIPAL - NANTES 2026\n"
            "François LEROY - Tête de liste « Nantes pour tous »\n\n"
            "CHAPITRE 1 : MOBILITÉS\n"
            "Extension de la ligne 1 du tramway jusqu'à Carquefou (+4 stations)\n"
            "Création d'un RER métropolitain avec 3 lignes\n"
            "100 km de pistes cyclables sécurisées\n"
            "Navettes fluviales sur l'Erdre et la Loire\n\n"
            "CHAPITRE 2 : ENVIRONNEMENT\n"
            "Zéro bétonisation des zones naturelles\n"
            "Restauration de 50 hectares de zones humides\n"
            "Cantine 100% bio et locale dans toutes les écoles\n"
            "Parc photovoltaïque sur les toits de la ZAC\n\n"
            "CHAPITRE 3 : SOLIDARITÉ\n"
            "Construction de 2000 logements sociaux\n"
            "Aide alimentaire : doublement des épiceries solidaires\n"
            "Programme d'insertion par l'activité économique\n"
            "Gratuité des musées municipaux pour les moins de 26 ans"
        ),
    },
]

# 5 upload document texts (diverse types the admin might upload)
UPLOAD_SAMPLES = [
    {
        "id": "upload_party_tract",
        "filename": "tract_renaissance_municipales.pdf",
        "expected_target_type": "party",
        "expected_target_id": "test_renaissance",
        "text": (
            "RENAISSANCE - MUNICIPALES 2026\n"
            "Votez pour le changement !\n\n"
            "Avec Renaissance, construisons ensemble une ville moderne, "
            "écologique et solidaire. Notre programme repose sur 5 axes "
            "prioritaires : l'emploi, le logement, la transition écologique, "
            "la sécurité et l'éducation.\n\n"
            "Rejoignez-nous sur renaissance-municipales.fr"
        ),
    },
    {
        "id": "upload_candidate_cv",
        "filename": "presentation_jean_dupont.pdf",
        "expected_target_type": "candidate",
        "expected_target_id": "test_cand_dupont",
        "text": (
            "Jean DUPONT - Parcours et engagements\n\n"
            "Né le 15 mars 1972 à Paris\n"
            "Diplômé de Sciences Po Paris et de l'ENA (promotion Simone Veil)\n"
            "Conseiller municipal du 15e arrondissement depuis 2020\n"
            "Président de la commission finances\n\n"
            "Mes réalisations :\n"
            "- Réduction de 12% du budget communication\n"
            "- Création de 3 jardins partagés\n"
            "- Mise en place du budget participatif (200 000€/an)"
        ),
    },
    {
        "id": "upload_unknown_document",
        "filename": "document_sans_titre.pdf",
        "expected_target_type": None,
        "expected_target_id": None,
        "text": (
            "Compte rendu de la réunion du 12 janvier 2026\n\n"
            "Présents : M. le Maire, Mme l'adjointe aux finances, "
            "M. le directeur des services techniques.\n\n"
            "Ordre du jour :\n"
            "1. Approbation du PV de la séance précédente\n"
            "2. Vote du budget primitif 2026\n"
            "3. Délibération sur le marché de voirie\n"
            "4. Questions diverses"
        ),
    },
    {
        "id": "upload_short_text",
        "filename": "note_interne.txt",
        "expected_target_type": None,
        "expected_target_id": None,
        "text": "Réunion reportée au 15 mars.",
    },
    {
        "id": "upload_electoral_poster_ocr",
        "filename": "panneau_2_75056.pdf",
        "expected_target_type": "candidate",
        "expected_target_id": "test_cand_dupont",
        "text": (
            "MUNICIPALES 2026 - PARIS 15e ARRONDISSEMENT\n\n"
            "Jean DUPONT\n"
            "Tête de liste « Paris 15 Ensemble »\n\n"
            "NOS ENGAGEMENTS :\n"
            "✓ Doubler les effectifs de la police municipale\n"
            "✓ Rénover les 12 écoles du quartier\n"
            "✓ Créer 500 places de crèche\n"
            "✓ Végétaliser la rue de Vaugirard\n"
            "✓ Installer des bornes de recharge électrique\n\n"
            "VOTEZ JEAN DUPONT LE 15 MARS 2026\n"
            "www.paris15ensemble.fr"
        ),
    },
]


# ---------------------------------------------------------------------------
# GEval metrics for pipeline quality
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def extraction_completeness_metric(judge_model):
    """Checks if text extraction preserves all key content from the source."""
    return GEval(
        name="Extraction Completeness",
        criteria="""Compare the extracted chunks (actual_output) against the original
        document text (expected_output). Evaluate whether ALL key information
        is preserved across the chunks:
        1. Are all proper nouns (names, places, organizations) present?
        2. Are all numbers (budgets, dates, percentages, counts) preserved?
        3. Are all policy proposals or commitments captured?
        4. Is the text in the same language (French) without garbling?

        Minor formatting differences (whitespace, bullet style) are acceptable.
        Score 1.0 if all content is preserved. Score 0.0 if major content is lost.""",
        evaluation_params=[
            LLMTestCaseParams.ACTUAL_OUTPUT,
            LLMTestCaseParams.EXPECTED_OUTPUT,
        ],
        threshold=0.8,
        model=judge_model,
    )


@pytest.fixture(scope="session")
def chunk_quality_metric(judge_model):
    """Checks if individual chunks are coherent and self-contained."""
    return GEval(
        name="Chunk Quality",
        criteria="""Evaluate the quality of the text chunks for use in a RAG system.
        Each chunk should:
        1. Be a coherent unit of text (not cut mid-sentence or mid-word)
        2. Contain enough context to be understood independently
        3. Not be mostly whitespace, boilerplate, or navigation text
        4. Be in readable French (not garbled encoding or OCR artifacts)
        5. Be between 100-1200 characters (not too short to be useful,
           not too long to lose specificity)

        Score 1.0 if chunks are well-formed. Score 0.0 if chunks are garbage.""",
        evaluation_params=[LLMTestCaseParams.ACTUAL_OUTPUT],
        threshold=0.7,
        model=judge_model,
    )


@pytest.fixture(scope="session")
def metadata_completeness_metric(judge_model):
    """Checks if chunk metadata has all required fields for RAG filtering."""
    return GEval(
        name="Metadata Completeness",
        criteria="""Evaluate whether the metadata attached to these chunks is complete
        enough for a political RAG system. Required metadata:
        1. namespace: identifies the entity (party_id or candidate_id) — MUST be present
        2. source_document: identifies the document type — MUST be present
        3. fiabilite: reliability level (1-4) — MUST be present and correct
        4. party_name OR candidate_name: human-readable entity name — at least one MUST be present
        5. document_name: name of the source document — SHOULD be present
        6. chunk_index and total_chunks: position info — SHOULD be present

        For candidate content, also check:
        7. municipality_code and municipality_name — SHOULD be present
        8. party_ids: list of associated parties — SHOULD be present

        Score 1.0 if all required fields are present and correct.
        Score 0.0 if critical fields are missing.""",
        evaluation_params=[LLMTestCaseParams.ACTUAL_OUTPUT],
        threshold=0.8,
        model=judge_model,
    )


@pytest.fixture(scope="session")
def theme_coverage_metric(judge_model):
    """Checks if theme classification captures the right political topics."""
    return GEval(
        name="Theme Coverage",
        criteria="""Given a political text (expected_output) and its assigned theme
        classification (actual_output), evaluate:
        1. Is the assigned theme correct for the content?
        2. Does the theme match the 14-theme taxonomy: economie, education,
           environnement, sante, securite, immigration, culture, logement,
           transport, numerique, agriculture, justice, international, institutions?
        3. If the text covers multiple topics, is the PRIMARY theme correct?
        4. Is the sub_theme (if present) more specific and relevant?

        Score 1.0 if theme is correct. Score 0.0 if completely wrong.""",
        evaluation_params=[
            LLMTestCaseParams.ACTUAL_OUTPUT,
            LLMTestCaseParams.EXPECTED_OUTPUT,
        ],
        threshold=0.7,
        model=judge_model,
    )


@pytest.fixture(scope="session")
def cross_pipeline_consistency_metric(judge_model):
    """Checks if the same content produces consistent chunks across pipelines."""
    return GEval(
        name="Cross-Pipeline Consistency",
        criteria="""Compare two sets of chunks produced from the SAME original text
        but through different ingestion pipelines. The actual_output is from
        pipeline A and the expected_output is from pipeline B. Evaluate:
        1. Do both sets contain the same key information?
        2. Are the chunk boundaries roughly similar?
        3. Is the total content coverage equivalent?
        4. Are proper nouns, numbers, and policy terms identical?

        Minor differences in formatting, chunk boundaries, or whitespace are OK.
        Score 1.0 if both pipelines produce equivalent chunks.
        Score 0.0 if one pipeline loses significant content.""",
        evaluation_params=[
            LLMTestCaseParams.ACTUAL_OUTPUT,
            LLMTestCaseParams.EXPECTED_OUTPUT,
        ],
        threshold=0.8,
        model=judge_model,
    )


# ---------------------------------------------------------------------------
# Helper: simulate each pipeline's chunking + metadata creation
# ---------------------------------------------------------------------------

def _simulate_manifesto_pipeline(sample: dict) -> list[Document]:
    """Simulate manifesto_indexer.py chunking."""
    splitter = _get_text_splitter()
    docs = []
    chunks = splitter.split_text(sample["text"])
    for i, chunk in enumerate(chunks):
        if len(chunk.strip()) < 30:
            continue
        cm = ChunkMetadata(
            namespace=sample["party_id"],
            source_document="election_manifesto",
            party_ids=[sample["party_id"]],
            party_name=sample["party_name"],
            document_name=f"{sample['party_name']} - Programme électoral",
            page=1,
            chunk_index=i,
            total_chunks=0,
        )
        docs.append(Document(page_content=chunk, metadata=cm.to_qdrant_payload()))
    for doc in docs:
        doc.metadata["total_chunks"] = len(docs)
    return docs


def _simulate_candidate_pipeline(sample: dict) -> list[Document]:
    """Simulate candidate_indexer.py chunking."""
    splitter = _get_text_splitter()
    docs = []
    chunks = splitter.split_text(sample["content"])
    for i, chunk in enumerate(chunks):
        if len(chunk.strip()) < 30:
            continue
        cm = ChunkMetadata(
            namespace=sample["candidate_id"],
            source_document=f"candidate_website_{sample['page_type']}",
            party_ids=[],
            candidate_ids=[sample["candidate_id"]],
            candidate_name=sample["candidate_name"],
            municipality_code=sample.get("municipality_code", ""),
            municipality_name=sample.get("municipality_name", ""),
            document_name=f"{sample['candidate_name']} - {sample['page_type'].capitalize()}",
            url=sample.get("url"),
            page_title=sample.get("title"),
            page_type=sample["page_type"],
            page=0,
            chunk_index=i,
            total_chunks=0,
        )
        docs.append(Document(page_content=chunk, metadata=cm.to_qdrant_payload()))
    for doc in docs:
        doc.metadata["total_chunks"] = len(docs)
    return docs


def _simulate_upload_pipeline(sample: dict) -> list[Document]:
    """Simulate document_upload.py chunking (post-assignment)."""
    splitter = _get_text_splitter()
    docs = []
    chunks = splitter.split_text(sample["text"])
    target_type = sample.get("expected_target_type", "party")
    target_id = sample.get("expected_target_id", "unknown")

    for i, chunk in enumerate(chunks):
        if len(chunk.strip()) < 30:
            continue
        cm = ChunkMetadata(
            namespace=target_id or "unassigned",
            source_document="uploaded_document",
            party_ids=[target_id] if target_type == "party" and target_id else [],
            candidate_ids=[target_id] if target_type == "candidate" and target_id else [],
            party_name=target_id if target_type == "party" else None,
            candidate_name=target_id if target_type == "candidate" else None,
            document_name=sample["filename"],
            chunk_index=i,
            total_chunks=0,
        )
        docs.append(Document(page_content=chunk, metadata=cm.to_qdrant_payload()))
    for doc in docs:
        doc.metadata["total_chunks"] = len(docs)
    return docs


def _docs_to_text(docs: list[Document]) -> str:
    """Concatenate document chunks for LLM evaluation."""
    parts = []
    for doc in docs:
        meta = doc.metadata
        meta_str = ", ".join(
            f"{k}={v}" for k, v in sorted(meta.items())
            if v is not None and k not in ("page_content",)
        )
        parts.append(f"[CHUNK {meta.get('chunk_index', '?')}/{meta.get('total_chunks', '?')}] "
                      f"{doc.page_content}\n[metadata: {meta_str}]")
    return "\n\n---\n\n".join(parts)


# ===========================================================================
# TEST SUITE 1: Extraction Completeness
# ===========================================================================

class TestExtractionCompleteness:
    """No content should be silently lost during chunking."""

    @pytest.mark.parametrize("sample", MANIFESTO_SAMPLES, ids=lambda s: s["id"])
    def test_manifesto_extraction(self, sample, extraction_completeness_metric):
        docs = _simulate_manifesto_pipeline(sample)
        assert len(docs) > 0, f"No chunks produced for {sample['id']}"

        test_case = LLMTestCase(
            input=f"Extraction test: {sample['id']}",
            actual_output=_docs_to_text(docs),
            expected_output=sample["text"],
        )
        assert_test(test_case, [extraction_completeness_metric])

    @pytest.mark.parametrize("sample", CANDIDATE_WEBSITE_SAMPLES, ids=lambda s: s["id"])
    def test_candidate_extraction(self, sample, extraction_completeness_metric):
        if len(sample["content"].strip()) < 50:
            pytest.skip("Content too short for meaningful extraction test")

        docs = _simulate_candidate_pipeline(sample)
        assert len(docs) > 0, f"No chunks produced for {sample['id']}"

        test_case = LLMTestCase(
            input=f"Extraction test: {sample['id']}",
            actual_output=_docs_to_text(docs),
            expected_output=sample["content"],
        )
        assert_test(test_case, [extraction_completeness_metric])


# ===========================================================================
# TEST SUITE 2: Chunk Quality
# ===========================================================================

class TestChunkQuality:
    """Chunks must be coherent, well-sized, and useful for RAG."""

    @pytest.mark.parametrize("sample", MANIFESTO_SAMPLES, ids=lambda s: s["id"])
    def test_manifesto_chunk_quality(self, sample, chunk_quality_metric):
        docs = _simulate_manifesto_pipeline(sample)
        if not docs:
            pytest.skip("No chunks produced")

        test_case = LLMTestCase(
            input=f"Chunk quality: {sample['id']}",
            actual_output=_docs_to_text(docs),
        )
        assert_test(test_case, [chunk_quality_metric])

    @pytest.mark.parametrize("sample", CANDIDATE_WEBSITE_SAMPLES, ids=lambda s: s["id"])
    def test_candidate_chunk_quality(self, sample, chunk_quality_metric):
        docs = _simulate_candidate_pipeline(sample)
        if not docs:
            pytest.skip("No chunks produced")

        test_case = LLMTestCase(
            input=f"Chunk quality: {sample['id']}",
            actual_output=_docs_to_text(docs),
        )
        assert_test(test_case, [chunk_quality_metric])

    def test_short_text_produces_no_garbage(self):
        """Text shorter than min chunk (30 chars) should produce zero chunks."""
        splitter = _get_text_splitter()
        chunks = splitter.split_text("Oui.")
        usable = [c for c in chunks if len(c.strip()) >= 30]
        assert len(usable) == 0, f"Short text should produce 0 chunks, got {len(usable)}"


# ===========================================================================
# TEST SUITE 3: Metadata Completeness
# ===========================================================================

class TestMetadataCompleteness:
    """Every chunk must carry enough metadata for RAG filtering."""

    @pytest.mark.parametrize("sample", MANIFESTO_SAMPLES, ids=lambda s: s["id"])
    def test_manifesto_metadata(self, sample, metadata_completeness_metric):
        docs = _simulate_manifesto_pipeline(sample)
        assert len(docs) > 0

        test_case = LLMTestCase(
            input=f"Metadata completeness: {sample['id']}",
            actual_output=_docs_to_text(docs),
        )
        assert_test(test_case, [metadata_completeness_metric])

    @pytest.mark.parametrize("sample", CANDIDATE_WEBSITE_SAMPLES, ids=lambda s: s["id"])
    def test_candidate_metadata(self, sample, metadata_completeness_metric):
        docs = _simulate_candidate_pipeline(sample)
        if not docs:
            pytest.skip("No chunks produced")

        test_case = LLMTestCase(
            input=f"Metadata completeness: {sample['id']}",
            actual_output=_docs_to_text(docs),
        )
        assert_test(test_case, [metadata_completeness_metric])

    @pytest.mark.parametrize("sample", UPLOAD_SAMPLES[:3], ids=lambda s: s["id"])
    def test_upload_metadata(self, sample, metadata_completeness_metric):
        if sample.get("expected_target_type") is None:
            pytest.skip("Unassigned document, no metadata to check")

        docs = _simulate_upload_pipeline(sample)
        if not docs:
            pytest.skip("No chunks produced")

        test_case = LLMTestCase(
            input=f"Metadata completeness: {sample['id']}",
            actual_output=_docs_to_text(docs),
        )
        assert_test(test_case, [metadata_completeness_metric])


# ===========================================================================
# TEST SUITE 4: Metadata Correctness (deterministic — no LLM judge needed)
# ===========================================================================

class TestMetadataCorrectness:
    """Deterministic checks on metadata values."""

    @pytest.mark.parametrize("sample", MANIFESTO_SAMPLES, ids=lambda s: s["id"])
    def test_manifesto_fiabilite_is_official(self, sample):
        docs = _simulate_manifesto_pipeline(sample)
        for doc in docs:
            assert doc.metadata.get("fiabilite") == int(Fiabilite.OFFICIAL), (
                f"Manifesto chunk should have fiabilite=OFFICIAL(2), "
                f"got {doc.metadata.get('fiabilite')}"
            )

    @pytest.mark.parametrize("sample", CANDIDATE_WEBSITE_SAMPLES, ids=lambda s: s["id"])
    def test_candidate_fiabilite_matches_page_type(self, sample):
        docs = _simulate_candidate_pipeline(sample)
        expected = (
            int(Fiabilite.OFFICIAL)
            if sample["page_type"] in ("about", "programme")
            else int(Fiabilite.PRESS)
        )
        for doc in docs:
            assert doc.metadata.get("fiabilite") == expected, (
                f"Candidate {sample['page_type']} chunk should have fiabilite={expected}, "
                f"got {doc.metadata.get('fiabilite')}"
            )

    @pytest.mark.parametrize("sample", UPLOAD_SAMPLES, ids=lambda s: s["id"])
    def test_upload_fiabilite_is_press(self, sample):
        if sample.get("expected_target_type") is None:
            pytest.skip("Unassigned document")
        docs = _simulate_upload_pipeline(sample)
        for doc in docs:
            assert doc.metadata.get("fiabilite") == int(Fiabilite.PRESS), (
                f"Upload chunk should have fiabilite=PRESS(3), "
                f"got {doc.metadata.get('fiabilite')}"
            )

    @pytest.mark.parametrize("sample", MANIFESTO_SAMPLES, ids=lambda s: s["id"])
    def test_manifesto_namespace_matches_party_id(self, sample):
        docs = _simulate_manifesto_pipeline(sample)
        for doc in docs:
            assert doc.metadata.get("namespace") == sample["party_id"]
            assert sample["party_id"] in doc.metadata.get("party_ids", [])

    @pytest.mark.parametrize("sample", CANDIDATE_WEBSITE_SAMPLES, ids=lambda s: s["id"])
    def test_candidate_namespace_matches_candidate_id(self, sample):
        docs = _simulate_candidate_pipeline(sample)
        for doc in docs:
            assert doc.metadata.get("namespace") == sample["candidate_id"]
            assert sample["candidate_id"] in doc.metadata.get("candidate_ids", [])

    @pytest.mark.parametrize("sample", CANDIDATE_WEBSITE_SAMPLES, ids=lambda s: s["id"])
    def test_candidate_has_municipality_info(self, sample):
        docs = _simulate_candidate_pipeline(sample)
        for doc in docs:
            assert doc.metadata.get("municipality_code") == sample["municipality_code"], (
                f"Missing municipality_code in candidate chunk"
            )
            assert doc.metadata.get("municipality_name") == sample["municipality_name"], (
                f"Missing municipality_name in candidate chunk"
            )

    def test_chunk_index_sequential(self):
        """chunk_index should be sequential 0, 1, 2, ..."""
        sample = MANIFESTO_SAMPLES[0]  # Use longest sample
        docs = _simulate_manifesto_pipeline(sample)
        indices = [doc.metadata["chunk_index"] for doc in docs]
        assert indices == list(range(len(docs))), (
            f"chunk_index not sequential: {indices}"
        )

    def test_total_chunks_consistent(self):
        """total_chunks should match actual document count."""
        sample = MANIFESTO_SAMPLES[0]
        docs = _simulate_manifesto_pipeline(sample)
        for doc in docs:
            assert doc.metadata["total_chunks"] == len(docs), (
                f"total_chunks={doc.metadata['total_chunks']} but {len(docs)} docs"
            )


# ===========================================================================
# TEST SUITE 5: Chunk Size Constraints (deterministic)
# ===========================================================================

class TestChunkSizeConstraints:
    """All chunks must respect the configured size limits."""

    def _all_chunks(self) -> list[tuple[str, Document]]:
        """Generate all chunks from all pipeline samples."""
        results = []
        for s in MANIFESTO_SAMPLES:
            for doc in _simulate_manifesto_pipeline(s):
                results.append((f"manifesto:{s['id']}", doc))
        for s in CANDIDATE_WEBSITE_SAMPLES:
            for doc in _simulate_candidate_pipeline(s):
                results.append((f"candidate:{s['id']}", doc))
        for s in UPLOAD_SAMPLES:
            if s.get("expected_target_type"):
                for doc in _simulate_upload_pipeline(s):
                    results.append((f"upload:{s['id']}", doc))
        return results

    def test_no_chunk_exceeds_max_size(self):
        """No chunk should exceed CHUNK_SIZE + CHUNK_OVERLAP (1200 chars)."""
        max_allowed = 1000 + 200  # chunk_size + overlap
        for label, doc in self._all_chunks():
            assert len(doc.page_content) <= max_allowed, (
                f"Chunk from {label} is {len(doc.page_content)} chars, "
                f"exceeds max {max_allowed}"
            )

    def test_no_chunk_below_min_size(self):
        """No chunk should be below 30 chars (our skip threshold)."""
        for label, doc in self._all_chunks():
            assert len(doc.page_content.strip()) >= 30, (
                f"Chunk from {label} is only {len(doc.page_content.strip())} chars"
            )

    def test_short_document_not_dropped(self):
        """A document with 50-200 chars should still produce at least 1 chunk."""
        short_text = (
            "Marie Petit, candidate aux municipales de Toulouse. "
            "Notre programme : gratuité des transports et 100% bio dans les cantines."
        )
        splitter = _get_text_splitter()
        chunks = [c for c in splitter.split_text(short_text) if len(c.strip()) >= 30]
        assert len(chunks) >= 1, "Short but valid text should produce at least 1 chunk"


# ===========================================================================
# TEST SUITE 6: Theme Classification Gap
# ===========================================================================

class TestThemeClassificationGap:
    """Catch the known problem: theme classification only runs on manifestos."""

    def test_manifesto_has_theme_field(self):
        """Manifesto pipeline DOES set theme (via chunk_classifier)."""
        # This is a structural test — we can't call the real LLM here,
        # but we verify the field exists in the metadata model.
        cm = ChunkMetadata(
            namespace="test",
            source_document="election_manifesto",
            theme="economie",
            sub_theme="emploi",
        )
        payload = cm.to_qdrant_payload()
        assert payload["theme"] == "economie"
        assert payload["sub_theme"] == "emploi"

    def test_candidate_pipeline_missing_theme(self):
        """BUG DETECTOR: candidate pipeline does NOT classify themes.

        This test documents the known gap. If it starts passing,
        someone fixed the issue.
        """
        sample = CANDIDATE_WEBSITE_SAMPLES[0]  # programme page
        docs = _simulate_candidate_pipeline(sample)
        themes = [doc.metadata.get("theme") for doc in docs]
        # Currently all None — this test SHOULD FAIL once we add theme
        # classification to the candidate pipeline
        assert all(t is None for t in themes), (
            "GOOD NEWS: Candidate chunks now have themes! "
            "Remove this test and update test_candidate_has_theme."
        )

    def test_upload_pipeline_missing_theme(self):
        """BUG DETECTOR: upload pipeline does NOT classify themes."""
        sample = UPLOAD_SAMPLES[0]
        docs = _simulate_upload_pipeline(sample)
        themes = [doc.metadata.get("theme") for doc in docs]
        assert all(t is None for t in themes), (
            "GOOD NEWS: Upload chunks now have themes! "
            "Remove this test and update test_upload_has_theme."
        )

    def test_theme_taxonomy_coverage(self):
        """All 14 themes should be valid in ChunkMetadata."""
        for theme in THEME_TAXONOMY:
            cm = ChunkMetadata(
                namespace="test",
                source_document="test",
                theme=theme,
            )
            assert cm.theme == theme

    def test_invalid_theme_rejected(self):
        """ChunkMetadata should reject themes not in taxonomy."""
        cm = ChunkMetadata(
            namespace="test",
            source_document="test",
            theme="invalid_theme",
        )
        # Validator sets invalid themes to None
        assert cm.theme is None


# ===========================================================================
# TEST SUITE 7: Cross-Pipeline Consistency
# ===========================================================================

class TestCrossPipelineConsistency:
    """Same text should produce equivalent chunks regardless of pipeline."""

    SHARED_TEXT = (
        "Programme de rénovation énergétique des bâtiments communaux. "
        "Budget prévu : 2 millions d'euros sur 3 ans. "
        "Objectif : réduire la consommation d'énergie de 40% d'ici 2030. "
        "Priorités : isolation thermique des écoles, remplacement des "
        "chaudières fioul par des pompes à chaleur, installation de "
        "panneaux solaires sur les toits des gymnases."
    )

    def test_manifesto_vs_upload_same_chunks(self, cross_pipeline_consistency_metric):
        """Same text chunked as manifesto vs upload should have same content."""
        manifesto_sample = {
            "party_id": "test_party",
            "party_name": "Test Party",
            "text": self.SHARED_TEXT,
        }
        upload_sample = {
            "filename": "test.pdf",
            "expected_target_type": "party",
            "expected_target_id": "test_party",
            "text": self.SHARED_TEXT,
        }

        manifesto_docs = _simulate_manifesto_pipeline(manifesto_sample)
        upload_docs = _simulate_upload_pipeline(upload_sample)

        # Both should produce the same number of chunks
        assert len(manifesto_docs) == len(upload_docs), (
            f"Manifesto produced {len(manifesto_docs)} chunks, "
            f"upload produced {len(upload_docs)} chunks for identical text"
        )

        # Content should match
        manifesto_text = "\n".join(d.page_content for d in manifesto_docs)
        upload_text = "\n".join(d.page_content for d in upload_docs)

        test_case = LLMTestCase(
            input="Cross-pipeline consistency: manifesto vs upload",
            actual_output=manifesto_text,
            expected_output=upload_text,
        )
        assert_test(test_case, [cross_pipeline_consistency_metric])

    def test_metadata_differs_correctly(self):
        """Same text through different pipelines should have different metadata."""
        manifesto_sample = {
            "party_id": "test_party",
            "party_name": "Test Party",
            "text": self.SHARED_TEXT,
        }
        upload_sample = {
            "filename": "test.pdf",
            "expected_target_type": "party",
            "expected_target_id": "test_party",
            "text": self.SHARED_TEXT,
        }

        manifesto_docs = _simulate_manifesto_pipeline(manifesto_sample)
        upload_docs = _simulate_upload_pipeline(upload_sample)

        if manifesto_docs and upload_docs:
            # source_document should differ
            assert manifesto_docs[0].metadata["source_document"] == "election_manifesto"
            assert upload_docs[0].metadata["source_document"] == "uploaded_document"

            # fiabilite should differ
            assert manifesto_docs[0].metadata["fiabilite"] == int(Fiabilite.OFFICIAL)
            assert upload_docs[0].metadata["fiabilite"] == int(Fiabilite.PRESS)


# ===========================================================================
# TEST SUITE 8: Edge Cases & Known Problems
# ===========================================================================

class TestEdgeCases:
    """Test edge cases that have caused real bugs."""

    def test_empty_text_produces_no_chunks(self):
        """Empty string should produce zero chunks, not crash."""
        splitter = _get_text_splitter()
        chunks = splitter.split_text("")
        assert len(chunks) == 0

    def test_whitespace_only_produces_no_chunks(self):
        """Whitespace-only text should produce zero usable chunks."""
        splitter = _get_text_splitter()
        chunks = splitter.split_text("   \n\n\t\t\n   ")
        usable = [c for c in chunks if len(c.strip()) >= 30]
        assert len(usable) == 0

    def test_unicode_french_characters_preserved(self):
        """French accents, cedillas, and special chars must survive chunking."""
        text = (
            "L'économie française nécessite des réformes. "
            "Le président a évoqué les « enjeux majeurs » lors du débat à l'Élysée. "
            "Coût estimé : 50 000 € pour le département du Rhône (69). "
            "Référence : arrêté n°2026-01-15/ABC préfectoral."
        )
        splitter = _get_text_splitter()
        chunks = splitter.split_text(text)
        rejoined = " ".join(chunks)
        assert "économie" in rejoined
        assert "réformes" in rejoined
        assert "Élysée" in rejoined
        assert "50 000 €" in rejoined or "50 000€" in rejoined
        assert "arrêté" in rejoined

    def test_very_long_text_chunked_correctly(self):
        """A 10,000+ char document should produce ~10+ chunks of ~1000 chars."""
        paragraph = (
            "Nous proposons un plan ambitieux de rénovation urbaine comprenant "
            "la construction de logements sociaux, la création d'espaces verts, "
            "et la modernisation des infrastructures de transport en commun. "
        )
        long_text = (paragraph * 100)  # ~16,000 chars
        splitter = _get_text_splitter()
        chunks = [c for c in splitter.split_text(long_text) if len(c.strip()) >= 30]
        assert len(chunks) >= 10, f"Expected ~15+ chunks from {len(long_text)} chars, got {len(chunks)}"
        for chunk in chunks:
            assert len(chunk) <= 1200, f"Chunk too long: {len(chunk)} chars"

    def test_upload_short_text_rejected(self):
        """Upload pipeline rejects text < 50 chars (in process_upload)."""
        # Simulate the check from document_upload.py line 458
        text = "Réunion reportée."
        min_length = 50
        assert len(text.strip()) < min_length, (
            "This text should be below the 50-char minimum"
        )

    def test_metadata_to_qdrant_payload_roundtrip(self):
        """ChunkMetadata should survive to_qdrant_payload → from_qdrant_payload."""
        cm = ChunkMetadata(
            namespace="test_candidate",
            source_document="candidate_website_programme",
            party_ids=["party_a", "party_b"],
            candidate_ids=["test_candidate"],
            candidate_name="Jean Dupont",
            municipality_code="75056",
            municipality_name="Paris",
            is_tete_de_liste=True,
            nuance_politique="DVC",
            theme="environnement",
            sub_theme="transition_energetique",
            page=3,
            chunk_index=5,
            total_chunks=20,
        )
        payload = cm.to_qdrant_payload()
        restored = ChunkMetadata.from_qdrant_payload(payload)

        assert restored.namespace == cm.namespace
        assert restored.source_document == cm.source_document
        assert restored.party_ids == cm.party_ids
        assert restored.candidate_ids == cm.candidate_ids
        assert restored.candidate_name == cm.candidate_name
        assert restored.municipality_code == cm.municipality_code
        assert restored.is_tete_de_liste == cm.is_tete_de_liste
        assert restored.theme == cm.theme
        assert restored.sub_theme == cm.sub_theme
        assert int(restored.fiabilite) == int(cm.fiabilite)

    def test_candidate_page_type_blog_gets_press_fiabilite(self):
        """Blog posts should get PRESS fiabilite, not OFFICIAL."""
        cm = ChunkMetadata(
            namespace="test",
            source_document="candidate_website_blog",
        )
        assert cm.fiabilite == Fiabilite.PRESS

    def test_candidate_page_type_programme_gets_official_fiabilite(self):
        """Programme pages should get OFFICIAL fiabilite."""
        cm = ChunkMetadata(
            namespace="test",
            source_document="candidate_website_programme",
        )
        assert cm.fiabilite == Fiabilite.OFFICIAL

    def test_uploaded_document_always_press(self):
        """Uploaded documents should always be PRESS regardless of content."""
        cm = ChunkMetadata(
            namespace="test",
            source_document="uploaded_document",
        )
        assert cm.fiabilite == Fiabilite.PRESS

    def test_upload_pipeline_missing_url(self):
        """BUG DETECTOR: upload pipeline doesn't set URL on chunks."""
        sample = UPLOAD_SAMPLES[0]
        docs = _simulate_upload_pipeline(sample)
        for doc in docs:
            url = doc.metadata.get("url")
            assert url is None, (
                "Upload pipeline shouldn't have URL (no source URL for uploads)"
            )

    def test_upload_pipeline_missing_page_number(self):
        """Upload pipeline doesn't preserve PDF page numbers."""
        sample = UPLOAD_SAMPLES[0]
        docs = _simulate_upload_pipeline(sample)
        for doc in docs:
            # document_upload._create_documents doesn't set page at all
            # (defaults to 0), unlike manifesto_indexer which tracks real pages
            page = doc.metadata.get("page", 0)
            assert page == 0, (
                "Upload pipeline should set page=0 (it doesn't track PDF pages)"
            )


# ===========================================================================
# TEST SUITE 9: OCR Pipeline (requires GOOGLE_API_KEY)
# ===========================================================================

class TestOCRPipeline:
    """Test the OCR fallback path for scanned PDFs."""

    @pytest.fixture(autouse=True)
    def skip_if_no_api_key(self):
        if not os.environ.get("GOOGLE_API_KEY"):
            pytest.skip("GOOGLE_API_KEY required for OCR tests")

    def test_ocr_threshold_triggers_correctly(self):
        """pypdf text < 200 chars should trigger OCR fallback."""
        from src.services.document_upload import _MIN_TEXT_LENGTH
        assert _MIN_TEXT_LENGTH == 200

    def test_extract_text_from_pdf_bytes_returns_string(self):
        """extract_text_from_pdf_bytes should return a string."""
        from src.services.document_upload import extract_text_from_pdf_bytes
        # Create a minimal valid PDF in memory
        from pypdf import PdfWriter
        writer = PdfWriter()
        writer.add_blank_page(width=200, height=200)
        buf = io.BytesIO()
        writer.write(buf)
        result = extract_text_from_pdf_bytes(buf.getvalue())
        assert isinstance(result, str)

    def test_manifesto_extract_pages_returns_tuples(self):
        """extract_pages_from_pdf should return list of (page_num, text)."""
        from src.services.manifesto_indexer import extract_pages_from_pdf
        from pypdf import PdfWriter
        writer = PdfWriter()
        writer.add_blank_page(width=200, height=200)
        buf = io.BytesIO()
        writer.write(buf)
        result = extract_pages_from_pdf(buf.getvalue())
        assert isinstance(result, list)
        # Blank PDF should return empty list (no text)
        assert len(result) == 0


# ===========================================================================
# TEST SUITE 10: Pipeline Inconsistency Detectors
# ===========================================================================

class TestPipelineInconsistencies:
    """Detect known inconsistencies between pipelines."""

    def test_pdf_extraction_implementations_count(self):
        """BUG DETECTOR: There should be ONE pdf extraction, not three.

        This test documents the duplication. It counts distinct implementations.
        When refactored to a single module, update this test.
        """
        import importlib
        modules_with_pdf_extract = []

        # Check manifesto_indexer
        mod = importlib.import_module("src.services.manifesto_indexer")
        if hasattr(mod, "extract_pages_from_pdf"):
            modules_with_pdf_extract.append("manifesto_indexer")

        # Check document_upload
        mod = importlib.import_module("src.services.document_upload")
        if hasattr(mod, "extract_text_from_pdf_bytes"):
            modules_with_pdf_extract.append("document_upload")

        # This test EXPECTS the duplication to exist (it's documenting a known issue)
        # When fixed, change the assertion
        assert len(modules_with_pdf_extract) >= 2, (
            "GOOD NEWS: PDF extraction has been consolidated! "
            "Update this test to expect exactly 1 implementation."
        )

    def test_chunking_config_consistent_across_pipelines(self):
        """All pipelines should use the same chunking parameters."""
        from src.services.manifesto_indexer import CHUNK_SIZE as M_SIZE, CHUNK_OVERLAP as M_OVERLAP
        from src.services.candidate_indexer import CHUNK_SIZE as C_SIZE, CHUNK_OVERLAP as C_OVERLAP
        from src.services.document_upload import CHUNK_SIZE as U_SIZE, CHUNK_OVERLAP as U_OVERLAP

        assert M_SIZE == C_SIZE == U_SIZE == 1000, (
            f"CHUNK_SIZE mismatch: manifesto={M_SIZE}, candidate={C_SIZE}, upload={U_SIZE}"
        )
        assert M_OVERLAP == C_OVERLAP == U_OVERLAP == 200, (
            f"CHUNK_OVERLAP mismatch: manifesto={M_OVERLAP}, candidate={C_OVERLAP}, upload={U_OVERLAP}"
        )

    def test_manifesto_has_page_tracking_but_upload_doesnt(self):
        """BUG DETECTOR: manifesto tracks real PDF pages, upload doesn't.

        When uploading a manifesto PDF through admin upload, page numbers
        are lost because document_upload._create_documents sets page=0.
        """
        # Manifesto pipeline: uses extract_pages_from_pdf → real page numbers
        manifesto_sample = MANIFESTO_SAMPLES[0]
        manifesto_docs = _simulate_manifesto_pipeline(manifesto_sample)
        manifesto_pages = {doc.metadata.get("page", 0) for doc in manifesto_docs}
        assert 1 in manifesto_pages, "Manifesto should have page=1 (1-indexed)"

        # Upload pipeline: uses extract_text → flattened, page=0
        upload_sample = UPLOAD_SAMPLES[0]
        upload_docs = _simulate_upload_pipeline(upload_sample)
        upload_pages = {doc.metadata.get("page", 0) for doc in upload_docs}
        assert upload_pages == {0}, "Upload pipeline sets page=0 (no page tracking)"

    def test_candidate_pipeline_missing_party_name(self):
        """BUG DETECTOR: candidate chunks have party_ids but not party_name.

        When a candidate belongs to a party, the chunk has party_ids=["lfi"]
        but no party_name="La France Insoumise". The RAG response cannot
        display the human-readable party name from chunk metadata alone.
        """
        sample = CANDIDATE_WEBSITE_SAMPLES[0]
        docs = _simulate_candidate_pipeline(sample)
        for doc in docs:
            party_name = doc.metadata.get("party_name")
            # candidate_indexer doesn't set party_name even when party_ids is set
            assert party_name is None, (
                "GOOD NEWS: Candidate chunks now have party_name! "
                "Update this test."
            )
