# SPDX-FileCopyrightText: 2025 chatvote
#
# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class Candidate(BaseModel):
    """Model representing a candidate for municipal or national elections."""

    candidate_id: str = Field(..., description="The unique identifier of the candidate")
    first_name: str = Field(..., description="The first name of the candidate")
    last_name: str = Field(..., description="The last name of the candidate")
    municipality_code: Optional[str] = Field(
        default=None,
        description="The INSEE code of the municipality. None for national elections.",
    )
    municipality_name: Optional[str] = Field(
        default=None, description="The name of the municipality"
    )
    party_ids: List[str] = Field(
        default_factory=list,
        description="List of party IDs the candidate is affiliated with. Multiple IDs indicate a coalition.",
    )
    election_type_id: str = Field(
        ..., description="The type of election (e.g., 'municipalities-2026')"
    )
    presence_score: int = Field(
        default=0,
        description="Score from 0 to 100 representing the candidate's visibility/presence. Used for sorting.",
    )
    position: Optional[str] = Field(
        default=None, description="The candidate's position (e.g., 'Tête de liste')"
    )
    bio: Optional[str] = Field(
        default=None, description="A brief biography of the candidate"
    )
    is_incumbent: bool = Field(
        default=False, description="True if the candidate is the current incumbent"
    )
    birth_year: Optional[int] = Field(
        default=None, description="The birth year of the candidate"
    )
    photo_url: Optional[str] = Field(
        default=None, description="The URL of the candidate's photo"
    )
    contact_email: Optional[str] = Field(
        default=None, description="The contact email of the candidate"
    )
    website_url: Optional[str] = Field(
        default=None, description="The campaign website URL of the candidate"
    )
    manifesto_pdf_url: Optional[str] = Field(
        default=None, description="URL of the profession de foi PDF"
    )
    created_at: Optional[datetime] = Field(
        default=None, description="When the candidate record was created"
    )
    updated_at: Optional[datetime] = Field(
        default=None, description="When the candidate record was last updated"
    )

    @property
    def full_name(self) -> str:
        """Return the full name of the candidate."""
        return f"{self.first_name} {self.last_name}"

    @property
    def is_in_coalition(self) -> bool:
        """Return True if the candidate represents multiple parties (coalition)."""
        return len(self.party_ids) >= 2

    @property
    def is_national_candidate(self) -> bool:
        """Return True if this is a national election candidate (no municipality)."""
        return self.municipality_code is None
