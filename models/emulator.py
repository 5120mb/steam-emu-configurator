import secrets
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from custom_types.common import KeyComboStr
from models.common import AllowExtraBaseModel, AllowExtraStrBaseModel

INT_MAX: int = 2_147_483_647


def generate_account_id() -> int:
    return secrets.randbelow(INT_MAX) + 1


class EmuConfigAppGeneral(BaseModel, validate_assignment=True):
    """
    Attributes:
        is_beta_branch: Report the game branch as beta.

        branch_name: The name of the current branch, it must also exist in the branches.json file, or it will be
            ignored and "public" will be used instead.
    """
    is_beta_branch: Literal[0, 1] = Field(default=0, ge=0, le=1)
    branch_name: str = "public"


class EmuConfigAppDLC(AllowExtraBaseModel, validate_assignment=True):
    """
    | The DLC listing format is:
    | *DLC_ID* = *DLC_NAME*

    Attributes:
        unlock_all: Whether to report all DLCs as unlocked or only the ones listed. 0: Only the listed, 1: Report all.
            Some games check for hidden DLCs, so sometimes this is needed, but other games do emulator detection by
            querying fake DLCs which in such cases this should be disabled.

        _DLC_ID_: The DLCs available for the game
    """
    unlock_all: Literal[0, 1] = Field(default=1, ge=0, le=1)


class EmuConfigAppController(BaseModel, validate_assignment=True):
    """
    Attributes:
        steam_input: Whether to enable SteamInput.
            SteamInput is automatically enabled when there are action sets in `steam_settings\\controller\\`.

        type: Override the controller type reported to SteamInput.
    """
    steam_input: Literal[0, 1] = Field(default=0, ge=0, le=1)
    type: Literal["XBOX360", "XBOXONE", "PS3", "PS4", "PS5", "SWITCH"] = "XBOX360"


class EmuConfigAppPaths(BaseModel, validate_assignment=True):
    """
    Some rare games might need to be provided one or more paths to appids, for example, the path to where a DLC is
    installed. This sets the paths returned by the `Steam_Apps::GetAppInstallDir` function.

    However, some other games might expect this function to return empty paths to properly load DLCs. You can
    deliberately set the path to be empty to specify this behavior.

    | The appid and path listing format is:
    | *APP_ID* = *PATH*

    Attributes:
        _APP_ID_: The appid of the DLC and its path as the value.
    """

    # pyrefly: ignore [bad-override-mutable-attribute]
    __pydantic_extra__: dict[str, str] = Field(init=False)

    model_config = ConfigDict(extra="allow")


class EmuConfigAppCloudSaveGeneral(BaseModel, validate_assignment=True):
    """
    Attributes:
        create_default_dir: Should the emulator create the default directory for cloud saves on startup:
            **[Steam Install]/userdata/{Steam3AccountID}/{AppID}/**

        create_specific_dirs: Should the emulator create the directories specified in the cloud saves section of the
            current OS on startup.
    """
    create_default_dir: Literal[0, 1] = Field(default=0, ge=0, le=1)
    create_specific_dirs: Literal[0, 1] = Field(default=0, ge=0, le=1)


class EmuConfigAppCloudSaveOS(AllowExtraStrBaseModel, validate_assignment=True):
    """
    Directories that should be created on startup, this is used for cloud saves.
    Some games refuse to work unless these directories exist.
    There are reserved identifiers that are replaced at runtime, you can find a list of them here:
    https://partner.steamgames.com/doc/features/cloud#setup

    | The identifiers must be wrapped with double colons "::" like this:
    | original value: `{SteamCloudDocuments}`
    | ini value: `{::SteamCloudDocuments::}`

    Notice the braces "{" and "}", they are not changed, the double colons are added between them as shown above-

    Attributes:
        _dir#_: The directory to create for cloud saves on the corresponding OS.
            The field name can be anything, it doesn't really matter. Empty values are ignored.
    """
    dir1: str = ""


class EmuConfigAppCloudSaveWin(EmuConfigAppCloudSaveOS):
    pass


class EmuConfigAppCloudSaveLinux(EmuConfigAppCloudSaveOS):
    pass


class EmuConfigApp(BaseModel, validate_assignment=True):
    app__general: EmuConfigAppGeneral = Field(serialization_alias="app::general")
    app__dlcs: EmuConfigAppDLC = Field(serialization_alias="app::dlcs")
    app__controller: EmuConfigAppController = Field(serialization_alias="app::controller")
    app__paths: EmuConfigAppPaths = Field(serialization_alias="app::paths")
    app__cloud_save__general: EmuConfigAppCloudSaveGeneral = Field(serialization_alias="app::cloud_save::general")
    app__cloud_save__win: EmuConfigAppCloudSaveWin = Field(serialization_alias="app::cloud_save::win")
    app__cloud_save__linux: EmuConfigAppCloudSaveLinux = Field(serialization_alias="app::cloud_save::linux")


class EmuConfigMainGeneral(BaseModel, validate_assignment=True):
    """
    All options must be set to 0 to disable or 1 to enable.

    Attributes:
        new_app_ticket: Generate a newer version of auth ticket, used by some modern apps.

        gc_token: Generate/embed Game Coordinator token inside the new auth ticket.

        block_unknown_clients: If enabled, the game server will only allow connections from legit Steam clients and
            known Steam emulators.

        steam_deck: Pretend the app is running on a steam deck.
            **Warning**: This option is deprecated and may be removed in the future. Please use the
            `steam_hardware_type` option instead.

        enable_account_avatar: Enable avatar functionality.

        enable_voice_chat: Enable the experimental voice chat feature.
            This may result in higher system usage and cause performance drops or cause crashes.

        immediate_gameserver_stats: Synchronize user stats/achievements with game servers as soon as possible instead
            of caching them until the next call to `Steam_RunCallbacks()`.
            **Not recommended to enable this.**

        matchmaking_server_list_actual_type: Use the proper type of the server list (internet, friends, etc...) when
            requested by the game. If disabled: always return the type of the server list as "LAN server".
            **Not recommended to enable this.**

        matchmaking_server_details_via_source_query: Grab the server details for matchmaking using an actual server
            query. If disabled: use the info from the local network messages shared between client/server.
            **Not recommended to enable this, currently breaks some games.**

        crash_printer_location: Path to a file where to log. Very basic crash logger/printer. This is intended to
            debug some annoying scenarios and best used with the debug build of the emu.

        steam_hardware_type: Pretend the app is running on a Steam hardware device.
            Possible hardware list: 0 (Not on a Steam hardware device), 1 (Steam deck), 2 (Steam Machine),
            3 (Steam Frame)

        steam_hardware_default_config: Set the default configuration for a Steam hardware device used by
            `Steam_Utils::GetSteamHardwareDefaultConfig()`. The emulator can auto-parse this option if
            `steam_hardware_type` is set to a valid device and `steam_hardware_default_config` is left untouched.
            Possible values: 0 (not set), 1 (low), 2 (medium), 3 (high), 4 (max), 5 (Steam Deck), 6 (Steam Machine),
            7 (Steam Frame)

        is_under_proton: Pretend the app is running on proton.
    """
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
    steam_hardware_type: Literal[0, 1, 2, 3] = Field(default=0, ge=0, le=3)
    # pyrefly: ignore [bad-assignment]
    steam_hardware_default_config: Literal[0, 1, 2, 3, 4, 5, 6, 7] = Field(default=0, ge=0, le=7)
    is_under_proton: Literal[0, 1] = Field(default=0, ge=0, le=1)


class EmuConfigMainStats(BaseModel, validate_assignment=True):
    """
    Most options must be set to 0 to disable or 1 to enable.

    Attributes:
        disable_leaderboards_create_unknown: Prevent `Steam_User_Stats::FindLeaderboard()` from always succeeding and
            creating the unknown leaderboard.
            **Not recommended to enable this.**

        allow_unknown_stats: Allow unknown stats to be saved/updated. By default, the emulator will only save/update
            stats defined by the user, unknown stats requested or updated by the game are rejected.

        stat_achievement_progress_functionality: The emulator has an internal extra functionality which reports an
            achievement's progress when a stat tied to an achievement is updated, also the progress is saved to
            disk (usual local storage folder for the current appid) so that external applications can watch these
            updates. Only used internally for a stat tied to an achievement, the normal achievement progress
            requests made by the game are not impacted, some applications tie many stats to achievements, and update
            these stats very frequently, causing spam of disk writes and overlay popups; in that case you can
            disable this functionality, but the stat progress won't be saved or displayed in the overlay.

        save_only_higher_stat_achievement_progress: Save stat achievement progress value only if it is higher than
            the current one.
            If disabled, the emulator will save any stat achievement progress value (higher or lower).
            Whenever a game updates a stat which is tied to an achievement's progress, the emulator will save that
            progress immediately to disk. However, some games will update the stat very frequently (with lower and
            higher values) resulting in spam of disk writes or overlay notifications.
            This has no impact on the stat itself; only the achievement progress, it also has no impact on the
            functions which directly change stats, achievements, or achievement progress.

        paginated_achievements_icons: How many icons to load in memory.
            If set to **0**, the icon will be loaded into memory only when it's requested.
            Set to **-1** to disable this functionality (`ISteamUserStats::GetAchievementIcon()` and the overlay won't
            be able to use icons).
            The emulator loads the achievement icons in memory. This is needed for APIs like
            `ISteamUserStats::GetAchievementIcon()` and the overlay.
            The loaded icon size is controlled by the *Icon_Size* attribute of *EmuConfigOverlayAppearance*.
            This value controls how many icons to load each iteration when the periodic callback of the emu is
            triggered or when the app/game calls `SteamAPI_RunCallbacks()`.
            Each achievement has 2 icons, one when it's locked and another when it's unlocked, so a value of 10 means
            loading 20 icons. **Increasing this value will cause a huge startup delay.**

        record_playtime: Enable the functionality that allows the emulator to record the user's playtime.
            This will create a file named "playtime.txt" in the game's GSE Saves folder.
            The recorded playtime will be updated every minute, the emulator will also resume recording playtime when
            the game is relaunched.

        pause_total_when_unfocused: When enabled, total playtime pauses when the game's window loses focus (on ALT+TAB).

        pause_session_when_unfocused: When enabled, session playtime pauses when the game's window loses focus
            (on ALT+TAB).
    """
    disable_leaderboards_create_unknown: Literal[0, 1] = Field(default=0, ge=0, le=1)
    allow_unknown_stats: Literal[0, 1] = Field(default=0, ge=0, le=1)
    stat_achievement_progress_functionality: Literal[0, 1] = Field(default=1, ge=0, le=1)
    save_only_higher_stat_achievement_progress: Literal[0, 1] = Field(default=1, ge=0, le=1)
    paginated_achievements_icons: int = Field(default=10, ge=-1)
    record_playtime: Literal[0, 1] = Field(default=0, ge=0, le=1)
    pause_total_when_unfocused: Literal[0, 1] = Field(default=0, ge=0, le=1)
    pause_session_when_unfocused: Literal[0, 1] = Field(default=0, ge=0, le=1)


class EmuConfigMainConnectivity(BaseModel, validate_assignment=True):
    """
    All options (except listen_port) must be set to 0 to disable or 1 to enable.

    Attributes:
        disable_lan_only: Prevent hooking OS networking APIs and allow any external requests only used by the
            experimental builds on **Windows**.

        disable_networking: Disable all the Steam networking interface functionality, this won't prevent games/apps
            from making external requests.
            Networking-related functionality like lobbies or those that launch a server in the background will not work.

        listen_port: Change the UDP/TCP port the emulator listens on, you should probably not change this because
            everyone needs to use the same port, or you won't find yourselves on the network.

        offline: Pretend Steam is running in offline mode. Mainly affects the function `ISteamUser::BLoggedOn()`.
            Some games that connect to online servers might only work if the emulator behaves like Steam when it's in
            offline mode.

        disable_sharing_stats_with_gameserver: Prevent sharing stats and achievements with any game server,
            this also disables the interface `ISteamGameServerStats`.

        disable_source_query: Don't send server details to the server browser. Only works for game servers.

        share_leaderboards_over_network: Enable sharing leaderboard scores with people playing the same game on the
            same network. *Not ideal and synchronization isn't perfect.*

        disable_lobby_creation: Prevent lobby creation in the steam matchmaking interface.

        download_steamhttp_requests: Attempt to download external HTTPs requests made via
            `Steam_HTTP::SendHTTPRequest()` inside **steam_settings/http/**. Make sure to enable *disable_lan_only*
            and to disable *disable_networking*. This will **not** work if the app is using native/OS web APIs.
    """
    disable_lan_only: Literal[0, 1] = Field(default=0, ge=0, le=1)
    disable_networking: Literal[0, 1] = Field(default=0, ge=0, le=1)
    listen_port: int = Field(default=47584, gt=0)
    offline: Literal[0, 1] = Field(default=0, ge=0, le=1)
    disable_sharing_stats_with_gameserver: Literal[0, 1] = Field(default=0, ge=0, le=1)
    disable_source_query: Literal[0, 1] = Field(default=0, ge=0, le=1)
    share_leaderboards_over_network: Literal[0, 1] = Field(default=0, ge=0, le=1)
    disable_lobby_creation: Literal[0, 1] = Field(default=0, ge=0, le=1)
    download_steamhttp_requests: Literal[0, 1] = Field(default=0, ge=0, le=1)


class EmuConfigMainMisc(BaseModel, validate_assignment=True):
    """
    These are workarounds for specific problems.
    Set to 0 to disable or 1 to enable.

    Attributes:
        achievements_bypass: Force `ISteamUserStats::SetAchievement()` to always return true.
            This is a workaround for some games that otherwise won't work.

        force_steamhttp_success: Force the function `Steam_HTTP::SendHTTPRequest()` to always succeed.

        disable_steamoverlaygameid_env_var: Don't write env var `SteamOverlayGameId`, allowing Steam Input to work.
            The env var `SteamOverlayGameId` breaks Steam Input when the game is added to Steam as a non-steam game.

        enable_steam_preowned_ids: Add many Steam apps to the list of owned DLCs and to the emulator's list of
            installed app IDs. Useful for many Source-based games.
            See: https://developer.valvesoftware.com/wiki/Steam_Application_IDs and
            https://developer.valvesoftware.com/wiki/Dedicated_Servers_List

        steam_game_stats_reports_dir: Some Source-based games use the interface `ISteamGameStats` to report some
            stats. The emulator can save this data to a folder. If set, the emulator will create the folders if it's
            missing, but the path specified must be writable.

        free_weekend: Some games may have extra bonuses/achievements when being or playing with a free-weekend player.

        use_32bit_inventory_item_ids: Very old versions of Team Fortress 2 don't properly handle 64-bit item IDs,
            this workaround makes Goldberg only generate 32-bit item IDs.
    """
    achievements_bypass: Literal[0, 1] = Field(default=0, ge=0, le=1)
    force_steamhttp_success: Literal[0, 1] = Field(default=0, ge=0, le=1)
    disable_steamoverlaygameid_env_var: Literal[0, 1] = Field(default=0, ge=0, le=1)
    enable_steam_preowned_ids: Literal[0, 1] = Field(default=0, ge=0, le=1)
    steam_game_stats_reports_dir: str = ""
    free_weekend: Literal[0, 1] = Field(default=0, ge=0, le=1)
    use_32bit_inventory_item_ids: Literal[0, 1] = Field(default=0, ge=0, le=1)


class EmuConfigMain(BaseModel, validate_assignment=True):
    main__general: EmuConfigMainGeneral = Field(serialization_alias="main::general")
    main__stats: EmuConfigMainStats = Field(serialization_alias="main::stats")
    main__connectivity: EmuConfigMainConnectivity = Field(serialization_alias="main::connectivity")
    main__misc: EmuConfigMainMisc = Field(serialization_alias="main::misc")


class EmuConfigOverlayGeneral(BaseModel, validate_assignment=True):
    """
    Most options must be set to 0 to disable or 1 to enable.

    Attributes:
        enable_experimental_overlay: Enable the experimental overlay, might cause crashes.

        hook_delay_sec: Amount of time to wait before attempting to detect and hook the renderer
            (DirectX, OpenGL, etc.).

        renderer_detector_timeout_sec: Timeout for the renderer detector.

        disable_achievement_notification: Disable the achievement notifications.

        disable_friend_notification: Disable friend invitations and message notifications.

        disable_achievement_progress: Disable showing notifications for achievements' progress.

        disable_warning_any: Disable any warning in the overlay.

        disable_warning_bad_appid: Disable the bad app ID warning in the overlay.

        disable_warning_local_save: Disable the local_save warning in the overlay.

        upload_achievements_icons_to_gpu: Attempt to upload the achievement icons to the GPU. If disabled,
            achievement icons won't be displayed in the overlay. This is done so that the icons are displayed in the
            overlay, in rare cases this might keep failing and cause FPS drops.

        fps_averaging_window: Amount of frames to accumulate, to eventually calculate the average frametime (in
            milliseconds). The minimum possible value is 1.
            Lower values would result in instantaneous frametime/fps, but the FPS would be erratic.
            Higher values would result in a more stable frametime/fps, but will be inaccurate due to averaging over
            a long time.

        overlay_always_show_user_info: Always show user info in the overlay.

        overlay_always_show_fps: Always show fps in the overlay.

        overlay_always_show_frametime: Always show frametime in the overlay.

        overlay_always_show_playtime: Always show playtime in the overlay.

        enable_screenshot: Enable the F12 screenshot feature, whether it is enabled or not the gallery/pins remain
            available.

        show_button_user_info: Show the button on the overlay.

        show_button_achievements: Show the button on the overlay.

        show_button_test_achievement: Show the button on the overlay.

        show_button_copy_id: Show the button on the overlay.

        show_button_screenshots: Show the button on the overlay.

        show_button_history: Show the button on the overlay.

        show_button_settings: Show the button on the overlay.

        show_checkbox_fps: Show the checkbox on the overlay.

        show_checkbox_frametime: Show the checkbox on the overlay.

        show_checkbox_playtime: Show the checkbox on the overlay.
    """
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
    enable_screenshot: Literal[0, 1] = Field(default=1, ge=0, le=1)
    show_button_user_info: Literal[0, 1] = Field(default=1, ge=0, le=1)
    show_button_achievements: Literal[0, 1] = Field(default=1, ge=0, le=1)
    show_button_test_achievement: Literal[0, 1] = Field(default=1, ge=0, le=1)
    show_button_copy_id: Literal[0, 1] = Field(default=1, ge=0, le=1)
    show_button_screenshots: Literal[0, 1] = Field(default=1, ge=0, le=1)
    show_button_history: Literal[0, 1] = Field(default=1, ge=0, le=1)
    show_button_settings: Literal[0, 1] = Field(default=1, ge=0, le=1)
    show_checkbox_fps: Literal[0, 1] = Field(default=1, ge=0, le=1)
    show_checkbox_frametime: Literal[0, 1] = Field(default=1, ge=0, le=1)
    show_checkbox_playtime: Literal[0, 1] = Field(default=1, ge=0, le=1)


class EmuConfigOverlayAppearance(BaseModel, validate_assignment=True):
    """
    Attributes:
        Font_Override: Load custom TrueType font from a path, it could be absolute, or relative.
            Relative paths will be looked up inside the local folder **steam_settings/fonts** first, if that isn't
            found, it will be looked up inside the global folder **GSE Settings/settings/fonts**.

        Font_Override_Achievement_Title: Custom font for achievement title. Leave empty to use the default font.

        Font_Override_Achievement_Description: Custom font for achievement description.
            Leave empty to use the default font.

        Font_Size: Global font size.
            For the built-in font, a multiple of 16 is recommended.
            E.g.: 16, 32...

        Font_Size_FPS: Optional independent font size. Less or equal than 0 uses **Font_Size**.

        Font_Size_Achievement_Title: Optional independent font size. Less or equal than 0 uses **Font_Size**.

        Font_Size_Achievement_Description: Optional independent font size. Less or equal than 0 uses **Font_Size**.

        Font_Achievement_Title_Bold: Bold font for achievement title.

        Icon_Size: Achievement icon size.

        Achievement_Notification_Delay: Minimum time interval between achievement notifications (in seconds).
            Set to 0 to show all achievements immediately without delay.

        Achievement_Unlock_Datetime_Format: Format for the achievement unlock date/time, limited to 79 characters.
            If the output formatted string exceeds this limit, the built-in format will be used.
            Look for the format here: https://en.cppreference.com/w/cpp/chrono/c/strftime

        Screenshot_Datetime_Format: Same as **Achievement_Unlock_Datetime_Format**, but for screenshots.
    """
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
    Screenshot_Datetime_Format: str = Field(default="%Y/%m/%d - %H:%M:%S", max_length=79)


class EmuConfigOverlayHotkeys(BaseModel, validate_assignment=True):
    """
    Attributes:
        key_combo: Combination of keys used to show/hide the overlay.
                    Available values:
                        - shift
                        - ctrl
                        - alt
                        - tab
                        - fn1
                        - fn2
                        - ...
                        - ...
                        - fn12
                    You can use the '+' sign to combine multiple keys.
                    Example: ctrl + shift + fn5

        screenshot_combo: Combination of keys used to take a screenshot (same syntax as key_combo).
    """
    key_combo: KeyComboStr = Field(default="shift + tab")
    screenshot_combo: KeyComboStr = Field(default="fn12")


class EmuConfigOverlay(BaseModel, validate_assignment=True):
    overlay__general: EmuConfigOverlayGeneral = Field(serialization_alias="overlay::general")
    overlay__hotkeys: EmuConfigOverlayHotkeys = Field(serialization_alias="overlay::hotkeys")
    overlay__appearance: EmuConfigOverlayAppearance = Field(serialization_alias="overlay::appearance")


class EmuConfigUserGeneral(BaseModel, validate_assignment=True):
    """
    Attributes:
        account_name: User account name.

        account_steamid: Your account ID in Steam64 format, if the specified ID is invalid, the emulator will ignore it
            and generate a proper one.

        ticket: Base64 Ticket.

        alt_steamid: Alt SteamId for encrypted savegames. Set to `0` to disable.

        alt_steamid_count: How many calls before swapping out the SteamId to Alt.
            IT WILL REPLACE IT AFTER THOSE CALLS. BE AWARE!

        language: The language reported to the app/game. This must exist in the **supported_languages.txt** file,
            otherwise it will be ignored by the emulator.

        ip_country: Report a country IP if the game queries it. ISO 3166-1-alpha-2 format.
    """
    account_name: str = "gse orca"
    account_steamid: int = Field(default_factory=lambda: generate_account_id(), gt=0, le=INT_MAX)
    ticket: str = ""
    alt_steamid: int = Field(default=0, ge=0, le=INT_MAX)
    alt_steamid_count: int = Field(default=5, ge=0)
    language: str = "english"
    ip_country: str = "US"


class EmuConfigUserGeneralWithOptionals(BaseModel, validate_assignment=True):
    """
    Attributes:
        account_name: User account name.

        account_steamid: Your account ID in Steam64 format, if the specified ID is invalid, the emulator will ignore it
            and generate a proper one.

        ticket: Base64 Ticket.

        alt_steamid: Alt SteamId for encrypted savegames. Set to `0` to disable.

        alt_steamid_count: How many calls before swapping out the SteamId to Alt.
            IT WILL REPLACE IT AFTER THOSE CALLS. BE AWARE!

        language: The language reported to the app/game. This must exist in the **supported_languages.txt** file,
            otherwise it will be ignored by the emulator.

        ip_country: Report a country IP if the game queries it. ISO 3166-1-alpha-2 format.
    """
    account_name: str | None = None
    account_steamid: int | None = Field(default=None, gt=0, le=INT_MAX)
    ticket: str | None = None
    alt_steamid: int | None = Field(default=None, ge=0, le=INT_MAX)
    alt_steamid_count: int | None = Field(default=None, ge=0)
    language: str | None = None
    ip_country: str | None = None


class EmuConfigUserGeneralOnlyLanguage(BaseModel, validate_assignment=True):
    """
    Attributes:
        language: The language reported to the app/game. This must exist in the **supported_languages.txt** file,
            otherwise it will be ignored by the emulator.
    """
    language: str


class EmuConfigUserSaves(BaseModel, validate_assignment=True):
    """
    Attributes:
        local_save_path: When this is set, it will force the emulator to use the specified location instead of the
            default global location. The path can be absolute or relative to the location of the .dll/.so.
            Leading and trailing whitespaces are trimmed.
            When this option is used, the global settings folder is completely ignored, allowing a full portable
            behavior.

        saves_folder_name: Name of the base folder used to store save data, leading and trailing whitespaces are
            trimmed. Only useful if **local_save_path** isn't used.
    """
    local_save_path: str = ""
    saves_folder_name: str = "GSE Saves"


class EmuConfigUserSavesWithOptionals(BaseModel, validate_assignment=True):
    """
    Attributes:
        local_save_path: When this is set, it will force the emulator to use the specified location instead of the
            default global location. The path can be absolute or relative to the location of the .dll/.so.
            Leading and trailing whitespaces are trimmed.
            When this option is used, the global settings folder is completely ignored, allowing a full portable
            behavior.

        saves_folder_name: Name of the base folder used to store save data, leading and trailing whitespaces are
            trimmed. Only useful if **local_save_path** isn't used.
    """
    local_save_path: str | None = None
    saves_folder_name: str | None = None


class EmuConfigUser(BaseModel, validate_assignment=True):
    user__general: EmuConfigUserGeneral = Field(serialization_alias="user::general")
    user__saves: EmuConfigUserSaves = Field(serialization_alias="user::saves")


class EmuConfigUserWithOptionals(BaseModel, validate_assignment=True):
    user__general: EmuConfigUserGeneralWithOptionals = Field(serialization_alias="user::general")
    user__saves: EmuConfigUserSavesWithOptionals = Field(serialization_alias="user::saves")


class EmuConfigUserOnlyGeneral(BaseModel, validate_assignment=True):
    user__general: EmuConfigUserGeneralWithOptionals = Field(serialization_alias="user::general")


class EmuConfigUserOnlySaves(BaseModel, validate_assignment=True):
    user__saves: EmuConfigUserSavesWithOptionals = Field(serialization_alias="user::saves")


class EmuConfigUserOnlyGeneralOnlyLanguage(BaseModel, validate_assignment=True):
    user__general: EmuConfigUserGeneralOnlyLanguage = Field(serialization_alias="user::general")
