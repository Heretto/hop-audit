"""The analysis agents every organization starts with: one per analysis that
needs judgement. Links don't (``links.py`` checks them and proposes fixes).

They are ordinary hop-core agents: people edit, duplicate, or delete them on
the Agents page. Seeding happens once per organization (``OrgSetup``), so an
agent someone deletes is not re-created. Context files come from
``agent_context/<slug>/``, most of them from the audit-asset-maker skill.
"""

from datetime import UTC, datetime
from pathlib import Path
from typing import NamedTuple
from uuid import UUID

from hop_core.models.agent import Agent, AgentContextFile
from sqlalchemy.orm import Session

from models import OrgSetup

CONTEXT_DIR = Path(__file__).resolve().parent / "agent_context"


class AgentSeed(NamedTuple):
    slug: str
    name: str
    analysis: str
    description: str


AGENT_SEEDS = (
    AgentSeed(
        "readability-reviewer",
        "Readability Reviewer",
        "readability",
        "Explains low Flesch scores and proposes concrete rewrites; applies the site's readability focus.",
    ),
    AgentSeed(
        "seo-analyst",
        "SEO Analyst",
        "seo",
        "Reviews titles, descriptions, headings, alt text and canonicals; drafts replacements that fit the limits.",
    ),
    AgentSeed(
        "content-integrity-reviewer",
        "Content Integrity Reviewer",
        "content_integrity",
        "Reads every article in every locale and logs what is wrong, conflicting, outdated or unscoped, "
        "in 10 categories, with exact quotes, slugs and a severity.",
    ),
    AgentSeed(
        "summary-writer",
        "Summary Writer",
        "summary",
        "Writes the audit's summary report from the metrics and the other agents' findings; "
        "compares with the previous run.",
    ),
    AgentSeed(
        "collateral-writer",
        "Collateral Writer",
        "deliverables",
        "Turns confirmed findings into the lead one-sheet, executive brief and internal note: "
        "headlines per the rules, business case mapped to Heretto's four imperatives.",
    ),
)


def context_files(slug: str) -> list[AgentContextFile]:
    """The agent's context files, ordered by their numeric filename prefix."""
    paths = sorted((CONTEXT_DIR / slug).glob("*.md"))
    return [
        AgentContextFile(name=p.stem.split("-", 1)[1].replace("-", " ").capitalize(), content=p.read_text(), position=i)
        for i, p in enumerate(paths)
    ]


def ensure_setup(db: Session, organization_id: UUID, user_id: UUID, user_email: str) -> OrgSetup:
    """Seed the organization's agents the first time; afterwards a no-op."""
    setup = db.get(OrgSetup, organization_id)
    if setup:
        return setup
    seeded = {}
    for seed in AGENT_SEEDS:
        agent = Agent(
            organization_id=organization_id,
            user_id=user_id,
            created_by=user_email,
            name=seed.name,
            description=seed.description,
            permitted_urls=[],
            feedback_memory="",
            context_files=context_files(seed.slug),
        )
        db.add(agent)
        db.flush()
        seeded[seed.analysis] = str(agent.id)
    setup = OrgSetup(
        organization_id=organization_id,
        agents_seeded_at=datetime.now(UTC),
        seeded_agents=seeded,
    )
    db.add(setup)
    db.commit()
    return setup
