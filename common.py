import os
import platform
import re
import sys
from argparse import Action, ArgumentParser, _ArgumentGroup, _StoreConstAction
from datetime import datetime
from string import Template
from typing import Any

import requests
from loguru import logger
from requests import Session

from models.app import DataFile


def get_program_dir() -> str:
    try:
        # noinspection PyUnresolvedReferences
        # pyrefly: ignore [unknown-name]
        return os.path.abspath(__compiled__.containing_dir)
    except NameError:
        return os.path.abspath(os.path.dirname(sys.argv[0]))


CURRENT_DATE = datetime.today().strftime("%Y%m")

CONFIG_MAIN_FILENAME = "configs.main.ini"
CONFIG_APP_FILENAME = "configs.app.ini"
CONFIG_OVERLAY_FILENAME = "configs.overlay.ini"
CONFIG_USER_FILENAME = "configs.user.ini"
SUPPORTED_LANGUAGES_FILENAME = "supported_languages.txt"
ACHIEVEMENTS_FILENAME = "achievements.json"
STATS_FILENAME = "stats.json"
INTERFACES_FILENAME = "steam_interfaces.txt"
STEAM_APPID_FILENAME = "steam_appid.txt"

ACHIEVEMENTS_DIRNAME = "achievement_images"

STEAMAPI_DLL_NAME = "steam_api.dll"
STEAMAPI64_DLL_NAME = "steam_api64.dll"
STEAMCLIENT_DLL_NAME = "steamclient.dll"
STEAMCLIENT64_DLL_NAME = "steamclient64.dll"

STEAMAPI_SO_NAME = "libsteam_api.so"
STEAMCLIENT_SO_NAME = "steamclient.so"

LOCKFILE_WAIT_TIME: float = 5.0

ACF_APPID_PATTERN: re.Pattern[str] = re.compile(r"^\s+\"appid\"\s+\"(\d{2,})\"", flags=re.IGNORECASE)
ACF_BUILDID_PATTERN: re.Pattern[str] = re.compile(r"^\s+\"buildid\"\s+\"(\d+)\"", flags=re.IGNORECASE)

INTERFACE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"STEAMAPPS_INTERFACE_VERSION\d+"),
    re.compile(r"STEAMAPPLIST_INTERFACE_VERSION\d+"),
    re.compile(r"STEAMAPPTICKET_INTERFACE_VERSION\d+"),
    re.compile(r"SteamClient\d+"),
    re.compile(r"STEAMCONTROLLER_INTERFACE_VERSION"),
    re.compile(r"SteamController\d+"),
    re.compile(r"SteamFriends\d+"),
    re.compile(r"SteamGameServerStats\d+"),
    re.compile(r"SteamGameCoordinator\d+"),
    re.compile(r"SteamGameServer\d+"),
    re.compile(r"STEAMHTMLSURFACE_INTERFACE_VERSION_\d+"),
    re.compile(r"STEAMHTTP_INTERFACE_VERSION\d+"),
    re.compile(r"SteamInput\d+"),
    re.compile(r"STEAMINVENTORY_INTERFACE_V\d+"),
    re.compile(r"SteamMatchMakingServers\d+"),
    re.compile(r"SteamMatchMaking\d+"),
    re.compile(r"SteamMatchGameSearch\d+"),
    re.compile(r"SteamParties\d+"),
    re.compile(r"STEAMMUSIC_INTERFACE_VERSION\d+"),
    re.compile(r"STEAMMUSICREMOTE_INTERFACE_VERSION\d+"),
    re.compile(r"SteamNetworkingMessages\d+"),
    re.compile(r"SteamNetworkingSockets\d+"),
    re.compile(r"SteamNetworkingUtils\d+"),
    re.compile(r"SteamNetworking\d+"),
    re.compile(r"STEAMPARENTALSETTINGS_INTERFACE_VERSION\d+"),
    re.compile(r"STEAMREMOTEPLAY_INTERFACE_VERSION\d+"),
    re.compile(r"STEAMREMOTESTORAGE_INTERFACE_VERSION\d+"),
    re.compile(r"STEAMSCREENSHOTS_INTERFACE_VERSION\d+"),
    re.compile(r"STEAMTIMELINE_INTERFACE_V\d+"),
    re.compile(r"STEAMUGC_INTERFACE_VERSION\d+"),
    re.compile(r"SteamUser\d+"),
    re.compile(r"STEAMUSERSTATS_INTERFACE_VERSION\d+"),
    re.compile(r"SteamUtils\d+"),
    re.compile(r"STEAMVIDEO_INTERFACE_V\d+"),
    re.compile(r"STEAMUNIFIEDMESSAGES_INTERFACE_VERSION\d+"),
    re.compile(r"SteamMasterServerUpdater\d+"),
)

# Taken from https://partner.steamgames.com/doc/store/localization/languages
SUPPORTED_LANGUAGES_MAPPING: dict[str, str] = {
    "Arabic": "arabic",
    "Bulgarian": "bulgarian",
    "Chinese (Simplified)": "schinese",
    "Chinese (Traditional)": "tchinese",
    "Czech": "czech",
    "Danish": "danish",
    "Dutch": "dutch",
    "English": "english",
    "Finnish": "finnish",
    "French": "french",
    "German": "german",
    "Greek": "greek",
    "Hungarian": "hungarian",
    "Indonesian": "indonesian",
    "Italian": "italian",
    "Japanese": "japanese",
    "Korean": "koreana",
    "Norwegian": "norwegian",
    "Polish": "polish",
    "Portuguese": "portuguese",
    "Portuguese-Brazil": "brazilian",
    "Romanian": "romanian",
    "Russian": "russian",
    "Spanish-Spain": "spanish",
    "Spanish-Latin America": "latam",
    "Swedish": "swedish",
    "Thai": "thai",
    "Turkish": "turkish",
    "Ukrainian": "ukrainian",
    "Vietnamese": "vietnamese"
}

LANGUAGES_ONLY_IN_GAMES: list[str] = [
    "Afrikaans",
    "Albanian",
    "Amharic",
    "Armenian",
    "Assamese",
    "Azerbaijani",
    "Bangla",
    "Basque",
    "Belarusian",
    "Bosnian",
    "Catalan",
    "Cherokee",
    "Croatian",
    "Dari",
    "Estonian",
    "Filipino",
    "Galician",
    "Georgian",
    "Gujarati",
    "Punjabi (Gurmukhi)",
    "Hausa",
    "Hebrew",
    "Hindi",
    "Icelandic",
    "Igbo",
    "Irish",
    "Kannada",
    "Kazakh",
    "Khmer",
    "K'iche'",
    "Kinyarwanda",
    "Konkani",
    "Kyrgyz",
    "Latvian",
    "Lithuanian",
    "Luxembourgish",
    "Macedonian",
    "Malay",
    "Malayalam",
    "Maltese",
    "Maori",
    "Marathi",
    "Mongolian",
    "Nepali",
    "Odia",
    "Persian",
    "Quechua",
    "Scots",
    "Serbian",
    "Punjabi (Shahmukhi)",
    "Sindhi",
    "Sinhala",
    "Slovak",
    "Slovenian",
    "Sorani",
    "Sotho",
    "Swahili",
    "Tajik",
    "Tamil",
    "Tatar",
    "Telugu",
    "Tigrinya",
    "Tswana",
    "Turkmen",
    "Urdu",
    "Uyghur",
    "Uzbek",
    "Valencian",
    "Welsh",
    "Wolof",
    "Xhosa",
    "Yoruba",
    "Zulu",
]

LANGUAGE_CHOICES_MAPPING: dict[str, str] = {
    # This is used to retrieve information from the API, Arabic is not here because Steam only supports it in-game
    "bg": "bulgarian",
    "zh-CN": "schinese",
    "zh-TW": "tchinese",
    "cs": "czech",
    "da": "danish",
    "nl": "dutch",
    "en": "english",
    "fi": "finnish",
    "fr": "french",
    "de": "german",
    "el": "greek",
    "hu": "hungarian",
    "id": "indonesian",
    "it": "italian",
    "ja": "japanese",
    "ko": "koreana",
    "no": "norwegian",
    "pl": "polish",
    "pt": "portuguese",
    "pt-BR": "brazilian",
    "br": "brazilian",
    "ro": "romanian",
    "ru": "russian",
    "es": "spanish",
    "es-419": "latam",
    "sv": "swedish",
    "th": "thai",
    "tr": "turkish",
    "uk": "ukrainian",
    "vi": "vietnamese"
}

SHORT_LANGUAGE_CHOICES: tuple[str, ...] = tuple(LANGUAGE_CHOICES_MAPPING.keys())
LONG_LANGUAGE_CHOICES: tuple[str, ...] = tuple(LANGUAGE_CHOICES_MAPPING.values())

PACKAGE_FILES_VALID_EXTENSIONS: tuple[str, ...] = ("001", "01", "7z", "rar", "zip", "tar", "xz", "gz",)

EXTRACT_FROM_PACKAGE_NAME_PATTERN: re.Pattern[str] = re.compile(
        r"^.+\((\d{2,})\)(?:\s\[Build\s(\d+)\])?\.(?:(?:part0*1\.)?rar|7z(?:\.\0{1,4}1)?|zip|tar|xz|gz)$",
        flags=re.IGNORECASE
)

STEAM_API_DLL_PATTERN: re.Pattern[str] = re.compile(r"^steam_api(64)?\.dll$", flags=re.IGNORECASE)
STEAMCLIENT_DLL_PATTERN: re.Pattern[str] = re.compile(r"^steamclient(64)?\.dll$", flags=re.IGNORECASE)

STEAM_API_SO_PATTERN: re.Pattern[str] = re.compile(r"^libsteam_api\.so$", flags=re.IGNORECASE)
STEAMCLIENT_SO_PATTERN: re.Pattern[str] = re.compile(r"^steamclient\.so$", flags=re.IGNORECASE)

STEAM_APPID_PATTERN: re.Pattern[str] = re.compile(r"^\d{2,}$")

PACKAGE_LIST_PATH_EXTRACT_PATTERN: re.Pattern[str] = re.compile(r"^Path = (.+)$")

STATS_URL_TEMPLATE: Template = Template(
        "https://api.steampowered.com/ISteamUserStats/GetSchemaForGame/v2/?l=$language&key=$apikey&appid=$appid"
)

APP_DETAILS_URL_TEMPLATE: Template = Template(
        "https://store.steampowered.com/api/appdetails?appids=$appid&l=$language"
)

DLC_INFO_URL_TEMPLATE: Template = Template(
        "https://store.steampowered.com/api/dlcforapp/?appid=$appid&l=$language"
)

SUPPORTED_LANG_EXTRACTION_STEP_1: re.Pattern[str] = re.compile(r"<strong>\*</strong>",
                                                               flags=re.IGNORECASE)
SUPPORTED_LANG_EXTRACTION_STEP_2: re.Pattern[str] = re.compile(r"<br>languages with full audio support(?:.+|$)",
                                                               flags=re.IGNORECASE)

STEAM_SETTINGS_FOLDER_NAME_PATTERN: re.Pattern[str] = re.compile(r"^steam_settings(_\d+)?$", flags=re.IGNORECASE)

EMULATOR_URL = "https://api.github.com/repos/Detanup01/gbe_fork/releases/latest"
SEVENZIP_URL = "https://api.github.com/repos/ip7z/7zip/releases/latest"
GH_STATS_PACKAGE_URL = "https://api.github.com/repos/Nemirtingas/games-infos-datas"
GH_STATS_PACKAGE_REPO_URL = "https://github.com/Nemirtingas/games-infos-datas"

GIT_FOR_WINDOWS_URL = "https://api.github.com/repos/git-for-windows/git/releases/latest"
GIT_FOR_WINDOWS_NAME = r"PortableGit-.+-64-bit\.7z\.exe"

CACHE_DELETING_SIGNAL = "deleting-cache"

SYSTEM_PLATFORM: str = sys.platform
if SYSTEM_PLATFORM.startswith("linux"):
    SYSTEM_PLATFORM = "linux"
elif SYSTEM_PLATFORM in ("win32", "cygwin"):
    SYSTEM_PLATFORM = "windows"

if sys.maxsize > 2 ** 32:
    SYSTEM_BITNESS = 64
else:
    SYSTEM_BITNESS = 32

SYSTEM_ARCH = platform.machine().lower()

match SYSTEM_ARCH:
    case "amd64" | "x86_64":
        SYSTEM_ARCH = "amd64"
    case "i386" | "i686":
        SYSTEM_ARCH = "x86"
    case "arm64" | "aarch64":
        SYSTEM_ARCH = "arm64"
    case _:
        raise RuntimeError(f"Unsupported architecture: {SYSTEM_ARCH}")

if SYSTEM_PLATFORM == "windows":
    SEVENZIP_EXE_NAME = "7z.exe"
    GIT_EXE_NAME = "git.exe"
elif SYSTEM_PLATFORM == "linux":
    SEVENZIP_EXE_NAME = "7zz"
    GIT_EXE_NAME = "git"
else:
    raise RuntimeError(f"Unsupported platform: {SYSTEM_PLATFORM}")

SESSION: Session

SESSION = requests.session()
SESSION.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:137.0) Gecko/20100101 Firefox/137.0"
})

DEFAULT_SEVENZIP_LIST_WILDCARD_PATTERNS: tuple[str, ...] = (
    "appmanifest_*.acf",
    "steam*.dll",
    "steam_appid.txt",
    "libsteam_api.so",
    "steam*.so",
)

SEVENZIP_LIST_WILDCARD_PATTERNS: set[str] = set()

EXECUTABLES_TO_IGNORE_PATTERNS: list[re.Pattern[str]] = []


def load_data_file() -> None:
    data_file_path = os.path.join(get_program_dir(), "steam_emu_configurator.json")

    if os.path.exists(data_file_path):
        with open(data_file_path, "r", encoding="utf-8") as stream:
            app_data = DataFile.model_validate_json(stream.read())

        for pattern in app_data.SEVENZIP_LIST_WILDCARD_PATTERNS:
            SEVENZIP_LIST_WILDCARD_PATTERNS.add(pattern)

        for executable in app_data.EXECUTABLES_TO_IGNORE:
            try:
                EXECUTABLES_TO_IGNORE_PATTERNS.append(re.compile(executable, flags=re.IGNORECASE))
            except re.error:
                logger.warning(f"Invalid regular expression: {executable}")

    # User provided should take priority so we add the defaults last
    for pattern in DEFAULT_SEVENZIP_LIST_WILDCARD_PATTERNS:
        SEVENZIP_LIST_WILDCARD_PATTERNS.add(pattern)


ELF_CLASS = {
    1: 32,
    2: 64,
}

DEFAULT_EARLY_ACCESS_LABEL = "[Early Access]"

STATS_REPO_SUB_PATH = "games-infos-datas"

PATHS_TO_CLEANUP: set[str] = set()

NON_GAME_APPIDS: set[int] = {
    228980,  # Steamworks Common Redistributables
    228500,  # Visual C Redistributables
    2152670,  # runtime-game-server (obsolete)
    1070560,  # Steam Linux Runtime 1.0 (scout)
    1391110,  # Steam Linux Runtime 2.0 (soldier)
    1628350,  # Steam Linux Runtime 3.0 (sniper)
    3810310,  # Steam Linux Runtime 3.0 - Arm64 (sniper)
    4183110,  # Steam Linux Runtime 4.0
    4185400,  # Steam Linux Runtime 4.0 - Arm64
    4690330,  # Legacy Steam Runtime
    1161040,  # Proton BattlEye Runtime
    1826330,  # Proton EasyAntiCheat Runtime
    1493710,  # Proton Experimental
    2348590,  # Proton 8.0
    211,  # Source SDK
    215,  # Source SDK Base 2006
    218,  # Source SDK Base 2007
    243730,  # Source SDK Base 2013 Singleplayer
    243750,  # Source SDK Base 2013 Multiplayer
    956040,  # Source VR SDK
    1007,  # Steamworks SDK Redist
    480,  # Spacewar (maybe the user forgot to remove it?)
}


class StoreTrueIntAction(_StoreConstAction):
    def __init__(self,
                 option_strings,
                 dest,
                 default: Any = None,
                 required: bool = False,
                 help: str | None = None,
                 deprecated: bool = False) -> None:
        super().__init__(
                option_strings=option_strings,
                dest=dest,
                const=1,
                deprecated=deprecated,
                required=required,
                help=help,
                default=default)


class StoreFalseIntAction(_StoreConstAction):
    def __init__(self,
                 option_strings,
                 dest,
                 default: Any = None,
                 required: bool = False,
                 help: str | None = None,
                 deprecated: bool = False) -> None:
        super().__init__(
                option_strings=option_strings,
                dest=dest,
                const=0,
                deprecated=deprecated,
                required=required,
                help=help,
                default=default)


class AdvancedArgumentGroup(_ArgumentGroup):
    def __init__(self,
                 container,
                 title = None,
                 description = None,
                 **kwargs):
        super().__init__(container, title, description, **kwargs)
        self.showing_help = container.showing_help
        self.show_advanced = container.show_advanced

    def add_advanced_argument(self,
                              *args,
                              **kwargs) -> Action | None:
        if not self.show_advanced and self.showing_help:
            return None

        return super().add_argument(*args, **kwargs)


class AdvancedArgumentParser(ArgumentParser):
    def __init__(self,
                 *args,
                 show_advanced: bool = False,
                 showing_help: bool = False,
                 **kwargs) -> None:
        self.show_advanced = show_advanced
        self.showing_help = showing_help
        super().__init__(*args, **kwargs)
        self.register("action", "store_true_int", StoreTrueIntAction)
        self.register("action", "store_false_int", StoreFalseIntAction)

    def add_advanced_argument(self,
                              *args,
                              **kwargs) -> Action | None:
        if not self.show_advanced and self.showing_help:
            return None

        return super().add_argument(*args, **kwargs)

    def add_argument_group(self,
                           *args,
                           advanced: bool = False,
                           **kwargs):
        group = AdvancedArgumentGroup(self, *args, **kwargs)
        if self.showing_help and not self.show_advanced:
            if advanced:
                return group

        self._action_groups.append(group)
        return group
