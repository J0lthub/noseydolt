"""
NoseyDolt Configuration
Credentials live in .env — never commit that file.
"""
import os
from dotenv import load_dotenv

load_dotenv()

# --- Reddit ---
REDDIT_CLIENT_ID     = os.getenv("REDDIT_CLIENT_ID", "")
REDDIT_CLIENT_SECRET = os.getenv("REDDIT_CLIENT_SECRET", "")
REDDIT_USER_AGENT    = "NoseyDolt/1.0 (social listener for DoltHub mentions)"

# --- Keywords ---
PRIMARY_KEYWORDS = [
    "Dolt",
    "DoltHub",
    "DoltGres",
    "dolthub.com",
]

SECONDARY_KEYWORDS = [
    "AI agents version control database",
    "versioned database AI",
    "git for data AI",
    "LLM memory database",
    "agent memory versioning",
    "go-mysql-server",
    # Agentic AI discourse
    "agentic memory",
    "agentic personality",
    # Data integrity / compliance
    "source of truth database",
    "EU AI Act compliance",
    "AI Act audit trail",
    # Steve Yegge + his Dolt-backed projects
    "Steve Yegge",
    "Yegge Gastown",
    "Beads",
]

ALL_KEYWORDS = PRIMARY_KEYWORDS + SECONDARY_KEYWORDS

# --- Weighted reach formula weights ---
REACH_WEIGHT_SHARES   = 15
REACH_WEIGHT_LIKES    = 0.5
REACH_WEIGHT_COMMENTS = 2
REACH_WEIGHT_UPVOTES  = 5

# --- Dolt ---
DOLT_REPO_PATH = os.path.dirname(os.path.abspath(__file__))
DOLT_BRANCH    = "nosey/work"

# --- Platforms ---
PLATFORMS_ENABLED = ["hackernews"]
