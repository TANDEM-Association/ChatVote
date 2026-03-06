"""
Unified chunk metadata model.

Every Qdrant payload MUST be produced by ChunkMetadata.to_qdrant_payload().
This is the single source of truth for chunk metadata shape.
"""

from enum import IntEnum
from typing import Optional

from pydantic import BaseModel, Field, model_validator


class Fiabilite(IntEnum):
    """Source reliability level. Lower = more trustworthy."""
    GOVERNMENT = 1       # Parliamentary records, official votes
    OFFICIAL = 2         # Party manifestos, official party/candidate websites
    PRESS = 3            # Blog posts, press articles, scraped content
    SOCIAL_MEDIA = 4     # Social media (excluded by default in queries)


# Mapping: source_document prefix → fiabilité level
_SOURCE_FIABILITE_MAP: dict[str, Fiabilite] = {
    "justified_voting_behavior": Fiabilite.GOVERNMENT,
    "parliamentary_question": Fiabilite.GOVERNMENT,
    "election_manifesto": Fiabilite.OFFICIAL,
    "party_website": Fiabilite.OFFICIAL,
    "candidate_website_about": Fiabilite.OFFICIAL,
    "candidate_website_programme": Fiabilite.OFFICIAL,
    "candidate_website_blog": Fiabilite.PRESS,
    "candidate_website_actualite": Fiabilite.PRESS,
    "candidate_website": Fiabilite.PRESS,
}


THEME_TAXONOMY: list[str] = [
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


def _infer_fiabilite(source_document: str) -> Fiabilite:
    """Auto-assign fiabilité from source_document field."""
    if source_document in _SOURCE_FIABILITE_MAP:
        return _SOURCE_FIABILITE_MAP[source_document]
    for prefix, level in sorted(
        _SOURCE_FIABILITE_MAP.items(), key=lambda x: -len(x[0])
    ):
        if source_document.startswith(prefix):
            return level
    return Fiabilite.PRESS


class ChunkMetadata(BaseModel):
    """Unified metadata for every chunk stored in Qdrant."""

    # Required
    namespace: str = Field(description="Primary entity ID for backward compat")
    source_document: str = Field(description="Source type key for fiabilité inference")

    # Multi-entity references
    party_ids: list[str] = Field(default_factory=list)
    candidate_ids: list[str] = Field(default_factory=list)

    # Entity display info
    party_name: Optional[str] = None
    candidate_name: Optional[str] = None
    municipality_code: Optional[str] = None
    municipality_name: Optional[str] = None
    election_type_id: Optional[str] = None

    # Source display info
    document_name: Optional[str] = None
    url: Optional[str] = None
    document_publish_date: Optional[str] = None
    page_title: Optional[str] = None
    page_type: Optional[str] = None

    # Chunk position
    page: int = 0
    chunk_index: int = 0
    total_chunks: int = 0

    # Quality & classification
    fiabilite: Fiabilite = Field(default=Fiabilite.PRESS)
    theme: Optional[str] = None
    sub_theme: Optional[str] = None

    @model_validator(mode="after")
    def _auto_fiabilite(self) -> "ChunkMetadata":
        self.fiabilite = _infer_fiabilite(self.source_document)
        return self

    def to_qdrant_payload(self) -> dict:
        d = self.model_dump(exclude_none=True)
        d["fiabilite"] = int(self.fiabilite)
        return d

    @classmethod
    def from_qdrant_payload(cls, payload: dict) -> "ChunkMetadata":
        return cls(**payload)
