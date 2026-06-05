import os
import tempfile
from typing import Any

from pydantic import BaseModel, Field, field_validator

from custom_types.common import OutputDirRelations
from models.steam import SteamStatInfo


class AppConfig(BaseModel, validate_assignment=True):
    """
    Attributes:
        output_dir: Output directory.
            This will always point to the steam_settings path, wherever the correct location should be.
        lib_locations: List of full filepaths to the game's steam DLL (either steam_api or steamclient) files.
        output_dir_is_base: Whether to treat the specified output directory as a base and construct the
            output directory from it.
        output_dir_relations: Dictionary of relations between the output directory (including "steam_settings" dir)
            and the game's DLLs/SOs fullpath.
    """
    appid: str | None
    buildid: str | None = None  # we are not using this at the moment
    output_dir: str | None
    orig_output_dir: str | None
    game_dir: str | None
    package_dir: str | None
    do_not_ask: bool
    api_key: str | None
    preferred_language: str
    log_file: str | None = None
    log_level: str
    include_emulator: bool

    rename_package_dir: bool
    only_rename: bool
    add_language_flag_on_rename: bool

    output_dir_is_base: bool
    archive_password: str | None
    use_steam_for_stats: bool
    tools_path: str
    fallback_to_steam: bool
    fail_if_no_dll: bool
    compress_config: bool
    compressed_filename: str | None
    skip_achievements: bool
    skip_stats: bool
    update_config_package: bool
    add_user_config: bool

    directory_to_compress: str | None = None
    lib_locations: list[str] | None = None
    extracted_files_path: str | None = None
    sanitized_language: str = ""
    fallback_language_used: bool = False
    acf_files: set[str] | None = None
    output_dir_relations: dict[str, list[str]] | dict[str, None] | None = None
    tried_extracting_package_files: bool = False
    tmp_dir: str = Field(default_factory=lambda: tempfile.mkdtemp(prefix="steam-emu-configurator_"))

    is_linux: bool = False
    add_early_access_label: bool = False
    custom_early_access_label: str | None = None

    cache_game_info: bool
    cache_location: str
    force_achievement_icon_download: bool
    copy_cache_back: bool

    include_dll: list[str]

    @field_validator("output_dir", "orig_output_dir", "game_dir", "package_dir", mode="after")
    @classmethod
    def sanitize_path(cls,
                      value: str | None) -> str | None:
        if value is not None:
            return os.path.abspath(os.path.normpath(value))
        return value

    @field_validator("include_dll", mode="before")
    @classmethod
    def normalize_include_dll(cls,
                              value: Any) -> list[str] | Any:
        if value is None:
            return []
        else:
            return value


class MinAppConfig(BaseModel, validate_assignment=True):
    output_dir: str | None
    orig_output_dir: str | None
    game_dir: str | None
    package_dir: str | None
    do_not_ask: bool
    api_key: str | None
    log_file: str | None = None
    log_level: str
    include_emulator: bool

    rename_package_dir: bool
    only_rename: bool
    add_language_flag_on_rename: bool

    output_dir_is_base: bool
    archive_password: str | None
    use_steam_for_stats: bool
    tools_path: str
    fallback_to_steam: bool
    fail_if_no_dll: bool
    compress_config: bool
    compressed_filename: str | None
    skip_achievements: bool
    skip_stats: bool
    update_config_package: bool
    add_user_config: bool

    add_early_access_label: bool = False
    custom_early_access_label: str | None = None

    include_dll: list[str]


class CacheOptions(BaseModel, validate_assignment=True):
    cache_game_info: bool
    cache_location: str
    force_achievement_icon_download: bool
    copy_cache_back: bool


class AchievementOptions(BaseModel, validate_assignment=True):
    appid: str
    api_key: str
    output_dir_relations: OutputDirRelations
    stat_info: SteamStatInfo
    acf_files: set[str] | None


class LanguageOptions(BaseModel, validate_assignment=True):
    preferred_language: str
    sanitized_language: str

    fallback_language_used: bool = False

    supported_languages: set[str] | None = None


class RuntimeData(BaseModel, validate_assignment=True):
    directory_to_compress: str | None = None
    lib_locations: list[str] | None = None
    extracted_files_path: str | None = None
    acf_files: set[str] | None = None
    output_dir_relations: dict[str, list[str]] | dict[str, None] | None = None
    tried_extracting_package_files: bool = False
    tmp_dir: str = Field(default_factory=lambda: tempfile.mkdtemp(prefix="steam-emu-configurator_"))


class GameDetails(BaseModel, validate_assignment=True):
    appid: str | None
    buildid: str | None = None
    is_linux: bool = False


class DataFile(BaseModel, validate_assignment=True):
    EXECUTABLES_TO_IGNORE: list[str] = Field(default_factory=list)
    SEVENZIP_LIST_WILDCARD_PATTERNS: list[str] = Field(default_factory=list)
