import sys
from unittest.mock import MagicMock, patch

import pytest
from qdrant_client.models import Filter, FieldCondition, MatchAny, Range


# ---------------------------------------------------------------------------
# Patch heavy dependencies before importing vector_store_helper so that the
# module-level side-effects (Firebase, Qdrant connections, embedding init)
# don't run during unit tests.
# ---------------------------------------------------------------------------

def _import_vsh():
    """Import vector_store_helper with all heavy side-effects mocked out."""
    mocks = {
        "src.chatbot_async": MagicMock(),
        "src.firebase_service": MagicMock(),
    }
    # Patch the QdrantClient / AsyncQdrantClient constructors so the
    # module-level `qdrant_client = QdrantClient(...)` doesn't connect.
    qdrant_mock = MagicMock()
    with patch.dict(sys.modules, mocks), \
         patch("qdrant_client.QdrantClient", return_value=qdrant_mock), \
         patch("qdrant_client.AsyncQdrantClient", return_value=qdrant_mock), \
         patch("src.vector_store_helper._get_embeddings", return_value=(MagicMock(), 3072)):
        # Force reimport if already cached
        sys.modules.pop("src.vector_store_helper", None)
        import src.vector_store_helper as vsh
        return vsh


@pytest.fixture(scope="module")
def vsh():
    return _import_vsh()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_build_party_filter(vsh):
    """_build_party_filter creates a MatchAny condition on metadata.party_ids."""
    f = vsh._build_party_filter(["ps", "nfp"])
    assert f is not None
    assert len(f.must) == 1
    cond = f.must[0]
    assert cond.key == "metadata.party_ids"
    assert cond.match.any == ["ps", "nfp"]


def test_build_fiabilite_filter(vsh):
    """_build_fiabilite_filter creates a must_not Range(gt=) filter."""
    f = vsh._build_fiabilite_filter(max_fiabilite=3)
    assert f is not None
    assert len(f.must_not) == 1
    cond = f.must_not[0]
    assert cond.key == "metadata.fiabilite"
    assert cond.range.gt == 3


def test_build_fiabilite_filter_custom(vsh):
    """Custom max_fiabilite value."""
    f = vsh._build_fiabilite_filter(max_fiabilite=2)
    assert f.must_not[0].range.gt == 2


def test_combine_filters_merges_must(vsh):
    """_combine_filters merges all must conditions."""
    f1 = Filter(must=[FieldCondition(key="a", match=MatchAny(any=["x"]))])
    f2 = Filter(must=[FieldCondition(key="b", range=Range(lte=3))])
    combined = vsh._combine_filters(f1, f2)
    assert combined is not None
    assert len(combined.must) == 2


def test_combine_filters_skips_none(vsh):
    """_combine_filters skips None filters."""
    f1 = Filter(must=[FieldCondition(key="a", match=MatchAny(any=["x"]))])
    combined = vsh._combine_filters(None, f1, None)
    assert combined is not None
    assert len(combined.must) == 1


def test_combine_filters_all_none(vsh):
    """_combine_filters returns None if all inputs are None."""
    assert vsh._combine_filters(None, None) is None
