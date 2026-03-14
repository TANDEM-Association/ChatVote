"""
Unified theme classification — LLM-primary with keyword fast-path.

Replaces chunk_classifier.py. Runs on ALL pipelines (manifestos, candidate
websites, uploads, posters).

Architecture:
  1. LLM is the PRIMARY classifier (Gemini Flash, ~$0.00004/chunk)
  2. Keywords are an OPTIONAL fast-path: only used when a chunk has 3+ hits
     for a single theme with a clear margin — saves API calls on obvious cases
  3. Never trust keywords alone for borderline cases

Usage:
    from src.services.theme_classifier import classify_chunks

    # Batch (LLM-primary, keyword fast-path for obvious cases)
    results = await classify_chunks(["text1", "text2", ...])

    # Keyword-only for testing/offline use
    result = classify_theme_keywords("Construction de 500 logements sociaux")
"""

import asyncio
import logging
import re
from dataclasses import dataclass
from typing import Optional

from src.models.chunk_metadata import THEME_TAXONOMY

logger = logging.getLogger(__name__)

# Minimum keyword hits to use the keyword fast-path instead of LLM.
# Must also have a clear margin (2x the second-best theme).
_KEYWORD_FAST_PATH_MIN_HITS = 2


@dataclass
class ThemeResult:
    """Result of theme classification."""
    theme: Optional[str] = None
    sub_theme: Optional[str] = None
    method: str = "none"  # "keyword", "llm", "none"
    confidence: float = 0.0


# ---------------------------------------------------------------------------
# Keyword-based classification (fast-path optimization only)
# ---------------------------------------------------------------------------

_THEME_KEYWORDS: dict[str, list[str]] = {
    "economie": [
        "économie", "economie", "impôt", "impot", "fiscal", "budget", "dette",
        "emploi", "chômage", "chomage", "salaire", "pouvoir d'achat",
        "inflation", "entreprise", "commerce", "travail", "investissement",
        "croissance", "PIB", "marché", "compétitivité",
    ],
    "education": [
        "école", "ecole", "éducation", "education", "enseignant", "professeur",
        "université", "universite", "lycée", "lycee", "collège", "college",
        "scolaire", "formation", "étudiant", "etudiant", "apprentissage",
        "cantine", "périscolaire", "crèche", "creche",
    ],
    "environnement": [
        "environnement", "écologie", "ecologie", "climat", "pollution",
        "déchet", "recyclage", "énergie", "energie", "renouvelable",
        "carbone", "transition verte", "énergie verte", "espace vert",
        "biodiversité", "biodiversite", "solaire",
        "éolien", "pesticide", "zéro artificialisation", "transition énergétique",
        "sobriété", "végétalisation", "arbre",
    ],
    "sante": [
        "santé", "sante", "hôpital", "hopital", "médecin", "medecin",
        "soins", "maladie", "vaccination", "pharmacie", "urgence",
        "infirmier", "soignant", "EHPAD", "maison de santé", "CPTS", "ARS",
    ],
    "securite": [
        "sécurité", "securite", "police", "délinquance", "delinquance",
        "criminalité", "criminalite", "violence", "cambriolage", "vol",
        "agression", "gendarmerie", "vidéoprotection", "vidéosurveillance",
        "caméra", "couvre-feu", "prévention",
    ],
    "immigration": [
        "immigration", "immigré", "immigre", "migrant", "frontière",
        "frontiere", "étranger", "etranger", "asile", "régularisation",
        "regularisation", "intégration", "integration", "communautariste",
        "résidence", "aide conditionnée", "titre de séjour",
    ],
    "culture": [
        "culture", "musée", "musee", "théâtre", "theatre", "cinéma",
        "cinema", "bibliothèque", "bibliotheque", "artiste", "artistique",
        "beaux-arts", "patrimoine",
        "festival", "spectacle", "pass culture",
    ],
    "logement": [
        "logement", "loyer", "immobilier", "HLM", "habitation",
        "propriétaire", "proprietaire", "locataire", "construction",
        "rénovation", "renovation", "appartement", "maison",
        "logement social", "logements sociaux", "SRU", "PSLA", "insalubre",
    ],
    "transport": [
        "transport", "métro", "metro", "autobus", "réseau de bus",
        "tramway", "vélo", "velo",
        "voiture", "route", "autoroute", "train", "mobilité", "mobilite",
        "circulation", "stationnement", "parking", "piste cyclable",
        "navette", "RER", "covoiturage",
    ],
    "numerique": [
        "numérique", "numerique", "internet", "digital", "fibre",
        "technologie", "données", "donnees", "cybersécurité",
        "cybersecurite", "IA", "intelligence artificielle", "WiFi",
        "tiers-lieu",
    ],
    "agriculture": [
        "agriculture", "agriculteur", "ferme", "paysan",
        "agriculture biologique", "culture bio", "label bio",
        "pesticide", "alimentaire", "PAC", "élevage", "elevage",
        "récolte", "recolte", "producteur", "circuit court",
        "épicerie solidaire",
    ],
    "justice": [
        "justice", "tribunal", "juge", "droit pénal", "droit civil",
        "droits de l'homme", "droits fondamentaux",
        "projet de loi", "proposition de loi", "prison",
        "peine", "avocat", "procès", "proces", "juridique", "magistrat",
        "médiation", "mediation",
    ],
    "international": [
        "international", "Europe", "UE", "Union européenne", "OTAN",
        "diplomatie", "guerre",
        "paix", "défense", "defense", "armée", "armee", "géopolitique",
        "geopolitique", "jumelage",
    ],
    "institutions": [
        "institution", "démocratie", "democratie", "élection", "election",
        "vote", "référendum", "referendum", "parlement", "sénat", "senat",
        "assemblée", "assemblee", "constitution", "maire", "conseil municipal",
        "budget participatif", "RIC", "citoyen",
    ],
}

# Pre-compiled word-boundary patterns for each keyword.
# Trailing (?:s|x|es|aux)? handles French plurals (école→écoles, animal→animaux).
_COMPILED_PATTERNS: dict[str, list[re.Pattern]] = {
    theme: [
        re.compile(r'\b' + re.escape(kw) + r'(?:s|x|es|aux)?\b', re.IGNORECASE)
        for kw in keywords
    ]
    for theme, keywords in _THEME_KEYWORDS.items()
}


def _keyword_scores(text: str) -> dict[str, int]:
    """Count keyword hits per theme. Internal helper."""
    scores: dict[str, int] = {}
    for theme, patterns in _COMPILED_PATTERNS.items():
        count = sum(1 for p in patterns if p.search(text))
        if count > 0:
            scores[theme] = count
    return scores


def classify_theme_keywords(text: str) -> ThemeResult:
    """Classify using keywords only. For testing/offline use.

    Returns the best theme if there's a clear winner with 3+ hits,
    otherwise returns method="none" (would go to LLM in production).
    """
    scores = _keyword_scores(text)
    if not scores:
        return ThemeResult(method="none")

    sorted_themes = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    best_theme, best_count = sorted_themes[0]

    # Only trust keywords when there's a clear, strong signal
    if best_count < _KEYWORD_FAST_PATH_MIN_HITS:
        return ThemeResult(method="none")

    # Require clear margin: best must be at least 1.5x the runner-up
    if len(sorted_themes) >= 2:
        second_count = sorted_themes[1][1]
        if best_count < 1.5 * second_count:
            return ThemeResult(method="none")

    confidence = best_count / (best_count + 2)
    return ThemeResult(theme=best_theme, method="keyword", confidence=confidence)


def _keyword_fast_path(text: str) -> Optional[ThemeResult]:
    """Try keyword fast-path. Returns ThemeResult only for high-confidence
    obvious cases (3+ hits, clear margin). Returns None to fall through to LLM.
    """
    result = classify_theme_keywords(text)
    if result.theme is not None:
        return result
    return None


# ---------------------------------------------------------------------------
# LLM classification (primary tier)
# ---------------------------------------------------------------------------

_LLM_PROMPT = (
    "Tu es un classificateur de thèmes politiques français. "
    "Classe le texte suivant dans UN SEUL thème principal parmi cette taxonomie :\n\n"
    "| Thème | Description | Exemples de sous-thèmes |\n"
    "|-------|-------------|------------------------|\n"
    "| economie | Fiscalité, emploi, budget, dette, pouvoir d'achat, entreprises | fiscalité, emploi, pouvoir d'achat, entrepreneuriat |\n"
    "| education | Écoles, universités, formation, petite enfance | enseignement primaire, enseignement supérieur, formation professionnelle |\n"
    "| environnement | Climat, pollution, énergie, biodiversité, déchets | changement climatique, transition énergétique, gestion des déchets |\n"
    "| sante | Hôpitaux, médecins, soins, prévention | hôpitaux, médecine de ville, accès aux soins |\n"
    "| securite | Police, délinquance, vidéoprotection, violences | forces de l'ordre, délinquance, vidéoprotection |\n"
    "| immigration | Migrants, frontières, asile, intégration, régularisation | politique migratoire, droit d'asile, intégration |\n"
    "| culture | Musées, théâtres, patrimoine, festivals, bibliothèques | spectacle vivant, patrimoine, événements culturels |\n"
    "| logement | HLM, loyers, rénovation, construction, habitat | logement social, encadrement des loyers, rénovation thermique |\n"
    "| transport | Vélo, métro, train, voiture, stationnement | mobilités douces, transports en commun, ferroviaire |\n"
    "| numerique | Internet, fibre, cybersécurité, IA, données | couverture numérique, cybersécurité, intelligence artificielle |\n"
    "| agriculture | Agriculteurs, bio, circuits courts, PAC, élevage | agriculture biologique, circuits courts, soutien aux agriculteurs |\n"
    "| justice | Tribunaux, magistrats, prisons, médiation | organisation judiciaire, système pénitentiaire, accès au droit |\n"
    "| international | Europe, OTAN, diplomatie, défense, armée | Union européenne, défense, diplomatie |\n"
    "| institutions | Démocratie, élections, référendum, parlement, mairie | démocratie directe, participation citoyenne, gouvernance locale |\n\n"
    "Règles :\n"
    "- Choisis le thème DOMINANT du texte\n"
    "- Le sous-thème doit être en 2-4 mots en français\n"
    "- Si le texte n'est pas politique (mentions légales, navigation web, etc.), renvoie null\n\n"
    "Exemples :\n"
    '- "Nous construirons 500 logements sociaux HLM" → theme: logement, sub_theme: logement social\n'
    '- "Renforcement des effectifs de police municipale" → theme: securite, sub_theme: forces de l\'ordre\n'
    '- "Mentions légales - Tous droits réservés" → theme: null, sub_theme: null\n\n'
    "Texte à classifier :\n---\n{chunk_text}\n---"
)


_LLM_BATCH_PROMPT = (
    "Tu es un classificateur de thèmes politiques français. "
    "Classe chacun des textes suivants dans UN SEUL thème principal parmi cette taxonomie :\n\n"
    "| Thème | Description |\n"
    "|-------|-------------|\n"
    "| economie | Fiscalité, emploi, budget, dette, pouvoir d'achat, entreprises |\n"
    "| education | Écoles, universités, formation, petite enfance |\n"
    "| environnement | Climat, pollution, énergie, biodiversité, déchets |\n"
    "| sante | Hôpitaux, médecins, soins, prévention |\n"
    "| securite | Police, délinquance, vidéoprotection, violences |\n"
    "| immigration | Migrants, frontières, asile, intégration |\n"
    "| culture | Musées, théâtres, patrimoine, festivals |\n"
    "| logement | HLM, loyers, rénovation, construction |\n"
    "| transport | Vélo, métro, train, voiture, stationnement |\n"
    "| numerique | Internet, fibre, cybersécurité, IA |\n"
    "| agriculture | Agriculteurs, bio, circuits courts, PAC |\n"
    "| justice | Tribunaux, magistrats, prisons, médiation |\n"
    "| international | Europe, OTAN, diplomatie, défense |\n"
    "| institutions | Démocratie, élections, référendum, parlement, mairie |\n\n"
    "Règles :\n"
    "- Pour chaque texte, choisis le thème DOMINANT\n"
    "- Le sous-thème doit être en 2-4 mots en français\n"
    "- Si un texte n'est pas politique, renvoie theme=null et sub_theme=null\n"
    "- Renvoie EXACTEMENT une classification par texte, dans le même ordre\n\n"
    "Textes à classifier :\n{chunks_text}"
)

_BATCH_SIZE = 5  # chunks per LLM call — keeps total input under ~4K tokens


async def _llm_classify_batch(chunk_texts: list[str]) -> list[ThemeResult]:
    """Classify a batch of chunks in a single LLM call."""
    import os
    import time as _t
    _debug = os.getenv("DEBUG_INDEXER", "").lower() in ("1", "true", "yes")
    _ts = _t.monotonic()

    # Format numbered chunks
    numbered = []
    for i, text in enumerate(chunk_texts, 1):
        numbered.append(f"--- Texte {i} ---\n{text[:600]}\n")
    chunks_text = "\n".join(numbered)

    try:
        from langchain_core.messages import HumanMessage
        from src.llms import DETERMINISTIC_LLMS, get_structured_output_from_llms
        from src.models.structured_outputs import BatchChunkThemeClassification, ChunkThemeClassification

        prompt = _LLM_BATCH_PROMPT.format(chunks_text=chunks_text)
        messages = [HumanMessage(content=prompt)]
        result = await get_structured_output_from_llms(
            DETERMINISTIC_LLMS,
            messages,
            BatchChunkThemeClassification,
        )
        elapsed = _t.monotonic() - _ts

        if isinstance(result, BatchChunkThemeClassification):
            classifications = result.classifications
        elif isinstance(result, dict):
            classifications = [
                ChunkThemeClassification(**c) if isinstance(c, dict) else c
                for c in result.get("classifications", [])
            ]
        else:
            if _debug:
                logger.info(f"[DEBUG][LLM_BATCH] {elapsed:.2f}s → bad result type: {type(result).__name__}")
            return [ThemeResult(method="none") for _ in chunk_texts]

        # Validate and convert
        theme_results = []
        for i, c in enumerate(classifications):
            theme = c.theme
            sub_theme = c.sub_theme

            if theme and theme not in THEME_TAXONOMY:
                if _debug:
                    logger.info(f"[DEBUG][LLM_BATCH] item {i}: invalid theme '{theme}'")
                theme = None

            theme_results.append(ThemeResult(
                theme=theme,
                sub_theme=sub_theme,
                method="llm",
                confidence=1.0,
            ))

        # If LLM returned fewer results than chunks, pad with "none"
        while len(theme_results) < len(chunk_texts):
            theme_results.append(ThemeResult(method="none"))

        # If LLM returned more, truncate
        theme_results = theme_results[:len(chunk_texts)]

        if _debug:
            classified = sum(1 for r in theme_results if r.theme)
            logger.info(f"[DEBUG][LLM_BATCH] {elapsed:.2f}s → {classified}/{len(chunk_texts)} classified")

        return theme_results

    except Exception as e:
        elapsed = _t.monotonic() - _ts
        logger.warning(f"LLM batch classification failed after {elapsed:.2f}s: {e}")
        return [ThemeResult(method="none") for _ in chunk_texts]


async def _llm_classify_single(chunk_text: str) -> ThemeResult:
    """Classify a single chunk using LLM structured output."""
    import os
    import time as _t
    _debug = os.getenv("DEBUG_INDEXER", "").lower() in ("1", "true", "yes")
    _ts = _t.monotonic()
    try:
        from langchain_core.messages import HumanMessage
        from src.llms import DETERMINISTIC_LLMS, get_structured_output_from_llms
        from src.models.structured_outputs import ChunkThemeClassification

        prompt = _LLM_PROMPT.format(chunk_text=chunk_text[:800])
        messages = [HumanMessage(content=prompt)]
        result = await get_structured_output_from_llms(
            DETERMINISTIC_LLMS,
            messages,
            ChunkThemeClassification,
        )
        elapsed = _t.monotonic() - _ts

        if isinstance(result, ChunkThemeClassification):
            theme = result.theme
            sub_theme = result.sub_theme
        elif isinstance(result, dict):
            theme = result.get("theme")
            sub_theme = result.get("sub_theme")
        else:
            if _debug:
                logger.info(f"[DEBUG][LLM_CLASSIFY] {elapsed:.2f}s → none (bad result type: {type(result).__name__})")
            return ThemeResult(method="none")

        # Validate theme is in taxonomy
        if theme and theme not in THEME_TAXONOMY:
            if _debug:
                logger.info(f"[DEBUG][LLM_CLASSIFY] {elapsed:.2f}s → invalid theme '{theme}' not in taxonomy")
            theme = None

        if _debug:
            logger.info(
                f"[DEBUG][LLM_CLASSIFY] {elapsed:.2f}s → theme={theme} sub={sub_theme} "
                f"input='{chunk_text[:100]}...'"
            )
        return ThemeResult(theme=theme, sub_theme=sub_theme, method="llm", confidence=1.0)

    except Exception as e:
        elapsed = _t.monotonic() - _ts
        logger.warning(f"LLM theme classification failed after {elapsed:.2f}s: {e}")
        return ThemeResult(method="none")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def classify_chunks(
    chunks: list[str],
    *,
    use_llm: bool = True,
    keyword_fast_path: bool = True,
    max_concurrent_llm: int = 10,
) -> list[ThemeResult]:
    """Classify a batch of chunks. LLM-primary with optional keyword fast-path.

    1. If keyword_fast_path=True, obvious chunks (3+ keyword hits, clear winner)
       skip the LLM call to save cost.
    2. All other chunks go to the LLM for classification.

    Args:
        chunks: Text chunks to classify.
        use_llm: If False, only use keyword classification (for testing).
        keyword_fast_path: If True, skip LLM for high-confidence keyword matches.
        max_concurrent_llm: Max concurrent LLM calls.

    Returns:
        List of ThemeResult, one per input chunk.
    """
    import os
    import time as _t
    _debug = os.getenv("DEBUG_INDEXER", "").lower() in ("1", "true", "yes")
    _t0 = _t.monotonic()

    results: list[ThemeResult] = [ThemeResult() for _ in chunks]
    llm_indices: list[int] = []

    # Step 1: keyword fast-path for obvious cases
    if keyword_fast_path:
        for i, chunk in enumerate(chunks):
            fast_result = _keyword_fast_path(chunk)
            if fast_result is not None:
                results[i] = fast_result
                if _debug:
                    scores = _keyword_scores(chunk)
                    logger.info(
                        f"[DEBUG][KEYWORD_HIT] chunk#{i} theme={fast_result.theme} "
                        f"conf={fast_result.confidence:.2f} scores={scores} "
                        f"text='{chunk[:100]}...'"
                    )
            else:
                llm_indices.append(i)
                if _debug:
                    scores = _keyword_scores(chunk)
                    logger.info(
                        f"[DEBUG][KEYWORD_MISS] chunk#{i} scores={scores} → sending to LLM "
                        f"text='{chunk[:100]}...'"
                    )
    else:
        llm_indices = list(range(len(chunks)))

    keyword_classified = len(chunks) - len(llm_indices)
    if keyword_classified > 0:
        logger.info(
            f"Keyword fast-path: {keyword_classified}/{len(chunks)} chunks "
            f"(high-confidence only)"
        )

    if not use_llm or not llm_indices:
        return results

    # Step 2: Batched LLM classification
    num_batches = (len(llm_indices) + _BATCH_SIZE - 1) // _BATCH_SIZE
    logger.info(
        f"LLM classification: {len(llm_indices)} chunks in {num_batches} batches "
        f"(batch_size={_BATCH_SIZE}, concurrency={max_concurrent_llm})..."
    )

    semaphore = asyncio.Semaphore(max_concurrent_llm)
    _llm_start = _t.monotonic()

    # Group into batches
    batches: list[list[int]] = []
    for i in range(0, len(llm_indices), _BATCH_SIZE):
        batches.append(llm_indices[i:i + _BATCH_SIZE])

    async def _bounded_batch(batch_indices: list[int]) -> list[ThemeResult]:
        async with semaphore:
            texts = [chunks[i] for i in batch_indices]
            return await _llm_classify_batch(texts)

    batch_tasks = [_bounded_batch(batch) for batch in batches]
    batch_results = await asyncio.gather(*batch_tasks)
    _llm_elapsed = _t.monotonic() - _llm_start

    # Map results back
    llm_classified_count = 0
    for batch_indices, batch_result in zip(batches, batch_results):
        for idx, result in zip(batch_indices, batch_result):
            results[idx] = result
            if result.theme is not None:
                llm_classified_count += 1

    total_classified = sum(1 for r in results if r.theme is not None)
    total_elapsed = _t.monotonic() - _t0
    logger.info(
        f"Theme classification complete: {total_classified}/{len(chunks)} "
        f"({keyword_classified} keyword, {llm_classified_count} LLM in {num_batches} batches) "
        f"total={total_elapsed:.1f}s llm={_llm_elapsed:.1f}s"
    )

    return results


def apply_themes_to_documents(
    documents: list,
    theme_results: list[ThemeResult],
) -> None:
    """Apply theme classification results to LangChain Documents in-place.

    Modifies document metadata to add theme and sub_theme fields.
    """
    for doc, result in zip(documents, theme_results, strict=True):
        if result.theme:
            doc.metadata["theme"] = result.theme
        if result.sub_theme:
            doc.metadata["sub_theme"] = result.sub_theme
