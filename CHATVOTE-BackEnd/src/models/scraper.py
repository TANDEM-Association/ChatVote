"""
Shared scraper output models.

Single source of truth for ScrapedPage and ScrapedWebsite dataclasses.
Used by both candidate_website_scraper.py and firecrawl_scraper.py.

Previously these were duplicated in both scraper modules.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class ScrapedPage:
    """Represents a single scraped page from a website."""

    url: str
    title: str
    content: str
    page_type: str = "html"  # "html", "pdf", "sitemap"
    depth: int = 0
    content_length: int = 0

    def __post_init__(self):
        self.content_length = len(self.content)


@dataclass
class ScrapedWebsite:
    """Represents the full scraped content from a candidate's website."""

    candidate_id: str
    website_url: str
    pages: List[ScrapedPage] = field(default_factory=list)
    error: Optional[str] = None
    stats: Dict[str, int] = field(default_factory=dict)

    @property
    def total_content_length(self) -> int:
        return sum(page.content_length for page in self.pages)

    @property
    def is_successful(self) -> bool:
        return len(self.pages) > 0
