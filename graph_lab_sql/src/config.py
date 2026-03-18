"""Configuration loading for graph_lab_sql — Postgres-native."""

import os
from pathlib import Path

import structlog
import yaml
from dotenv import load_dotenv
from graph_lab_sql.src.types import GraphConfig, PersonaConfig, TriggersConfig

logger = structlog.get_logger()

_ROOT = Path(__file__).parent.parent
_CONFIG_DIR = _ROOT / "config"

# Load .env from graph_lab_sql root, then repo root
_local_env = _ROOT / ".env"
if _local_env.exists():
    load_dotenv(_local_env)
_repo_env = _ROOT.parent / ".env"
if _repo_env.exists():
    load_dotenv(_repo_env, override=False)


def get_env(key: str, default: str | None = None) -> str:
    val = os.environ.get(key, default)
    if val is None:
        raise ValueError(f"Missing required env var: {key}")
    return val


# --- Environment ---

PG_DSN: str = os.environ.get(
    "PG_DSN", "postgresql://graph_lab:graph_lab@localhost:5433/graph_lab"
)

LLM_API_KEY: str = os.environ.get("LLM_API_KEY", "")
LLM_MODEL: str = os.environ.get("LLM_MODEL", "claude-sonnet-4-6")
LLM_MODEL_FAST: str = os.environ.get("LLM_MODEL_FAST", "claude-haiku-4-5-20251001")

OPENAI_API_KEY: str = os.environ.get("OPENAI_API_KEY", "")
EMBEDDING_MODEL: str = os.environ.get("EMBEDDING_MODEL", "text-embedding-3-small")

OLLAMA_URL: str = os.environ.get("OLLAMA_URL", "http://localhost:11434")

ENVIRONMENT: str = os.environ.get("ENVIRONMENT", "development")


def _load_yaml(filename: str) -> dict:
    path = _CONFIG_DIR / filename
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")
    with open(path) as f:
        return yaml.safe_load(f) or {}


_graph_config: GraphConfig | None = None
_triggers_config: TriggersConfig | None = None


def load_graph_config() -> GraphConfig:
    global _graph_config
    if _graph_config is None:
        raw = _load_yaml("graph.yaml")
        _graph_config = GraphConfig(**raw)
    return _graph_config


def load_triggers_config() -> TriggersConfig:
    global _triggers_config
    if _triggers_config is None:
        raw = _load_yaml("triggers.yaml")
        _triggers_config = TriggersConfig(**raw)
    return _triggers_config


def load_persona(name: str) -> PersonaConfig:
    raw = _load_yaml(f"personas/{name}.yaml")
    return PersonaConfig(**raw)


def load_simulation_config() -> dict:
    return _load_yaml("simulation.yaml")


def load_prompt(name: str) -> str:
    path = _CONFIG_DIR / "prompts" / name
    if not path.exists():
        raise FileNotFoundError(f"Prompt template not found: {path}")
    return path.read_text()


def prompts_dir() -> Path:
    return _CONFIG_DIR / "prompts"


def resolve_model(config_value: str | None, fallback_env: str) -> str:
    if config_value:
        return config_value
    return os.environ.get(fallback_env, LLM_MODEL)
