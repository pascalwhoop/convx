from __future__ import annotations

import tomllib
from pathlib import Path

from pydantic import BaseModel, Field, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict

CONFIG_REFERENCE_URL = "https://github.com/pascalwhoop/convx/blob/main/src/convx_ai/config.py"


class SyncDefaults(BaseModel):
    source_system: str = "all"
    input_path: str | None = None
    user: str | None = None
    system_name: str | None = None
    history_subpath: str = ".ai/history"
    dry_run: bool = False
    redact: bool = True
    with_context: bool = False
    with_thinking: bool = False
    skip_if_contains: str = "CONVX_NO_SYNC"
    overwrite: bool = False


class BackupDefaults(BaseModel):
    source_system: str = "all"
    input_path: str | None = None
    user: str | None = None
    system_name: str | None = None
    history_subpath: str = "history"
    dry_run: bool = False
    redact: bool = True
    with_context: bool = False
    with_thinking: bool = False
    skip_if_contains: str = "CONVX_NO_SYNC"
    overwrite: bool = False


class HooksDefaults(BaseModel):
    history_subpath: str = "history"


class WordStatsDefaults(BaseModel):
    history_subpath: str = "history"


class SanitizeDefaults(BaseModel):
    keywords: list[str] = Field(default_factory=list)


class ConvxConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="CONVX_",
        env_nested_delimiter="__",
        extra="ignore",
    )

    sync: SyncDefaults = Field(default_factory=SyncDefaults)
    backup: BackupDefaults = Field(default_factory=BackupDefaults)
    hooks: HooksDefaults = Field(default_factory=HooksDefaults)
    word_stats: WordStatsDefaults = Field(default_factory=WordStatsDefaults)
    sanitize: SanitizeDefaults = Field(default_factory=SanitizeDefaults)

    @classmethod
    def for_repo(cls, repo_path: Path) -> "ConvxConfig":
        config_path = repo_path / ".convx" / "config.toml"
        if not config_path.exists():
            return cls()
        try:
            with config_path.open("rb") as f:
                data = tomllib.load(f)
        except (tomllib.TOMLDecodeError, OSError):
            return cls()
        if not isinstance(data, dict):
            return cls()
        try:
            return cls.model_validate(data)
        except ValidationError:
            return cls()


def create_config_if_missing(repo_path: Path) -> Path:
    config_path = repo_path / ".convx" / "config.toml"
    if config_path.exists():
        return config_path
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        (
            "# convx configuration\n"
            "# Reference: "
            f"{CONFIG_REFERENCE_URL}\n"
            "# Add sections like [sync], [backup], [sanitize] to override defaults.\n"
        ),
        encoding="utf-8",
    )
    return config_path
