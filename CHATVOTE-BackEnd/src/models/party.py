# SPDX-FileCopyrightText: 2025 chatvote
#
# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0

from pydantic import BaseModel, Field


class Party(BaseModel):
    """Model representing a political party or list for municipal elections."""

    party_id: str = Field(..., description="The unique identifier of the party/list")
    name: str = Field(..., description="The short name of the party/list")
    long_name: str = Field(..., description="The full name of the party/list")
    description: str = Field(..., description="The description of the party/list")
    website_url: str = Field(..., description="The website URL of the party/list")
    candidate: str = Field(..., description="The lead candidate or head of list")
    election_manifesto_url: str = Field(
        ..., description="The URL of the party/list election manifesto"
    )
    logo_url: str = Field(default="", description="The URL of the party/list logo")
    candidate_image_url: str = Field(
        default="", description="The URL of the candidate's photo"
    )
    background_color: str = Field(
        default="#4A90D9",
        description="The background color for the party/list (hex format)",
    )
    is_small_party: bool = Field(
        description="True if it's a small party/list, False otherwise",
        default=False,
    )
    is_already_in_parliament: bool = Field(
        description="True if the party/list is already represented in the municipal council, False otherwise",
        default=False,
    )
