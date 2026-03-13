# SPDX-FileCopyrightText: 2025 chatvote
#
# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0

from pydantic import BaseModel, Field


# Constant for the assistant ID - used for comparisons
ASSISTANT_ID = "chat-vote"


class Assistant(BaseModel):
    """Model representing the ChatVote assistant."""

    assistant_id: str = Field(..., description="The unique identifier of the assistant")
    name: str = Field(..., description="The name of the assistant")
    long_name: str = Field(..., description="The full name of the assistant")
    description: str = Field(..., description="The description of the assistant")
    website_url: str = Field(..., description="The website URL")
    logo_url: str = Field(default="", description="The logo URL")
    background_color: str = Field(
        default="#4A90D9", description="The background color (hex format)"
    )

    @property
    def party_id(self) -> str:
        """Alias for assistant_id - provides compatibility with code expecting party_id."""
        return self.assistant_id


CHATVOTE_ASSISTANT = Assistant(
    assistant_id=ASSISTANT_ID,
    name="ChatVote",
    long_name="ChatVote Assistant",
    description=(
        "The ChatVote assistant can answer general questions about municipal elections, "
        "the French electoral system, and the ChatVote application. "
        "When multiple parties are being compared, it remains neutral and provides an overview based on sources."
    ),
    website_url="https://chatvote.fr",
    logo_url="https://chatvote-public-assets.s3.fr-par.scw.cloud/public/chat-vote/logo.svg",
    background_color="#4A90D9",
)
