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


def test_explicit_fiabilite_preserved():
    """Explicit fiabilité should NOT be overwritten by auto-inference."""
    cm = ChunkMetadata(
        namespace="x",
        source_document="candidate_website_blog",  # would infer PRESS (3)
        fiabilite=Fiabilite.GOVERNMENT,             # explicit override
    )
    assert cm.fiabilite == Fiabilite.GOVERNMENT


def test_from_qdrant_payload_preserves_fiabilite():
    """Roundtrip via payload preserves the stored fiabilité value."""
    original = ChunkMetadata(
        namespace="x",
        source_document="candidate_website_blog",
    )
    payload = original.to_qdrant_payload()
    # Simulate a mapping change: manually set a different fiabilite in payload
    payload["fiabilite"] = int(Fiabilite.GOVERNMENT)
    restored = ChunkMetadata.from_qdrant_payload(payload)
    assert restored.fiabilite == Fiabilite.GOVERNMENT


def test_fiabilite_int_values():
    """Verify IntEnum values match expected levels."""
    assert int(Fiabilite.GOVERNMENT) == 1
    assert int(Fiabilite.OFFICIAL) == 2
    assert int(Fiabilite.PRESS) == 3
    assert int(Fiabilite.SOCIAL_MEDIA) == 4


def test_invalid_theme_normalized_to_none():
    """Off-taxonomy theme should be silently set to None."""
    cm = ChunkMetadata(
        namespace="ps",
        source_document="election_manifesto",
        theme="pizza",
    )
    assert cm.theme is None


def test_valid_theme_accepted():
    cm = ChunkMetadata(
        namespace="ps",
        source_document="election_manifesto",
        theme="economie",
    )
    assert cm.theme == "economie"


def test_theme_taxonomy_exists():
    from src.models.chunk_metadata import THEME_TAXONOMY
    assert len(THEME_TAXONOMY) == 14
    assert "economie" in THEME_TAXONOMY
    assert "securite" in THEME_TAXONOMY


def test_theme_classification_schema():
    from src.models.structured_outputs import ChunkThemeClassification
    tc = ChunkThemeClassification(theme="economie", sub_theme="pouvoir d'achat")
    assert tc.theme == "economie"
    assert tc.sub_theme == "pouvoir d'achat"


def test_theme_classification_none_theme():
    from src.models.structured_outputs import ChunkThemeClassification
    tc = ChunkThemeClassification(theme=None, sub_theme=None)
    assert tc.theme is None


def test_theme_classification_valid_taxonomy():
    from src.models.structured_outputs import ChunkThemeClassification
    from src.models.chunk_metadata import THEME_TAXONOMY
    # Any taxonomy theme should work
    for theme in THEME_TAXONOMY:
        tc = ChunkThemeClassification(theme=theme, sub_theme=None)
        assert tc.theme == theme


# --- New metadata fields tests ---


def test_election_context_fields():
    """Election year and postal code are stored correctly."""
    cm = ChunkMetadata(
        namespace="montcenis-demain",
        source_document="election_manifesto",
        election_year=2026,
        municipality_code="71302",
        municipality_name="Montcenis",
        municipality_postal_code="71710",
        election_type_id="municipales-2026",
    )
    assert cm.election_year == 2026
    assert cm.municipality_postal_code == "71710"
    assert cm.municipality_code == "71302"
    payload = cm.to_qdrant_payload()
    assert payload["election_year"] == 2026
    assert payload["municipality_postal_code"] == "71710"


def test_epci_fields():
    """EPCI (inter-communal grouping) fields serialize correctly."""
    cm = ChunkMetadata(
        namespace="test",
        source_document="election_manifesto",
        epci_nom="CC du Grand Autunois Morvan",
        epci_code="200066721",
    )
    assert cm.epci_nom == "CC du Grand Autunois Morvan"
    assert cm.epci_code == "200066721"
    payload = cm.to_qdrant_payload()
    assert payload["epci_nom"] == "CC du Grand Autunois Morvan"
    assert payload["epci_code"] == "200066721"


def test_electoral_list_context_fields():
    """Electoral list metadata: tete de liste, nombre candidats, nuance, incumbent."""
    cm = ChunkMetadata(
        namespace="montcenis-demain",
        source_document="election_manifesto",
        is_tete_de_liste=True,
        liste_nombre_candidats=15,
        nuance_politique="DVC",
        is_incumbent=False,
    )
    assert cm.is_tete_de_liste is True
    assert cm.liste_nombre_candidats == 15
    assert cm.nuance_politique == "DVC"
    assert cm.is_incumbent is False
    payload = cm.to_qdrant_payload()
    assert payload["is_tete_de_liste"] is True
    assert payload["liste_nombre_candidats"] == 15
    assert payload["nuance_politique"] == "DVC"
    assert payload["is_incumbent"] is False


def test_provenance_fields():
    """Document ID and scraping date are stored correctly."""
    cm = ChunkMetadata(
        namespace="test",
        source_document="election_manifesto",
        document_id="uuid-stable-par-document",
        date_scraping="2026-02-15T10:30:00Z",
    )
    assert cm.document_id == "uuid-stable-par-document"
    assert cm.date_scraping == "2026-02-15T10:30:00Z"
    payload = cm.to_qdrant_payload()
    assert payload["document_id"] == "uuid-stable-par-document"
    assert payload["date_scraping"] == "2026-02-15T10:30:00Z"


def test_new_fields_excluded_when_none():
    """New optional fields should not appear in payload when None."""
    cm = ChunkMetadata(
        namespace="ps",
        source_document="election_manifesto",
    )
    payload = cm.to_qdrant_payload()
    assert "election_year" not in payload
    assert "municipality_postal_code" not in payload
    assert "epci_nom" not in payload
    assert "epci_code" not in payload
    assert "is_tete_de_liste" not in payload
    assert "liste_nombre_candidats" not in payload
    assert "nuance_politique" not in payload
    assert "is_incumbent" not in payload
    assert "document_id" not in payload
    assert "date_scraping" not in payload


def test_full_municipal_chunk_roundtrip():
    """Full municipal election chunk with all new fields roundtrips through Qdrant payload."""
    original = ChunkMetadata(
        namespace="montcenis-demain",
        source_document="election_manifesto",
        party_ids=["en-marche"],
        party_name="Montcenis Demain",
        candidate_name="Marie Dupont",
        municipality_code="71302",
        municipality_name="Montcenis",
        municipality_postal_code="71710",
        election_type_id="municipales-2026",
        election_year=2026,
        epci_nom="CC du Grand Autunois Morvan",
        epci_code="200066721",
        is_tete_de_liste=True,
        liste_nombre_candidats=15,
        nuance_politique="DVC",
        is_incumbent=False,
        document_name="Programme Montcenis Demain",
        document_id="uuid-123",
        url="https://montcenis-demain.fr/programme.pdf",
        date_scraping="2026-02-15T10:30:00Z",
        page=4,
        chunk_index=12,
        total_chunks=50,
        theme="environnement",
        sub_theme="transition énergétique",
    )
    payload = original.to_qdrant_payload()
    restored = ChunkMetadata.from_qdrant_payload(payload)

    assert restored.election_year == 2026
    assert restored.municipality_postal_code == "71710"
    assert restored.epci_nom == "CC du Grand Autunois Morvan"
    assert restored.epci_code == "200066721"
    assert restored.is_tete_de_liste is True
    assert restored.liste_nombre_candidats == 15
    assert restored.nuance_politique == "DVC"
    assert restored.is_incumbent is False
    assert restored.document_id == "uuid-123"
    assert restored.date_scraping == "2026-02-15T10:30:00Z"
    assert restored.fiabilite == Fiabilite.OFFICIAL
    assert restored.theme == "environnement"
