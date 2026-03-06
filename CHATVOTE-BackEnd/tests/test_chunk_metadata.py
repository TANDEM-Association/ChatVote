import pytest
from src.models.chunk_metadata import ChunkMetadata, Fiabilite


def test_chunk_metadata_minimal():
    """Minimal valid chunk: just namespace and source_document."""
    cm = ChunkMetadata(
        namespace="ps",
        source_document="election_manifesto",
    )
    assert cm.namespace == "ps"
    assert cm.fiabilite == Fiabilite.OFFICIAL  # election_manifesto → level 2
    assert cm.party_ids == []
    assert cm.candidate_ids == []
    assert cm.theme is None
    assert cm.sub_theme is None


def test_fiabilite_auto_assignment_government():
    cm = ChunkMetadata(
        namespace="govt",
        source_document="justified_voting_behavior",
    )
    assert cm.fiabilite == Fiabilite.GOVERNMENT  # level 1


def test_fiabilite_auto_assignment_press():
    cm = ChunkMetadata(
        namespace="cand-1",
        source_document="candidate_website_blog",
    )
    assert cm.fiabilite == Fiabilite.PRESS  # level 3


def test_fiabilite_auto_assignment_official_candidate():
    cm = ChunkMetadata(
        namespace="cand-1",
        source_document="candidate_website_about",
    )
    assert cm.fiabilite == Fiabilite.OFFICIAL  # level 2


def test_fiabilite_unknown_source_defaults_press():
    cm = ChunkMetadata(
        namespace="x",
        source_document="unknown_source_type",
    )
    assert cm.fiabilite == Fiabilite.PRESS  # level 3 default


def test_party_ids_array():
    cm = ChunkMetadata(
        namespace="ps",
        source_document="election_manifesto",
        party_ids=["ps", "nfp"],
    )
    assert cm.party_ids == ["ps", "nfp"]


def test_candidate_ids_array():
    cm = ChunkMetadata(
        namespace="cand-1",
        source_document="candidate_website",
        candidate_ids=["cand-1", "cand-2"],
    )
    assert cm.candidate_ids == ["cand-1", "cand-2"]


def test_to_qdrant_payload():
    cm = ChunkMetadata(
        namespace="ps",
        source_document="election_manifesto",
        party_ids=["ps"],
        party_name="Parti Socialiste",
        document_name="PS - Programme",
        url="https://example.com/ps.pdf",
        page=3,
        chunk_index=0,
        total_chunks=10,
        theme="economie",
        sub_theme="pouvoir d'achat",
    )
    payload = cm.to_qdrant_payload()
    assert payload["namespace"] == "ps"
    assert payload["party_ids"] == ["ps"]
    assert payload["fiabilite"] == 2
    assert payload["theme"] == "economie"
    assert payload["sub_theme"] == "pouvoir d'achat"
    assert payload["page"] == 3
    # None fields should be excluded
    assert "candidate_name" not in payload


def test_from_qdrant_payload_roundtrip():
    original = ChunkMetadata(
        namespace="cand-paris-001",
        source_document="candidate_website_about",
        candidate_ids=["cand-paris-001"],
        party_ids=["lr"],
        candidate_name="Jean Dupont",
        municipality_code="75056",
    )
    payload = original.to_qdrant_payload()
    restored = ChunkMetadata.from_qdrant_payload(payload)
    assert restored.namespace == original.namespace
    assert restored.candidate_ids == original.candidate_ids
    assert restored.party_ids == original.party_ids
    assert restored.fiabilite == original.fiabilite


def test_fiabilite_int_values():
    """Verify IntEnum values match expected levels."""
    assert int(Fiabilite.GOVERNMENT) == 1
    assert int(Fiabilite.OFFICIAL) == 2
    assert int(Fiabilite.PRESS) == 3
    assert int(Fiabilite.SOCIAL_MEDIA) == 4


def test_theme_taxonomy_exists():
    from src.models.chunk_metadata import THEME_TAXONOMY
    assert len(THEME_TAXONOMY) == 14
    assert "economie" in THEME_TAXONOMY
    assert "securite" in THEME_TAXONOMY
