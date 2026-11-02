"""SJSU Agentic AI Coworkers.

Two LangGraph agents that share one long-term memory:

* DailyTechUpgradeAgent        -> coworkers.tech_upgrade
* nextLevelPersonalCoachForCareerLevel -> coworkers.career_coach
"""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
CONFIG_DIR = ROOT / "config"
DEFAULT_DB = Path(os.getenv("COWORKER_DB", ROOT / "data" / "coworker_memory.sqlite"))
DEFAULT_PROFILE = Path(os.getenv("COWORKER_PROFILE", CONFIG_DIR / "profile.yaml"))
OUTPUT_DIR = Path(os.getenv("COWORKER_OUT", ROOT / "output"))

__version__ = "1.0.0"
