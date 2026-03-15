"""Tests for pure helper functions in src/services/data_pipeline/populate.py.

All tested functions are pure Python with no I/O or async behaviour,
so no mocking or fixtures are required.
"""
from src.services.data_pipeline.populate import (
    _build_candidates,
    _build_electoral_lists,
    _build_municipalities,
    _doc_hash,
    _norm,
)


# ---------------------------------------------------------------------------
# _norm
# ---------------------------------------------------------------------------

class TestNorm:
    def test_strips_accents_and_lowercases(self):
        assert _norm("Élodie Trémeau") == "elodietremeau"

    def test_empty_string(self):
        assert _norm("") == ""

    def test_removes_non_alpha(self):
        # Spaces, hyphens, apostrophes, digits all removed
        assert _norm("Jean-Paul O'Brien 42") == "jeanpaulobrien"

    def test_already_normalised(self):
        assert _norm("test") == "test"

    def test_all_uppercase(self):
        assert _norm("DUPONT") == "dupont"

    def test_mixed_diacritics(self):
        assert _norm("François") == "francois"


# ---------------------------------------------------------------------------
# _doc_hash
# ---------------------------------------------------------------------------

class TestDocHash:
    def test_deterministic(self):
        data = {"commune_code": "75056", "nom": "Paris", "population": 2161000}
        assert _doc_hash(data) == _doc_hash(data)

    def test_content_sensitive(self):
        a = {"commune_code": "75056", "nom": "Paris"}
        b = {"commune_code": "75056", "nom": "Lyon"}
        assert _doc_hash(a) != _doc_hash(b)

    def test_key_order_independent(self):
        a = {"b": 2, "a": 1}
        b = {"a": 1, "b": 2}
        assert _doc_hash(a) == _doc_hash(b)

    def test_returns_hex_string(self):
        result = _doc_hash({"x": 1})
        assert isinstance(result, str)
        assert len(result) == 64  # SHA-256 hex digest


# ---------------------------------------------------------------------------
# _build_municipalities
# ---------------------------------------------------------------------------

_SAMPLE_COMMUNES = {
    "75056": {
        "nom": "Paris",
        "population": 2161000,
        "dep_code": "75",
        "dep_nom": "Paris",
        "reg_code": "11",
        "reg_nom": "Île-de-France",
        "code_postal": "75001",
        "epci_code": "200054781",
        "epci_nom": "Métropole du Grand Paris",
    },
    "69123": {
        "nom": "Lyon",
        "population": 522969,
        "dep_code": "69",
        "dep_nom": "Rhône",
        "reg_code": "84",
        "reg_nom": "Auvergne-Rhône-Alpes",
        "code_postal": "69001",
        "epci_code": "200046977",
        "epci_nom": "Métropole de Lyon",
    },
}


class TestBuildMunicipalities:
    def test_maps_fields_correctly(self):
        result = _build_municipalities(_SAMPLE_COMMUNES)

        paris = result["75056"]
        assert paris["code"] == "75056"
        assert paris["nom"] == "Paris"
        assert paris["population"] == 2161000
        assert paris["codeDepartement"] == "75"
        assert paris["departement"] == {"code": "75", "nom": "Paris"}
        assert paris["codeRegion"] == "11"
        assert paris["region"] == {"code": "11", "nom": "Île-de-France"}
        assert paris["codesPostaux"] == ["75001"]
        assert paris["codeEpci"] == "200054781"
        assert paris["epci"] == {"code": "200054781", "nom": "Métropole du Grand Paris"}

    def test_all_input_communes_present(self):
        result = _build_municipalities(_SAMPLE_COMMUNES)
        assert set(result.keys()) == {"75056", "69123"}

    def test_empty_code_postal_gives_empty_list(self):
        communes = {
            "01001": {
                "nom": "Test",
                "population": 100,
                "dep_code": "01",
                "dep_nom": "Ain",
                "reg_code": "84",
                "reg_nom": "ARA",
                "code_postal": None,
                "epci_code": "X",
                "epci_nom": "Y",
            }
        }
        result = _build_municipalities(communes)
        assert result["01001"]["codesPostaux"] == []

    def test_empty_input(self):
        assert _build_municipalities({}) == {}


# ---------------------------------------------------------------------------
# Shared candidatures fixture
# ---------------------------------------------------------------------------

def _make_candidatures():
    """Return a minimal candidatures dict for two communes."""
    return {
        "75056": {
            "commune_name": "Paris",
            "lists": {
                1: {
                    "panneau": 1,
                    "list_label": "Paris en Commun",
                    "list_short_label": "PeC",
                    "nuance_code": "DVG",
                    "nuance_label": "Divers gauche",
                    "head_first_name": "Anne",
                    "head_last_name": "Hidalgo",
                    "candidates": [
                        {"prenom": "Anne", "nom": "Hidalgo", "tete_de_liste": True},
                        {"prenom": "Jean", "nom": "Dupont", "tete_de_liste": False},
                    ],
                },
                2: {
                    "panneau": 2,
                    "list_label": "Paris Nouveau",
                    "list_short_label": "PN",
                    "nuance_code": "DVD",
                    "nuance_label": "Divers droite",
                    "head_first_name": "Marc",
                    "head_last_name": "Martin",
                    "candidates": [
                        {"prenom": "Marc", "nom": "Martin", "tete_de_liste": True},
                    ],
                },
            },
        },
        "69123": {
            "commune_name": "Lyon",
            "lists": {
                1: {
                    "panneau": 1,
                    "list_label": "Lyon Ensemble",
                    "list_short_label": "LE",
                    "nuance_code": "UCG",
                    "nuance_label": "Union centre gauche",
                    "head_first_name": "Sophie",
                    "head_last_name": "Bernard",
                    "candidates": [
                        {"prenom": "Sophie", "nom": "Bernard", "tete_de_liste": True},
                    ],
                },
                3: {
                    "panneau": 3,
                    "list_label": "Lyon Avenir",
                    "list_short_label": "LA",
                    "nuance_code": "RN",
                    "nuance_label": "Rassemblement National",
                    "head_first_name": "Paul",
                    "head_last_name": "Leroy",
                    "candidates": [
                        # No tete_de_liste candidate — should be skipped
                        {"prenom": "Paul", "nom": "Leroy", "tete_de_liste": False},
                    ],
                },
            },
        },
    }


# ---------------------------------------------------------------------------
# _build_candidates
# ---------------------------------------------------------------------------

class TestBuildCandidates:
    def test_creates_tete_de_liste_only(self):
        cands = _build_candidates(_make_candidatures())
        # List 3 in 69123 has no tete_de_liste — must be absent
        assert "cand-69123-3" not in cands

    def test_includes_lists_with_tete_de_liste(self):
        cands = _build_candidates(_make_candidatures())
        assert "cand-75056-1" in cands
        assert "cand-75056-2" in cands
        assert "cand-69123-1" in cands

    def test_cand_id_format(self):
        cands = _build_candidates(_make_candidatures())
        cand = cands["cand-75056-1"]
        assert cand["candidate_id"] == "cand-75056-1"

    def test_candidate_fields(self):
        cands = _build_candidates(_make_candidatures())
        cand = cands["cand-75056-1"]
        assert cand["first_name"] == "Anne"
        assert cand["last_name"] == "Hidalgo"
        assert cand["commune_code"] == "75056"
        assert cand["commune_name"] == "Paris"
        assert cand["panel_number"] == 1
        assert cand["position"] == "Tête de liste"
        assert cand["election_type_id"] == "municipalities-2026"

    def test_empty_candidatures(self):
        assert _build_candidates({}) == {}


# ---------------------------------------------------------------------------
# _build_electoral_lists
# ---------------------------------------------------------------------------

class TestBuildElectoralLists:
    def test_sorts_by_panel(self):
        # Lyon has panels 1 and 3; both should appear and be in ascending order.
        result = _build_electoral_lists(_make_candidatures())
        lyon_lists = result["69123"]["lists"]
        panel_numbers = [lst["panel_number"] for lst in lyon_lists]
        assert panel_numbers == sorted(panel_numbers)

    def test_list_count_matches(self):
        result = _build_electoral_lists(_make_candidatures())
        assert result["75056"]["list_count"] == 2
        assert result["69123"]["list_count"] == 2

    def test_commune_fields(self):
        result = _build_electoral_lists(_make_candidatures())
        paris = result["75056"]
        assert paris["commune_code"] == "75056"
        assert paris["commune_name"] == "Paris"

    def test_list_fields(self):
        result = _build_electoral_lists(_make_candidatures())
        first_list = result["75056"]["lists"][0]  # sorted by panneau → panel 1
        assert first_list["panel_number"] == 1
        assert first_list["list_label"] == "Paris en Commun"
        assert first_list["nuance_code"] == "DVG"
        assert first_list["head_first_name"] == "Anne"
        assert first_list["head_last_name"] == "Hidalgo"

    def test_empty_input(self):
        assert _build_electoral_lists({}) == {}
