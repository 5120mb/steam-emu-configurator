from typing import Literal

from pydantic import Field

from custom_types.common import KeyComboStr
from models.common import FrozenModel, FrozenModelWithExtra
from models.emulator import INT_MAX


class UserProvidedEmuConfigAppGeneral(FrozenModel):
    is_beta_branch: Literal[0, 1] = Field(default=0, ge=0, le=1)
    branch_name: str = "public"


class UserProvidedEmuConfigAppDLC(FrozenModelWithExtra):
    unlock_all: Literal[0, 1] = Field(default=1, ge=0, le=1)


class UserProvidedEmuConfigAppController(FrozenModel):
    steam_input: Literal[0, 1] = Field(default=0, ge=0, le=1)
    type: Literal["XBOX360", "XBOXONE", "PS3", "PS4", "PS5", "SWITCH"] = "XBOX360"


class UserProvidedEmuConfigAppPaths(FrozenModelWithExtra):
    # pyrefly: ignore [bad-override, bad-override-mutable-attribute]
    __pydantic_extra__: dict[str, str] = Field(init=False)


class UserProvidedEmuConfigAppCloudSaveGeneral(FrozenModel):
    create_default_dir: Literal[0, 1] = Field(default=0, ge=0, le=1)
    create_specific_dirs: Literal[0, 1] = Field(default=0, ge=0, le=1)


class UserProvidedEmuConfigAppCloudSaveOS(FrozenModelWithExtra):
    # pyrefly: ignore [bad-override]
    __pydantic_extra__: dict[str, str] = Field(init=False)


class UserProvidedEmuConfigAppCloudSaveWin(UserProvidedEmuConfigAppCloudSaveOS):
    pass


class UserProvidedEmuConfigAppCloudSaveLinux(UserProvidedEmuConfigAppCloudSaveOS):
    pass


class UserProvidedEmuConfigMainGeneral(FrozenModel):
    new_app_ticket: Literal[0, 1] = Field(default=1, ge=0, le=1)
    gc_token: Literal[0, 1] = Field(default=1, ge=0, le=1)
    block_unknown_clients: Literal[0, 1] = Field(default=0, ge=0, le=1)
    steam_deck: Literal[0, 1] = Field(default=0, ge=0, le=1)
    enable_account_avatar: Literal[0, 1] = Field(default=0, ge=0, le=1)
    enable_voice_chat: Literal[0, 1] = Field(default=0, ge=0, le=1)
    immediate_gameserver_stats: Literal[0, 1] = Field(default=0, ge=0, le=1)
    matchmaking_server_list_actual_type: Literal[0, 1] = Field(default=0, ge=0, le=1)
    matchmaking_server_details_via_source_query: Literal[0, 1] = Field(default=0, ge=0, le=1)
    crash_printer_location: str = ""


class UserProvidedEmuConfigMainStats(FrozenModel):
    disable_leaderboards_create_unknown: Literal[0, 1] = Field(default=0, ge=0, le=1)
    allow_unknown_stats: Literal[0, 1] = Field(default=0, ge=0, le=1)
    stat_achievement_progress_functionality: Literal[0, 1] = Field(default=1, ge=0, le=1)
    save_only_higher_stat_achievement_progress: Literal[0, 1] = Field(default=1, ge=0, le=1)
    paginated_achievements_icons: int = Field(default=10, ge=-1)
    record_playtime: Literal[0, 1] = Field(default=0, ge=0, le=1)


class UserProvidedEmuConfigMainConnectivity(FrozenModel):
    disable_lan_only: Literal[0, 1] = Field(default=0, ge=0, le=1)
    disable_networking: Literal[0, 1] = Field(default=0, ge=0, le=1)
    listen_port: int = Field(default=47584, gt=0)
    offline: Literal[0, 1] = Field(default=0, ge=0, le=1)
    disable_sharing_stats_with_gameserver: Literal[0, 1] = Field(default=0, ge=0, le=1)
    disable_source_query: Literal[0, 1] = Field(default=0, ge=0, le=1)
    share_leaderboards_over_network: Literal[0, 1] = Field(default=0, ge=0, le=1)
    disable_lobby_creation: Literal[0, 1] = Field(default=0, ge=0, le=1)
    download_steamhttp_requests: Literal[0, 1] = Field(default=0, ge=0, le=1)


class UserProvidedEmuConfigMainMisc(FrozenModel):
    achievements_bypass: Literal[0, 1] = Field(default=0, ge=0, le=1)
    force_steamhttp_success: Literal[0, 1] = Field(default=0, ge=0, le=1)
    disable_steamoverlaygameid_env_var: Literal[0, 1] = Field(default=0, ge=0, le=1)
    enable_steam_preowned_ids: Literal[0, 1] = Field(default=0, ge=0, le=1)
    steam_game_stats_reports_dir: str = ""
    free_weekend: Literal[0, 1] = Field(default=0, ge=0, le=1)
    use_32bit_inventory_item_ids: Literal[0, 1] = Field(default=0, ge=0, le=1)


class UserProvidedEmuConfigOverlayGeneral(FrozenModel):
    enable_experimental_overlay: Literal[0, 1] = Field(default=0, ge=0, le=1)
    hook_delay_sec: int = Field(default=0, ge=0)
    renderer_detector_timeout_sec: int = Field(default=15, ge=0)
    disable_achievement_notification: Literal[0, 1] = Field(default=0, ge=0, le=1)
    disable_friend_notification: Literal[0, 1] = Field(default=0, ge=0, le=1)
    disable_achievement_progress: Literal[0, 1] = Field(default=1, ge=0, le=1)
    disable_warning_any: Literal[0, 1] = Field(default=0, ge=0, le=1)
    disable_warning_bad_appid: Literal[0, 1] = Field(default=0, ge=0, le=1)
    disable_warning_local_save: Literal[0, 1] = Field(default=0, ge=0, le=1)
    upload_achievements_icons_to_gpu: Literal[0, 1] = Field(default=1, ge=0, le=1)
    fps_averaging_window: int = Field(default=10, ge=1)
    overlay_always_show_user_info: Literal[0, 1] = Field(default=0, ge=0, le=1)
    overlay_always_show_fps: Literal[0, 1] = Field(default=0, ge=0, le=1)
    overlay_always_show_frametime: Literal[0, 1] = Field(default=0, ge=0, le=1)
    overlay_always_show_playtime: Literal[0, 1] = Field(default=0, ge=0, le=1)


class UserProvidedEmuConfigOverlayAppearance(FrozenModel):
    Font_Override: str = ""
    Font_Override_Achievement_Title: str = ""
    Font_Override_Achievement_Description: str = ""

    Font_Size: float = Field(default=16.0, gt=0.9)
    Font_Size_FPS: float = Field(default=0.0, ge=0.0)
    Font_Size_Achievement_Title: float = Field(default=0.0, ge=0.0)
    Font_Size_Achievement_Description: float = Field(default=0.0, ge=0.0)
    Font_Achievement_Title_Bold: Literal[0, 1] = Field(default=0, ge=0, le=1)

    Icon_Size: float = Field(default=64.0, gt=0.0)

    Achievement_Notification_Delay: int = Field(default=0, ge=0)
    Achievement_Unlock_Datetime_Format: str = Field(default="%Y/%m/%d - %H:%M:%S", max_length=79)


class UserProvidedEmuConfigOverlayHotkeys(FrozenModel):
    key_combo: KeyComboStr = Field(default="shift + tab")


class UserProvidedEmuConfigUserGeneral(FrozenModel):
    """
    User-provided model needs all fields to be optional because for the user configuration there are scenarios where
    leaving out a field is valid and changes the behavior of the emulator.
    """
    account_name: str | None = None
    account_steamid: int | None = Field(default=None, gt=0, le=INT_MAX)
    ticket: str | None = None
    alt_steamid: int | None = Field(default=None, ge=0, le=INT_MAX)
    alt_steamid_count: int | None = Field(default=None, ge=0)
    language: str | None = None
    ip_country: str | None = None


class UserProvidedEmuConfigUserSaves(FrozenModel):
    """
    User-provided model needs all fields to be optional because for the user configuration there are scenarios where
    leaving out a field is valid and changes the behavior of the emulator.
    """
    local_save_path: str | None = None
    saves_folder_name: str | None = None
