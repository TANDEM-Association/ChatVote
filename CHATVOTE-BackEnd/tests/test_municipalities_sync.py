from src.services import municipalities_sync
from src.services.data_pipeline import population


def test_transform_to_firestore_format_keeps_low_population_communes():
    municipalities = [
        {"code": "75056", "nom": "Paris", "population": 2161000},
        {"code": "01001", "nom": "L'Abergement-Clémenciat", "population": 784},
    ]

    result = municipalities_sync.transform_to_firestore_format(municipalities)

    assert set(result.keys()) == {"75056", "01001"}
    assert result["01001"]["nom"] == "L'Abergement-Clémenciat"
    assert "_syncedAt" in result["01001"]


def test_transform_to_firestore_format_skips_missing_codes():
    municipalities = [
        {"nom": "Missing code", "population": 10},
        {"code": "01001", "nom": "Valid commune", "population": 784},
    ]

    result = municipalities_sync.transform_to_firestore_format(municipalities)

    assert set(result.keys()) == {"01001"}


def test_get_top_communes_returns_ranked_subset(monkeypatch):
    cached = {
        "75056": {"nom": "Paris", "population": 2161000},
        "69123": {"nom": "Lyon", "population": 522250},
        "01001": {"nom": "Small commune", "population": 784},
    }
    monkeypatch.setattr(population, "_cached_communes", cached)

    assert population.get_all_communes() == cached
    assert list(population.get_top_communes(2).keys()) == ["75056", "69123"]
    assert population.get_top_communes(0) == {}
