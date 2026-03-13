# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0

import logging
import os
from typing import AsyncIterator, List, Tuple, Dict, Union, Optional
from datetime import datetime
from urllib.parse import quote
from openai import AsyncOpenAI  # for API format

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.documents import Document
from langchain_core.messages import BaseMessageChunk

from openai.types.chat.chat_completion_message_param import (
    ChatCompletionSystemMessageParam,
    ChatCompletionUserMessageParam,
)

from src.models.general import LLM, LLMSize
from src.llms import (
    DETERMINISTIC_LLMS,
    NON_DETERMINISTIC_LLMS,
    get_answer_from_llms,
    get_structured_output_from_llms,
    stream_answer_from_llms,
)
from src.models.candidate import Candidate
from src.models.party import Party
from src.models.assistant import ASSISTANT_ID, CHATVOTE_ASSISTANT, Assistant
from src.models.vote import Vote, VotingResultsByParty
from src.utils import (
    build_document_string_for_context,
    build_message_from_perplexity_response,
    build_party_str,
    load_env,
)
from src.prompts import (
    # Type and default
    Locale,
    DEFAULT_LOCALE,
    # Direct imports (still needed for some functions)
    get_chat_answer_guidelines,
    perplexity_system_prompt,
    perplexity_user_prompt,
    perplexity_candidate_system_prompt,
    perplexity_candidate_user_prompt,
    generate_party_vote_behavior_summary_system_prompt,
    generate_party_vote_behavior_summary_user_prompt,
    system_prompt_improvement_rag_template_vote_behavior_summary,
    user_prompt_improvement_rag_template_vote_behavior_summary,
    generate_chatvote_title_and_quick_replies_system_prompt_str,
    # Templates used directly (default locale)
    reranking_system_prompt_template,
    reranking_user_prompt_template,
    determine_question_targets_system_prompt,
    determine_question_targets_user_prompt,
    determine_question_type_system_prompt,
    determine_question_type_user_prompt,
    system_prompt_improvement_template,
    system_prompt_improve_general_chat_rag_query_template,
    user_prompt_improvement_template,
    generate_chat_summary_system_prompt,
    generate_chat_summary_user_prompt,
    # Candidate-specific prompts (non-localized for now)
    get_candidate_chat_answer_guidelines,
    candidate_response_system_prompt_template,
    candidate_local_response_system_prompt_template,
    candidate_national_response_system_prompt_template,
    streaming_candidate_response_user_prompt_template,
    system_prompt_improvement_candidate_template,
    # Entity detection prompts
    detect_entities_system_prompt_template,
    detect_entities_user_prompt_template,
    get_combined_answer_guidelines,
    combined_response_system_prompt_template,
    streaming_combined_response_user_prompt_template,
    # Locale-aware getters
    get_party_response_system_prompt_template,
    get_party_comparison_system_prompt_template,
    get_streaming_party_response_user_prompt_template,
    get_chatvote_response_system_prompt_template,
    get_quick_reply_guidelines_for_locale,
    get_generate_chat_title_and_quick_replies_system_prompt,
    get_generate_chat_title_and_quick_replies_user_prompt,
    get_global_combined_answer_guidelines_for_locale,
    get_global_combined_response_system_prompt_template,
    get_streaming_combined_response_user_prompt_template,
)

from src.models.chat import Message
from src.models.structured_outputs import (
    PartyListGenerator,
    ChatSummaryGenerator,
    GroupChatTitleQuickReplyGenerator,
    QuestionTypeClassifier,
    RerankingOutput,
    EntityDetector,
)

load_env()

logger = logging.getLogger(__name__)

# Type for entities that can respond to questions (party or assistant)
Responder = Union[Party, Assistant]


chat_response_llms: list[LLM] = NON_DETERMINISTIC_LLMS

voting_behavior_summary_llms: list[LLM] = NON_DETERMINISTIC_LLMS

prompt_improvement_llms: list[LLM] = DETERMINISTIC_LLMS

generate_party_list_llms: list[LLM] = DETERMINISTIC_LLMS

generate_message_type_and_general_question_llms: list[LLM] = DETERMINISTIC_LLMS

generate_chat_summary_llms: list[LLM] = DETERMINISTIC_LLMS

generate_chat_title_and_quick_replies_llms: list[LLM] = DETERMINISTIC_LLMS

reranking_llms = DETERMINISTIC_LLMS

# Perplexity client (conditionally initialized)
_perplexity_api_key = os.getenv("PERPLEXITY_API_KEY")
perplexity_client = (
    AsyncOpenAI(api_key=_perplexity_api_key, base_url="https://api.perplexity.ai")
    if _perplexity_api_key
    else None
)

_VIEWER_BASE = "https://app.chatvote.org"


def _pdf_viewer_url(raw_url: str) -> str:
    """Wrap a PDF URL into the in-app viewer URL."""
    return f"{_VIEWER_BASE}/pdf/view?page=1&pdf={quote(raw_url, safe='')}"


async def rerank_documents(
    relevant_docs: List[Document], user_message: str, chat_history: str
) -> List[Document]:
    # get the context and the relevant documents
    docs = [
        build_document_string_for_context(index, doc, doc_num_label="Index")
        for index, doc in enumerate(relevant_docs)
    ]
    sources_str = "\n".join(docs)
    # build messages for the reranking model
    system_prompt = reranking_system_prompt_template.format(sources=sources_str)
    user_prompt = reranking_user_prompt_template.format(
        conversation_history=chat_history, user_message=user_message
    )
    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_prompt),
    ]
    # rerank the documents
    response = await get_structured_output_from_llms(
        reranking_llms, messages, RerankingOutput
    )

    # get the reranked document indices
    reranked_doc_indices = getattr(response, "reranked_doc_indices", [])
    logger.debug(f"Reranked document indices: {reranked_doc_indices}")
    try:
        # only take first 5 elements of relevant indices
        relevant_indices = reranked_doc_indices[:5]
        reranked_relevant_docs = [relevant_docs[i] for i in relevant_indices]
        logger.debug(f"Reranked document indices: {relevant_indices}")
        return reranked_relevant_docs
    except Exception as e:
        logger.error(f"Error extracting reranked documents: {e}")
        logger.warning("Returning top-5 of original relevant documents.")
        relevant_docs = relevant_docs[:5]
        return relevant_docs


async def get_question_targets_and_type(
    user_message: str,
    previous_chat_history: str,
    all_available_parties: List[Party],
    currently_selected_parties: List[Party],
) -> Tuple[List[str], str, bool]:
    """
    Determine which parties should respond to the user's message.

    Logic:
    - If exactly one party is selected (not chat-vote), route directly to that party
    - If multiple parties are selected, use LLM to determine if it's a comparison question
    - If no party selected (or only chat-vote), use LLM for general routing
    """
    # Filter out chat-vote from selected parties to get "real" parties
    real_selected_parties = [
        p for p in currently_selected_parties if p.party_id != ASSISTANT_ID
    ]

    # Case 1: Exactly one real party selected -> route directly to that party
    if len(real_selected_parties) == 1:
        selected_party_id = real_selected_parties[0].party_id
        logger.info(f"Single party selected - routing directly to: {selected_party_id}")
        return ([selected_party_id], user_message, False)

    # Case 2: Multiple real parties selected -> need LLM to determine comparison vs individual
    # Case 3: No real party selected -> need LLM for general routing

    is_assistant_only_chat = len(real_selected_parties) == 0

    user_message_for_target_selection = user_message
    if previous_chat_history == "":
        if is_assistant_only_chat:
            previous_chat_history = f"Chat avec {CHATVOTE_ASSISTANT.name} démarré.\n"
        else:
            previous_chat_history = f"Chat avec {', '.join([party.name for party in currently_selected_parties])} démarré.\n"
            user_message_for_target_selection = f"@{', '.join([party.name for party in currently_selected_parties])}: {user_message}"

    currently_selected_parties_str = ""
    for party in currently_selected_parties:
        currently_selected_parties_str += build_party_str(party)

    additionally_available_parties = [
        party
        for party in all_available_parties
        if party not in currently_selected_parties
    ]
    additional_party_list_str = ""
    big_additional_parties = [
        party for party in additionally_available_parties if not party.is_small_party
    ]
    small_additional_parties = [
        party for party in additionally_available_parties if party.is_small_party
    ]

    additional_party_list_str += "Grandes listes:\n"
    for party in big_additional_parties:
        additional_party_list_str += build_party_str(party)
    additional_party_list_str += "Petites listes:\n"
    for party in small_additional_parties:
        additional_party_list_str += build_party_str(party)

    system_prompt = determine_question_targets_system_prompt.format(
        current_party_list=currently_selected_parties_str,
        additional_party_list=additional_party_list_str,
    )
    user_prompt = determine_question_targets_user_prompt.format(
        previous_chat_history=previous_chat_history,
        user_message=user_message_for_target_selection,
    )
    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_prompt),
    ]

    response_targets = await get_structured_output_from_llms(
        generate_party_list_llms, messages, PartyListGenerator
    )

    party_id_list = getattr(response_targets, "party_id_list", [])
    logger.debug(f"LLM returned party ID list: {party_id_list}")
    party_id_list = [
        str(party_id) for party_id in party_id_list
    ]  # make sure all party IDs are represented as strings (and not enums)
    # Make sure the party_id_list contains no duplicates
    party_id_list = list(set(party_id_list))

    if len(party_id_list) >= 2:
        # Filter out "chat-vote" party from the list of selected parties
        party_id_list = [
            party_id for party_id in party_id_list if party_id != ASSISTANT_ID
        ]

    # create a prompt for the question type model
    if len(party_id_list) >= 2:
        system_prompt = determine_question_type_system_prompt.format()
        user_prompt = determine_question_type_user_prompt.format(
            previous_chat_history=previous_chat_history,
            user_message=f'Utilisateur: "{user_message_for_target_selection}"',
        )

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ]

        response_question_type = await get_structured_output_from_llms(
            generate_message_type_and_general_question_llms,
            messages,
            QuestionTypeClassifier,
        )

        question_for_parties = getattr(
            response_question_type, "non_party_specific_question", user_message
        )
        is_comparing_question = getattr(
            response_question_type, "is_comparing_question", False
        )
    else:
        question_for_parties = user_message
        is_comparing_question = False

    return (party_id_list, question_for_parties, is_comparing_question)


async def detect_entities_and_route(
    user_message: str,
    conversation_history: str,
    all_parties: List[Party],
    all_candidates: List[Candidate],
    scope: str,
    municipality_code: str | None = None,
) -> EntityDetector:
    """
    Detect parties and candidates mentioned in the user message.

    Returns an EntityDetector with:
    - party_ids: List of detected party IDs
    - candidate_ids: List of detected candidate IDs
    - needs_clarification: True if user should specify a party/candidate
    - clarification_message: Message to show if clarification needed
    - reformulated_question: The question reformulated for general use
    """
    # Build parties list string
    parties_list = "Partis disponibles :\n"
    for party in all_parties:
        parties_list += f"- ID: {party.party_id}, Nom: {party.name}, Nom complet: {party.long_name}\n"

    # Build candidates list string (filtered by scope if local)
    candidates_list = "Candidats disponibles :\n"
    filtered_candidates = all_candidates
    if scope == "local" and municipality_code is not None:
        filtered_candidates = [
            c for c in all_candidates if c.municipality_code == municipality_code
        ]

    for candidate in filtered_candidates:
        party_names = (
            ", ".join(candidate.party_ids) if candidate.party_ids else "Indépendant"
        )
        municipality = candidate.municipality_name or "National"
        candidates_list += f"- ID: {candidate.candidate_id}, Nom: {candidate.full_name}, Commune: {municipality}, Partis: {party_names}\n"

    if not filtered_candidates:
        candidates_list += "(Aucun candidat disponible pour ce scope)\n"

    # Build scope info
    if scope == "local" and municipality_code is not None:
        scope_info = f"Scope LOCAL - Commune code INSEE: {municipality_code}. Seuls les candidats de cette commune sont disponibles."
    else:
        scope_info = "Scope NATIONAL - Tous les partis et candidats sont disponibles."

    system_prompt = detect_entities_system_prompt_template.format(
        parties_list=parties_list,
        candidates_list=candidates_list,
        scope_info=scope_info,
    )
    user_prompt = detect_entities_user_prompt_template.format(
        conversation_history=conversation_history,
        user_message=user_message,
    )

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_prompt),
    ]

    response = await get_structured_output_from_llms(
        generate_party_list_llms, messages, EntityDetector
    )

    # Validate and clean up the response
    party_ids = getattr(response, "party_ids", [])
    candidate_ids = getattr(response, "candidate_ids", [])
    needs_clarification = getattr(response, "needs_clarification", False)
    clarification_message = getattr(response, "clarification_message", "")
    reformulated_question = getattr(response, "reformulated_question", user_message)

    # Validate party_ids exist
    valid_party_ids = [p.party_id for p in all_parties]
    party_ids = [pid for pid in party_ids if pid in valid_party_ids]

    # Validate candidate_ids exist (considering scope)
    valid_candidate_ids = [c.candidate_id for c in filtered_candidates]
    candidate_ids = [cid for cid in candidate_ids if cid in valid_candidate_ids]

    # If we found party_ids from candidate affiliations, add them
    for cid in candidate_ids:
        matching_candidate = next(
            (c for c in filtered_candidates if c.candidate_id == cid), None
        )
        if matching_candidate is not None:
            for pid in matching_candidate.party_ids:
                if pid not in party_ids and pid in valid_party_ids:
                    party_ids.append(pid)

    # Check if user is asking about ALL parties or candidates
    # Keywords indicating user wants all parties (not just one specific party)
    user_msg_lower = user_message.lower()
    all_parties_keywords = [
        "tous les partis",
        "les partis",
        "différents partis",
        "les différents partis",
        "chaque parti",
        "comparer les partis",
        "comparatif",
        "partis politiques",
        "programmes des partis",
        "par les différents",
        "proposé par les",
    ]
    all_candidates_keywords = [
        "tous les candidats",
        "les candidats",
        "différents candidats",
        "les différents candidats",
        "chaque candidat",
        "comparer les candidats",
    ]

    # If user asks about all parties, ALWAYS include all parties (override LLM detection)
    if any(kw in user_msg_lower for kw in all_parties_keywords):
        party_ids = valid_party_ids
        needs_clarification = False
        clarification_message = ""
        logger.info(
            f"User asked about all parties, including all {len(party_ids)} parties"
        )

    # If user asks about all candidates, don't require clarification
    if any(kw in user_msg_lower for kw in all_candidates_keywords):
        needs_clarification = False
        clarification_message = ""
        logger.info("User asked about all candidates, no clarification needed")

    # Override needs_clarification if we found entities
    if party_ids or candidate_ids:
        needs_clarification = False
        clarification_message = ""

    return EntityDetector(
        party_ids=party_ids,
        candidate_ids=candidate_ids,
        needs_clarification=needs_clarification,
        clarification_message=clarification_message,
        reformulated_question=reformulated_question,
    )


async def generate_improvement_rag_query(
    responder: Responder, conversation_history: str, last_user_message: str
) -> str:
    if responder.party_id == ASSISTANT_ID:
        system_prompt = system_prompt_improve_general_chat_rag_query_template.format()
    else:
        system_prompt = system_prompt_improvement_template.format(
            party_name=responder.name
        )
    user_prompt = user_prompt_improvement_template.format(
        conversation_history=conversation_history,
        last_user_message=last_user_message,
    )

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_prompt),
    ]

    response = await get_answer_from_llms(prompt_improvement_llms, messages)

    if isinstance(response.content, list):
        if isinstance(response.content[0], str):
            return response.content[0]
        else:
            return response.content[0]["content"]
    return response.content


async def generate_pro_con_perspective(
    chat_history: List[Message], party: Party
) -> Message:
    # from a list of Message elements, extract the last assistant and user message by checking the role
    last_assistant_message = next(
        (message for message in chat_history[::-1] if message.role == "assistant"), None
    )
    last_user_message = next(
        (message for message in chat_history[::-1] if message.role == "user"), None
    )

    system_prompt = perplexity_system_prompt.format(
        party_name=party.name,
        party_long_name=party.long_name,
        party_description=party.description,
        party_candidate=party.candidate,
    )
    user_prompt = perplexity_user_prompt.format(
        assistant_message=last_assistant_message.content
        if last_assistant_message
        else "",
        user_message=last_user_message.content if last_user_message else "",
        party_name=party.name,
    )

    # Prepare messages with explicit roles
    messages: list[
        ChatCompletionSystemMessageParam | ChatCompletionUserMessageParam
    ] = [
        ChatCompletionSystemMessageParam(role="system", content=system_prompt),
        ChatCompletionUserMessageParam(role="user", content=user_prompt),
    ]

    # Check if Perplexity is available
    if perplexity_client is None:
        raise Exception(
            "Perplexity API key not configured. Set PERPLEXITY_API_KEY environment variable."
        )

    # chat completion without streaming
    response = await perplexity_client.chat.completions.create(
        model="sonar",
        messages=messages,
    )

    return build_message_from_perplexity_response(response)


async def generate_pro_con_perspective_candidate(
    chat_history: List[Message],
    candidate: Candidate,
    all_parties: List[Party],
) -> Message:
    """
    Generate a pro/con perspective for a candidate's response using Perplexity.

    This function takes the chat history with a candidate and generates an external
    critical evaluation using Perplexity's search capabilities. The evaluation
    focuses on the feasibility and impact of the candidate's proposals at the
    municipal level.

    Args:
        chat_history: List of messages from the conversation with the candidate.
        candidate: The Candidate object for which to generate the perspective.
        all_parties: List of all parties to resolve party names from party_ids.

    Returns:
        Message: The pro/con perspective message with citations.

    Raises:
        Exception: If Perplexity API key is not configured.
    """
    # Extract the last assistant and user message from the chat history
    last_assistant_message = next(
        (message for message in chat_history[::-1] if message.role == "assistant"),
        None,
    )
    last_user_message = next(
        (message for message in chat_history[::-1] if message.role == "user"), None
    )

    # Resolve party names from party_ids
    party_names = []
    for party_id in candidate.party_ids:
        party = next((p for p in all_parties if p.party_id == party_id), None)
        if party is not None:
            party_names.append(party.name)
    party_names_str = ", ".join(party_names) if party_names else "Indépendant"

    municipality_name = candidate.municipality_name or "France"
    position = candidate.position or "Candidat(e)"

    system_prompt = perplexity_candidate_system_prompt.format(
        candidate_name=candidate.full_name,
        municipality_name=municipality_name,
        party_names=party_names_str,
        position=position,
    )
    user_prompt = perplexity_candidate_user_prompt.format(
        assistant_message=last_assistant_message.content
        if last_assistant_message
        else "",
        user_message=last_user_message.content if last_user_message else "",
        candidate_name=candidate.full_name,
        municipality_name=municipality_name,
        party_names=party_names_str,
    )

    # Prepare messages with explicit roles
    messages: list[
        ChatCompletionSystemMessageParam | ChatCompletionUserMessageParam
    ] = [
        ChatCompletionSystemMessageParam(role="system", content=system_prompt),
        ChatCompletionUserMessageParam(role="user", content=user_prompt),
    ]

    # Check if Perplexity is available
    if perplexity_client is None:
        raise Exception(
            "Perplexity API key not configured. Set PERPLEXITY_API_KEY environment variable."
        )

    # Chat completion without streaming
    response = await perplexity_client.chat.completions.create(
        model="sonar",
        messages=messages,
    )

    return build_message_from_perplexity_response(response)


async def generate_chat_summary(chat_history: list[Message]) -> str:
    # create a list of messages from the chat history, user messages as "Utilisateur: " and assistant messages use the party_id as role
    conversation_history = []
    for message in chat_history:
        if message.role == "user":
            conversation_history.append(
                {"role": "Utilisateur", "content": message.content}
            )
        else:
            conversation_history.append(
                {"role": message.party_id or "", "content": message.content}
            )

    system_prompt = generate_chat_summary_system_prompt.format()
    user_prompt = generate_chat_summary_user_prompt.format(
        conversation_history=conversation_history
    )

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_prompt),
    ]

    response = await get_structured_output_from_llms(
        generate_chat_summary_llms, messages, ChatSummaryGenerator
    )

    return getattr(response, "chat_summary", "Un résumé devrait apparaître ici.")


def get_rag_context(relevant_docs: List[Document]) -> str:
    rag_context = ""
    for doc_num, doc in enumerate(relevant_docs):
        context_obj = build_document_string_for_context(doc_num, doc)
        rag_context += context_obj
    if rag_context == "":
        rag_context = (
            "Aucune information pertinente trouvée dans la collection de documents."
        )
    return rag_context


def get_rag_comparison_context(
    relevant_docs: Dict[str, List[Document]], relevant_parties: List[Party]
) -> str:
    rag_context = ""
    doc_num = 0
    for party in relevant_parties:
        rag_context += f"\n\nInformations de {party.name}:\n"
        for doc in relevant_docs[party.party_id]:
            context_obj = f"""- ID: {doc_num}
- Nom du document: {doc.metadata.get("document_name", "inconnu")}
- Liste: {party.name}
- Date de publication: {doc.metadata.get("document_publish_date", "inconnu")}
- Contenu: "{doc.page_content}"

"""
            doc_num += 1
            rag_context += context_obj
    if rag_context == "":
        rag_context = (
            "Aucune information pertinente trouvée dans la collection de documents."
        )
    return rag_context


async def get_improved_rag_query_voting_behavior(
    party: Party, last_user_message: str, last_assistant_message: str
) -> str:
    system_prompt = system_prompt_improvement_rag_template_vote_behavior_summary.format(
        party_name=party.name
    )
    user_prompt = user_prompt_improvement_rag_template_vote_behavior_summary.format(
        last_user_message=last_user_message,
        last_assistant_message=last_assistant_message,
        party_name=party.name,
    )

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_prompt),
    ]

    response = await get_answer_from_llms(prompt_improvement_llms, messages)

    return getattr(response, "content", "")


async def generate_streaming_chatbot_response(
    responder: Responder,
    conversation_history: str,
    user_message: str,
    relevant_docs: List[Document],
    all_parties: list[Party],
    chat_response_llm_size: LLMSize,
    use_premium_llms: bool = False,
    locale: Locale = DEFAULT_LOCALE,
) -> AsyncIterator[BaseMessageChunk]:
    rag_context = get_rag_context(relevant_docs)

    now = datetime.now()

    answer_guidelines = get_chat_answer_guidelines(
        responder.name, is_comparing=False, locale=locale
    )

    if responder.party_id == ASSISTANT_ID:
        all_parties_list = ""
        for party in all_parties:
            all_parties_list += f"### {party.long_name}\n"
            all_parties_list += (
                f"Short name: {party.name}\n"
                if locale == "en"
                else f"Nom court: {party.name}\n"
            )
            all_parties_list += f"Description: {party}\n"
            all_parties_list += (
                f"Party leader: {party.candidate}\n"
                if locale == "en"
                else f"Tête de liste: {party.candidate}\n"
            )
        system_prompt = get_chatvote_response_system_prompt_template(locale).format(
            all_parties_list=all_parties_list,
            date=now.strftime("%Y-%m-%d"),
            time=now.strftime("%H:%M"),
            rag_context=rag_context,
        )
    else:
        # It's a party (not the assistant)
        assert isinstance(responder, Party)
        system_prompt = get_party_response_system_prompt_template(locale).format(
            party_name=responder.name,
            party_long_name=responder.long_name,
            party_description=responder.description,
            party_url=responder.website_url,
            party_candidate=responder.candidate,
            date=now.strftime("%Y-%m-%d"),
            time=now.strftime("%H:%M"),
            rag_context=rag_context,
            answer_guidelines=answer_guidelines,
        )

    user_prompt = get_streaming_party_response_user_prompt_template(locale).format(
        conversation_history=conversation_history,
        last_user_message=user_message,
    )

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_prompt),
    ]

    return await stream_answer_from_llms(
        chat_response_llms,
        messages,
        preferred_llm_size=chat_response_llm_size,
        use_premium_llms=use_premium_llms,
    )


async def generate_streaming_chatbot_comparing_response(
    conversation_history: str,
    user_message: str,
    relevant_docs: Dict[str, List[Document]],
    relevant_parties: List[Party],
    chat_response_llm_size: LLMSize,
    use_premium_llms: bool = False,
    locale: Locale = DEFAULT_LOCALE,
) -> AsyncIterator[BaseMessageChunk]:
    """Generate a comparison response between multiple parties.

    The ChatVote assistant always responds to comparison questions.
    """
    rag_context = get_rag_comparison_context(relevant_docs, relevant_parties)

    now = datetime.now()

    answer_guidelines = get_chat_answer_guidelines(
        CHATVOTE_ASSISTANT.name, is_comparing=True, locale=locale
    )

    parties_being_compared = [party.name for party in relevant_parties]

    system_prompt = get_party_comparison_system_prompt_template(locale).format(
        party_name=CHATVOTE_ASSISTANT.name,
        party_long_name=CHATVOTE_ASSISTANT.long_name,
        party_description=CHATVOTE_ASSISTANT.description,
        party_url=CHATVOTE_ASSISTANT.website_url,
        party_candidate=CHATVOTE_ASSISTANT.name,  # Assistant has no candidate
        date=now.strftime("%Y-%m-%d"),
        time=now.strftime("%H:%M"),
        rag_context=rag_context,
        answer_guidelines=answer_guidelines,
        parties_being_compared=parties_being_compared,
    )

    user_prompt = get_streaming_party_response_user_prompt_template(locale).format(
        conversation_history=conversation_history,
        last_user_message=user_message,
    )

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_prompt),
    ]

    return await stream_answer_from_llms(
        chat_response_llms,
        messages,
        preferred_llm_size=chat_response_llm_size,
        use_premium_llms=use_premium_llms,
    )


async def generate_chat_title_and_chick_replies(
    chat_history_str: str,
    chat_title: str,
    parties_in_chat: List[Party],
    chatvote_assistant_last_responded: bool = False,
    is_comparing: bool = False,
    locale: Locale = DEFAULT_LOCALE,
) -> GroupChatTitleQuickReplyGenerator:
    # filter chat-vote party out of the list of parties
    parties_in_chat = [
        party for party in parties_in_chat if party.party_id != ASSISTANT_ID
    ]
    party_list = ""
    for party in parties_in_chat:
        party_list += f"- {party.name} ({party.long_name}): {party.description}\n"
    if party_list == "":
        party_list = (
            "No party is in this chat yet."
            if locale == "en"
            else "Aucune liste n'est encore dans ce chat."
        )
    if chatvote_assistant_last_responded:
        system_prompt = (
            generate_chatvote_title_and_quick_replies_system_prompt_str.format(
                party_list=party_list,
                quick_reply_guidelines=get_quick_reply_guidelines_for_locale(
                    is_comparing=is_comparing, locale=locale
                ),
            )
        )
    else:
        system_prompt = get_generate_chat_title_and_quick_replies_system_prompt(
            locale
        ).format(party_list=party_list)

    user_prompt = get_generate_chat_title_and_quick_replies_user_prompt(locale).format(
        current_chat_title=chat_title,
        conversation_history=chat_history_str,
    )
    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_prompt),
    ]

    response = await get_structured_output_from_llms(
        generate_chat_title_and_quick_replies_llms,
        messages,
        GroupChatTitleQuickReplyGenerator,
    )
    return GroupChatTitleQuickReplyGenerator(
        chat_title=getattr(response, "chat_title", ""),
        quick_replies=getattr(response, "quick_replies", []),
    )


async def generate_party_vote_behavior_summary(
    party: Party,
    last_user_message: str,
    last_assistant_message: str,
    votes: List[Vote],
    summary_llm_size: LLMSize,
    use_premium_llms: bool = False,
) -> AsyncIterator[BaseMessageChunk]:
    votes_list = ""
    # sort votes by date (oldest first)
    votes.sort(key=lambda x: x.date)
    for vote in votes:
        submitting_parties: str = "non spécifié"
        if vote.submitting_parties is not None:
            submitting_parties = ", ".join(vote.submitting_parties)

        party_results = [
            party_vote
            for party_vote in vote.voting_results.by_party
            if party_vote.party == party.party_id
        ]
        if not party_results:
            continue

        party_result = party_results[0]

        votes_list += _format_vote_summary(
            vote,
            (vote.short_description or "Aucun résumé fourni.")
            .replace("\n", " ")
            .strip(),
            party_result,
            submitting_parties,
            party.name,
        )

    if votes_list == "":
        votes_list = "Aucun vote correspondant trouvé."

    system_prompt = generate_party_vote_behavior_summary_system_prompt.format(
        party_name=party.name,
        party_long_name=party.long_name,
        votes_list=votes_list,
    )
    user_prompt = generate_party_vote_behavior_summary_user_prompt.format(
        user_message=last_user_message,
        assistant_message=last_assistant_message,
        party_name=party.name,
    )

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_prompt),
    ]

    return await stream_answer_from_llms(
        voting_behavior_summary_llms,
        messages,
        preferred_llm_size=summary_llm_size,
        use_premium_llms=use_premium_llms,
    )


def _format_vote_summary(
    vote: Vote,
    description: str,
    party_result: VotingResultsByParty,
    submitting_parties: str,
    party_name: str,
) -> str:
    return f"""
# Vote {vote.id}
- Date: {vote.date}
- Sujet: {vote.title}
- Résumé: {description}
- Listes à l'origine: {submitting_parties}
- Résultats:
    - Global:
        - Pour: {vote.voting_results.overall.yes}
        - Contre: {vote.voting_results.overall.no}
        - Abstentions: {vote.voting_results.overall.abstain}
        - N'a pas voté: {vote.voting_results.overall.not_voted}
        - Nombre total de membres: {vote.voting_results.overall.members}
    - Comportement de vote de la liste {party_name}:
        - Pour: {party_result.yes}
        - Contre: {party_result.no}
        - Abstentions: {party_result.abstain}
        - N'a pas voté: {party_result.not_voted}
        - Justification: {party_result.justification if party_result.justification else "Aucune justification fournie."}\n\n
"""


# ==================== Candidate-specific Functions ====================


def get_rag_context_for_candidates(relevant_docs: List[Document]) -> str:
    """Build RAG context from candidate website documents."""
    rag_context = ""
    for doc_num, doc in enumerate(relevant_docs):
        candidate_name = doc.metadata.get("candidate_name", "Inconnu")
        municipality = doc.metadata.get("municipality_name", "")
        page_type = doc.metadata.get("page_type", "page")

        context_obj = f"""- ID: {doc_num}
- Candidat(e): {candidate_name}
- Commune: {municipality}
- Source: {doc.metadata.get("document_name", "Site web")} ({page_type})
- URL: {doc.metadata.get("url", "non spécifié")}
- Contenu: "{doc.page_content}"

"""
        rag_context += context_obj

    if rag_context == "":
        rag_context = (
            "Aucune information pertinente trouvée sur les sites web des candidats."
        )

    return rag_context


async def generate_improvement_rag_query_candidate(
    conversation_history: str,
    last_user_message: str,
    municipality_code: str | None = None,
) -> str:
    """Generate an improved RAG query for candidate document search."""
    if municipality_code is not None:
        scope_context = f"Le Vector Store contient des documents de sites web de candidats de la commune (code INSEE: {municipality_code}). Limite ta requête aux candidats de cette commune."
    else:
        scope_context = "Le Vector Store contient des documents de sites web de candidats de toutes les communes de France. Tu peux rechercher des candidats de n'importe quelle commune."

    system_prompt = system_prompt_improvement_candidate_template.format(
        scope_context=scope_context
    )
    user_prompt = user_prompt_improvement_template.format(
        conversation_history=conversation_history,
        last_user_message=last_user_message,
    )

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_prompt),
    ]

    response = await get_answer_from_llms(prompt_improvement_llms, messages)

    if isinstance(response.content, list):
        if isinstance(response.content[0], str):
            return response.content[0]
        else:
            return response.content[0]["content"]
    return response.content


async def generate_streaming_candidate_response(
    candidate: Candidate,
    conversation_history: str,
    user_message: str,
    relevant_docs: List[Document],
    all_parties: List[Party],
    chat_response_llm_size: LLMSize,
    use_premium_llms: bool = False,
) -> AsyncIterator[BaseMessageChunk]:
    """Generate a streaming response for a single candidate."""
    rag_context = get_rag_context_for_candidates(relevant_docs)
    now = datetime.now()

    answer_guidelines = get_candidate_chat_answer_guidelines(
        candidate.full_name, is_comparing=False
    )

    # Get party names for the candidate
    party_names = []
    for party_id in candidate.party_ids:
        party = next((p for p in all_parties if p.party_id == party_id), None)
        if party is not None:
            party_names.append(party.name)
    party_names_str = ", ".join(party_names) if party_names else "Indépendant"

    system_prompt = candidate_response_system_prompt_template.format(
        candidate_name=candidate.full_name,
        municipality_name=candidate.municipality_name or "France",
        party_names=party_names_str,
        position=candidate.position or "Candidat(e)",
        website_url=candidate.website_url or "Non spécifié",
        date=now.strftime("%Y-%m-%d"),
        time=now.strftime("%H:%M"),
        rag_context=rag_context,
        answer_guidelines=answer_guidelines,
    )

    user_prompt = streaming_candidate_response_user_prompt_template.format(
        conversation_history=conversation_history,
        last_user_message=user_message,
    )

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_prompt),
    ]

    return await stream_answer_from_llms(
        chat_response_llms,
        messages,
        preferred_llm_size=chat_response_llm_size,
        use_premium_llms=use_premium_llms,
    )


async def generate_streaming_candidate_local_response(
    municipality_code: str,
    municipality_name: str,
    candidates: List[Candidate],
    conversation_history: str,
    user_message: str,
    relevant_docs: List[Document],
    all_parties: List[Party],
    chat_response_llm_size: LLMSize,
    use_premium_llms: bool = False,
) -> AsyncIterator[BaseMessageChunk]:
    """Generate a streaming response for candidates in a specific municipality (local scope)."""
    rag_context = get_rag_context_for_candidates(relevant_docs)
    now = datetime.now()

    # Build candidates list string
    candidates_list = ""
    for c in candidates:
        party_names = []
        for party_id in c.party_ids:
            party = next((p for p in all_parties if p.party_id == party_id), None)
            if party is not None:
                party_names.append(party.name)
        party_str = ", ".join(party_names) if party_names else "Indépendant"
        website_part = f" - Site web : {c.website_url}" if c.website_url else ""
        manifesto = f" - [Profession de foi]({_pdf_viewer_url(c.manifesto_pdf_url)})" if c.has_manifesto and c.manifesto_pdf_url else ""
        candidates_list += f"- **{c.full_name}** ({party_str}){website_part}{manifesto}\n"

    if not candidates_list:
        candidates_list = "Aucun candidat enregistré pour cette commune."

    system_prompt = candidate_local_response_system_prompt_template.format(
        municipality_name=municipality_name,
        municipality_code=municipality_code,
        candidates_list=candidates_list,
        date=now.strftime("%Y-%m-%d"),
        time=now.strftime("%H:%M"),
        rag_context=rag_context,
    )

    user_prompt = streaming_candidate_response_user_prompt_template.format(
        conversation_history=conversation_history,
        last_user_message=user_message,
    )

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_prompt),
    ]

    return await stream_answer_from_llms(
        chat_response_llms,
        messages,
        preferred_llm_size=chat_response_llm_size,
        use_premium_llms=use_premium_llms,
    )


async def generate_streaming_candidate_national_response(
    conversation_history: str,
    user_message: str,
    relevant_docs: List[Document],
    chat_response_llm_size: LLMSize,
    use_premium_llms: bool = False,
) -> AsyncIterator[BaseMessageChunk]:
    """Generate a streaming response for candidates at national level."""
    rag_context = get_rag_context_for_candidates(relevant_docs)
    now = datetime.now()

    system_prompt = candidate_national_response_system_prompt_template.format(
        date=now.strftime("%Y-%m-%d"),
        time=now.strftime("%H:%M"),
        rag_context=rag_context,
    )

    user_prompt = streaming_candidate_response_user_prompt_template.format(
        conversation_history=conversation_history,
        last_user_message=user_message,
    )

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_prompt),
    ]

    return await stream_answer_from_llms(
        chat_response_llms,
        messages,
        preferred_llm_size=chat_response_llm_size,
        use_premium_llms=use_premium_llms,
    )


# ==================== Combined Response Functions ====================


def get_combined_rag_context(
    manifesto_docs: List[Document],
    candidate_docs: List[Document],
) -> Tuple[str, str]:
    """
    Build RAG context from both manifesto and candidate website documents.

    Uses unified numbering (0, 1, 2...) across all sources for consistent citation matching.
    Manifesto docs come first (0 to len(manifesto_docs)-1), then candidate docs continue the numbering.

    Returns a tuple of (manifesto_context, candidates_context).
    """
    # Build manifesto context with unified numbering starting at 0
    manifesto_context = ""
    for doc_num, doc in enumerate(manifesto_docs):
        party_id = doc.metadata.get("namespace", "")
        source_url = doc.metadata.get("url", "non spécifié")
        context_obj = f"""- ID: {doc_num}
- Type: Programme officiel
- Parti: {party_id}
- URL: {source_url}
- Contenu: "{doc.page_content}"

"""
        manifesto_context += context_obj

    if manifesto_context == "":
        manifesto_context = "Aucune information trouvée dans les programmes officiels."

    # Build candidates context - continue numbering from where manifesto left off
    candidates_context = ""
    start_index = len(manifesto_docs)
    for doc_num, doc in enumerate(candidate_docs):
        unified_id = start_index + doc_num
        candidate_name = doc.metadata.get("candidate_name", "Inconnu")
        municipality = doc.metadata.get("municipality_name", "")
        page_type = doc.metadata.get("page_type", "page")
        party_ids = doc.metadata.get("party_ids", [])
        party_str = ", ".join(party_ids) if party_ids else "Non affilié"

        context_obj = f"""- ID: {unified_id}
- Type: Site web candidat
- Candidat(e): {candidate_name}
- Parti(s): {party_str}
- Commune: {municipality}
- Source: {doc.metadata.get("document_name", "Site web")} ({page_type})
- URL: {doc.metadata.get("url", "non spécifié")}
- Contenu: "{doc.page_content}"

"""
        candidates_context += context_obj

    if candidates_context == "":
        candidates_context = (
            "Aucune information trouvée sur les sites web des candidats."
        )

    return (manifesto_context, candidates_context)


async def generate_streaming_combined_response(
    party: Party,
    conversation_history: str,
    user_message: str,
    manifesto_docs: List[Document],
    candidate_docs: List[Document],
    scope: str,
    municipality_name: str = "",
    chat_response_llm_size: LLMSize = LLMSize.LARGE,
    use_premium_llms: bool = False,
) -> AsyncIterator[BaseMessageChunk]:
    """
    Generate a streaming response combining manifesto and candidate website information.

    Args:
        party: The primary party being discussed
        conversation_history: Previous chat messages
        user_message: Current user question
        manifesto_docs: Documents from party manifesto
        candidate_docs: Documents from candidate websites
        scope: 'national' or 'local'
        municipality_name: Name of the municipality (for local scope)
        chat_response_llm_size: LLM size preference
        use_premium_llms: Whether to use premium models
    """
    now = datetime.now()

    manifesto_context, candidates_context = get_combined_rag_context(
        manifesto_docs, candidate_docs
    )

    answer_guidelines = get_combined_answer_guidelines(scope, municipality_name)

    # Build scope description
    if scope == "local" and municipality_name:
        scope_description = f"Niveau LOCAL - Commune de {municipality_name}. Tu réponds sur les propositions du parti {party.name} et de ses candidats dans cette commune."
    else:
        scope_description = f"Niveau NATIONAL - Tu réponds sur les propositions du parti {party.name} et de l'ensemble de ses candidats en France."

    system_prompt = combined_response_system_prompt_template.format(
        party_name=party.name,
        party_description=party.long_name or party.name,
        party_url=party.website_url or "Non spécifié",
        scope_description=scope_description,
        date=now.strftime("%Y-%m-%d"),
        time=now.strftime("%H:%M"),
        manifesto_context=manifesto_context,
        candidates_context=candidates_context,
        answer_guidelines=answer_guidelines,
    )

    user_prompt = streaming_combined_response_user_prompt_template.format(
        conversation_history=conversation_history,
        last_user_message=user_message,
    )

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_prompt),
    ]

    return await stream_answer_from_llms(
        chat_response_llms,
        messages,
        preferred_llm_size=chat_response_llm_size,
        use_premium_llms=use_premium_llms,
    )


async def generate_streaming_global_combined_response(
    conversation_history: str,
    user_message: str,
    manifesto_docs: List[Document],
    candidate_docs: List[Document],
    all_parties: List[Party],
    scope: str,
    municipality_name: str = "",
    local_candidates: Optional[List[Candidate]] = None,
    chat_response_llm_size: LLMSize = LLMSize.LARGE,
    use_premium_llms: bool = False,
    is_single_party_focus: bool = False,
    locale: Locale = DEFAULT_LOCALE,
    selected_electoral_lists: Optional[List[dict]] = None,
) -> AsyncIterator[BaseMessageChunk]:
    """
    Generate a streaming response combining information from parties and candidates.

    This is the main function for the combined search approach:
    - SINGLE PARTY: Focuses on one specific party's manifesto + affiliated candidates
    - NATIONAL: Uses manifesto data from ALL parties + candidate data from ALL candidates
    - LOCAL: Uses manifesto data from parties present in the municipality + candidate data

    Args:
        conversation_history: Previous chat messages
        user_message: Current user question
        manifesto_docs: Documents from party manifestos (already searched)
        candidate_docs: Documents from candidate websites (already filtered by scope)
        all_parties: List of parties to include in the response (may be filtered)
        scope: 'national' or 'local'
        municipality_name: Name of the municipality (for local scope)
        local_candidates: List of candidates in the municipality (for local scope)
        chat_response_llm_size: LLM size preference
        use_premium_llms: Whether to use premium models
        is_single_party_focus: True if the user selected a specific party
        locale: Response language (fr or en)
    """
    if local_candidates is None:
        local_candidates = []

    now = datetime.now()

    manifesto_context, candidates_context = get_combined_rag_context(
        manifesto_docs, candidate_docs
    )

    answer_guidelines = get_global_combined_answer_guidelines_for_locale(
        scope, municipality_name, locale
    )

    # Build scope description based on context
    local_candidates_info = ""

    # Determine scope description based on single party focus or broader scope
    if is_single_party_focus and len(all_parties) == 1:
        # User selected a specific party - focus on that party only
        focused_party = all_parties[0]
        if locale == "en":
            scope_description = (
                f"You are the assistant for the party **{focused_party.name}** ({focused_party.long_name}). "
                f"You respond ONLY about the proposals and program of this party. "
                f"Base yourself on the official program provided below."
            )
        else:
            scope_description = (
                f"Tu es l'assistant du parti **{focused_party.name}** ({focused_party.long_name}). "
                f"Tu réponds UNIQUEMENT sur les propositions et le programme de ce parti. "
                f"Base-toi sur le programme officiel fourni ci-dessous."
            )
    elif is_single_party_focus and len(all_parties) > 1:
        # User selected multiple specific parties - focus only on those
        party_names_str = ", ".join(f"**{p.name}**" for p in all_parties)
        if locale == "en":
            scope_description = (
                f"The user has selected the following parties: {party_names_str}. "
                f"You respond ONLY about the proposals and programs of these selected parties. "
                f"Do NOT include information about other parties."
            )
        else:
            scope_description = (
                f"L'utilisateur a sélectionné les partis suivants : {party_names_str}. "
                f"Tu réponds UNIQUEMENT sur les propositions et programmes de ces partis sélectionnés. "
                f"N'inclus PAS d'informations sur d'autres partis."
            )
    elif scope == "local" and municipality_name:
        if locale == "en":
            scope_description = f"LOCAL level - Municipality of {municipality_name}. You respond about the candidates present in this municipality and their parties' proposals."
        else:
            scope_description = f"Niveau LOCAL - Commune de {municipality_name}. Tu réponds sur les candidats présents dans cette commune et les propositions de leurs partis."

        # Build detailed candidates list
        if local_candidates:
            if locale == "en":
                local_candidates_info = (
                    f"\n## Candidates present in {municipality_name}\n"
                )
            else:
                local_candidates_info = (
                    f"\n## Candidats présents à {municipality_name}\n"
                )
            for candidate in local_candidates:
                party_names = []
                for pid in candidate.party_ids:
                    party = next((p for p in all_parties if p.party_id == pid), None)
                    if party is not None:
                        party_names.append(party.name)
                party_str = (
                    ", ".join(party_names)
                    if party_names
                    else ("Independent" if locale == "en" else "Indépendant")
                )
                position = candidate.position or (
                    "Candidate" if locale == "en" else "Candidat(e)"
                )
                if locale == "en":
                    website_info = (
                        f" - Website: {candidate.website_url}"
                        if candidate.website_url
                        else ""
                    )
                    incumbent_info = " (incumbent)" if candidate.is_incumbent else ""
                    manifesto_info = (
                        f" - Manifesto PDF: {candidate.manifesto_pdf_url}"
                        if candidate.has_manifesto and candidate.manifesto_pdf_url
                        else ""
                    )
                else:
                    website_info = (
                        f" - Site web : {candidate.website_url}"
                        if candidate.website_url
                        else ""
                    )
                    incumbent_info = " (sortant)" if candidate.is_incumbent else ""
                    manifesto_info = (
                        f" - [Profession de foi]({_pdf_viewer_url(candidate.manifesto_pdf_url)})"
                        if candidate.has_manifesto and candidate.manifesto_pdf_url
                        else ""
                    )
                local_candidates_info += f"- **{candidate.full_name}** ({party_str}) - {position}{incumbent_info}{website_info}{manifesto_info}\n"
        else:
            if locale == "en":
                local_candidates_info = f"\n## Candidates present in {municipality_name}\nNo candidate registered for this municipality.\n"
            else:
                local_candidates_info = f"\n## Candidats présents à {municipality_name}\nAucun candidat enregistré pour cette commune.\n"

        # Append selected electoral lists info if user selected specific lists
        if selected_electoral_lists:
            if locale == "en":
                local_candidates_info += f"\n## Electoral lists selected by the user in {municipality_name}\n"
                local_candidates_info += (
                    "The user has explicitly selected the following electoral lists in the interface. "
                    "You KNOW what the user selected. If the user asks what they selected, or asks about 'those' / 'these' / 'my selection', "
                    "refer to the lists below. Prioritize information about these lists and their candidates:\n"
                )
            else:
                local_candidates_info += f"\n## Listes électorales sélectionnées par l'utilisateur à {municipality_name}\n"
                local_candidates_info += (
                    "L'utilisateur a explicitement sélectionné les listes électorales suivantes dans l'interface. "
                    "Tu SAIS ce que l'utilisateur a sélectionné. S'il demande ce qu'il a sélectionné, ou parle de 'celles-ci' / 'ces listes' / 'ma sélection', "
                    "réfère-toi aux listes ci-dessous. Priorise les informations sur ces listes et leurs candidats :\n"
                )
            for el_list in selected_electoral_lists:
                head_name = f"{el_list.get('head_first_name', '')} {el_list.get('head_last_name', '')}".strip()
                local_candidates_info += f"- **{el_list.get('list_label', '')}** ({el_list.get('list_short_label', '')}) — Tête de liste : {head_name}\n"
    else:
        if locale == "en":
            scope_description = "NATIONAL level - You respond about the proposals of ALL parties and all candidates in France."
        else:
            scope_description = "Niveau NATIONAL - Tu réponds sur les propositions de TOUS les partis et de l'ensemble des candidats en France."

    # Build parties list (filter to relevant parties for local scope)
    if scope == "local" and local_candidates:
        # Only include parties that have candidates in this municipality
        relevant_party_ids = set()
        for candidate in local_candidates:
            relevant_party_ids.update(candidate.party_ids)
        parties_list = ""
        for party in all_parties:
            if party.party_id in relevant_party_ids:
                parties_list += f"- {party.name} ({party.long_name})\n"
    else:
        parties_list = ""
        for party in all_parties:
            parties_list += f"- {party.name} ({party.long_name})\n"

    system_prompt = get_global_combined_response_system_prompt_template(locale).format(
        scope_description=scope_description,
        parties_list=parties_list,
        local_candidates_info=local_candidates_info,
        date=now.strftime("%Y-%m-%d"),
        time=now.strftime("%H:%M"),
        manifesto_context=manifesto_context,
        candidates_context=candidates_context,
        answer_guidelines=answer_guidelines,
    )

    user_prompt = get_streaming_combined_response_user_prompt_template(locale).format(
        conversation_history=conversation_history,
        last_user_message=user_message,
    )

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_prompt),
    ]

    return await stream_answer_from_llms(
        chat_response_llms,
        messages,
        preferred_llm_size=chat_response_llm_size,
        use_premium_llms=use_premium_llms,
    )
