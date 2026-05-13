"""
Pydantic-based configuration management for AgentIQ.

Replaces raw .env hardcoding with structured, validated settings.
Supports environment variables, .env files, and programmatic overrides.

Usage:
    from config.settings import settings
    
    # Access settings
    api_key = settings.openai_api_key
    db_dsn = settings.firebird_dsn
    
    # All settings are validated at startup
"""

from __future__ import annotations

import os
from enum import Enum
from typing import Optional
from pathlib import Path

from pydantic import BaseSettings, Field, validator


class StorageMode(str, Enum):
    """Storage backend selection."""
    MEMORY = "memory"
    FIREBIRD = "firebird"


class LLMProvider(str, Enum):
    """LLM provider selection."""
    OPENAI = "openai"
    NVIDIA = "nvidia"
    ANTHROPIC = "anthropic"


class PipelineConfig(BaseSettings):
    """Pipeline execution configuration."""
    
    # ── Storage ──────────────────────────────────────────────────────────
    storage_mode: StorageMode = Field(
        default=StorageMode.MEMORY,
        description="Storage backend: 'memory' (fast, in-process) or 'firebird' (persistent)"
    )
    
    # ── LLM Configuration ────────────────────────────────────────────────
    llm_provider: LLMProvider = Field(
        default=LLMProvider.OPENAI,
        description="LLM provider: 'openai', 'nvidia', or 'anthropic'"
    )
    
    openai_api_key: Optional[str] = Field(
        default=None,
        description="OpenAI API key (required if llm_provider=openai)"
    )
    
    openai_model: str = Field(
        default="gpt-4o-mini",
        description="OpenAI model ID (e.g., 'gpt-4o-mini', 'gpt-4-turbo')"
    )
    
    nvidia_api_key: Optional[str] = Field(
        default=None,
        description="NVIDIA API key (required if llm_provider=nvidia)"
    )
    
    nvidia_model_id: str = Field(
        default="minimax/minimax-m2-text",
        description="NVIDIA model ID"
    )
    
    anthropic_api_key: Optional[str] = Field(
        default=None,
        description="Anthropic API key (required if llm_provider=anthropic)"
    )
    
    llm_temperature: float = Field(
        default=0.3,
        description="LLM temperature (0.0-1.0, lower = more deterministic)"
    )
    
    llm_max_tokens: int = Field(
        default=4096,
        description="Maximum tokens per LLM response"
    )
    
    # ── Firebird Database ────────────────────────────────────────────────
    firebird_dsn: Optional[str] = Field(
        default=None,
        description="Firebird database path (e.g., 'C:\\path\\to\\database.fdb')"
    )
    
    firebird_user: str = Field(
        default="SYSDBA",
        description="Firebird database user"
    )
    
    firebird_password: Optional[str] = Field(
        default=None,
        description="Firebird database password"
    )
    
    firebird_charset: str = Field(
        default="UTF8",
        description="Firebird character set"
    )
    
    # ── LangSmith Observability ──────────────────────────────────────────
    langsmith_api_key: Optional[str] = Field(
        default=None,
        description="LangSmith API key for tracing and monitoring"
    )
    
    langsmith_project: str = Field(
        default="agentiq-pipeline",
        description="LangSmith project name"
    )
    
    langchain_tracing_v2: bool = Field(
        default=False,
        description="Enable LangChain tracing v2"
    )
    
    # ── Pipeline Behavior ────────────────────────────────────────────────
    enable_revision_loop: bool = Field(
        default=True,
        description="Enable self-review loop for agents"
    )
    
    max_iterations_per_agent: int = Field(
        default=1,
        description="Maximum iterations per agent (for speed, default=1)"
    )
    
    enable_human_in_loop: bool = Field(
        default=False,
        description="Enable human-in-the-loop approval gates"
    )
    
    # ── Data Paths ───────────────────────────────────────────────────────
    data_dir: Path = Field(
        default=Path("data"),
        description="Root directory for data storage"
    )
    
    raw_data_dir: Path = Field(
        default=Path("data/raw"),
        description="Directory for raw uploaded datasets"
    )
    
    cleaned_data_dir: Path = Field(
        default=Path("data/cleaned"),
        description="Directory for cleaned datasets"
    )
    
    engineered_data_dir: Path = Field(
        default=Path("data/engineered"),
        description="Directory for feature-engineered datasets"
    )
    
    # ── API Configuration ────────────────────────────────────────────────
    api_host: str = Field(
        default="0.0.0.0",
        description="API server host"
    )
    
    api_port: int = Field(
        default=8000,
        description="API server port"
    )
    
    api_reload: bool = Field(
        default=True,
        description="Enable auto-reload for development"
    )
    
    # ── Logging ──────────────────────────────────────────────────────────
    log_level: str = Field(
        default="INFO",
        description="Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)"
    )
    
    log_file: Optional[Path] = Field(
        default=None,
        description="Log file path (None = console only)"
    )
    
    class Config:
        """Pydantic config."""
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False
        
        # Allow environment variables to override .env
        env_nested_delimiter = "__"
    
    @validator("openai_api_key")
    def validate_openai_key(cls, v, values):
        """Validate OpenAI API key if provider is OpenAI."""
        if values.get("llm_provider") == LLMProvider.OPENAI and not v:
            raise ValueError("openai_api_key required when llm_provider=openai")
        return v
    
    @validator("firebird_dsn")
    def validate_firebird_dsn(cls, v, values):
        """Validate Firebird DSN if storage mode is Firebird."""
        if values.get("storage_mode") == StorageMode.FIREBIRD and not v:
            raise ValueError("firebird_dsn required when storage_mode=firebird")
        return v
    
    @validator("llm_temperature")
    def validate_temperature(cls, v):
        """Validate temperature is between 0 and 1."""
        if not 0.0 <= v <= 1.0:
            raise ValueError("llm_temperature must be between 0.0 and 1.0")
        return v
    
    @validator("max_iterations_per_agent")
    def validate_max_iterations(cls, v):
        """Validate max iterations is positive."""
        if v < 1:
            raise ValueError("max_iterations_per_agent must be >= 1")
        return v
    
    @validator("api_port")
    def validate_port(cls, v):
        """Validate port is in valid range."""
        if not 1 <= v <= 65535:
            raise ValueError("api_port must be between 1 and 65535")
        return v
    
    def get_firebird_connection_string(self) -> str:
        """Build Firebird connection string."""
        if self.storage_mode != StorageMode.FIREBIRD:
            raise ValueError("Firebird not configured (storage_mode != firebird)")
        
        return (
            f"firebird://{self.firebird_user}:{self.firebird_password}"
            f"@{self.firebird_dsn}?charset={self.firebird_charset}"
        )
    
    def get_openai_client_kwargs(self) -> dict:
        """Get kwargs for OpenAI client initialization."""
        return {
            "api_key": self.openai_api_key,
        }
    
    def get_llm_config(self) -> dict:
        """Get LLM configuration dict."""
        return {
            "provider": self.llm_provider.value,
            "model": (
                self.openai_model if self.llm_provider == LLMProvider.OPENAI
                else self.nvidia_model_id if self.llm_provider == LLMProvider.NVIDIA
                else "claude-3-sonnet"
            ),
            "temperature": self.llm_temperature,
            "max_tokens": self.llm_max_tokens,
        }


# ── Global Settings Instance ─────────────────────────────────────────────
# Load from .env file and environment variables
settings = PipelineConfig()


# ── Convenience Functions ────────────────────────────────────────────────

def get_settings() -> PipelineConfig:
    """Get global settings instance."""
    return settings


def validate_settings() -> bool:
    """Validate all settings at startup."""
    try:
        # Check required keys
        if settings.llm_provider == LLMProvider.OPENAI:
            if not settings.openai_api_key:
                raise ValueError("OPENAI_API_KEY not set")
        
        if settings.storage_mode == StorageMode.FIREBIRD:
            if not settings.firebird_dsn:
                raise ValueError("FIREBIRD_DSN not set")
        
        # Check data directories exist
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        settings.raw_data_dir.mkdir(parents=True, exist_ok=True)
        settings.cleaned_data_dir.mkdir(parents=True, exist_ok=True)
        settings.engineered_data_dir.mkdir(parents=True, exist_ok=True)
        
        return True
    except Exception as e:
        print(f"Settings validation failed: {e}")
        return False


# ── Example Usage ────────────────────────────────────────────────────────

if __name__ == "__main__":
    """Print current settings (for debugging)."""
    print("AgentIQ Configuration")
    print("=" * 60)
    print(f"Storage Mode: {settings.storage_mode.value}")
    print(f"LLM Provider: {settings.llm_provider.value}")
    print(f"LLM Model: {settings.openai_model}")
    print(f"LLM Temperature: {settings.llm_temperature}")
    print(f"Enable Revision Loop: {settings.enable_revision_loop}")
    print(f"Max Iterations: {settings.max_iterations_per_agent}")
    print(f"Enable Human-in-Loop: {settings.enable_human_in_loop}")
    print(f"API Host: {settings.api_host}:{settings.api_port}")
    print(f"Log Level: {settings.log_level}")
    print(f"Data Directory: {settings.data_dir}")
    print(f"LangSmith Project: {settings.langsmith_project}")
    print(f"LangChain Tracing V2: {settings.langchain_tracing_v2}")
    print("=" * 60)
    
    # Validate
    if validate_settings():
        print("✅ All settings validated successfully")
    else:
        print("❌ Settings validation failed")

