import configparser
import glob
import json
import os
import shutil
import sys
import threading
import time
from datetime import datetime
from email.utils import parsedate_to_datetime
from http.client import RemoteDisconnected
from re import Match
from textwrap import dedent
from typing import overload, Literal

import dateparser
import orjson
from loguru import logger
from pydantic import ValidationError
from requests import HTTPError
from rich_argparse import RawDescriptionRichHelpFormatter
from slugify import slugify

from __version__ import __version__
from common import (AdvancedArgumentParser,
                    STATS_REPO_SUB_PATH,
                    GH_STATS_PACKAGE_REPO_URL,
                    DEFAULT_EARLY_ACCESS_LABEL,
                    SEVENZIP_LIST_WILDCARD_PATTERNS,
                    STEAMAPI_SO_NAME,
                    STEAMCLIENT_SO_NAME,
                    STEAMCLIENT_SO_PATTERN,
                    STEAM_API_SO_PATTERN,
                    SESSION,
                    EXTRACT_FROM_PACKAGE_NAME_PATTERN,
                    STEAM_API_DLL_PATTERN,
                    STEAMCLIENT_DLL_PATTERN,
                    STEAM_APPID_PATTERN,
                    STATS_URL_TEMPLATE,
                    APP_DETAILS_URL_TEMPLATE,
                    SUPPORTED_LANG_EXTRACTION_STEP_1,
                    SUPPORTED_LANG_EXTRACTION_STEP_2,
                    LANGUAGES_ONLY_IN_GAMES,
                    SUPPORTED_LANGUAGES_MAPPING,
                    CONFIG_MAIN_FILENAME,
                    CONFIG_APP_FILENAME,
                    CONFIG_OVERLAY_FILENAME,
                    STATS_FILENAME,
                    INTERFACE_PATTERNS,
                    INTERFACES_FILENAME,
                    LONG_LANGUAGE_CHOICES,
                    SHORT_LANGUAGE_CHOICES,
                    ACF_APPID_PATTERN,
                    ACF_BUILDID_PATTERN,
                    STEAM_APPID_FILENAME,
                    LANGUAGE_CHOICES_MAPPING,
                    get_program_dir,
                    CURRENT_DATE,
                    STEAM_SETTINGS_FOLDER_NAME_PATTERN,
                    DLC_INFO_URL_TEMPLATE,
                    GH_STATS_PACKAGE_URL,
                    SYSTEM_PLATFORM,
                    ACHIEVEMENTS_DIRNAME,
                    SUPPORTED_LANGUAGES_FILENAME,
                    LOCKFILE_WAIT_TIME,
                    STEAMAPI_DLL_NAME,
                    STEAMAPI64_DLL_NAME,
                    STEAMCLIENT64_DLL_NAME,
                    STEAMCLIENT_DLL_NAME,
                    CONFIG_USER_FILENAME,
                    load_data_file,
                    NON_GAME_APPIDS)
from custom_types.common import (OutputDirRelations,
                                 OutputDirResult,
                                 ExtractIdsResult,
                                 ExtractOrAskIdsResult,
                                 ExtractFromPackageFilesResult,
                                 GetSteamLibLocationResult,
                                 ExtractIdFromAcfResult)
from custom_types.emulator_user_provided import ParseEmuConfigArgsResult
from models.app import (AppConfig,
                        MinAppConfig,
                        CacheOptions,
                        AchievementOptions,
                        LanguageOptions,
                        RuntimeData,
                        GameDetails)
from models.common import (ErrorOccurred)
from models.emulator import (EmuConfigUserWithOptionals,
                             EmuConfigUserSavesWithOptionals,
                             EmuConfigUserGeneralWithOptionals,
                             EmuConfigUserOnlyGeneral,
                             EmuConfigUserOnlySaves,
                             EmuConfigAppGeneral,
                             EmuConfigAppDLC,
                             EmuConfigAppController,
                             EmuConfigAppPaths,
                             EmuConfigAppCloudSaveGeneral,
                             EmuConfigAppCloudSaveWin,
                             EmuConfigAppCloudSaveLinux,
                             EmuConfigApp,
                             EmuConfigMainGeneral,
                             EmuConfigMainStats,
                             EmuConfigMainConnectivity,
                             EmuConfigMainMisc,
                             EmuConfigMain,
                             EmuConfigOverlayGeneral,
                             EmuConfigOverlayAppearance,
                             EmuConfigOverlayHotkeys,
                             EmuConfigOverlay,
                             EmuConfigUserGeneralOnlyLanguage,
                             EmuConfigUserOnlyGeneralOnlyLanguage)
from models.game import AchievementInfo, GameStat
from models.github import GHGameStat, GHGameInfo
from models.parsed_emulator_user_provided import (ParsedUserProvidedEmuConfigMain,
                                                  ParsedUserProvidedEmuConfigApp,
                                                  ParsedUserProvidedEmuConfigOverlay,
                                                  ParsedUserProvidedEmuConfigUser)
from models.steam import (SteamStatEntry,
                          RawSteamStatInfo,
                          SteamStatInfo,
                          SteamGameReleaseDate,
                          RawSteamGameInfo,
                          SteamGameInfo,
                          SteamDLCInfo)
from utils import (custom_copy,
                   write_last_retrieval_flag,
                   should_refresh_cache,
                   GitRepo,
                   get_git_path,
                   check_python_version,
                   delete_old_caches,
                   _handle_ro,
                   ensure_sevenzip,
                   remove_readonly_flag,
                   process_errors,
                   sanitize_name,
                   get_gray_icon_from_normal,
                   read_file_content,
                   update_emulator,
                   pad_directory,
                   search_for_package_file,
                   list_compressed_file_content,
                   extract_compressed_file_content,
                   compress_directory_content,
                   extract_paths_from_7z_listing,
                   get_with_retry,
                   get_elf_lib_bitness,
                   cleanup, parse_emu_config_args)

PROGRAM_DIR: str = get_program_dir()

error_occurred = ErrorOccurred()

print_progress_flag = threading.Event()
achievement_thread_error_flag = threading.Event()

unnamed_stat_counter = 0
unnamed_achievement_counter = 0

NEW_LINE: Literal["\n", "\r\n"] | None = None


def error_sink(message):
    record = message.record
    if record["level"].no >= logger.level("ERROR").no:
        error_occurred.value = True


def _build_emu_config_args(parser: AdvancedArgumentParser) -> None:
    emu_group = parser.add_argument_group(
            advanced=True,
            title="Emulator Config",
            description=dedent("""
            --------------------------------------
            
            You should carefully read the help for each argument and understand the default values.
            
            Using these arguments switches the default to the opposite value for the ones that are Enable/Disable,
            the name of the arguments don't necessarily represent the action each will perform, the name is
            simply a copy of the original option name in the ini files.
            
            So if an option default is Enable then using the argument will Disable the option even if the argument
            name doesn't describe it will switch off anything.
            
            i.e.: Using --ec--main--general--new-app-ticket will disable the `new-app-ticket` option because the 
            default is to enable it.
            
            We do not validate any path whatsoever.
            
            About the User config:
            
            This app, if the --add-user-config is used, creates a user config with only the language defined.
            If any argument related to the user-config is given then it will replace this behavior and the given user 
            config data will be created. In this case the language can be left unspecified to use the one the app 
            automatically calculates, otherwise that will also be overridden even.
            
            The language this app calculated will only be added if --add-user-config is used. In any other case 
            either the one the user specifies is used or is simply not defined. 
            
            No user-related emu config uses the default value when the appropiate argument is not used, 
            only the specified options are included in the ini file.
            
            --------------------------------------
            """)
    )

    # region App Config

    # region App - General

    emu_group.add_advanced_argument("--ec--app--general--is-beta-branch",
                                    help="Report the game branch as beta. Default: `Disabled`",
                                    action="store_true_int")
    emu_group.add_advanced_argument("--ec--app--general--branch-name",
                                    help="The name of the current branch, it must also exist in the branches.json "
                                         "file, or it will be ignored and \"public\" will be used instead. "
                                         "Default: `public`",
                                    type=str,
                                    metavar="BRANCH-NAME")

    # endregion

    # region App - DLCs

    emu_group.add_advanced_argument("--ec--app--dlcs--unlock-all",
                                    help="Whether to report all DLCs as unlocked or only the ones listed. Some games "
                                         "check for hidden DLCs, so sometimes this is needed, but other games do "
                                         "emulator detection by querying fake DLCs which in such cases this should be "
                                         "disabled. Default: `Disabled`",
                                    action="store_true_int")

    emu_group.add_advanced_argument("--ec--app--dlcs--add-dlcs",
                                    help="Add the following DLCs to the list. Notice that by default the list of DLCs "
                                         "is automatically retrieved from the game's data. This is processed in "
                                         "append mode. "
                                         "Specify values as two-item tuples `(appid, name) (appid, name)`. "
                                         "If you need to quote values, quote the entire tuple: "
                                         "`\"(appid, name with spaces)\" (appid, name)`. "
                                         "Default: `empty`",
                                    nargs="*",
                                    metavar="(APPID, NAME)")

    # endregion

    # region App - Controller

    emu_group.add_advanced_argument("--ec--app--controller--steam-input",
                                    help="Whether to enable SteamInput. SteamInput is automatically enabled when there "
                                         "are action sets in \"steam_settings\\controller\\\". Default: `Disabled`",
                                    action="store_true_int")
    emu_group.add_advanced_argument("--ec--app--controller--type",
                                    help="Override the controller type reported to SteamInput. Default: `XBOX360`",
                                    choices=["XBOX360", "XBOXONE", "PS3", "PS4", "PS5", "SWITCH"])

    # endregion

    # region App - Paths

    emu_group.add_advanced_argument("--ec--app--paths",
                                    help="Some rare games might need to be provided one or more paths to appids, "
                                         "for example, the path to where a DLC is installed. This sets the paths "
                                         "returned by the `Steam_Apps::GetAppInstallDir` function. "
                                         "However, some other games might expect this function to return empty paths "
                                         "to properly load DLCs. You can deliberately set the path to be empty to "
                                         "specify this behavior. "
                                         "Specify values as two-item tuples: `(appid, path) (appid,)`. If you need to "
                                         "quote values, quote the entire tuple: "
                                         "`\"(appid, path with spaces)\" (appid,)`. "
                                         "Default: `empty`",
                                    nargs="*",
                                    metavar="(APPID, [PATH])")

    # endregion

    # region App - Cloud Save

    emu_group.add_advanced_argument("--ec--app--cloud-save--general--create-default-dir",
                                    help="Should the emulator create the default directory for cloud saves on "
                                         "startup. Default: `Disabled`",
                                    action="store_true_int")
    emu_group.add_advanced_argument("--ec--app--cloud-save--general--create-specific-dir",
                                    help="Should the emulator create the directories specified in the cloud saves "
                                         "section of the current OS on startup. Default: `Disabled`",
                                    action="store_true_int")

    emu_group.add_advanced_argument("--ec--app--cloud-save--win",
                                    help="Directories that should be created on startup, this is used for cloud "
                                         "saves. Some games refuse to work unless these directories exist. "
                                         "There are reserved identifiers that are replaced at runtime, you can find a "
                                         "list of them here: https://partner.steamgames.com/doc/features/cloud#setup "
                                         "Default: `empty`",
                                    nargs="*",
                                    metavar="PATH")
    emu_group.add_advanced_argument("--ec--app--cloud-save--linux",
                                    help="Directories that should be created on startup, this is used for cloud "
                                         "saves. Some games refuse to work unless these directories exist. "
                                         "There are reserved identifiers that are replaced at runtime, you can find a "
                                         "list of them here: https://partner.steamgames.com/doc/features/cloud#setup "
                                         "Default: `empty`",
                                    nargs="*",
                                    metavar="PATH")

    # endregion

    # endregion

    # region Main Config

    # region Main - General

    emu_group.add_advanced_argument("--ec--main--general--new-app-ticket",
                                    help="Generate a newer version of auth ticket, used by some modern apps. "
                                         "Default: `Enabled`",
                                    action="store_false_int")
    emu_group.add_advanced_argument("--ec--main--general--gc-token",
                                    help="Generate/embed Game Coordinator token inside the new auth ticket. "
                                         "Default: `Enabled`",
                                    action="store_false_int")
    emu_group.add_advanced_argument("--ec--main--general--block-unknown-clients",
                                    help="If enabled, the game server will only allow connections from legit Steam "
                                         "clients and known Steam emulators. "
                                         "Default: `Disabled`",
                                    action="store_true_int")
    emu_group.add_advanced_argument("--ec--main--general--steam-deck",
                                    help="Pretend the app is running on a steam deck. "
                                         "Default: `Disabled`",
                                    action="store_true_int")
    emu_group.add_advanced_argument("--ec--main--general--enable-account-avatar",
                                    help="Enable avatar functionality. "
                                         "Default: `Disabled`",
                                    action="store_true_int")
    emu_group.add_advanced_argument("--ec--main--general--enable-voice-chat",
                                    help="Enable the experimental voice chat feature. This may result in higher "
                                         "system usage and cause performance drops or cause crashes. "
                                         "Default: `Disabled`",
                                    action="store_true_int")
    emu_group.add_advanced_argument("--ec--main--general--immediate-gameserver-stats",
                                    help="Synchronize user stats/achievements with game servers as soon as possible "
                                         "instead of caching them until the next call to `Steam_RunCallbacks()`. *Not "
                                         "recommended to enable this.* "
                                         "Default: `Disabled`",
                                    action="store_true_int")
    emu_group.add_advanced_argument("--ec--main--general--matchmaking-server-list-actual-type",
                                    help="Use the proper type of the server list (internet, friends, etc...) when "
                                         "requested by the game. If disabled: always return the type of the server "
                                         "list as \"LAN server\". *Not recommended to enable this.* "
                                         "Default: `Disabled`",
                                    action="store_true_int")
    emu_group.add_advanced_argument("--ec--main--general--matchmaking-server-details-via-source-query",
                                    help="Grab the server details for matchmaking using an actual server query. If "
                                         "disabled: use the info from the local network messages shared between "
                                         "client/server. *Not recommended to enable this, currently breaks some "
                                         "games.* "
                                         "Default: `Disabled`",
                                    action="store_true_int")
    emu_group.add_advanced_argument("--ec--main--general--crash-printer-location",
                                    help="Path to a file where to log. Very basic crash logger/printer. This is "
                                         "intended to debug some annoying scenarios and best used with the debug "
                                         "build of the emu. "
                                         "Default: `empty`",
                                    type=str,
                                    metavar="PATH")

    # endregion

    # region Main - Stats

    emu_group.add_advanced_argument("--ec--main--stats--disable-leaderboards-create-unknown",
                                    help="Prevent `Steam_User_Stats::FindLeaderboard()` from always succeeding and "
                                         "creating the unknown leaderboard. **Not recommended to enable this.** "
                                         "Default: `Disabled`",
                                    action="store_true_int")
    emu_group.add_advanced_argument("--ec--main--stats--allow-unknown-stats",
                                    help="Allow unknown stats to be saved/updated. By default, the emulator will only "
                                         "save/update stats defined by the user, unknown stats requested or updated "
                                         "by the game are rejected. "
                                         "Default: `Disabled`",
                                    action="store_true_int")
    emu_group.add_advanced_argument("--ec--main--stats--stat-achievement-progress-functionality",
                                    help="The emulator has an internal extra functionality which reports an "
                                         "achievement's progress when a stat tied to an achievement is updated, "
                                         "also the progress is saved to disk so that external applications can watch "
                                         "these updates. Only used internally for a stat tied to an achievement, "
                                         "the normal achievement progress requests made by the game are not impacted, "
                                         "some applications tie many stats to achievements, and update these stats "
                                         "very frequently, causing a spam of disk writes and overlay popups; in that "
                                         "case you can disable this functionality, but the stat progress won't be "
                                         "saved or displayed in the overlay. "
                                         "Default: `Enabled`",
                                    action="store_false_int")
    emu_group.add_advanced_argument("--ec--main--stats--save-only-higher-stat-achievement-progress",
                                    help="Save stat achievement progress value only if it is higher than the current "
                                         "one. If disabled, the emulator will save any stat achievement progress "
                                         "value (higher or lower). Whenever a game updates a stat which is tied to an "
                                         "achievement's progress, the emulator will save that progress immediately to "
                                         "disk. However, some games will update the stat very frequently (with lower "
                                         "and higher values) resulting in spam of disk writes or overlay "
                                         "notifications. This has no impact on the stat itself; only the achievement "
                                         "progress, it also has no impact on the functions which directly change "
                                         "stats, achievements, or achievement progress. "
                                         "Default: `Enabled`",
                                    action="store_false_int")
    emu_group.add_advanced_argument("--ec--main--stats--paginated-achievements-icons",
                                    help="How many icons to load in memory. If set to `0`, the icon will be loaded "
                                         "into memory only when it's requested. Set to `-1` to disable this "
                                         "functionality (`ISteamUserStats::GetAchievementIcon()` and the overlay "
                                         "won't be able to use icons). Each achievement has 2 icons, one when it's "
                                         "locked and another when it's unlocked, so a value of 10 means loading 20 "
                                         "icons. *Increasing this value will cause a huge startup delay.* "
                                         "Default: `10`",
                                    type=int,
                                    metavar="NUMBER-OF-ICONS")
    emu_group.add_advanced_argument("--ec--main--stats--record-playtime",
                                    help="Enable the functionality that allows the emulator to record the user's "
                                         "playtime. This will create a file named \"playtime.txt\" in the game's GSE "
                                         "Saves folder. The recorded playtime will be updated every minute, "
                                         "the emulator will also resume recording playtime when the game is "
                                         "relaunched. "
                                         "Default: `Disabled`",
                                    action="store_true_int")

    # endregion

    # region Main - Connectivity

    emu_group.add_advanced_argument("--ec--main--connectivity--disable-lan-only",
                                    help="Prevent hooking OS networking APIs and allow any external requests only "
                                         "used by the experimental builds on *Windows*. "
                                         "Default: `Disabled`",
                                    action="store_true_int")
    emu_group.add_advanced_argument("--ec--main--connectivity--disable-networking",
                                    help="Disable all the Steam networking interface functionality, this won't "
                                         "prevent games/apps from making external requests. Networking-related "
                                         "functionality like lobbies or those that launch a server in the background "
                                         "will not work. "
                                         "Default: `Disabled`",
                                    action="store_true_int")
    emu_group.add_advanced_argument("--ec--main--connectivity--listen-port",
                                    help="Change the UDP/TCP port the emulator listens on, you should probably not "
                                         "change this because everyone needs to use the same port, or you won't find "
                                         "yourselves on the network. "
                                         "Default: `47584`",
                                    type=int,
                                    metavar="PORT-NUMBER")
    emu_group.add_advanced_argument("--ec--main--connectivity--offline",
                                    help="Pretend Steam is running in offline mode. Mainly affects the function "
                                         "`ISteamUser::BLoggedOn()`. Some games that connect to online servers might "
                                         "only work if the emulator behaves like Steam when it's in offline mode. "
                                         "Default: `Disabled`",
                                    action="store_true_int")
    emu_group.add_advanced_argument("--ec--main--connectivity--disable-sharing-stats-with-gameserver",
                                    help="Prevent sharing stats and achievements with any game server, "
                                         "this also disables the interface `ISteamGameServerStats`. "
                                         "Default: `Disabled`",
                                    action="store_true_int")
    emu_group.add_advanced_argument("--ec--main--connectivity--disable-source-query",
                                    help="Don't send server details to the server browser. Only works for game "
                                         "servers. "
                                         "Default: `Disabled`",
                                    action="store_true_int")
    emu_group.add_advanced_argument("--ec--main--connectivity--share-leaderboards-over-network",
                                    help="Enable sharing leaderboard scores with people playing the same game on the "
                                         "same network. *Not ideal and synchronization isn't perfect.* "
                                         "Default: `Disabled`",
                                    action="store_true_int")
    emu_group.add_advanced_argument("--ec--main--connectivity--disable-lobby-creation",
                                    help="Prevent lobby creation in the steam matchmaking interface. "
                                         "Default: `Disabled`",
                                    action="store_true_int")
    emu_group.add_advanced_argument("--ec--main--connectivity--download-steamhttp-requests",
                                    help="Attempt to download external HTTPs requests made via "
                                         "`Steam_HTTP::SendHTTPRequest()` inside `steam_settings/http/`. Make sure to "
                                         "enable --ec--main--connectivity--disable-lan-only and to disable "
                                         "--ec--main--connectivity--disable-networking. This will `not` work if the "
                                         "app is using native/OS web APIs. "
                                         "Default: `Disabled`",
                                    action="store_true_int")

    # endregion

    # region Main - Misc

    emu_group.add_advanced_argument("--ec--main--misc--achievements-bypass",
                                    help="Force `ISteamUserStats::SetAchievement()` to always return true. This is a "
                                         "workaround for some games that otherwise won't work. "
                                         "Default: `Disabled`",
                                    action="store_true_int")
    emu_group.add_advanced_argument("--ec--main--misc--force-steamhttp-success",
                                    help="Force the function `Steam_HTTP::SendHTTPRequest()` to always succeed. "
                                         "Default: `Disabled`",
                                    action="store_true_int")
    emu_group.add_advanced_argument("--ec--main--misc--disable-steamoverlaygameid-env-var",
                                    help="Don't write env var `SteamOverlayGameId`, allowing Steam Input to work. The "
                                         "env var `SteamOverlayGameId` breaks Steam Input when the game is added to "
                                         "Steam as a non-steam game. "
                                         "Default: `Disabled`",
                                    action="store_true_int")
    emu_group.add_advanced_argument("--ec--main--misc--enable-steam-preowned-ids",
                                    help="Add many Steam apps to the list of owned DLCs and to the emulator's list of "
                                         "installed app IDs. Useful for many Source-based games. See: "
                                         "https://developer.valvesoftware.com/wiki/Steam_Application_IDs and "
                                         "https://developer.valvesoftware.com/wiki/Dedicated_Servers_List "
                                         "Default: `Disabled`",
                                    action="store_true_int")
    emu_group.add_advanced_argument("--ec--main--misc--steam-game-stats-reports-dir",
                                    help="Some Source-based games use the interface `ISteamGameStats` to report some "
                                         "stats. The emulator can save this data to a folder. If set, the emulator "
                                         "will create the folders if it's missing, but the path specified must be "
                                         "writable. "
                                         "Default: `empty`",
                                    type=str,
                                    metavar="PATH")
    emu_group.add_advanced_argument("--ec--main--misc--free-weekend",
                                    help="Some games may have extra bonuses/achievements when being or playing with a "
                                         "free-weekend player. "
                                         "Default: `Disabled`",
                                    action="store_true_int")
    emu_group.add_advanced_argument("--ec--main--misc--use-32bit-inventory-item-ids",
                                    help="Very old versions of Team Fortress 2 don't properly handle 64-bit item IDs, "
                                         "this workaround makes Goldberg only generate 32-bit item IDs. "
                                         "Default: `Disabled`",
                                    action="store_true_int")
    # endregion

    # endregion

    # region Overlay Config

    # region Overlay - General

    emu_group.add_advanced_argument("--ec--overlay--general--enable-experimental-overlay",
                                    help="Enable the experimental overlay, might cause crashes. "
                                         "Default: `Disabled`",
                                    action="store_true_int")
    emu_group.add_advanced_argument("--ec--overlay--general--hook-delay-sec",
                                    help="Amount of time to wait before attempting to detect and hook the renderer ("
                                         "DirectX, OpenGL, etc.). "
                                         "Default: `0`",
                                    type=int,
                                    metavar="DELAY-IN-SEC")
    emu_group.add_advanced_argument("--ec--overlay--general--renderer-detector-timeout-sec",
                                    help="Timeout for the renderer detector. "
                                         "Default: `15`",
                                    type=int,
                                    metavar="TIMEOUT-IN-SEC")
    emu_group.add_advanced_argument("--ec--overlay--general--disable-achievement-notification",
                                    help="Disable the achievement notifications. "
                                         "Default: `Disabled`",
                                    action="store_true_int")
    emu_group.add_advanced_argument("--ec--overlay--general--disable-friend-notification",
                                    help="Disable friend invitations and message notifications. "
                                         "Default: `Disabled`",
                                    action="store_true_int")
    emu_group.add_advanced_argument("--ec--overlay--general--disable-achievement-progress",
                                    help="Disable showing notifications for achievements' progress. "
                                         "Default: `Enabled`",
                                    action="store_false_int")
    emu_group.add_advanced_argument("--ec--overlay--general--disable-warning-any",
                                    help="Disable any warning in the overlay. "
                                         "Default: `Disabled`",
                                    action="store_true_int")
    emu_group.add_advanced_argument("--ec--overlay--general--disable-warning-bad-appid",
                                    help="Disable the bad app ID warning in the overlay. "
                                         "Default: `Disabled`",
                                    action="store_true_int")
    emu_group.add_advanced_argument("--ec--overlay--general--disable-warning-local-save",
                                    help="Disable the local_save warning in the overlay. "
                                         "Default: `Disabled`",
                                    action="store_true_int")
    emu_group.add_advanced_argument("--ec--overlay--general--upload-achievements-icons-to-gpu",
                                    help="Attempt to upload the achievement icons to the GPU. If disabled, "
                                         "achievement icons won't be displayed in the overlay. This is done so that "
                                         "the icons are displayed in the overlay, in rare cases this might keep "
                                         "failing and cause FPS drops. "
                                         "Default: `Enabled`",
                                    action="store_false_int")
    emu_group.add_advanced_argument("--ec--overlay--general--fps-averaging-window",
                                    help="Amount of frames to accumulate, to eventually calculate the average "
                                         "frametime (in milliseconds). The minimum possible value is 1. Lower values "
                                         "would result in instantaneous frametime/fps, but the FPS would be erratic. "
                                         "Higher values would result in a more stable frametime/fps, but will be "
                                         "inaccurate due to averaging over a long time. "
                                         "Default: `10`",
                                    type=int,
                                    metavar="TIME-IN-MS")
    emu_group.add_advanced_argument("--ec--overlay--general--overlay-always-show-user-info",
                                    help="Always show user info in the overlay. "
                                         "Default: `Disabled`",
                                    action="store_true_int")
    emu_group.add_advanced_argument("--ec--overlay--general--overlay-always-show-fps",
                                    help="Always show fps in the overlay. "
                                         "Default: `Disabled`",
                                    action="store_true_int")
    emu_group.add_advanced_argument("--ec--overlay--general--overlay-always-show-frametime",
                                    help="Always show frametime in the overlay. "
                                         "Default: `Disabled`",
                                    action="store_true_int")
    emu_group.add_advanced_argument("--ec--overlay--general--overlay-always-show-playtime",
                                    help="Always show playtime in the overlay. "
                                         "Default: `Disabled`",
                                    action="store_true_int")

    # endregion

    # region Overlay - Hotkeys

    emu_group.add_advanced_argument("--ec--overlay--hotkeys--key-combo",
                                    help="Combination of keys used to show/hide the overlay. Available values: shift, "
                                         "ctrl, alt, tab, fn1, fn2, ..., fn12. You can use the \"+\" sign to combine "
                                         "multiple keys. "
                                         "Default: `shift + tab`",
                                    type=str,
                                    metavar="KEY-COMBO")

    # endregion

    # region Overlay - Appearance

    emu_group.add_advanced_argument("--ec--overlay--appearance--Font-Override",
                                    help="Load custom TrueType font from a path, it could be absolute, or relative. "
                                         "Relative paths will be looked up inside the local folder "
                                         "`steam_settings/fonts` first, if that isn't found, it will be looked up "
                                         "inside the global folder `GSE Settings/settings/fonts`. "
                                         "Default: `empty`",
                                    type=str,
                                    metavar="PATH")
    emu_group.add_advanced_argument("--ec--overlay--appearance--Font-Override-Achievement-Title",
                                    help="Custom font for achievement title. Leave empty to use the default font. "
                                         "Default: `empty`",
                                    type=str,
                                    metavar="PATH")
    emu_group.add_advanced_argument("--ec--overlay--appearance--Font-Override-Achievement-Description",
                                    help="Custom font for achievement description. Leave empty to use the default "
                                         "font. "
                                         "Default: `empty`",
                                    type=str,
                                    metavar="PATH")

    emu_group.add_advanced_argument("--ec--overlay--appearance--Font-Size",
                                    help="Global font size. For the built-in font, a multiple of 16 is recommended. "
                                         "E.g.: 16, 32... "
                                         "Default: `16.0`",
                                    type=float,
                                    metavar="SIZE")
    emu_group.add_advanced_argument("--ec--overlay--appearance--Font-Size-FPS",
                                    help="Optional independent font size. Less or equal than 0 uses "
                                         "--ec--overlay--appearance--Font-Size. "
                                         "Default: `0.0`",
                                    type=float,
                                    metavar="SIZE")
    emu_group.add_advanced_argument("--ec--overlay--appearance--Font-Size-Achievement-Title",
                                    help="Optional independent font size. Less or equal than 0 uses "
                                         "--ec--overlay--appearance--Font-Size. "
                                         "Default: `0.0`",
                                    type=float,
                                    metavar="SIZE")
    emu_group.add_advanced_argument("--ec--overlay--appearance--Font-Size-Achievement-Description",
                                    help="Optional independent font size. Less or equal than 0 uses "
                                         "--ec--overlay--appearance--Font-Size. "
                                         "Default: `0.0`",
                                    type=float,
                                    metavar="SIZE")

    emu_group.add_advanced_argument("--ec--overlay--appearance--Font-Achievement-Title-Bold",
                                    help="Bold font for achievement title. "
                                         "Default: `Disabled`",
                                    action="store_true_int")

    emu_group.add_advanced_argument("--ec--overlay--appearance--Icon-Size",
                                    help="Achievement icon size. "
                                         "Default: `64.0`",
                                    type=float,
                                    metavar="SIZE")

    emu_group.add_advanced_argument("--ec--overlay--appearance--Achievement-Notification-Delay",
                                    help="Minimum time interval between achievement notifications (in seconds). Set "
                                         "to 0 to show all achievements immediately without delay. "
                                         "Default: `0`",
                                    type=int,
                                    metavar="DELAY-IN-SEC")

    emu_group.add_advanced_argument("--ec--overlay--appearance--Achievement-Unlock-Datetime-Format",
                                    help="Format for the achievement unlock date/time, limited to 79 characters. If "
                                         "the output formatted string exceeds this limit, the builtin format will be "
                                         "used. Look for the format here: "
                                         "https://en.cppreference.com/w/cpp/chrono/c/strftime "
                                         "Default: `%%Y/%%m/%%d - %%H:%%M:%%S`",
                                    type=str,
                                    metavar="DATETIME-FORMAT")

    # endregion

    # endregion

    # region User Config

    # region User - General

    emu_group.add_advanced_argument("--ec--user--general--account-name",
                                    help="User account name. "
                                         "Default: `gse orca`",
                                    type=str,
                                    metavar="ACCOUNT-NAME")
    emu_group.add_advanced_argument("--ec--user--general--account-steamid",
                                    help="Your account ID in Steam64 format, if the specified ID is invalid, "
                                         "the emulator will ignore it and generate a proper one. "
                                         "Default: `randomly-generated`",
                                    type=int,
                                    metavar="STEAM-ID")
    emu_group.add_advanced_argument("--ec--user--general--ticket",
                                    help="Base64 Ticket. "
                                         "Default: `empty`",
                                    type=str,
                                    metavar="BASE64-TICKET")
    emu_group.add_advanced_argument("--ec--user--general--alt-steamid",
                                    help="Alt SteamId for encrypted savegames. "
                                         "Default: `0`",
                                    type=int,
                                    metavar="ALT-STEAM-ID")
    emu_group.add_advanced_argument("--ec--user--general--alt-steamid-count",
                                    help="How many calls before swapping out the SteamId to Alt. IT WILL REPLACE IT "
                                         "AFTER THOSE CALLS. BE AWARE! "
                                         "Default: `5`",
                                    type=int,
                                    metavar="COUNT")
    emu_group.add_advanced_argument("--ec--user--general--language",
                                    help="The language reported to the app/game. This must exist in the "
                                         "`supported_languages.txt` file, otherwise it will be ignored by the "
                                         "emulator. "
                                         "Default: `english`",
                                    type=str,
                                    metavar="LANGUAGE")
    emu_group.add_advanced_argument("--ec--user--general--ip-country",
                                    help="Report a country IP if the game queries it. ISO 3166-1-alpha-2 format. "
                                         "Default: `US`",
                                    type=str,
                                    metavar="IP-COUNTRY")

    # endregion

    # region User - Saves

    emu_group.add_advanced_argument("--ec--user--saves--local-save-path",
                                    help="When this is set, it will force the emulator to use the specified location "
                                         "instead of the default global location. The path can be absolute or "
                                         "relative to the location of the .dll/.so. Leading and trailing whitespaces "
                                         "are trimmed. When this option is used, the global settings folder is "
                                         "completely ignored, allowing a full portable behavior. "
                                         "Default: `empty`",
                                    type=str,
                                    metavar="PATH")
    emu_group.add_advanced_argument("--ec--user--saves--saves-folder-name",
                                    help="Name of the base folder used to store save data, leading and trailing "
                                         "whitespaces are trimmed. Only useful if "
                                         "--ec--user--saves--local-save-path isn't used. "
                                         "Default: `GSE Saves`",
                                    type=str,
                                    metavar="FOLDER-NAME")

    # endregion

    # endregion


def main() -> None:
    show_advanced = "--help-advanced" in sys.argv

    for arg in sys.argv[1:]:
        if arg in ("-h", "--help", "--help-advanced"):
            showing_help = True
            break
    else:
        showing_help = False

    if show_advanced:
        sys.argv.remove("--help-advanced")
        sys.argv.append("--help")

    parser = AdvancedArgumentParser(description="Build Steam emulator configuration",
                                    show_advanced=show_advanced,
                                    showing_help=showing_help,
                                    formatter_class=RawDescriptionRichHelpFormatter)

    parser.add_argument("-v", "--version",
                        action="version",
                        version=f"%(prog)s v{__version__}")

    parser.add_argument("--help-advanced",
                        help="Show help for the extra arguments.",
                        action="store_true")

    parser.add_argument("--appid",
                        help="Game's Steam app ID. If not specified it is extracted from the provided directories if "
                             "possible.",
                        required=False,
                        type=str)
    parser.add_argument("--output-dir",
                        help="Where to store the configuration. If not specified it is inferred based on the provided "
                             "directory.",
                        required=False,
                        type=str)
    parser.add_argument("--game-dir",
                        help="Path to the (extracted/installed) game directory.",
                        required=False,
                        type=str)
    parser.add_argument("--package-dir",
                        help="Path to the game package directory. Can either be packaged or unpackaged.",
                        required=False,
                        type=str)
    parser.add_argument("--api-key",
                        help="Steam API key. Can also be specified with the env var STEAM_API_KEY",
                        required=False,
                        type=str)
    # noinspection PyTypeChecker
    parser.add_argument("--preferred-language",
                        help="The preferred language to use to retrieve achievements. Not all are supported, "
                             "it fallbacks to English.",
                        default="english",
                        choices=LONG_LANGUAGE_CHOICES + SHORT_LANGUAGE_CHOICES,
                        metavar="LANGUAGE",
                        type=str.lower)
    parser.add_argument("--do-not-ask",
                        help="Don't ask for the Steam app ID when it can't be automatically extracted and simply exit.",
                        action="store_true")
    parser.add_argument("--include-emulator",
                        help="Include the emulator files in the package.",
                        action="store_true")
    parser.add_argument("--rename-package-dir",
                        help="Rename package directory to the game's name and release year. E.g. 'The Game (2025)'.",
                        action="store_true")
    parser.add_argument("--only-rename",
                        help="Do not write anything, only rename.",
                        action="store_true")
    parser.add_argument("--add-language-flag-on-rename",
                        help="On renaming when a language is provided if the game doesn't support said language "
                             "(nor their fallback) an \"[eng]\" flag will be appended to the name.",
                        action="store_true")
    parser.add_argument("--add-early-access-label", "--add-ea-label",
                        help="Add early access label to the new name if game is early access.",
                        action="store_true")
    parser.add_argument("--custom-early-access-label", "--custom-ea-label",
                        help=f"Custom early access label to use instead of the default one. (Default: \""
                             f"{DEFAULT_EARLY_ACCESS_LABEL}\")",
                        required=False,
                        type=str)
    parser.add_argument("--output-dir-is-base",
                        help="Treat the specified output directory as a base for building the output directory.",
                        action="store_true")
    parser.add_argument("--archive-password",
                        help="Password to open compressed files.",
                        required=False,
                        type=str)
    parser.add_argument("--use-steam-for-stats",
                        help="Use Steam for stats (not achievements) retrieval.",
                        action="store_true")
    parser.add_argument("--fallback-to-steam",
                        help="Fallback to Steam when no stat has been found on the GitHub stats package.",
                        action="store_true")
    parser.add_argument("--fail-if-no-dll",
                        help="Fail earlier if no DLL/SO file is found. Otherwise only fails if no DLL/SO is found and "
                             "--include-emulator is used.",
                        action="store_true")
    parser.add_argument("--compress-config",
                        help="Compress configuration directory using the --compressed-filename specified name",
                        action="store_true")
    parser.add_argument("--compressed-filename",
                        help="Filename of the resulting compressed file.",
                        required=False,
                        type=str)
    parser.add_argument("--skip-achievements",
                        help="Skip downloading and configuring the game's achievements.",
                        action="store_true")
    parser.add_argument("--skip-stats",
                        help="Skip configuring the game's stats.",
                        action="store_true")
    parser.add_argument("--update-config-package",
                        help="Update compressed configuration package if found. The name is taken from "
                             "--compressed-filename so it must be supplied.",
                        action="store_true")
    parser.add_argument("--add-user-config",
                        help="Add user config to setup the language.",
                        action="store_true")

    parser.add_argument("--cache-game-info",
                        help="Cache the downloaded game info and achievement icon files",
                        action="store_true")
    parser.add_argument("--cache-location",
                        help="Path where to store the cache",
                        required=False,
                        type=str,
                        default=os.path.join(PROGRAM_DIR, "cache"))
    parser.add_argument("--force-achievement-icon-download",
                        help="When using --cache-game-info, force download the icon files for the achievements and "
                             "cache them.",
                        action="store_true")
    parser.add_argument("--copy-cache-back",
                        help="Copy downloaded icons back to the cache when they exist in the existing config but not "
                             "in the cache location. This is only useful when updating old configs",
                        action="store_true")

    parser.add_argument("--include-dll",
                        help="Include the specified DLL/SO files into the configuration for the emulator to load.",
                        nargs="*")

    # noinspection PyTypeChecker
    parser.add_argument("--log-level",
                        help="How much stuff is logged.",
                        default="WARNING",
                        choices=["TRACE", "DEBUG", "INFO", "SUCCESS", "WARNING", "ERROR", "CRITICAL"],
                        type=str.upper)
    parser.add_argument("--log-file",
                        help="Where to store the log file. By default in the program dir.",
                        required=False,
                        type=str)

    _build_emu_config_args(parser=parser)

    args = parser.parse_args()

    app_config = AppConfig(**vars(args), tools_path=os.path.join(PROGRAM_DIR, "tools"), orig_output_dir=args.output_dir)

    logger.remove()
    logger.add(sys.stderr, level=app_config.log_level)

    if app_config.log_file is None:
        app_config.log_file = os.path.join(PROGRAM_DIR, f"steam-emu-configurator_{CURRENT_DATE}.log")

    if logger.level(app_config.log_level).no > logger.level("WARNING").no:
        logger.add(app_config.log_file, level="WARNING")
    else:
        logger.add(app_config.log_file, level=app_config.log_level)

    logger.add(error_sink, level="ERROR")

    logger.info(f"steam-emu-configurator v{__version__} - {SYSTEM_PLATFORM}")

    logger.debug(f"Using the following configuration:\n{app_config}")

    check_python_version()

    if app_config.game_dir is None and app_config.package_dir is None:
        logger.critical("At least one of --game-dir or --package-dir must be specified.")
        sys.exit(1)

    if app_config.game_dir is not None and app_config.package_dir is not None:
        logger.critical("Either --game-dir or --package-dir must be specified, not both.")
        sys.exit(1)

    if not app_config.only_rename:
        if not app_config.skip_achievements or not app_config.skip_stats:
            if app_config.api_key is None:
                app_config.api_key = os.getenv("STEAM_API_KEY")
                if app_config.api_key is None:
                    logger.critical("The API key must be specified.")
                    sys.exit(1)

    if app_config.game_dir is not None:
        app_config.game_dir = os.path.abspath(os.path.normpath(app_config.game_dir))
    elif app_config.package_dir is not None:
        app_config.package_dir = os.path.abspath(os.path.normpath(app_config.package_dir))

    if app_config.only_rename:
        app_config.rename_package_dir = True

    if app_config.compress_config:
        if app_config.compressed_filename is None or app_config.compressed_filename.strip() == "":
            logger.critical("Compressed filename must be specified when using --compress-config.")
            sys.exit(1)

        if not app_config.compressed_filename.lower().endswith(".7z"):
            app_config.compressed_filename += ".7z"

    if app_config.update_config_package and app_config.compressed_filename is None:
        logger.critical("Can't update the compressed configuration package because "
                        "no compressed filename was supplied.")
        sys.exit(1)

    if len(app_config.include_dll) != 0:
        for index, lib in enumerate(app_config.include_dll):
            normalized_lib = os.path.abspath(os.path.normpath(lib))

            if not os.path.isfile(normalized_lib):
                logger.error(f"Additional DLL/SO is not a file: {normalized_lib}")
                sys.exit(3)

            app_config.include_dll[index] = normalized_lib

    if app_config.cache_game_info and app_config.cache_location is None:
        logger.info("Using default cache location.")

    thread = threading.Thread(target=delete_old_caches,
                              kwargs={
                                  "product_name": "steam-emu-configurator",
                                  "current_version": __version__,
                              },
                              daemon=False,
                              name="cache_deleter")
    thread.start()

    load_data_file()

    app_config.preferred_language = normalize_language(preferred_language=app_config.preferred_language)

    os.makedirs(app_config.tools_path, exist_ok=True)

    app_config_dict = app_config.model_dump()
    stripped_app_config = MinAppConfig(**app_config_dict)
    cache_opts = CacheOptions(**app_config_dict)
    lang_opts = LanguageOptions(**app_config_dict)
    game_details = GameDetails(**app_config_dict)

    runtime_data: RuntimeData | None = None

    try:
        user_provided_emu_config: ParseEmuConfigArgsResult = parse_emu_config_args(args=args)
    except ValidationError as err:
        logger.critical(f"Failed to parse the provided configuration\n {process_errors(err.errors())}")
        logger.opt(exception=True).debug("Traceback:")
        sys.exit(6)

    try:
        runtime_data = start_configuration(app_config=stripped_app_config,
                                           cache_opts=cache_opts,
                                           lang_opts=lang_opts,
                                           game_details=game_details,
                                           user_provided_emu_config=user_provided_emu_config)

        if error_occurred.value:
            sys.exit(9)
    finally:
        SESSION.close()

        if runtime_data is not None and runtime_data.extracted_files_path is not None:
            try:
                shutil.rmtree(runtime_data.extracted_files_path, onexc=_handle_ro)
            except FileNotFoundError:
                pass


def normalize_language(preferred_language: str) -> str:
    """
    Normalize the language to a format that Steam supports.
    """
    if preferred_language in SHORT_LANGUAGE_CHOICES:
        preferred_language = LANGUAGE_CHOICES_MAPPING[preferred_language]
        logger.info(f"Preferred language normalized to: {preferred_language}")

    return preferred_language


def start_configuration(app_config: MinAppConfig,
                        cache_opts: CacheOptions,
                        lang_opts: LanguageOptions,
                        game_details: GameDetails,
                        user_provided_emu_config: ParseEmuConfigArgsResult) -> RuntimeData:
    logger.info("Starting configuration creation...")

    runtime_data = RuntimeData()

    if game_details.appid is None:
        ids_result = get_appid_and_buildid(game_dir=app_config.game_dir,
                                           package_dir=app_config.package_dir,
                                           do_not_ask=app_config.do_not_ask,
                                           tools_path=app_config.tools_path,
                                           archive_password=app_config.archive_password)

        game_details.appid = ids_result["appid"]
        game_details.buildid = ids_result["buildid"]  # currently not used for anything

        runtime_data.extracted_files_path = ids_result["extracted_files_path"]
        runtime_data.acf_files = ids_result["resulting_acf_files"]
        runtime_data.tried_extracting_package_files = ids_result["tried_extracting_package_files"]
    else:
        if app_config.package_dir is not None:
            found_acf_files, extracted_files_path = retrieve_acf_files(package_dir=app_config.package_dir,
                                                                       tools_path=app_config.tools_path,
                                                                       archive_password=app_config.archive_password)

            runtime_data.acf_files = found_acf_files
            if extracted_files_path is not None:
                runtime_data.extracted_files_path = extracted_files_path
                runtime_data.tried_extracting_package_files = True

    game_info: SteamGameInfo | GHGameInfo
    steam_game_info = get_steam_game_info(appid=game_details.appid,
                                          cache_opts=cache_opts)

    if steam_game_info is None:
        gh_game_info = get_gh_game_info(tools_path=app_config.tools_path, appid=game_details.appid)

        if gh_game_info is None:
            logger.critical("No game info could be found in the GH package. Probably this app ID has no game "
                            "information. Exiting...")
            sys.exit(3)
        else:
            game_info = gh_game_info
    else:
        game_info = steam_game_info

    lang_opts.supported_languages = get_supported_languages(game_info=game_info, appid=game_details.appid)

    if not app_config.only_rename:
        output_dir_data = set_output_directory(package_dir=app_config.package_dir,
                                               game_dir=app_config.game_dir,
                                               output_dir=app_config.output_dir,
                                               output_dir_is_base=app_config.output_dir_is_base,
                                               extracted_files_path=runtime_data.extracted_files_path,
                                               tried_extracting_package_files=runtime_data.tried_extracting_package_files,
                                               fail_if_no_dll=app_config.fail_if_no_dll,
                                               tools_path=app_config.tools_path,
                                               archive_password=app_config.archive_password)

        app_config.output_dir = output_dir_data["output_dir"]
        runtime_data.lib_locations = output_dir_data["lib_locations"]
        runtime_data.directory_to_compress = output_dir_data["directory_to_compress"]
        runtime_data.output_dir_relations = output_dir_data["output_dir_relations"]
        runtime_data.extracted_files_path = output_dir_data["extracted_files_path"]
        game_details.is_linux = output_dir_data["is_linux"]

        if app_config.update_config_package and app_config.compressed_filename is not None:
            extract_configuration_package(directory_to_compress=runtime_data.directory_to_compress,
                                          compressed_filename=app_config.compressed_filename,
                                          tools_path=app_config.tools_path)

        logger.debug("Creating output directory...")
        for output_dir in runtime_data.output_dir_relations:
            os.makedirs(output_dir, exist_ok=True)

        lang_opts.sanitized_language, fallback_language_used = get_sanitized_preferred_language(
                supported_languages=lang_opts.supported_languages,
                preferred_language=lang_opts.preferred_language)

        if fallback_language_used:
            lang_opts.fallback_language_used = fallback_language_used

        achievements_thread: threading.Thread | None = None

        global NEW_LINE
        if game_details.is_linux:
            NEW_LINE = "\n"
        else:
            NEW_LINE = "\r\n"

        if not app_config.skip_achievements or not app_config.skip_stats:
            if app_config.api_key is not None:
                achievements_thread, fallback_language_used = handle_stat_and_achievements(
                        skip_achievements=app_config.skip_achievements,
                        skip_stats=app_config.skip_stats,
                        appid=game_details.appid,
                        tools_path=app_config.tools_path,
                        api_key=app_config.api_key,
                        output_dir_relations=runtime_data.output_dir_relations,
                        acf_files=runtime_data.acf_files,
                        use_steam_for_stats=app_config.use_steam_for_stats,
                        fallback_to_steam=app_config.fallback_to_steam,
                        cache_opts=cache_opts,
                        lang_opts=lang_opts)

                if fallback_language_used:
                    lang_opts.fallback_language_used = fallback_language_used
            else:
                logger.warning("No API key has been provided, skipping stats and achievements.")

        write_supported_languages(supported_languages=lang_opts.supported_languages,
                                  output_dir_relations=runtime_data.output_dir_relations)

        write_interfaces_file(lib_locations=runtime_data.lib_locations,
                              output_dir_relations=runtime_data.output_dir_relations,
                              extracted_files_path=runtime_data.extracted_files_path,
                              is_linux=game_details.is_linux)

        write_steam_appid(appid=game_details.appid,
                          output_dir_relations=runtime_data.output_dir_relations)

        write_emu_config(game_info=game_info,
                         tools_path=app_config.tools_path,
                         appid=game_details.appid,
                         add_user_config=app_config.add_user_config,
                         output_dir_relations=runtime_data.output_dir_relations,
                         fallback_to_steam=app_config.fallback_to_steam,
                         cache_opts=cache_opts,
                         lang_opts=lang_opts,
                         user_provided_emu_config=user_provided_emu_config)

        if app_config.include_emulator:
            add_emulator(tools_path=app_config.tools_path,
                         output_dir_relations=runtime_data.output_dir_relations,
                         lib_locations=runtime_data.lib_locations,
                         output_dir=app_config.output_dir,
                         game_dir=app_config.game_dir,
                         extracted_files_path=runtime_data.extracted_files_path,
                         is_linux=game_details.is_linux,
                         include_dll=app_config.include_dll)

        if achievements_thread is not None and achievements_thread.is_alive():
            logger.info("Waiting for achievements to finish downloading...")
            print_progress_flag.set()
            achievements_thread.join()

            if achievement_thread_error_flag.is_set():
                logger.critical("An error occurred in the achievements thread, aborting...")
                sys.exit(4)

        if (app_config.compress_config
                and runtime_data.directory_to_compress is not None
                and app_config.compressed_filename is not None):
            compress_config(directory_to_compress=runtime_data.directory_to_compress,
                            game_dir=app_config.game_dir,
                            tools_path=app_config.tools_path,
                            compressed_filename=app_config.compressed_filename)
    else:
        logger.info("Configured to only rename.")

    rename_package_dir(game_info=game_info,
                       do_rename_package_dir=app_config.rename_package_dir,
                       package_dir=app_config.package_dir,
                       appid=game_details.appid,
                       only_rename=app_config.only_rename,
                       add_language_flag_on_rename=app_config.add_language_flag_on_rename,
                       add_early_access_label=app_config.add_early_access_label,
                       custom_early_access_label=app_config.custom_early_access_label,
                       lang_opts=lang_opts)

    logger.info("Configuration creation finished.")

    return runtime_data


def handle_stat_and_achievements(skip_achievements: bool,
                                 skip_stats: bool,
                                 appid: str,
                                 tools_path: str,
                                 api_key: str,
                                 output_dir_relations: OutputDirRelations,
                                 acf_files: set[str] | None,
                                 use_steam_for_stats: bool,
                                 fallback_to_steam: bool,
                                 cache_opts: CacheOptions,
                                 lang_opts: LanguageOptions) -> tuple[threading.Thread | None, bool]:
    stat_info: SteamStatInfo | None = None
    fallback_language_used = lang_opts.fallback_language_used
    if not skip_achievements or not skip_stats:
        stat_info, fallback_language_used = get_stat_info(appid=appid,
                                                          api_key=api_key,
                                                          cache_opts=cache_opts,
                                                          lang_opts=lang_opts)

    achievements_thread: threading.Thread | None = None
    if skip_achievements:
        logger.info("Skipping downloading achievements.")
    else:
        if stat_info is None:
            logger.info("Game has no stat information, skipping achievements and stats.")
        else:
            logger.info("Executing achievements download in a new thread...")
            achievements_thread_opts = AchievementOptions(
                    appid=appid,
                    api_key=api_key,
                    stat_info=stat_info,
                    acf_files=acf_files,
                    output_dir_relations=output_dir_relations,
            )
            achievements_thread = threading.Thread(target=write_achievements_wrapper,
                                                   kwargs={
                                                       "opts": achievements_thread_opts,
                                                       "cache_opts": cache_opts,
                                                       "lang_opts": lang_opts,
                                                   },
                                                   daemon=True,
                                                   name=f"ACH_DOWNLOAD_{appid}")
            achievements_thread.start()

    if skip_stats:
        logger.info("Skipping downloading and configuring stats.")
    else:
        if stat_info is not None:
            write_stats(stat_info=stat_info,
                        use_steam_for_stats=use_steam_for_stats,
                        output_dir_relations=output_dir_relations,
                        tools_path=tools_path,
                        appid=appid,
                        fallback_to_steam=fallback_to_steam)

    return achievements_thread, fallback_language_used


def get_appid_and_buildid(game_dir: str | None,
                          package_dir: str | None,
                          do_not_ask: bool,
                          tools_path: str,
                          archive_password: str | None) -> ExtractOrAskIdsResult:
    """
    Retrieve the app ID and build ID from either the game or package directories.
    """
    ids_result = get_ids(game_dir=game_dir,
                         package_dir=package_dir,
                         tools_path=tools_path,
                         archive_password=archive_password)

    if ids_result["appid"] is None:
        if do_not_ask:
            logger.critical("Game app ID couldn't be extracted and --do-not-ask was supplied. Exiting...")
            sys.exit(1)

        appid = input("Game app ID: ").strip()

        if appid == "":
            logger.critical("No app ID was supplied. Exiting...")
            sys.exit(1)
        elif STEAM_APPID_PATTERN.match(appid) is None:
            logger.critical("Invalid app ID. Exiting...")
            sys.exit(1)

        ids_result["appid"] = appid

    logger.info(f"Extracted app ID: {ids_result['appid']} - Extracted build ID: {ids_result['buildid']}")
    return {
        "appid": ids_result["appid"],
        "buildid": ids_result["buildid"],
        "extracted_files_path": ids_result["extracted_files_path"],
        "resulting_acf_files": ids_result["resulting_acf_files"],
        "tried_extracting_package_files": ids_result["tried_extracting_package_files"],
    }


def set_output_directory(package_dir: str | None,
                         game_dir: str | None,
                         output_dir: str | None,
                         output_dir_is_base: bool,
                         extracted_files_path: str | None,
                         tried_extracting_package_files: bool,
                         fail_if_no_dll: bool,
                         tools_path: str,
                         archive_password: str | None) -> OutputDirResult:
    if output_dir is None:
        logger.info("Trying to infer output directory...")
        result = get_output_dir(package_dir=package_dir,
                                game_dir=game_dir,
                                extracted_files_path=extracted_files_path,
                                tried_extracting_package_files=tried_extracting_package_files,
                                fail_if_no_dll=fail_if_no_dll,
                                tools_path=tools_path,
                                archive_password=archive_password)

        logger.debug(f"Output directories:\n"
                     f"{orjson.dumps(result['output_dir_relations'], option=orjson.OPT_INDENT_2).decode('utf-8')}")

        return result
    else:
        if output_dir_is_base:
            logger.info("Treat output directory as base was specified.")
            return force_output_dir(output_dir=output_dir,
                                    package_dir=package_dir,
                                    game_dir=game_dir,
                                    extracted_files_path=extracted_files_path,
                                    tried_extracting_package_files=tried_extracting_package_files,
                                    fail_if_no_dll=fail_if_no_dll,
                                    tools_path=tools_path,
                                    archive_password=archive_password)
        else:
            if STEAM_SETTINGS_FOLDER_NAME_PATTERN.search(os.path.basename(output_dir)) is not None:
                out_path: str = os.path.dirname(output_dir)
            else:
                out_path = output_dir
                output_dir = os.path.join(output_dir, "steam_settings")

            if out_path == package_dir or out_path == game_dir:
                directory_to_compress = None
            else:
                directory_to_compress = out_path

            result = get_steam_lib_location(
                    game_dir=game_dir,
                    package_dir=package_dir,
                    extracted_files_path=extracted_files_path,
                    tried_extracting_package_files=tried_extracting_package_files,
                    fail_if_no_dll=fail_if_no_dll,
                    tools_path=tools_path,
                    archive_password=archive_password)

            lib_locations = result["lib_locations"]
            extracted_files_path = result["extracted_files_path"]

            # If DLLs/SOs are found, we try to use the best one here because the output directory shouldn't be used as a
            # base and should be respected (the output of this program should directly be stored in that location)
            if lib_locations is not None and len(lib_locations) > 1:
                logger.warning("Found more than one DLL/SO location, using only one...")

            if lib_locations is not None:
                output_dir_relations = {
                    output_dir: [get_best_lib_file(lib_locations=lib_locations)]
                }
            else:
                output_dir_relations = {
                    output_dir: None
                }

            return {
                "output_dir": output_dir,
                "directory_to_compress": directory_to_compress,
                "lib_locations": lib_locations,
                "output_dir_relations": output_dir_relations,
                "extracted_files_path": extracted_files_path,
                "is_linux": result["is_linux"],
            }


def extract_configuration_package(directory_to_compress: str | None,
                                  compressed_filename: str,
                                  tools_path: str) -> None:
    if directory_to_compress is None:
        return

    compressed_filepath: str = os.path.join(directory_to_compress, compressed_filename)

    if not os.path.isfile(compressed_filepath):
        return

    logger.info("Extracting existing configuration package...")

    sevenzip_path = ensure_sevenzip(tools_path=tools_path)

    if sevenzip_path is None:
        logger.error("Couldn't download 7-zip, aborting...")
        sys.exit(2)

    tmp_dir = extract_compressed_file_content(sevenzip_path=sevenzip_path,
                                              compressed_file_path=compressed_filepath,
                                              file_list=[],
                                              output_path=directory_to_compress)
    if tmp_dir is None:
        sys.exit(4)

    os.remove(remove_readonly_flag(path=compressed_filepath))


def get_best_lib_file(lib_locations: list[str]) -> str:
    logger.info("Searching for the best DLL/SO...")

    for name_to_search in (STEAMAPI64_DLL_NAME, STEAMAPI_DLL_NAME, STEAMCLIENT64_DLL_NAME, STEAMCLIENT_DLL_NAME,
                           STEAMAPI_SO_NAME, STEAMCLIENT_SO_NAME):
        for lib_location in lib_locations:
            lib_name = os.path.basename(lib_location)

            if lib_name.lower() == name_to_search.lower():
                logger.info(f"Found the best DLL/SO: {name_to_search} (location: {lib_location})")
                return lib_location

    logger.info("Couldn't find the best DLL/SO, using the first one found...")
    return lib_locations[0]


def get_ids(game_dir: str | None,
            package_dir: str | None,
            tools_path: str,
            archive_password: str | None) -> ExtractIdsResult:
    """
    Search for the app ID and build ID in the package files or the steam_appid.txt file in the game directory.

    Returns:
        The retrieved app ID and build ID.
    """
    # This function should never return None for the appid, either return a string or exit.
    # The build ID is not used at the moment, which is why it can return None for it.

    logger.info("Getting IDs...")

    if game_dir is not None:
        # If game directory is provided we can't retrieve the build ID.
        return {
            "appid": extract_appid_from_game_dir(game_dir=game_dir),
            "buildid": None,
            "extracted_files_path": None,
            "resulting_acf_files": None,
            "tried_extracting_package_files": False,
        }
    elif package_dir is not None:
        return extract_ids_from_package_dir(package_dir=package_dir,
                                            tools_path=tools_path,
                                            archive_password=archive_password)
    else:
        logger.critical("No package directory or game directory was specified. Exiting...")
        sys.exit(3)


def extract_appid_from_game_dir(game_dir: str) -> str | None:
    logger.info("Extracting app ID from game directory...")

    appid_files = glob.glob(f"**{os.path.sep}steam_appid.txt", recursive=True, root_dir=game_dir)
    logger.debug(f"Found steam_appid.txt files:\n{appid_files}")

    if len(appid_files) == 0:
        logger.error("No steam_appid.txt file found in the game directory.")
        return None

    # We use the first file here.
    with open(os.path.join(game_dir, appid_files[0]), "r", encoding="utf-8") as stream:
        appid = stream.readline().strip()

    if STEAM_APPID_PATTERN.match(appid) is None:
        logger.error("Invalid steam_appid.txt content.")
        return None

    logger.info("Finished extracting app ID from game directory.")
    return appid


def extract_ids_from_package_dir(package_dir: str,
                                 tools_path: str,
                                 archive_password: str | None) -> ExtractIdsResult:
    """
        Extract the app ID and build ID from the provided package directory.
    """
    logger.info("Extracting IDs from package directory...")

    extracted_appid: str | None
    extracted_build_id: str | None
    resulting_acf_files: set[str] | None = None

    # First, we try with the compressed files contents
    logger.info("Trying to determine app ID and build ID from the compressed package files...")
    result = extract_ids_from_compressed_package_files(
            package_dir=package_dir,
            tools_path=tools_path,
            archive_password=archive_password)

    extracted_appid = result["appid"]
    extracted_build_id = result["buildid"]
    extraction_path = result["temp_path"]
    extracted_acf_files = result["acf_files"]
    tried_extracting_package_files = result["tried_extracting_package_files"]

    if extracted_acf_files is not None and len(extracted_acf_files) > 0:
        resulting_acf_files = extracted_acf_files

    # if we could extract one, then most likely both were
    if extracted_appid is not None and extracted_build_id is not None:
        logger.debug(f"Found IDs:\nApp ID: {extracted_appid}\nBuild ID: {extracted_build_id}")
        logger.info("Finished extracting IDs from package directory.")
        return {
            "appid": extracted_appid,
            "buildid": extracted_build_id,
            "extracted_files_path": extraction_path,
            "resulting_acf_files": resulting_acf_files,
            "tried_extracting_package_files": tried_extracting_package_files
        }

    # Next, we try with the loose ACF files, provided there are exactly one ACF (excluding the redistributables)
    logger.info("Trying to extract IDs from loose ACF file...")
    extract_id_result = extract_id_from_acf(root_dir=package_dir)

    extracted_appid = extract_id_result["appid"]
    extracted_build_id = extract_id_result["buildid"]
    loose_acf_files = extract_id_result["acf_files"]

    if loose_acf_files is not None and len(loose_acf_files) > 0:
        resulting_acf_files = loose_acf_files

    # if we could extract one, then most likely both were
    if extracted_appid is not None:
        logger.debug(f"Found IDs:\nApp ID: {extracted_appid}\nBuild ID: {extracted_build_id}")
        logger.info("Finished extracting IDs from package directory.")
        return {
            "appid": extracted_appid,
            "buildid": extracted_build_id,
            "extracted_files_path": extraction_path,
            "resulting_acf_files": resulting_acf_files,
            "tried_extracting_package_files": tried_extracting_package_files
        }

    logger.info("IDs not found in ACF file, trying with the compressed filenames...")

    filename_appid: str | None = None
    filename_build_id: str | None = None

    # Next we try by simply reading the filenames; for this to work, the filename must follow the pattern (extension
    # might differ): "Game Name (%appid%) [%build_id%].7z.001"
    package_files = os.listdir(package_dir)
    for file in package_files:
        if not os.path.isfile(os.path.join(package_dir, file)):
            continue

        filename_ids: Match[str] | None = EXTRACT_FROM_PACKAGE_NAME_PATTERN.search(file)
        if filename_ids is None:
            continue

        filename_appid: str | None = filename_ids.group(1)
        # The app ID might belong to a non-game one, but since it is present in the package files, we simply use it as
        # is, so no filtering here.
        logger.debug(f"Filename app ID: {filename_appid}")

        try:
            filename_build_id: str | None = filename_ids.group(2)
            logger.debug(f"Filename build ID: {filename_build_id}")
        except (AttributeError, IndexError):
            logger.debug("Build ID not found in filename.")

        break

    if filename_appid is not None:
        logger.debug(f"Found IDs:\nApp ID: {filename_appid}\nBuild ID: {filename_build_id}")
        logger.info("Finished extracting IDs from package directory.")
        return {
            "appid": filename_appid,
            "buildid": filename_build_id,
            "extracted_files_path": extraction_path,
            "resulting_acf_files": resulting_acf_files,
            "tried_extracting_package_files": tried_extracting_package_files
        }

    # If the appid wasn't found in the filename, then try looking for the steam_appid.txt file.

    logger.info("IDs not found in the filename, trying looking for steam_appid.txt file...")

    found_appid = extract_appid_from_steam_appid_file(root_dir=package_dir)

    # If that didn't work, then just return None because we need the appid to get the build ID from the ACF file.
    if found_appid is None:
        logger.critical("Couldn't extract the app ID from the package files.")
        return {
            "appid": None,
            "buildid": None,
            "extracted_files_path": extraction_path,
            "resulting_acf_files": resulting_acf_files,
            "tried_extracting_package_files": tried_extracting_package_files
        }

    logger.debug(f"Extracted app ID from steam_appid.txt file: {found_appid}.")

    if extracted_acf_files is not None and len(extracted_acf_files) > 0:
        acf_files = extracted_acf_files
    elif loose_acf_files is not None:
        acf_files = loose_acf_files
    else:
        acf_files = None

    if acf_files is not None and len(acf_files) > 0:
        resulting_acf_files = acf_files
        logger.info("Trying to extract buildid from ACF file using the found app ID...")
        extracted_build_id = extract_buildid_from_acf(acf_files=acf_files,
                                                      appid=found_appid)

    logger.info("Finished extracting IDs from package directory.")
    return {
        "appid": found_appid,
        "buildid": extracted_build_id,
        "extracted_files_path": extraction_path,
        "resulting_acf_files": resulting_acf_files,
        "tried_extracting_package_files": tried_extracting_package_files
    }


@overload
def extract_ids_from_compressed_package_files(package_dir: str,
                                              tools_path: str,
                                              archive_password: str | None,
                                              no_appid_search: Literal[True]) -> str | None:
    ...


@overload
def extract_ids_from_compressed_package_files(package_dir: str,
                                              tools_path: str,
                                              archive_password: str | None,
                                              no_appid_search: Literal[False] = ...) -> ExtractFromPackageFilesResult:
    ...


def extract_ids_from_compressed_package_files(package_dir: str,
                                              tools_path: str,
                                              archive_password: str | None,
                                              no_appid_search: bool = False) -> (ExtractFromPackageFilesResult | str |
                                                                                 None):
    """
    Returns a dict containing the app ID, build ID, path to the extracted files, a list of all the found ACF files, and
    whether we have tried extracting the package files.

    If `no_appid_search` is True, then it only returns the path where the files have been extracted.
    """
    if not no_appid_search:
        logger.info("Extracting app ID and build ID from compressed files...")

    tmp_dir = extract_from_package_files(directory=package_dir,
                                         tools_path=tools_path,
                                         archive_password=archive_password)

    if tmp_dir is None:
        if no_appid_search:
            return None
        else:
            return {
                "appid": None,
                "buildid": None,
                "temp_path": None,
                "acf_files": None,
                "tried_extracting_package_files": False
            }

    if no_appid_search:
        return tmp_dir

    logger.info("Finished extracting files.")

    extract_id_result = extract_id_from_acf(root_dir=tmp_dir)

    appid = extract_id_result["appid"]

    if appid is None:
        logger.info("Trying to retrieve app ID from extracted steam_appid.txt file...")

        appid = extract_appid_from_steam_appid_file(root_dir=tmp_dir)

    return {
        "appid": appid,
        "buildid": extract_id_result["buildid"],
        "temp_path": tmp_dir,
        "acf_files": extract_id_result["acf_files"],
        "tried_extracting_package_files": True
    }


def extract_from_package_files(directory: str,
                               tools_path: str,
                               archive_password: str | None) -> str | None:
    """
    Extracts all the found .dll, .so, and .acf files from the found package file in the provided directory.

    Returns:
        The path where the files have been extracted to.
    """
    compressed_file = search_for_package_file(directory=directory)

    if compressed_file is None:
        logger.info("No compressed file was found...")
        return None

    sevenzip_path = ensure_sevenzip(tools_path=tools_path)
    if sevenzip_path is None:
        logger.critical("Couldn't download 7-zip, aborting...")
        sys.exit(2)

    sevenzip_output = list_compressed_file_content(sevenzip_path=sevenzip_path,
                                                   compressed_file_path=compressed_file,
                                                   patterns=SEVENZIP_LIST_WILDCARD_PATTERNS,
                                                   archive_password=archive_password)

    if sevenzip_output is None:
        return None

    logger.debug(f"7-zip listing output:\n{sevenzip_output}")

    if sevenzip_output == "":
        logger.info("No Steam files found in the compressed files...")
        return None

    found_files = extract_paths_from_7z_listing(sevenzip_output=sevenzip_output)

    if len(found_files) == 0:
        logger.error("No Steam files found in the compressed files...")
        return None

    logger.debug(f"Found files: {found_files}")

    logger.info("Extracting found Steam files...")

    return extract_compressed_file_content(sevenzip_path=sevenzip_path,
                                           compressed_file_path=compressed_file,
                                           file_list=found_files,
                                           archive_password=archive_password)


def get_output_dir(game_dir: str | None,
                   package_dir: str | None,
                   extracted_files_path: str | None,
                   tried_extracting_package_files: bool,
                   fail_if_no_dll: bool,
                   tools_path: str,
                   archive_password: str | None) -> OutputDirResult:
    """
    Build the output directory path from scratch.
    """
    logger.info("Determining output directory...")

    if package_dir is not None:
        logger.info("Building output directory...")

        result = get_steam_lib_location(
                game_dir=game_dir,
                package_dir=package_dir,
                extracted_files_path=extracted_files_path,
                tried_extracting_package_files=tried_extracting_package_files,
                fail_if_no_dll=fail_if_no_dll,
                tools_path=tools_path,
                archive_password=archive_password)

        relative_lib_location = result["relative_lib_location"]
        lib_locations = result["lib_locations"]
        extracted_files_path = result["extracted_files_path"]

        base_path: str = os.path.join(package_dir, "emu_config")
        directory_to_compress = base_path

        output_dir_relations: OutputDirRelations

        if relative_lib_location is None:
            output_dir_relations = {
                os.path.join(base_path, "steam_settings"): None
            }
        else:
            output_dir_relations = {}
            for full_path in relative_lib_location:
                location_parts = relative_lib_location[full_path].split(os.path.sep)
                steamapps_index: int | None = None
                try:
                    steamapps_index = location_parts.index("steamapps")
                except ValueError:
                    pass

                common_index: int | None = None
                try:
                    common_index = location_parts.index("common")
                except ValueError:
                    pass

                if common_index is not None and steamapps_index is not None:
                    if common_index - steamapps_index == 1:
                        location_parts = location_parts[common_index + 1:]

                output_dir = os.path.join(base_path, *location_parts, "steam_settings")

                if output_dir not in output_dir_relations:
                    output_dir_relations[output_dir] = [full_path]
                else:
                    output_dir_relations[output_dir].append(full_path)
    else:
        result = get_steam_lib_location(
                game_dir=game_dir,
                package_dir=package_dir,
                extracted_files_path=extracted_files_path,
                tried_extracting_package_files=tried_extracting_package_files,
                fail_if_no_dll=fail_if_no_dll,
                tools_path=tools_path,
                archive_password=archive_password)

        lib_locations = result["lib_locations"]
        extracted_files_path = result["extracted_files_path"]

        directory_to_compress = None

        if lib_locations is None:
            # No output directory has been given, and no DLL/SO file has been found, so we fall back to the current
            # working directory
            output_dir_relations = {
                os.path.join(os.getcwd(), "steam_settings"): None
            }
        else:
            output_dir_relations = {}
            for lib in lib_locations:
                output_dir = os.path.join(os.path.dirname(lib), "steam_settings")

                if output_dir not in output_dir_relations:
                    output_dir_relations[output_dir] = [lib]
                else:
                    output_dir_relations[output_dir].append(lib)

    return {
        "output_dir_relations": output_dir_relations,
        "lib_locations": lib_locations,
        "directory_to_compress": directory_to_compress,
        "output_dir": None,
        "extracted_files_path": extracted_files_path,
        "is_linux": result["is_linux"],
    }


def force_output_dir(output_dir: str,
                     package_dir: str | None,
                     game_dir: str | None,
                     extracted_files_path: str | None,
                     tried_extracting_package_files: bool,
                     fail_if_no_dll: bool,
                     tools_path: str,
                     archive_password: str | None) -> OutputDirResult:
    logger.info("Determining output directory from base...")

    if STEAM_SETTINGS_FOLDER_NAME_PATTERN.search(os.path.basename(output_dir)) is not None:
        output_dir = os.path.dirname(output_dir)

    if output_dir == package_dir or output_dir == game_dir:
        # We do this only if the output directory is the same as the package or game directory because the user
        # specified that we should use it as base so the user doesn't want the configuration in the
        # correct place (that is, not in the DLL/SO location in the game directory and not in the DLL/SO location
        # in the package directory with loose files), so in these cases we add an "emu_config" intermediary folder.
        output_dir = os.path.join(output_dir, "emu_config")

    directory_to_compress = output_dir

    logger.info("Building output directory...")

    result = get_steam_lib_location(
            game_dir=game_dir,
            package_dir=package_dir,
            extracted_files_path=extracted_files_path,
            tried_extracting_package_files=tried_extracting_package_files,
            fail_if_no_dll=fail_if_no_dll,
            tools_path=tools_path,
            archive_password=archive_password)

    relative_lib_location = result["relative_lib_location"]
    lib_locations = result["lib_locations"]
    extracted_files_path = result["extracted_files_path"]
    is_linux = result["is_linux"]

    output_dir_relations: OutputDirRelations

    if relative_lib_location is None:
        output_dir_relations = {
            os.path.join(output_dir, "steam_settings"): None
        }
    else:
        output_dir_relations = {}

        for fullpath_lib in relative_lib_location:
            location_parts = relative_lib_location[fullpath_lib].split(os.path.sep)
            steamapps_index: int | None = None
            try:
                steamapps_index = location_parts.index("steamapps")
            except ValueError:
                pass

            common_index: int | None = None
            try:
                common_index = location_parts.index("common")
            except ValueError:
                pass

            if common_index is not None and steamapps_index is not None:
                if common_index - steamapps_index == 1:
                    location_parts = location_parts[common_index + 1:]

            output_directory = os.path.join(output_dir, *location_parts, "steam_settings")

            if output_directory not in output_dir_relations:
                output_dir_relations[output_directory] = [fullpath_lib]
            else:
                output_dir_relations[output_directory].append(fullpath_lib)

    logger.debug(f"Output directories:\n"
                 f"{orjson.dumps(output_dir_relations, option=orjson.OPT_INDENT_2).decode('utf-8')}")

    return {
        "output_dir": output_dir,
        "directory_to_compress": directory_to_compress,
        "lib_locations": lib_locations,
        "output_dir_relations": output_dir_relations,
        "extracted_files_path": extracted_files_path,
        "is_linux": is_linux,
    }


def get_steam_lib_location(game_dir: str | None,
                           package_dir: str | None,
                           extracted_files_path: str | None,
                           tried_extracting_package_files: bool,
                           fail_if_no_dll: bool,
                           tools_path: str,
                           archive_password: str | None) -> GetSteamLibLocationResult:
    """
    Retrieves all locations where a Steam DLL/SO file is found.
    """
    logger.info("Searching for the steam DLL/SO location...")

    is_linux = False

    root_dir: str
    if game_dir is not None:
        logger.debug("Using the game directory as base.")
        root_dir = game_dir
    elif package_dir is not None:
        if extracted_files_path is None and not tried_extracting_package_files:
            logger.info("DLL/SO files haven't been searched for...")
            extracted_files_path = extract_ids_from_compressed_package_files(tools_path=tools_path,
                                                                             package_dir=package_dir,
                                                                             archive_password=archive_password,
                                                                             no_appid_search=True)

        if extracted_files_path is not None:
            logger.debug("Using the extracted files directory as base.")
            root_dir = extracted_files_path
        else:
            logger.debug("Using the package directory as base.")
            root_dir = package_dir
    else:
        logger.critical("Both game_dir and package_dir were not specified. Exiting...")
        sys.exit(3)

    logger.debug(f"Root dir: {root_dir}")

    all_game_lib_files = glob.glob(f"**{os.path.sep}*.dll", recursive=True, root_dir=root_dir)

    if len(all_game_lib_files) == 0:
        is_linux = True
        all_game_lib_files = glob.glob(f"**{os.path.sep}*.so", recursive=True, root_dir=root_dir)

    logger.debug(f"All found DLL/SO:\n{all_game_lib_files}")

    steam_lib_files: list[str] = []
    relative_dict: dict[str, str] = {}

    if is_linux:
        patterns = (STEAM_API_SO_PATTERN, STEAMCLIENT_SO_PATTERN)
    else:
        patterns = (STEAM_API_DLL_PATTERN, STEAMCLIENT_DLL_PATTERN)

    for pattern in patterns:
        for lib_file in all_game_lib_files:
            if pattern.search(os.path.basename(lib_file)) is not None:
                lib_filepath: str = os.path.join(root_dir, lib_file)
                steam_lib_files.append(lib_filepath)

                relative_dict[lib_filepath] = os.path.dirname(lib_file)

                logger.info(f"Found Steam DLL/SO: {lib_file}")
                logger.debug(f"Full path: {lib_filepath}")

    if len(steam_lib_files) > 0:
        return {
            "relative_lib_location": relative_dict,
            "lib_locations": steam_lib_files,
            "extracted_files_path": extracted_files_path,
            "is_linux": is_linux,
        }

    if fail_if_no_dll:
        logger.critical("No steam DLL/SO file found.")
        sys.exit(10)
    else:
        logger.info("No steam DLL/SO file found.")
        return {
            "relative_lib_location": None,
            "lib_locations": None,
            "extracted_files_path": extracted_files_path,
            "is_linux": is_linux,
        }


def extract_id_from_acf(root_dir: str) -> ExtractIdFromAcfResult:
    """
    Extract app ID and build ID from found .ACF files in the provided directory.
    """
    logger.info("Trying to retrieve app ID and build ID from ACF files...")

    acf_files = find_acf_files(root_dir=root_dir)

    # If we didn't get only one result, then we can't do anything yet, any of the files could be the game's.
    if len(acf_files) != 1:
        logger.info("There is not only a single ACF file, can't extract app ID from ACF.")
        logger.debug("If there is more than one ACF file then we can't know which one is the one belonging to the "
                     "game.")
        return {
            "appid": None,
            "buildid": None,
            "acf_files": acf_files
        }

    acf_file = next(iter(acf_files))

    logger.debug(f"Retrieving app ID from file: {acf_file}")

    with open(acf_file, "r", encoding="utf-8") as stream:
        acf_content = stream.readlines()

    appid: str | None = None

    for line in acf_content:
        acf_appid_match = ACF_APPID_PATTERN.search(line)

        if acf_appid_match is None:
            continue

        try:
            appid = acf_appid_match.group(1)
        except IndexError:
            continue

        if int(appid) in NON_GAME_APPIDS:
            logger.debug(f"Skipping non game app ID: {appid}")
            continue

        logger.debug(f"Found app ID: {appid}")
        break

    if appid is None:
        logger.debug("Couldn't extract the app ID from the ACF file.")

    buildid: str | None = None

    for line in acf_content:
        acf_buildid_match = ACF_BUILDID_PATTERN.search(line)

        if acf_buildid_match is None:
            continue

        try:
            buildid = acf_buildid_match.group(1)

            logger.debug(f"Found build ID: {buildid}")
            break
        except IndexError:
            continue

    if buildid is None:
        logger.debug("Couldn't extract the build ID from the ACF file.")

    logger.info("Finished retrieving app ID and build ID from ACF file.")
    return {
        "appid": appid,
        "buildid": buildid,
        "acf_files": acf_files
    }


def extract_appid_from_steam_appid_file(root_dir: str) -> str | None:
    """
    Extract the app ID from found steam_appid.txt files in the provided directory.
    """
    appid: str | None = None

    for appid_file in glob.glob(f"**{os.path.sep}steam_appid.txt", recursive=True, root_dir=root_dir):
        with open(os.path.join(root_dir, appid_file), "r", encoding="utf-8") as stream:
            extracted_appid = stream.readline().strip()

        appid_match = ACF_APPID_PATTERN.match(extracted_appid)

        if appid_match is None:
            continue

        extracted_appid = appid_match.group(1)

        if int(extracted_appid) in NON_GAME_APPIDS:
            continue
        else:
            appid = extracted_appid
            logger.debug(f"Found app ID in extracted steam_appid.txt file: {appid}")
            break

    return appid


def extract_buildid_from_acf(acf_files: set[str],
                             appid: str) -> str | None:
    """
    Extract the build ID from the ACF file using the provided app ID.
    """
    for file in acf_files:
        with open(file, "r", encoding="utf-8") as stream:
            acf_content = stream.read()

        appid_match = ACF_APPID_PATTERN.search(acf_content)

        if appid_match is None:
            continue

        try:
            extracted_appid: str = appid_match.group(1)
        except IndexError:
            continue

        if extracted_appid != appid:
            continue

        buildid_match = ACF_BUILDID_PATTERN.search(acf_content)

        if buildid_match is None:
            continue

        try:
            extracted_buildid: str = buildid_match.group(1)
            return extracted_buildid
        except IndexError:
            logger.debug(f"Couldn't extract the build ID from the ACF file: {file}")
            return None

    return None


def get_steam_game_info(appid: str,
                        cache_opts: CacheOptions) -> SteamGameInfo | None:
    logger.info("Retrieving game information...")

    steam_game_info_file_cache_path = os.path.join(cache_opts.cache_location, appid, f"steam_game_info_english.json")
    steam_game_info_last_retrieval_flag_path = os.path.join(cache_opts.cache_location,
                                                            appid,
                                                            f"steam_game_info_english_last_retrieval")

    if cache_opts.cache_game_info and os.path.isfile(steam_game_info_last_retrieval_flag_path):
        with open(steam_game_info_last_retrieval_flag_path, "r", encoding="utf-8") as flag_stream:
            last_retrieval = flag_stream.read()

        if not should_refresh_cache(date=last_retrieval):
            logger.info(f"Using cached game info: {steam_game_info_file_cache_path}")

            with open(steam_game_info_file_cache_path, "r", encoding="utf-8") as file_stream:
                game_info_dict = json.loads(file_stream.read())

            return SteamGameInfo(game_info=game_info_dict)

    try:
        # Use English here to be able to extract the supported languages
        store_info_response = get_with_retry(url=APP_DETAILS_URL_TEMPLATE.substitute(appid=appid,
                                                                                     language="english"))
    except RemoteDisconnected:
        logger.critical("Couldn't retrieve game information.")
        sys.exit(1)
    except HTTPError as err:
        if err.response.status_code == 404:
            logger.error("Game information not found.")
            return None
        else:
            logger.error("An error occurred retrieving the game information.")
            sys.exit(2)

    game_info_dict = json.loads(store_info_response.content.decode(encoding="utf-8"))
    logger.info("Game info retrieved.")
    logger.debug(f"Game info:\n{game_info_dict}")

    try:
        raw_gameinfo = RawSteamGameInfo(game_info=game_info_dict)
    except ValidationError as err:
        logger.critical(f"Error validating game information:\n{process_errors(error_details=err.errors())}")
        logger.opt(exception=True).debug("Traceback:")
        sys.exit(6)

    if not raw_gameinfo.game_info[appid].success or raw_gameinfo.game_info[appid].data is None:
        return None
    else:
        try:
            steam_game_info = SteamGameInfo(game_info=game_info_dict)
        except ValidationError as err:
            logger.critical(f"Error validating game information:\n{process_errors(error_details=err.errors())}")
            logger.opt(exception=True).debug("Traceback:")
            sys.exit(6)

        if cache_opts.cache_game_info:
            os.makedirs(os.path.dirname(steam_game_info_file_cache_path), exist_ok=True)

            with open(steam_game_info_file_cache_path, "wb") as file_stream:
                file_stream.write(store_info_response.content)

            write_last_retrieval_flag(steam_game_info_last_retrieval_flag_path)

        return steam_game_info


def get_gh_game_info(tools_path: str,
                     appid: str) -> GHGameInfo | None:
    game_info_file: str = os.path.join(tools_path, STATS_REPO_SUB_PATH, "steam", appid, f"{appid}.json")

    if not os.path.exists(game_info_file):
        return None

    with open(game_info_file, "rb") as stream:
        try:
            gh_game_info = GHGameInfo.model_validate(orjson.loads(stream.read()))
        except ValidationError as err:
            logger.critical(f"Error validating GH game information:\n{process_errors(error_details=err.errors())}")
            logger.opt(exception=True).debug("Traceback:")
            sys.exit(6)

    return gh_game_info


def get_stat_info(appid: str,
                  api_key: str,
                  cache_opts: CacheOptions,
                  lang_opts: LanguageOptions,
                  do_not_retry: bool = False) -> tuple[SteamStatInfo | None, bool]:
    """
    Since this uses the language to grab the stat info, a fallback language may be requested, because of this it returns
    a tuple with the stat info and whether a fallback was used or not.
    """
    if not do_not_retry:
        logger.info("Retrieving game stats and achievements...")

    responses: dict[str, RawSteamStatInfo] = {}

    # We are avoiding modifying objects in sub-functions, so the value is extracted into a variable and then the
    # variable itself will be returned to finally set the object to the new value
    fallback_language_used = lang_opts.fallback_language_used

    if lang_opts.sanitized_language == "english":
        languages = [lang_opts.sanitized_language]
        do_not_compare = True
    else:
        languages = [lang_opts.sanitized_language, "english"]
        do_not_compare = False

    for language in languages:
        response_content = download_stat_info(appid=appid,
                                              language=language,
                                              api_key=api_key,
                                              cache_opts=cache_opts)
        try:
            responses[language] = RawSteamStatInfo.model_validate_json(response_content)
        except ValidationError as err:
            logger.critical(f"Error validating stats information:\n{process_errors(error_details=err.errors())}")
            logger.opt(exception=True).debug("Traceback:")
            sys.exit(6)

    if do_not_compare:
        if responses[languages[0]].game is None:
            return None, fallback_language_used
        else:
            return SteamStatInfo.model_validate(responses[languages[0]].model_dump()), fallback_language_used

    preferred_language_data = responses[languages[0]]
    english_language_data = responses[languages[1]]

    if preferred_language_data.game is None:
        # if the preferred language is not available
        if fallback_language_used:
            logger.warning(f"No game stats found for {languages[0]} language. Trying with English...")
            if english_language_data.game is None:
                logger.warning(f"No game stats found for this game.")  # possible duplicated log
                return None, fallback_language_used
            else:
                return SteamStatInfo.model_validate(english_language_data.model_dump()), fallback_language_used
    elif english_language_data.game is not None:
        # if the preferred language is available and English was also available
        lang_1_arch = preferred_language_data.game.availableGameStats.achievements
        lang_2_arch = english_language_data.game.availableGameStats.achievements
        if lang_1_arch == lang_2_arch:
            if not fallback_language_used:
                logger.warning("Achievements in the preferred language aren't localized, trying with fallback...")
            else:
                logger.warning("Achievements in the preferred language aren't localized, will use English.")
                return SteamStatInfo.model_validate(english_language_data.model_dump()), fallback_language_used
        else:
            return SteamStatInfo.model_validate(preferred_language_data.model_dump()), fallback_language_used
    else:
        # if the preferred language was available and English was not available,
        # this would be very rare to happen, info is almost always available in English
        return SteamStatInfo.model_validate(preferred_language_data.model_dump()), fallback_language_used

    if lang_opts.supported_languages is None:
        logger.warning(f"No game stats found for {languages[0]} language and the supported languages is "
                       f"unknown, skipping...")
        return None, fallback_language_used
    else:
        logger.warning(f"No game stats found for {languages[0]} language. Trying with fallback language...")

    alt_supported_languages = lang_opts.supported_languages.copy()
    alt_supported_languages.remove(lang_opts.sanitized_language)
    fallback_language, fallback_language_used = get_sanitized_preferred_language(
            supported_languages=alt_supported_languages,
            preferred_language=lang_opts.preferred_language,
            quiet=True)

    if fallback_language_used:
        logger.info(f"Using fallback language: {fallback_language}")

        response_content = download_stat_info(appid=appid,
                                              language=fallback_language,
                                              api_key=api_key,
                                              cache_opts=cache_opts)
        try:
            fallback_response = RawSteamStatInfo.model_validate_json(response_content)
        except ValidationError as err:
            logger.critical(f"Error validating stats information:\n{process_errors(error_details=err.errors())}")
            logger.opt(exception=True).debug("Traceback:")
            sys.exit(6)

        if fallback_response.game is not None:
            return SteamStatInfo.model_validate(fallback_response.model_dump()), fallback_language_used
        elif english_language_data.game is None:
            logger.warning("No game stats available for the game.")
            return None, fallback_language_used
        else:
            logger.warning(f"No game stats found for the fallback language {fallback_language}, English will be used "
                           f"for the achievements info.")
            return SteamStatInfo.model_validate(english_language_data.model_dump()), fallback_language_used
    elif english_language_data.game is None:
        logger.warning(f"No fallback exists for the preferred language and there are no game stats in English.")
        return None, fallback_language_used
    else:
        logger.warning("No fallback exists for the preferred language, English will be used for the achievements info.")
        return SteamStatInfo.model_validate(english_language_data.model_dump()), fallback_language_used


def download_stat_info(appid: str,
                       language: str,
                       api_key: str,
                       cache_opts: CacheOptions) -> str:
    stat_file_cache_path = os.path.join(cache_opts.cache_location, appid, f"steam_stat_{language}.json")
    stat_last_retrieval_flag_path = os.path.join(cache_opts.cache_location,
                                                 appid,
                                                 f"steam_stat_{language}_last_retrieval")

    if cache_opts.cache_game_info and os.path.isfile(stat_last_retrieval_flag_path):
        with open(stat_last_retrieval_flag_path, "r", encoding="utf-8") as flag_stream:
            last_retrieval = flag_stream.read()

        if not should_refresh_cache(date=last_retrieval):
            logger.info(f"Using cached Steam stat: {stat_file_cache_path}")

            with open(stat_file_cache_path, "r", encoding="utf-8") as file_stream:
                return file_stream.read()

    try:
        stats_response = get_with_retry(url=STATS_URL_TEMPLATE.substitute(appid=appid,
                                                                          language=language,
                                                                          apikey=api_key))
    except RemoteDisconnected:
        logger.critical(f"Couldn't retrieve stats information for {language}.")
        sys.exit(1)
    except HTTPError as err:
        if err.response.status_code == 404:
            logger.error(f"Stats information for {language} not found.")
            sys.exit(1)
        else:
            logger.opt(exception=True).error(f"An error occurred retrieving the stat information for {language}.")
            sys.exit(2)

    response_content: str = stats_response.content.decode(encoding="utf-8")

    if cache_opts.cache_game_info:
        os.makedirs(os.path.dirname(stat_file_cache_path), exist_ok=True)

        with open(stat_file_cache_path, "wb") as file_stream:
            file_stream.write(stats_response.content)

        write_last_retrieval_flag(stat_last_retrieval_flag_path)

    logger.debug(f"Retrieved stats info for {language}:\n{response_content}")

    return response_content


def get_preferred_lang(preferred_lang: str,
                       fallback_language: str,
                       supported_languages: set[str],
                       quiet: bool) -> tuple[str, bool]:
    fallback_language_used = False
    if fallback_language in supported_languages:
        if not quiet:
            logger.info(f"{preferred_lang} is not supported by the game, falling back to "
                        f"{fallback_language}.")
        fallback_language_used = True
        preferred_lang = fallback_language
    else:
        if not quiet:
            logger.warning(f"{preferred_lang} and {fallback_language} are not supported by the game, "
                           f"falling back to English.")
        preferred_lang = "english"

    return preferred_lang, fallback_language_used


def get_sanitized_preferred_language(supported_languages: set[str] | None,
                                     preferred_language: str,
                                     quiet: bool = False) -> tuple[str, bool]:
    """
    Verifies that the preferred language is listed in the supported languages, if it's not, the closest variation
    is used instead if it's supported by the game, otherwise English is used.
    """

    if not quiet:
        logger.info("Sanitizing language...")

    preferred_lang = preferred_language
    fallback_language_used = False

    if supported_languages is not None:
        match preferred_lang:
            case "latam":
                if preferred_lang not in supported_languages:
                    fallback_language = "spanish"
                    preferred_lang, fallback_language_used = get_preferred_lang(preferred_lang=preferred_lang,
                                                                                supported_languages=supported_languages,
                                                                                fallback_language=fallback_language,
                                                                                quiet=quiet)
            case "spanish":
                if preferred_lang not in supported_languages:
                    fallback_language = "latam"
                    preferred_lang, fallback_language_used = get_preferred_lang(preferred_lang=preferred_lang,
                                                                                supported_languages=supported_languages,
                                                                                fallback_language=fallback_language,
                                                                                quiet=quiet)
            case "brazilian":
                if preferred_lang not in supported_languages:
                    fallback_language = "portuguese"
                    preferred_lang, fallback_language_used = get_preferred_lang(preferred_lang=preferred_lang,
                                                                                supported_languages=supported_languages,
                                                                                fallback_language=fallback_language,
                                                                                quiet=quiet)
            case "portuguese":
                if preferred_lang not in supported_languages:
                    fallback_language = "brazilian"
                    preferred_lang, fallback_language_used = get_preferred_lang(preferred_lang=preferred_lang,
                                                                                supported_languages=supported_languages,
                                                                                fallback_language=fallback_language,
                                                                                quiet=quiet)
            case "tchinese":
                if preferred_lang not in supported_languages:
                    fallback_language = "schinese"
                    preferred_lang, fallback_language_used = get_preferred_lang(preferred_lang=preferred_lang,
                                                                                supported_languages=supported_languages,
                                                                                fallback_language=fallback_language,
                                                                                quiet=quiet)
            case "schinese":
                if preferred_lang not in supported_languages:
                    fallback_language = "tchinese"
                    preferred_lang, fallback_language_used = get_preferred_lang(preferred_lang=preferred_lang,
                                                                                supported_languages=supported_languages,
                                                                                fallback_language=fallback_language,
                                                                                quiet=quiet)
            case _:
                if preferred_lang not in supported_languages:
                    preferred_lang = "english"

    if not quiet:
        logger.info("Finished sanitizing language.")

    return preferred_lang, fallback_language_used


def get_supported_languages(game_info: SteamGameInfo | GHGameInfo,
                            appid: str) -> set[str] | None:
    logger.info("Extracting supported languages...")

    supported_languages: set[str] = set()
    normalized_supported_langs: set[str] = set()

    if isinstance(game_info, GHGameInfo):
        logger.info("Found GH package info, returning list of languages...")

        if game_info.Languages is None:
            return None
        else:
            return set(game_info.Languages)

    raw_supported_languages = game_info.game_info[appid].data.supported_languages
    logger.debug(f"Raw supported languages:\n{raw_supported_languages}")

    if raw_supported_languages is not None:
        raw_supported_languages = SUPPORTED_LANG_EXTRACTION_STEP_1.sub("", raw_supported_languages)
        raw_supported_languages = SUPPORTED_LANG_EXTRACTION_STEP_2.sub("", raw_supported_languages)
        supported_languages_aux = raw_supported_languages.split(",")
        for supported_language in supported_languages_aux:
            supported_language = supported_language.strip().replace(" - ", "-")

            if supported_language == "Simplified Chinese":
                supported_language = "Chinese (Simplified)"
            elif supported_language == "Traditional Chinese":
                supported_language = "Chinese (Traditional)"
            elif supported_language == "Portuguese-Portugal":
                supported_language = "Portuguese"

            supported_languages.add(supported_language)

        for language in supported_languages:
            if language in LANGUAGES_ONLY_IN_GAMES:
                logger.warning(f"Language {language} found supported in game but no support in Steam API, configure "
                               f"it in-game.")
            elif language in SUPPORTED_LANGUAGES_MAPPING:
                normalized_supported_langs.add(SUPPORTED_LANGUAGES_MAPPING[language])
            else:
                logger.warning(f"Language({language}) not recognized.")

        logger.debug(f"Normalized supported languages:\n{normalized_supported_langs}")
        logger.info("Supported language extraction finished.")
        return normalized_supported_langs
    else:
        logger.info("No supported languages found.")
        return None


def write_supported_languages(supported_languages: set[str] | None,
                              output_dir_relations: OutputDirRelations) -> None:
    logger.info("Writing supported languages...")

    if supported_languages is None or len(supported_languages) == 0:
        logger.info("No supported languages found, not writing anything.")
        return

    output_directories: list[str] = list(output_dir_relations.keys())
    main_output_filepath: str = os.path.join(output_directories[0], SUPPORTED_LANGUAGES_FILENAME)

    with open(main_output_filepath, "w", encoding="utf-8", newline=NEW_LINE) as stream:
        stream.write("\n".join(sorted(supported_languages)))

    logger.info("Finished writing supported languages.")

    if len(output_directories) > 1:
        logger.info("Copying supported languages file to the additional directories...")

        for output_dir in output_directories[1:]:
            custom_copy(main_output_filepath, output_dir)

        logger.info("Finished copying supported languages file.")


def write_interfaces_file(lib_locations: list[str] | None,
                          output_dir_relations: OutputDirRelations,
                          extracted_files_path: str | None,
                          is_linux: bool) -> None:
    logger.info("Writing interfaces file...")

    if lib_locations is None:
        logger.warning("No DLL/SO found, not writing interfaces file.")
        return

    if is_linux:
        lib_pattern = STEAM_API_SO_PATTERN
    else:
        lib_pattern = STEAM_API_DLL_PATTERN

    found: bool = False
    for output_path, relative_lib_locations in output_dir_relations.items():
        if relative_lib_locations is None:
            continue

        for lib_location in relative_lib_locations:
            if lib_pattern.search(os.path.basename(lib_location)) is not None:
                if extracted_files_path is None:
                    logger.debug(f"Using DLL/SO file: {lib_location}")
                else:
                    logger.debug(f"Using DLL/SO file: {os.path.relpath(lib_location, extracted_files_path)}")
                found = True

                with open(lib_location, "rb") as stream:
                    lib_content = stream.read().decode(encoding="utf-8", errors="backslashreplace")

                interfaces_list: set[str] = set()

                for pattern in INTERFACE_PATTERNS:
                    for match in pattern.finditer(lib_content):
                        interfaces_list.add(match.group(0))
                        break

                logger.debug(f"Interfaces found:\n{interfaces_list}")

                with open(os.path.join(output_path, INTERFACES_FILENAME),
                          "w",
                          encoding="utf-8",
                          newline=NEW_LINE) as stream:
                    stream.write("\n".join(sorted(interfaces_list)))

                if is_linux:
                    break
                elif lib_location.lower().endswith("64.dll"):
                    # We break if we found a 64.dll file because sometimes x64 games have both versions, whereas x86
                    # games will only include the x86 dll
                    break

    if not found:
        logger.warning("No Steam API DLL/SO found, not writing interfaces file.")
        logger.debug(f"Output dir and Steam DLL/SO path relations:\n"
                     f"{orjson.dumps(output_dir_relations, option=orjson.OPT_INDENT_2).decode(encoding='utf-8')}")

    logger.info("Finished writing interfaces file.")


def write_achievements_wrapper(opts: AchievementOptions,
                               cache_opts: CacheOptions,
                               lang_opts: LanguageOptions) -> None:
    try:
        write_achievements(opts=opts, cache_opts=cache_opts, lang_opts=lang_opts)
    except Exception:
        logger.opt(exception=True).critical("Error writing achievements:")
        achievement_thread_error_flag.set()
        sys.exit(7)


def write_achievements(opts: AchievementOptions,
                       cache_opts: CacheOptions,
                       lang_opts: LanguageOptions) -> None:
    logger.info("Downloading and writing achievements...")

    additional_appids: set[str] = set()

    if opts.acf_files is not None and len(opts.acf_files) > 1:
        logger.info("Getting additional appids...")
        additional_appids = get_extra_appids(acf_files=opts.acf_files, appid=opts.appid)

        if len(additional_appids) == 0:
            logger.debug("No additional appids found.")
        else:
            logger.debug(f"Found additional appids: {additional_appids}")

        logger.info("Finished getting additional appids.")

    sanitized_achievements: list[AchievementInfo] = []
    output_directories: list[str] = list(opts.output_dir_relations.keys())

    for extra_appid in additional_appids:
        extra_game_info = get_steam_game_info(appid=extra_appid,
                                              cache_opts=cache_opts)

        if extra_game_info is None:
            continue

        supported_languages: set[str] | None = get_supported_languages(game_info=extra_game_info,
                                                                       appid=extra_appid)

        extra_appid_lang_opts = lang_opts.model_copy(update={
            "supported_languages": supported_languages or lang_opts.supported_languages
        })

        extra_stat_info, _ = get_stat_info(appid=extra_appid,
                                           lang_opts=extra_appid_lang_opts,
                                           api_key=opts.api_key,
                                           cache_opts=cache_opts)

        if extra_stat_info is None:
            continue

        try:
            dlc_name: str = extra_game_info.game_info[extra_appid].data.name
        except (KeyError, AttributeError):
            dlc_name = extra_appid

        sanitized_achievements.extend(download_achievements(stat_info=extra_stat_info,
                                                            output_dir=output_directories[0],
                                                            appid=opts.appid,
                                                            base_game=False,
                                                            downloaded_achievements=tuple(sanitized_achievements),
                                                            dlc_name=dlc_name,
                                                            cache_opts=cache_opts))

    sanitized_achievements.extend(download_achievements(stat_info=opts.stat_info,
                                                        output_dir=output_directories[0],
                                                        appid=opts.appid,
                                                        downloaded_achievements=tuple(sanitized_achievements),
                                                        cache_opts=cache_opts))

    logger.info("Finished downloading achievements.")

    logger.info("Writing achievements json file...")

    achievement_list = []
    for achievement_info in sanitized_achievements:
        achievement_list.append(achievement_info.model_dump(exclude_none=True))

    with open(os.path.join(output_directories[0], "achievements.json"), "wb") as stream:
        stream.write(orjson.dumps(achievement_list, option=orjson.OPT_INDENT_2))

    logger.info("Finished writing achievements json file.")

    if len(output_directories) > 1:
        logger.info("Copying achievement files to the additional directories...")

        for output_directory in output_directories[1:]:
            custom_copy(os.path.join(output_directories[0], ACHIEVEMENTS_DIRNAME),
                        os.path.join(output_directory, ACHIEVEMENTS_DIRNAME))
            custom_copy(os.path.join(output_directories[0], "achievements.json"), output_directory)

        logger.info("Finished copying achievement files.")


def get_extra_appids(acf_files: set[str],
                     appid: str) -> set[str]:
    logger.info("Retrieving extra appids...")

    extra_appids: set[str] = set()

    for acf_file in acf_files:
        with open(acf_file, "r", encoding="utf-8") as stream:
            acf_content = stream.read().splitlines()

        additional_appid: str | None = None

        for line in acf_content:
            match_additional_appid = ACF_APPID_PATTERN.search(line)

            if match_additional_appid is None:
                continue

            try:
                additional_appid = match_additional_appid.group(1)
                logger.debug(f"Found app ID: {additional_appid}")
                break
            except IndexError:
                continue

        if additional_appid is not None and additional_appid != appid:
            extra_appids.add(additional_appid)

    return extra_appids


@overload
def download_achievements(stat_info: SteamStatInfo,
                          output_dir: str,
                          appid: str,
                          cache_opts: CacheOptions,
                          base_game: Literal[False],
                          dlc_name: str,
                          downloaded_achievements: tuple[AchievementInfo, ...] | None = None) -> list[AchievementInfo]:
    ...


@overload
def download_achievements(stat_info: SteamStatInfo,
                          output_dir: str,
                          appid: str,
                          cache_opts: CacheOptions,
                          base_game: Literal[True] = ...,
                          dlc_name: None = ...,
                          downloaded_achievements: tuple[AchievementInfo, ...] | None = None) -> list[AchievementInfo]:
    ...


def download_achievements(stat_info: SteamStatInfo,
                          output_dir: str,
                          appid: str,
                          cache_opts: CacheOptions,
                          base_game: bool = True,
                          dlc_name: str | None = None,
                          downloaded_achievements: tuple[AchievementInfo, ...] | None = None) -> list[AchievementInfo]:
    sanitized_achievements: list[AchievementInfo] = []

    if (stat_info.game is None
            or stat_info.game.availableGameStats.achievements is None
            or len(stat_info.game.availableGameStats.achievements) == 0):
        if base_game:
            logger.warning("No achievements found.")
        else:
            logger.warning(f"DLC {dlc_name}: No achievements found.")

        return []

    if base_game:
        extra_path = ""
    else:
        if dlc_name is None:
            logger.error("DLC name is None, this shouldn't happen.")
            sys.exit(4)

        extra_path = sanitize_name(name=dlc_name, do_not_use_unicode=True)

    os.makedirs(os.path.join(output_dir, ACHIEVEMENTS_DIRNAME, extra_path), exist_ok=True)

    number_of_achievements: int = len(stat_info.game.availableGameStats.achievements)
    max_msg_length: int = 0

    for idx, achievement in enumerate(stat_info.game.availableGameStats.achievements, start=1):
        if base_game:
            progress_msg: str = f"Downloading achievement {idx}/{number_of_achievements}..."
        else:
            progress_msg: str = (f"DLC {dlc_name} - Downloading achievement {idx}/"
                                 f"{number_of_achievements}...")

        max_msg_length = max(len(progress_msg), max_msg_length)

        if idx == number_of_achievements:
            progress_msg += "\n"

        if print_progress_flag.is_set():
            sys.stdout.write("\r" + " " * max_msg_length + "\r" + progress_msg)
            sys.stdout.flush()

        if achievement.hidden == 0:
            ach_hidden = 0
        else:
            ach_hidden = 1

        normal_icon_ext = os.path.splitext(achievement.icon)[1]
        gray_icon_ext = os.path.splitext(achievement.icongray)[1]

        normal_icon_rel_path = os.path.join(ACHIEVEMENTS_DIRNAME,
                                            extra_path,
                                            achievement.name +
                                            normal_icon_ext)

        if achievement.icongray.endswith("/"):
            gray_icon_rel_path = os.path.join(ACHIEVEMENTS_DIRNAME,
                                              extra_path,
                                              achievement.name + "_gray" +
                                              normal_icon_ext)
        else:
            gray_icon_rel_path = os.path.join(ACHIEVEMENTS_DIRNAME,
                                              extra_path,
                                              achievement.name + "_gray" +
                                              gray_icon_ext)

        achievement_info = AchievementInfo(name=achievement.name,
                                           displayName=achievement.displayName,
                                           description=achievement.description,
                                           icon=normal_icon_rel_path,
                                           icongray=gray_icon_rel_path,
                                           hidden=ach_hidden)

        file_path_color: str = os.path.join(output_dir, normal_icon_rel_path)
        file_path_gray: str = os.path.join(output_dir, gray_icon_rel_path)

        color_icon_cache_path = os.path.join(cache_opts.cache_location, appid, normal_icon_rel_path)
        gray_icon_cache_path = os.path.join(cache_opts.cache_location, appid, gray_icon_rel_path)

        if os.path.exists(file_path_color) and os.path.exists(file_path_gray):
            if cache_opts.copy_cache_back:
                if not os.path.exists(color_icon_cache_path):
                    custom_copy(file_path_color, color_icon_cache_path)

                if not os.path.exists(gray_icon_cache_path):
                    custom_copy(file_path_gray, gray_icon_cache_path)

            sanitized_achievements.append(achievement_info)
            logger.debug(f"Skipping achievement {achievement_info.name} because it's already downloaded.")
            continue

        # This check is here because sometimes the DLC info has achievements already present in the base game
        if downloaded_achievements is not None:
            if achievement_info in downloaded_achievements:
                logger.debug(f"Skipping achievement {achievement_info.name} because it's already downloaded.")
                continue

        if not cache_opts.force_achievement_icon_download and cache_opts.cache_game_info and os.path.isfile(
                color_icon_cache_path):
            logger.debug(f"Using cached color icon file: {color_icon_cache_path}")

            custom_copy(color_icon_cache_path, file_path_color)
        elif achievement.icon.endswith("/"):
            logger.error(f"Color icon not available for achievement: {achievement.name}.")
            achievement_info.icon = None
        else:
            try:
                response_color = get_with_retry(url=achievement.icon)

                with open(file_path_color, "wb") as stream:
                    stream.write(response_color.content)

                online_mtime: str | None = response_color.headers.get("last-modified")
                if online_mtime is not None:
                    parsed_online_mtime = parsedate_to_datetime(online_mtime).timestamp()
                    os.utime(file_path_color, times=(parsed_online_mtime, parsed_online_mtime))

                if cache_opts.cache_game_info:
                    custom_copy(file_path_color, color_icon_cache_path)
            except HTTPError:
                logger.error(f"Error downloading color icon for \"{achievement.name}\".")
                achievement_info.icon = None

        if not cache_opts.force_achievement_icon_download and cache_opts.cache_game_info and os.path.isfile(
                gray_icon_cache_path):
            logger.debug(f"Using cached gray icon file: {gray_icon_cache_path}")

            custom_copy(gray_icon_cache_path, file_path_gray)
        elif achievement.icongray.endswith("/"):
            if achievement_info.icon is not None:
                logger.warning("Gray icon not available, converting color icon to grayscale...")
                if get_gray_icon_from_normal(color_icon=file_path_color,
                                             output_path=file_path_gray):
                    if cache_opts.cache_game_info:
                        custom_copy(file_path_gray, gray_icon_cache_path)
                else:
                    achievement_info.icongray = None
            else:
                achievement_info.icongray = None
        else:
            try:
                response_gray = get_with_retry(url=achievement.icongray)

                with open(file_path_gray, "wb") as stream:
                    stream.write(response_gray.content)

                online_mtime: str | None = response_gray.headers.get("last-modified")
                if online_mtime is not None:
                    parsed_online_mtime = parsedate_to_datetime(online_mtime).timestamp()
                    os.utime(file_path_gray, times=(parsed_online_mtime, parsed_online_mtime))

                if cache_opts.cache_game_info:
                    custom_copy(file_path_gray, gray_icon_cache_path)
            except HTTPError:
                logger.warning(f"Error downloading gray icon for {achievement.name}. Converting from color icon to "
                               f"grayscale if available...")
                if achievement_info.icon is not None:
                    logger.warning("Gray icon not available, converting color icon to grayscale...")
                    if get_gray_icon_from_normal(color_icon=file_path_color,
                                                 output_path=file_path_gray):
                        if cache_opts.cache_game_info:
                            custom_copy(file_path_gray, gray_icon_cache_path)
                    else:
                        achievement_info.icongray = None
                else:
                    achievement_info.icongray = None

        sanitized_achievements.append(achievement_info)

    return sanitized_achievements


def write_stats(stat_info: SteamStatInfo,
                use_steam_for_stats: bool,
                output_dir_relations: OutputDirRelations,
                tools_path: str,
                appid: str,
                fallback_to_steam: bool) -> None:
    logger.info("Writing stats...")

    stats: set[GameStat] | None
    if use_steam_for_stats:
        stats = get_stats_from_steam(stat_info=stat_info)
    else:
        stats = get_stats_from_gh(stat_info=stat_info,
                                  tools_path=tools_path,
                                  appid=appid,
                                  fallback_to_steam=fallback_to_steam)

    if stats is None:
        logger.info("No stats found.")
        return

    output_directories: list[str] = list(output_dir_relations.keys())

    main_output_path: str = os.path.join(output_directories[0], STATS_FILENAME)

    stat_list = []
    for game_stat in stats:
        stat_list.append(game_stat.model_dump(exclude_none=True, by_alias=True))

    with open(main_output_path, "wb") as stream:
        stream.write(orjson.dumps(stat_list, option=orjson.OPT_INDENT_2))

    logger.info("Finished writing stats.")

    if len(output_directories) > 1:
        logger.info("Copying stats files to the additional directories...")

        for output_directory in output_directories[1:]:
            custom_copy(main_output_path, output_directory)

        logger.info("Finished copying stats files.")


def get_stats_from_steam(stat_info: SteamStatInfo) -> set[GameStat] | None:
    global unnamed_stat_counter
    logger.info("Getting stats from Steam...")

    if stat_info.game is None or stat_info.game.availableGameStats.stats is None:
        logger.warning("Game has no available stats.")
        return None

    game_stats: set[GameStat] = set()

    stat_entry: SteamStatEntry
    for stat_entry in stat_info.game.availableGameStats.stats:
        stat_entry_name = stat_entry.name

        if stat_entry_name is None:
            stat_entry_name = stat_entry.displayName

            if stat_entry_name is None:
                unnamed_stat_counter += 1
                stat_entry_name = f"unnamed_stat_{unnamed_stat_counter}"
            else:
                stat_entry_name = slugify(stat_entry_name[:120])

        stat_type = type(stat_entry.defaultvalue).__name__
        if stat_type not in ("float", "int"):
            logger.warning(f"Stat {stat_entry_name} is not the expected type: {stat_type}.")
            continue

        stat_entry_default = stat_entry.defaultvalue

        if isinstance(stat_entry_default, float) or isinstance(stat_entry_default, int):
            stat_entry_default = str(stat_entry_default)

        game_stat = GameStat(name=stat_entry_name,
                             type=stat_type,
                             default_val=stat_entry_default)
        game_stats.add(game_stat)

    return game_stats


def get_stats_from_gh(stat_info: SteamStatInfo,
                      tools_path: str,
                      appid: str,
                      fallback_to_steam: bool) -> set[GameStat] | None:
    global unnamed_stat_counter
    logger.info("Getting stats from GitHub...")

    if not update_gh_stats_package(tools_path=tools_path):
        logger.critical("Aborting...")
        sys.exit(9)

    stat_dir: str = os.path.join(tools_path, STATS_REPO_SUB_PATH, "steam", appid)

    if not os.path.exists(stat_dir) or not os.path.exists(os.path.join(stat_dir, "stats_db.json")):
        logger.info("No stats found on GH package.")

        if fallback_to_steam:
            logger.info("Falling back to Steam for stats...")
            return get_stats_from_steam(stat_info=stat_info)
        else:
            return None

    game_stats: set[GameStat] = set()

    with open(os.path.join(stat_dir, "stats_db.json"), "rb") as stream:
        stat_info = orjson.loads(stream.read())

    for json_entry in stat_info:
        try:
            stat_entry = GHGameStat.model_validate(json_entry)

            # gbe_fork supports only `avgrate`, `float` and `int` as the type
            # ref: https://github.com/Detanup01/gbe_fork/blob/0482c57aac070f29780af46cb1dfaea6af9ffd4b/dll
            # /steam_user_stats.cpp#L208

            stat_entry_name = stat_entry.name

            if stat_entry_name is None:
                stat_entry_name = stat_entry.displayName

                if stat_entry_name is None:
                    unnamed_stat_counter += 1
                    stat_entry_name = f"unnamed_stat_{unnamed_stat_counter}"
                else:
                    stat_entry_name = slugify(stat_entry_name[:120])

            stat_entry_type = stat_entry.type

            if stat_entry_type is None:
                logger.warning(f"Stat {stat_entry.name} has no type, skipping...")
                continue

            if stat_entry_type == "0" or stat_entry_type == 0:
                stat_entry_type = "int"

            stat_entry_default = stat_entry.default

            if isinstance(stat_entry_default, float) or isinstance(stat_entry_default, int):
                stat_entry_default = str(stat_entry_default)

            game_stat_entry = GameStat(name=stat_entry_name,
                                       type=stat_entry_type,
                                       default_val=stat_entry_default)
            game_stats.add(game_stat_entry)
        except ValidationError as err:
            logger.critical(f"Error validating stats information:\n{process_errors(error_details=err.errors())}")
            logger.opt(exception=True).debug("Traceback:")
            sys.exit(6)

    return game_stats


def update_gh_stats_package(tools_path: str) -> bool:
    current_version = read_file_content(os.path.join(tools_path, "stats_last_version"))
    latest_check = read_file_content(os.path.join(tools_path, "stats_last_check"))

    lock_file_package_path: str = os.path.join(tools_path, "stats_package.lock")

    if os.path.exists(lock_file_package_path):
        logger.info("Lock file found, waiting for the stats package to be available...")

        while os.path.exists(lock_file_package_path):
            time.sleep(LOCKFILE_WAIT_TIME)

        return True

    if current_version is None:
        logger.debug("File \"stats_last_version\" not found.")
    if latest_check is None:
        logger.debug("File \"stats_last_check\" not found.")

    if current_version is None:
        return download_gh_stats_package(tools_path=tools_path)
    else:
        if latest_check is not None:
            if abs(time.time() - float(latest_check)) < abs(24 * 60 * 60):
                logger.info("Latest check was less than 24 hours ago, skipping...")
                return True

        latest_version = get_latest_gh_stats_pkg_version()

        if current_version != latest_version:
            logger.info("Updating GitHub stats package...")
            return download_gh_stats_package(tools_path=tools_path, latest_push=latest_version)
        else:
            logger.info("No update found for GitHub stats package.")
            with open(os.path.join(tools_path, "stats_last_check"), "w", encoding="utf-8") as stream:
                stream.write(str(time.time()))
            return True


def download_gh_stats_package(tools_path: str,
                              latest_push: str | None = None) -> bool:
    logger.info("Downloading GitHub stats package...")

    old_stats_package_path: str = os.path.join(tools_path, "stats_package")
    lock_file_package_path: str = os.path.join(tools_path, "stats_package.lock")

    if os.path.exists(lock_file_package_path):
        logger.info("Lock file found, waiting for the stats package to be available...")

        while os.path.exists(lock_file_package_path):
            time.sleep(LOCKFILE_WAIT_TIME)

        return True

    try:
        open(lock_file_package_path, "x").close()

        if latest_push is None:
            latest_push = get_latest_gh_stats_pkg_version()

        if latest_push is None:
            return False

        git_path = get_git_path(tools_path=tools_path)

        if git_path is None:
            logger.critical("Couldn't get git, aborting...")
            sys.exit(4)

        stats_repo_path = os.path.join(tools_path, "games-infos-datas")

        repo = GitRepo(git_path=git_path, repo_path=stats_repo_path, repo_url=GH_STATS_PACKAGE_REPO_URL)

        if os.path.isdir(os.path.join(stats_repo_path, ".git")):
            result = repo.pull()
        else:
            result = repo.clone()

        if result.process.returncode != 0:
            logger.critical(f"Couldn't retrieve the GitHub stats package, aborting...\n{result.read_stderr()}")
            sys.exit(3)

        logger.info("Writing reference files... (stats_last_version & stats_last_check)")

        with open(os.path.join(tools_path, "stats_last_version"), "w", encoding="utf-8") as stream:
            stream.write(latest_push)

        with open(os.path.join(tools_path, "stats_last_check"), "w", encoding="utf-8") as stream:
            stream.write(str(time.time()))

        if os.path.isdir(old_stats_package_path):
            logger.info("Removing old stats package directory.")
            shutil.rmtree(old_stats_package_path)

            stats_package_zip = os.path.join(tools_path, "stats_package.zip")
            if os.path.isfile(stats_package_zip):
                os.remove(stats_package_zip)

        logger.info("Finished setting up GH stats package.")

        return True
    finally:
        if os.path.exists(lock_file_package_path):
            os.remove(lock_file_package_path)


def get_latest_gh_stats_pkg_version() -> str | None:
    try:
        api_response = get_with_retry(url=GH_STATS_PACKAGE_URL, allow_redirects=True)

        api_info = api_response.json()

        return api_info["pushed_at"]
    except HTTPError:
        return None


def write_steam_appid(output_dir_relations: OutputDirRelations,
                      appid: str) -> None:
    logger.info(f"Writing {STEAM_APPID_FILENAME} file...")

    output_directories: list[str] = list(output_dir_relations.keys())
    main_output_path: str = os.path.join(output_directories[0], STEAM_APPID_FILENAME)

    try:
        with open(main_output_path, "w", encoding="utf-8", newline=NEW_LINE) as stream:
            stream.write(appid)
    except OSError:
        logger.info(f"There was an error writing the {STEAM_APPID_FILENAME} file.")
        logger.opt(exception=True).debug("Traceback:")
        return

    logger.info(f"Finished writing {STEAM_APPID_FILENAME} file.")

    if len(output_directories) > 1:
        logger.info(f"Copying {STEAM_APPID_FILENAME} file to the additional directories...")

        for output_directory in output_directories[1:]:
            custom_copy(main_output_path, output_directory)

        logger.info(f"Finished copying {STEAM_APPID_FILENAME} file.")


def get_emu_config_app(game_info: SteamGameInfo | GHGameInfo,
                       tools_path: str,
                       appid: str,
                       fallback_to_steam: bool,
                       cache_opts: CacheOptions,
                       lang_opts: LanguageOptions,
                       ec_app: ParsedUserProvidedEmuConfigApp | None) -> EmuConfigApp:
    if ec_app is not None and ec_app.app__general is not None:
        emu_config_app_general = EmuConfigAppGeneral.model_validate(ec_app.app__general.model_dump())
    else:
        emu_config_app_general = EmuConfigAppGeneral()

    if ec_app is not None and ec_app.app__dlcs is not None:
        dlc_unlock_all_user_provided = ec_app.app__dlcs.unlock_all
    else:
        dlc_unlock_all_user_provided = None

    emu_config_app_dlc: EmuConfigAppDLC = get_dlc_config_from_gh_pkg(game_info=game_info,
                                                                     tools_path=tools_path,
                                                                     appid=appid,
                                                                     fallback_to_steam=fallback_to_steam,
                                                                     cache_opts=cache_opts,
                                                                     lang_opts=lang_opts,
                                                                     unlock_all=dlc_unlock_all_user_provided)

    if ec_app is not None and ec_app.app__dlcs is not None:
        if ec_app.app__dlcs.model_extra is not None:
            emu_config_app_dlc = emu_config_app_dlc.model_copy(update=ec_app.app__dlcs.model_extra)

    if ec_app is not None and ec_app.app__cloud_save__general is not None:
        emu_config_app_cloud_saves_general = EmuConfigAppCloudSaveGeneral.model_validate(
                ec_app.app__cloud_save__general.model_dump()
        )
    else:
        emu_config_app_cloud_saves_general = EmuConfigAppCloudSaveGeneral()

    if ec_app is not None and ec_app.app__cloud_save__win is not None:
        emu_config_app_cloud_saves_win = EmuConfigAppCloudSaveWin.model_validate(
                ec_app.app__cloud_save__win.model_dump()
        )
    else:
        emu_config_app_cloud_saves_win = EmuConfigAppCloudSaveWin()

    if ec_app is not None and ec_app.app__cloud_save__linux is not None:
        emu_config_app_cloud_saves_linux = EmuConfigAppCloudSaveLinux.model_validate(
                ec_app.app__cloud_save__linux.model_dump()
        )
    else:
        emu_config_app_cloud_saves_linux = EmuConfigAppCloudSaveLinux()

    if ec_app is not None and ec_app.app__controller is not None:
        emu_config_app_controller = EmuConfigAppController.model_validate(ec_app.app__controller.model_dump())
    else:
        emu_config_app_controller = EmuConfigAppController()

    if ec_app is not None and ec_app.app__paths is not None:
        emu_config_app_paths = EmuConfigAppPaths.model_validate(ec_app.app__paths.model_dump())
    else:
        emu_config_app_paths = EmuConfigAppPaths()

    return EmuConfigApp(app__general=emu_config_app_general,
                        app__dlcs=emu_config_app_dlc,
                        app__controller=emu_config_app_controller,
                        app__paths=emu_config_app_paths,
                        app__cloud_save__general=emu_config_app_cloud_saves_general,
                        app__cloud_save__win=emu_config_app_cloud_saves_win,
                        app__cloud_save__linux=emu_config_app_cloud_saves_linux)


def get_emu_config_main(ec_main: ParsedUserProvidedEmuConfigMain | None) -> EmuConfigMain:
    if ec_main is not None and ec_main.main__general is not None:
        emu_config_main_general = EmuConfigMainGeneral.model_validate(ec_main.main__general.model_dump())
    else:
        emu_config_main_general = EmuConfigMainGeneral(enable_account_avatar=1)

    if ec_main is not None and ec_main.main__stats is not None:
        emu_config_main_stats = EmuConfigMainStats.model_validate(ec_main.main__stats.model_dump())
    else:
        emu_config_main_stats = EmuConfigMainStats()

    if ec_main is not None and ec_main.main__connectivity is not None:
        emu_config_main_connectivity = EmuConfigMainConnectivity.model_validate(ec_main.main__connectivity.model_dump())
    else:
        emu_config_main_connectivity = EmuConfigMainConnectivity()

    if ec_main is not None and ec_main.main__misc is not None:
        emu_config_main_misc = EmuConfigMainMisc.model_validate(ec_main.main__misc.model_dump())
    else:
        emu_config_main_misc = EmuConfigMainMisc()

    return EmuConfigMain(main__general=emu_config_main_general,
                         main__stats=emu_config_main_stats,
                         main__connectivity=emu_config_main_connectivity,
                         main__misc=emu_config_main_misc)


def get_emu_config_overlay(ec_overlay: ParsedUserProvidedEmuConfigOverlay | None) -> EmuConfigOverlay:
    if ec_overlay is not None and ec_overlay.overlay__general is not None:
        emu_config_overlay_general = EmuConfigOverlayGeneral.model_validate(ec_overlay.overlay__general.model_dump())
    else:
        emu_config_overlay_general = EmuConfigOverlayGeneral(enable_experimental_overlay=1)

    if ec_overlay is not None and ec_overlay.overlay__hotkeys is not None:
        emu_config_overlay_hotkeys = EmuConfigOverlayHotkeys.model_validate(ec_overlay.overlay__hotkeys.model_dump())
    else:
        emu_config_overlay_hotkeys = EmuConfigOverlayHotkeys()

    if ec_overlay is not None and ec_overlay.overlay__appearance is not None:
        emu_config_overlay_appearance = EmuConfigOverlayAppearance.model_validate(
                ec_overlay.overlay__appearance.model_dump()
        )
    else:
        emu_config_overlay_appearance = EmuConfigOverlayAppearance()

    return EmuConfigOverlay(overlay__general=emu_config_overlay_general,
                            overlay__hotkeys=emu_config_overlay_hotkeys,
                            overlay__appearance=emu_config_overlay_appearance)


def get_emu_config_user(lang_opts: LanguageOptions,
                        add_user_config: bool,
                        ec_user: ParsedUserProvidedEmuConfigUser | None) -> (EmuConfigUserWithOptionals
                                                                             | EmuConfigUserOnlyGeneral
                                                                             | EmuConfigUserOnlySaves
                                                                             | EmuConfigUserOnlyGeneralOnlyLanguage
                                                                             | None):
    if ec_user is not None:
        if ec_user.user__general is not None:
            # The user can override the language, so we have to handle it here. In case the user has not, then we set
            # it ourselves.
            user_general_dump = ec_user.user__general.model_dump(exclude_none=True)
            if ec_user.user__general.language is None and add_user_config:
                user_general_dump["language"] = lang_opts.sanitized_language
            emu_config_user_general = EmuConfigUserGeneralWithOptionals.model_validate(user_general_dump)
        elif add_user_config:
            emu_config_user_general = EmuConfigUserGeneralWithOptionals(language=lang_opts.sanitized_language)
        else:
            emu_config_user_general = None

        if ec_user.user__saves is not None:
            emu_config_user_saves = EmuConfigUserSavesWithOptionals.model_validate(
                    ec_user.user__saves.model_dump(exclude_none=True)
            )
        else:
            emu_config_user_saves = None

        if emu_config_user_general is not None:
            if emu_config_user_saves is not None:
                return EmuConfigUserWithOptionals(user__general=emu_config_user_general,
                                                  user__saves=emu_config_user_saves)
            else:
                return EmuConfigUserOnlyGeneral(user__general=emu_config_user_general)
        elif emu_config_user_saves is not None:
            return EmuConfigUserOnlySaves(user__saves=emu_config_user_saves)
        else:
            raise ValueError("At least one of user--general or user--saves should have been provided.")
    elif add_user_config:
        return EmuConfigUserOnlyGeneralOnlyLanguage(
                user__general=EmuConfigUserGeneralOnlyLanguage(language=lang_opts.sanitized_language)
        )
    else:
        return None


def write_emu_config(game_info: SteamGameInfo | GHGameInfo,
                     tools_path: str,
                     appid: str,
                     add_user_config: bool,
                     output_dir_relations: OutputDirRelations,
                     fallback_to_steam: bool,
                     cache_opts: CacheOptions,
                     lang_opts: LanguageOptions,
                     user_provided_emu_config: ParseEmuConfigArgsResult) -> None:
    logger.info("Writing emulator configuration...")

    ec_app = user_provided_emu_config["ec_app"]
    ec_main = user_provided_emu_config["ec_main"]
    ec_overlay = user_provided_emu_config["ec_overlay"]
    ec_user = user_provided_emu_config["ec_user"]

    emu_config_app: EmuConfigApp = get_emu_config_app(game_info=game_info,
                                                      tools_path=tools_path,
                                                      appid=appid,
                                                      fallback_to_steam=fallback_to_steam,
                                                      cache_opts=cache_opts,
                                                      lang_opts=lang_opts,
                                                      ec_app=ec_app)

    emu_config_main: EmuConfigMain = get_emu_config_main(ec_main=ec_main)

    emu_config_overlay = get_emu_config_overlay(ec_overlay=ec_overlay)

    output_directories: list[str] = list(output_dir_relations.keys())
    emu_config_app_path: str = os.path.join(output_directories[0], CONFIG_APP_FILENAME)
    emu_config_main_path: str = os.path.join(output_directories[0], CONFIG_MAIN_FILENAME)
    emu_config_overlay_path: str = os.path.join(output_directories[0], CONFIG_OVERLAY_FILENAME)
    emu_config_user_path: str = os.path.join(output_directories[0], CONFIG_USER_FILENAME)

    with open(emu_config_app_path, "w", encoding="utf-8", newline=NEW_LINE) as stream:
        config = configparser.ConfigParser(interpolation=None)
        config.read_dict(emu_config_app.model_dump(by_alias=True))
        config.write(stream, space_around_delimiters=False)

    with open(emu_config_main_path, "w", encoding="utf-8", newline=NEW_LINE) as stream:
        config = configparser.ConfigParser(interpolation=None)
        config.read_dict(emu_config_main.model_dump(by_alias=True))
        config.write(stream, space_around_delimiters=False)

    with open(emu_config_overlay_path, "w", encoding="utf-8", newline=NEW_LINE) as stream:
        config = configparser.ConfigParser(interpolation=None)
        config.read_dict(emu_config_overlay.model_dump(by_alias=True))
        config.write(stream, space_around_delimiters=False)

    emu_config_user = get_emu_config_user(lang_opts=lang_opts,
                                          add_user_config=add_user_config,
                                          ec_user=ec_user)

    if emu_config_user is not None:
        with open(emu_config_user_path, "w", encoding="utf-8", newline=NEW_LINE) as stream:
            config = configparser.ConfigParser(interpolation=None)
            config.read_dict(emu_config_user.model_dump(by_alias=True, exclude_none=True))
            config.write(stream, space_around_delimiters=False)

    logger.info("Finished writing emulator configuration.")

    if len(output_directories) > 1:
        logger.info("Copying emulator configuration files to the additional directories...")

        for output_directory in output_directories[1:]:
            custom_copy(emu_config_app_path, output_directory)
            custom_copy(emu_config_main_path, output_directory)
            custom_copy(emu_config_overlay_path, output_directory)

            if emu_config_user is not None:
                custom_copy(emu_config_user_path, output_directory)

        logger.info("Finished copying emulator configuration files.")


def get_dlc_config_from_gh_pkg(game_info: SteamGameInfo | GHGameInfo,
                               tools_path: str,
                               appid: str,
                               fallback_to_steam: bool,
                               cache_opts: CacheOptions,
                               lang_opts: LanguageOptions,
                               unlock_all: Literal[0, 1] | None) -> EmuConfigAppDLC:
    logger.info("Getting DLC configuration from GH stats package...")

    if not update_gh_stats_package(tools_path=tools_path):
        logger.critical("Aborting...")
        sys.exit(9)

    if isinstance(game_info, SteamGameInfo):
        gh_game_info = get_gh_game_info(tools_path=tools_path, appid=appid)

        if gh_game_info is None or not isinstance(gh_game_info.Dlcs, dict) or len(gh_game_info.Dlcs) == 0:
            if fallback_to_steam:
                return get_dlc_config_from_steam(game_info=game_info,
                                                 appid=appid,
                                                 cache_opts=cache_opts,
                                                 lang_opts=lang_opts)
            else:
                return EmuConfigAppDLC()
    else:
        gh_game_info = game_info

    dlc_list: dict[str, str] = {}
    for dlc in gh_game_info.Dlcs:
        dlc_list[str(gh_game_info.Dlcs[dlc].AppId)] = gh_game_info.Dlcs[dlc].Name

    if unlock_all is not None:
        return EmuConfigAppDLC(unlock_all=unlock_all, **dlc_list)
    else:

        return EmuConfigAppDLC(unlock_all=0, **dlc_list)


def get_dlc_config_from_steam(game_info: SteamGameInfo,
                              appid: str,
                              cache_opts: CacheOptions,
                              lang_opts: LanguageOptions) -> EmuConfigAppDLC:
    logger.info("Building DLC configuration...")

    dlc_list: dict[str, str] = {}

    dlc_data = game_info.game_info[appid].data.dlc

    if dlc_data is None:
        logger.warning("No DLC found.")
    else:
        dlc_info = get_dlc_info_from_steam(appid=appid,
                                           cache_opts=cache_opts,
                                           lang_opts=lang_opts)
        logger.debug(f"DLC info:\n{dlc_info}")

        for dlc in dlc_data:
            dlc_name = "0"
            if dlc_info is not None:
                for dlc_entry in dlc_info.dlc:
                    if dlc_entry.id == dlc:
                        if dlc_entry.name is not None:
                            dlc_name = dlc_entry.name
                        break
            dlc_list[str(dlc)] = dlc_name

    if len(dlc_list) == 0:
        emu_config_app_dlc: EmuConfigAppDLC = EmuConfigAppDLC()
    else:
        emu_config_app_dlc: EmuConfigAppDLC = EmuConfigAppDLC(unlock_all=0, **dlc_list)

    return emu_config_app_dlc


def get_dlc_info_from_steam(appid: str,
                            cache_opts: CacheOptions,
                            lang_opts: LanguageOptions) -> SteamDLCInfo | None:
    logger.info("Retrieving DLC information...")

    if lang_opts.sanitized_language is None:
        sanitized_language, _ = get_sanitized_preferred_language(supported_languages=lang_opts.supported_languages,
                                                                 preferred_language=lang_opts.preferred_language)

    dlc_info_file_cache_path = os.path.join(cache_opts.cache_location,
                                            appid,
                                            f"dlc_info_{lang_opts.sanitized_language}.json")
    dlc_info_last_retrieval_flag_path = os.path.join(cache_opts.cache_location,
                                                     appid,
                                                     f"dlc_info_{lang_opts.sanitized_language}_last_retrieval")

    if cache_opts.cache_game_info and os.path.isfile(dlc_info_last_retrieval_flag_path):
        with open(dlc_info_last_retrieval_flag_path, "r", encoding="utf-8") as flag_stream:
            last_retrieval = flag_stream.read()

        if not should_refresh_cache(date=last_retrieval):
            logger.info(f"Using cached DLC info: {dlc_info_file_cache_path}")

            with open(dlc_info_file_cache_path, "r", encoding="utf-8") as file_stream:
                return SteamDLCInfo.model_validate(file_stream.read())

    try:
        response = get_with_retry(url=DLC_INFO_URL_TEMPLATE.substitute(appid=appid,
                                                                       language=lang_opts.sanitized_language))
    except HTTPError as err:
        if err.response.status_code == 404:
            logger.error("DLC information not found.")
        else:
            logger.error("An error occurred retrieving the DLC information.")
        return None
    except RemoteDisconnected:
        logger.error("An error occurred retrieving the DLC information.")
        return None

    response_json = response.json()

    try:
        dlc_info = SteamDLCInfo.model_validate(response_json)
    except ValidationError as err:
        logger.critical(f"Failed to validate DLC information:\n{process_errors(error_details=err.errors())}")
        logger.opt(exception=True).debug("Traceback:")
        # Don't return None here, validation errors are errors in code, most likely the game does have DLC
        # information available
        sys.exit(6)

    if cache_opts.cache_game_info:
        os.makedirs(os.path.dirname(dlc_info_file_cache_path), exist_ok=True)

        with open(dlc_info_file_cache_path, "wb") as file_stream:
            file_stream.write(response.content)

        write_last_retrieval_flag(dlc_info_last_retrieval_flag_path)

    return dlc_info


def add_emulator(tools_path: str,
                 output_dir_relations: OutputDirRelations,
                 lib_locations: list[str] | None,
                 output_dir: str | None,
                 game_dir: str | None,
                 extracted_files_path: str | None,
                 is_linux: bool,
                 include_dll: list[str]) -> None:
    logger.info("Adding emulator...")

    if is_linux:
        emu_files_path: str = os.path.join(tools_path, "linux", "gbe_fork_experimental")
    else:
        emu_files_path: str = os.path.join(tools_path, "windows", "gbe_fork_experimental")

    if lib_locations is None:
        logger.info("Copying sound files...")
        custom_copy(os.path.join(emu_files_path, "sounds"),
                    os.path.join(list(output_dir_relations.keys())[0], "sounds"))
        logger.error("No DLL/SO location found, can't add emulator, bitness is unknown.")
        return

    if not update_emulator(tools_path=tools_path):
        logger.error("Failed to get the emulator, aborting...")
        sys.exit(2)

    max_items: int = len(output_dir_relations)
    cur_item: int = 0

    for lib_output_dir, full_lib_locations in output_dir_relations.items():
        cur_item += 1

        if full_lib_locations is None:
            # this should never be reached since the value of lib_locations already guards against this
            logger.error("No lib locations available...")
            continue

        if output_dir != lib_output_dir:
            rel_processing_dir = os.path.relpath(lib_output_dir, output_dir)
        else:
            rel_processing_dir = lib_output_dir

        logger.info(f"({cur_item}/{max_items}) Adding emulator to: {os.path.dirname(rel_processing_dir)}...")

        x64: bool = False
        x86: bool = False

        for lib_location in full_lib_locations:
            if is_linux:
                bitness = get_elf_lib_bitness(path=lib_location)

                if bitness == 64:
                    x64 = True
                else:
                    x86 = True

                break
            else:
                if lib_location.lower().endswith("64.dll"):
                    x64 = True
                else:
                    x86 = True

        if x64:
            if not x86:
                logger.info("Game is 64-bit.")
            else:
                # this is only possible on Windows since linux lib names are the same
                logger.info("Game includes 64 and 32 bit DLL files.")
        else:
            logger.info("Game is 32-bit.")

        if STEAM_SETTINGS_FOLDER_NAME_PATTERN.match(os.path.basename(lib_output_dir)) is not None:
            orig_output_dir = lib_output_dir
            lib_output_dir = os.path.dirname(lib_output_dir)
        else:
            orig_output_dir = os.path.join(lib_output_dir, "steam_settings")

        if output_dir is not None:
            logger.info(f"Emulator directory: {os.path.relpath(lib_output_dir, output_dir)}")
        else:
            logger.info(f"Emulator directory: {lib_output_dir}")

        libs_to_add: list[tuple[str, str, str, str, str]] = []

        if is_linux:
            STEAMAPI64_LIB_NAME = STEAMAPI_SO_NAME
            STEAMCLIENT64_LIB_NAME = STEAMCLIENT_SO_NAME
            STEAMAPI_LIB_NAME = STEAMAPI_SO_NAME
            STEAMCLIENT_LIB_NAME = STEAMCLIENT_SO_NAME
        else:
            STEAMAPI64_LIB_NAME = STEAMAPI64_DLL_NAME
            STEAMCLIENT64_LIB_NAME = STEAMCLIENT64_DLL_NAME
            STEAMAPI_LIB_NAME = STEAMAPI_DLL_NAME
            STEAMCLIENT_LIB_NAME = STEAMCLIENT_DLL_NAME

        if x64:
            api_lib_path_x64: str = os.path.join(lib_output_dir, STEAMAPI64_LIB_NAME)
            client_lib_path_x64: str = os.path.join(lib_output_dir, STEAMCLIENT64_LIB_NAME)
            sub_dir_name_x64: str = "x64"

            libs_to_add.append((api_lib_path_x64, client_lib_path_x64, STEAMAPI64_LIB_NAME, STEAMCLIENT64_LIB_NAME,
                                sub_dir_name_x64))

        if x86:
            api_lib_path_x86: str = os.path.join(lib_output_dir, STEAMAPI_LIB_NAME)
            client_lib_path_x86: str = os.path.join(lib_output_dir, STEAMCLIENT_LIB_NAME)
            sub_dir_name_x86: str = "x86"

            libs_to_add.append((api_lib_path_x86, client_lib_path_x86, STEAMAPI_LIB_NAME, STEAMCLIENT_LIB_NAME,
                                sub_dir_name_x86))

        for api_lib_path, client_lib_path, api_lib_name, client_lib_name, sub_dir_name in libs_to_add:
            logger.debug(f"Info:\nAPI DLL/SO path: {api_lib_path}\nClient DLL/SO path: {client_lib_path}\nAPI DLL/SO "
                         f"name: {api_lib_name}\nClient DLL/SO name: {client_lib_name}\nSub dir name: {sub_dir_name}")

            for lib_path, lib_name in ((api_lib_path, api_lib_name), (client_lib_path, client_lib_name)):
                if game_dir is not None and (output_dir is None or output_dir == game_dir):
                    if os.path.exists(lib_path):
                        logger.info(f"Original DLL/SO found ({lib_name}), renaming it with \".orig\" extension...")

                        backup_filename = lib_path + ".orig"

                        if os.path.exists(backup_filename):
                            os.remove(remove_readonly_flag(backup_filename))

                        os.rename(lib_path, backup_filename)
                else:
                    for lib_location in full_lib_locations:
                        if os.path.basename(lib_location).lower() == lib_name:
                            if os.path.exists(lib_location):
                                if extracted_files_path is not None:
                                    rel_location: str = os.path.relpath(lib_location, extracted_files_path)
                                elif game_dir is not None:
                                    rel_location: str = os.path.relpath(lib_location, game_dir)
                                else:
                                    rel_location: str = lib_location

                                logger.info(f"Original DLL/SO found ({rel_location}), copying it with \".orig\" "
                                            f"extension...")
                                custom_copy(lib_location, lib_path + ".orig")

                            break

            emu_api_lib_path: str = os.path.join(emu_files_path, sub_dir_name, api_lib_name)
            logger.info("Copying emulator api DLL/SO files...")
            custom_copy(emu_api_lib_path, api_lib_path)

            emu_client_lib_path = os.path.join(emu_files_path, sub_dir_name, client_lib_name)
            logger.info("Copying emulator client DLL/SO files...")
            custom_copy(emu_client_lib_path, client_lib_path)

            if len(include_dll) != 0:
                logger.info("Copying additional DLL/SO files...")

                for additional_lib in include_dll:
                    custom_copy(additional_lib,
                                os.path.join(orig_output_dir, "load_dlls", os.path.basename(additional_lib)))

            logger.info("Copying sound files...")
            custom_copy(os.path.join(emu_files_path, "sounds"),
                        os.path.join(orig_output_dir, "sounds"))

    logger.info("Finished adding emulator.")


def rename_package_dir(game_info: SteamGameInfo | GHGameInfo,
                       do_rename_package_dir: bool,
                       package_dir: str | None,
                       appid: str,
                       only_rename: bool,
                       add_language_flag_on_rename: bool,
                       add_early_access_label: bool,
                       custom_early_access_label: str | None,
                       lang_opts: LanguageOptions) -> None:
    if not do_rename_package_dir or package_dir is None:
        return

    if isinstance(game_info, GHGameInfo):
        logger.warning("Can't rename package directory for games that do not have their info available in Steam.")
        return

    logger.info("Starting renaming the package directory...")

    title: str = game_info.game_info[appid].data.name
    release_date_data: SteamGameReleaseDate | None = game_info.game_info[appid].data.release_date

    if release_date_data is None or release_date_data.date is None:
        logger.error("Release date not found for the game.")
        return
    else:
        release_date = release_date_data.date

    release_datetime: datetime | None = dateparser.parse(release_date)
    if release_datetime is None:
        logger.error("Couldn't parse the release date to extract the year.")
        return

    logger.debug(f"Title: {title}\nRelease date: {release_date}")

    if add_language_flag_on_rename:
        extra_name_info: str = get_extra_name_info(supported_languages=lang_opts.supported_languages,
                                                   preferred_language=lang_opts.preferred_language)
    else:
        extra_name_info = ""

    sanitized_title: str = sanitize_name(name=title, do_not_use_unicode=True)

    if add_early_access_label:
        genres = game_info.game_info[appid].data.genres
        if genres is not None:
            for genre in genres:
                if genre.id == 70:
                    if custom_early_access_label is not None:
                        extra_name_info += " " + sanitize_name(name=custom_early_access_label, do_not_use_unicode=True)
                    else:
                        extra_name_info += " " + DEFAULT_EARLY_ACCESS_LABEL
                    break
        else:
            logger.warning("No genres available. Can't detect if game is early access.")

    new_name: str = os.path.join(os.path.dirname(package_dir),
                                 f"{sanitized_title} ({release_datetime.year}){extra_name_info}")

    if new_name != package_dir:
        if os.path.exists(new_name):
            new_name = pad_directory(dirname=new_name)
    else:
        logger.info("Skipping renaming. Old and new name are the same.")
        return

    logger.debug(f"New name: {new_name}")

    try:
        if os.getcwd() == package_dir:
            os.chdir(os.path.normpath(os.path.join(package_dir, os.pardir)))
        os.rename(package_dir, new_name)
        logger.info("Finished renaming package directory.")
    except OSError as err:
        msg: str = f"Couldn't rename package directory: {err.strerror}\nNew name would have been: {new_name}"

        if only_rename:
            logger.critical(msg)
            logger.opt(exception=True).debug("Couldn't rename package directory:")

            sys.exit(3)
        else:
            logger.error(msg)
            logger.opt(exception=True).debug("Couldn't rename package directory:")


def get_extra_name_info(supported_languages: set[str] | None,
                        preferred_language: str) -> str:
    logger.info("Getting extra information to append to name...")

    if supported_languages is not None:
        if preferred_language not in supported_languages:
            match preferred_language:
                case "latam":
                    if "spanish" in supported_languages:
                        return ""
                case "spanish":
                    if "latam" in supported_languages:
                        return ""
                case "brazilian":
                    if "portuguese" in supported_languages:
                        return ""
                case "portuguese":
                    if "brazilian" in supported_languages:
                        return ""
                case "schinese":
                    if "tchinese" in supported_languages:
                        return ""
                case "tchinese":
                    if "schinese" in supported_languages:
                        return ""
                case _:
                    pass

            if "english" in supported_languages:
                return " [eng]"
            else:
                return " [unknown]"

    return ""


def compress_config(directory_to_compress: str,
                    game_dir: str | None,
                    tools_path: str,
                    compressed_filename: str) -> None:
    if directory_to_compress is None:
        if game_dir is not None:
            logger.warning("Can only compress configuration if --package-dir has been used or if --game-dir is used "
                           "with --output-dir. Not compressing.")
            return
        else:
            logger.error("Not compressing.")
            return

    logger.info("Compressing configuration...")

    sevenzip_path: str | None = ensure_sevenzip(tools_path=tools_path)

    if sevenzip_path is None:
        logger.error("Couldn't get 7-zip.")
        return

    compressed_filepath: str = os.path.join(directory_to_compress, compressed_filename)

    if not compress_directory_content(sevenzip_path=sevenzip_path,
                                      output_path=compressed_filepath,
                                      directory_to_compress=directory_to_compress):
        return

    logger.info("Finished compressing configuration.")


def find_acf_files(root_dir: str) -> set[str]:
    """
    Find all the available ACF files in the provided directory, skipping all the known non-game app IDs.
    """
    logger.info("Trying to find ACF files...")
    logger.info(f"Root directory used as base for ACF file search is: {root_dir}")

    found_acf_files = glob.glob(f"**{os.path.sep}*.acf",
                                recursive=True,
                                root_dir=root_dir)

    if len(found_acf_files) == 0:
        logger.info("No ACF files found.")
        return set()

    logger.debug(f"Found ACF files (unfiltered):\n{found_acf_files}")

    acf_files: set = set()

    for acf_file in found_acf_files:
        orig_acf_file = acf_file
        acf_file = os.path.basename(acf_file).lower()

        logger.debug(f"Filtering file: {acf_file}")

        if not os.path.isfile(os.path.join(root_dir, orig_acf_file)):
            continue
        elif not acf_file.startswith("appmanifest_"):
            continue

        skip_appid = False
        for appid_to_skip in NON_GAME_APPIDS:
            if acf_file == f"appmanifest_{appid_to_skip}.acf":
                skip_appid = True
                break

        if skip_appid:
            continue

        acf_files.add(os.path.join(root_dir, orig_acf_file))

    logger.debug(f"Found ACF files (filtered):\n{acf_files}")

    return acf_files


def retrieve_acf_files(package_dir: str,
                       tools_path: str,
                       archive_password: str | None) -> tuple[set[str], str | None]:
    """
    Retrieve the ACF files, and optionally the temp extraction path, from the provided package directory.
    Processes loose and compressed package files.

    This doesn't search for any ID at all.

    Returns:
        Tuple containing the found ACF files and the temp extraction path, if any.
    """
    logger.info("Searching for ACF files...")

    acf_files = find_acf_files(root_dir=package_dir)
    tmp_dir = None

    if len(acf_files) == 0:
        tmp_dir = extract_from_package_files(directory=package_dir,
                                             tools_path=tools_path,
                                             archive_password=archive_password)

        if tmp_dir is not None:
            acf_files = find_acf_files(root_dir=tmp_dir)

    logger.info("Finished searching for ACF files.")

    return acf_files, tmp_dir


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.warning("Interrupted by user.")
        sys.exit(1)
    except Exception:
        logger.opt(exception=True).critical("An unexpected error occurred:")
        sys.exit(2)
    finally:
        cleanup()
