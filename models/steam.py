from typing import Literal

from pydantic import BaseModel, field_validator

from models.common import AllowExtraBaseModel


class SteamStatEntry(AllowExtraBaseModel, validate_assignment=True):
    """
    Attributes:
        name: The ID of the stat.
        defaultvalue: The default value of the stat.
        displayName: The name of the stat, sometimes localized.
    """
    name: str
    defaultvalue: float | int = 0
    displayName: str | None = None


class SteamAchievementEntry(AllowExtraBaseModel, validate_assignment=True):
    """
    Attributes:
        name: The ID of the achievement.
        defaultvalue: The default value of the achievement.
        displayName: The name of the achievement, sometimes localized.
        hidden: Whether the achievement is hidden (1) or not (0).
        description: The description of the achievement, sometimes localized.
        icon: The achievement's icon URL.
        icongray: The achievement's gray icon URL.
    """
    name: str
    defaultvalue: int
    displayName: str | None = None
    hidden: int
    description: str | None = None
    icon: str
    icongray: str

    def __hash__(self):
        return hash((self.name, self.displayName))

    def __eq__(self,
               other):
        if isinstance(other, SteamAchievementEntry):
            return self.name == other.name and self.displayName == other.displayName

        return False


class SteamAvailableGameStats(AllowExtraBaseModel, validate_assignment=True):
    """
    Attributes:
        stats: List containing the stats.
        achievements: List containing the achievements.
    """
    stats: list[SteamStatEntry] | None = None
    achievements: list[SteamAchievementEntry] | None = None

    @field_validator("stats", "achievements", mode="before")
    @classmethod
    def empty_list_to_none(cls,
                           value) -> list | None:
        if isinstance(value, list):
            if len(value) == 0:
                return None
            else:
                return value
        else:
            return None


class SteamStatGameInfo(AllowExtraBaseModel, validate_assignment=True):
    """
    Attributes:
        gameName: The name of the game.
        gameVersion: The version of the game.
            This is not what you are most likely looking for, this is an internal version number, not always the same
            as the real version.
        availableGameStats: The available stats and achievements for the game.
    """
    gameName: str
    gameVersion: str
    availableGameStats: SteamAvailableGameStats

    @field_validator("availableGameStats", mode="before")
    @classmethod
    def process_none_types(cls,
                           value) -> SteamAvailableGameStats:
        if value is None:
            return SteamAvailableGameStats()
        else:
            return value


class RawSteamStatInfo(AllowExtraBaseModel, validate_assignment=True):
    """
    Attributes:
        game: Game stats and achievement information.
    """
    game: SteamStatGameInfo | None = None

    @field_validator("game", mode="before")
    @classmethod
    def empty_dict_to_none(cls,
                           value) -> dict | None:
        if isinstance(value, dict):
            if len(value) == 0:
                return None
            else:
                return value
        else:
            return value


class SteamStatInfo(RawSteamStatInfo, validate_assignment=True):
    """
    Attributes:
        game: Game stats and achievement information.
    """
    # pyrefly: ignore [bad-override-mutable-attribute]
    game: SteamStatGameInfo


class SteamGameRequirement(AllowExtraBaseModel, validate_assignment=True):
    minimum: str | None = None
    recommended: str | None = None


class SteamPriceOverview(AllowExtraBaseModel, validate_assignment=True):
    currency: str
    initial: int
    final: int
    discount_percent: int
    initial_formatted: str | None = None
    final_formatted: str | None = None


class SteamCategory(AllowExtraBaseModel, validate_assignment=True):
    id: int
    description: str


class SteamGenre(AllowExtraBaseModel, validate_assignment=True):
    id: int
    description: str


class SteamScreenshot(AllowExtraBaseModel, validate_assignment=True):
    id: int
    path_thumbnail: str
    path_full: str


class SteamMovie(AllowExtraBaseModel, validate_assignment=True):
    id: int
    name: str
    thumbnail: str

    # Looks like these are old and no longer used
    webm: dict[str, str] | None = None
    mp4: dict[str, str] | None = None

    # These are the new ones
    dash_av1: str | None = None
    dash_h264: str | None = None
    hls_h264: str | None = None

    highlight: bool


class SteamGameReleaseDate(AllowExtraBaseModel, validate_assignment=True):
    """
    Attributes:
        coming_soon: Whether the game is released or not.
        date: Date string formatted in the locale of the requested language.
    """
    coming_soon: bool
    date: str | None

    @field_validator("date", mode="before")
    @classmethod
    def empty_str_to_none(cls,
                          value) -> str | None:
        if isinstance(value, str) and value == "":
            return None
        return value


class SteamRating(AllowExtraBaseModel, validate_assignment=True):
    rating: str | None = None
    interactive_elements: str | None = None
    display_online_notice: str | None = None
    descriptors: str | None = None
    use_age_gate: bool | None = None

    @field_validator("use_age_gate", mode="before")
    @classmethod
    def string_to_bool(cls,
                       value):
        if isinstance(value, str):
            if value.strip().lower() == "true":
                value = True
            elif value.strip().lower() == "false":
                value = False
        return value


class SteamRatings(AllowExtraBaseModel, validate_assignment=True):
    esrb: SteamRating | None = None
    dejus: SteamRating | None = None
    usk: SteamRating | None = None
    pegi: SteamRating | None = None
    nzoflc: SteamRating | None = None
    cero: SteamRating | None = None


class SteamPlatforms(AllowExtraBaseModel, validate_assignment=True):
    """
    Attributes:
        windows: Whether Windows is supported or not.
        linux: Whether Linux is supported or not.
        mac: Whether Mac is supported or not.
    """
    windows: bool
    linux: bool
    mac: bool


class SteamMetacritic(AllowExtraBaseModel, validate_assignment=True):
    score: int
    url: str


class StoreEntryData(AllowExtraBaseModel, validate_assignment=True):
    """
    Attributes:
        type: Entry type, this will always be "game".
        name: The name of the game.
        steam_appid: The appid of the game.
        required_age: The minimum required age to play this game.
        is_free: Whether the game is free or not.
        dlc: The list of the game's DLC
        supported_languages: Languages supported by the game.
            It's an HTML string containing a list of languages.
        ext_user_account_notice: If the game requires an external account, this string will be set,
            otherwise this is None.
        platforms: The platforms the game supports.
        release_date: Information about the game's release.
    """
    type: str
    name: str
    steam_appid: int
    required_age: int = 0
    is_free: bool | None = None
    controller_support: str | None = None
    dlc: list[int] | None = None
    detailed_description: str | None = None
    about_the_game: str | None = None
    short_description: str | None = None
    supported_languages: str | None = None
    header_image: str | None = None
    capsule_image: str | None = None
    capsule_imagev5: str | None = None
    website: str | None = None
    pc_requirements: SteamGameRequirement | None = None
    mac_requirements: SteamGameRequirement | None = None
    linux_requirements: SteamGameRequirement | None = None
    ext_user_account_notice: str | None = None
    developers: list[str] | None = None
    publishers: list[str] | None = None
    price_overview: SteamPriceOverview | None = None
    packages: list[int] | None = None
    package_groups: list[dict] | None = None  # We don't really care for this
    platforms: SteamPlatforms | None = None
    metacritic: SteamMetacritic | None = None
    categories: list[SteamCategory] | None = None
    genres: list[SteamGenre] | None = None
    screenshots: list[SteamScreenshot] | None = None
    movies: list[SteamMovie] | None = None
    recommendations: dict[str, int] | None = None  # Not important
    achievements: dict | None = None  # We don't care for this, achievements are retrieved elsewhere
    release_date: SteamGameReleaseDate | None = None
    support_info: dict[str, str] | None = None  # Not important
    background: str | None = None
    background_raw: str | None = None
    content_descriptors: dict | None = None  # Not important
    ratings: SteamRatings | None = None

    @field_validator("dlc", "mac_requirements", "linux_requirements", "pc_requirements", mode="before")
    @classmethod
    def empty_list_to_none(cls,
                           value) -> list | None:
        if isinstance(value, list) and len(value) == 0:
            return None
        return value


class RawStoreEntry(BaseModel, validate_assignment=True):
    """
    Attributes:
        success: Whether the request was successful.
        data: Information about the game.
    """
    success: bool
    data: StoreEntryData | None = None


class StoreEntry(BaseModel, validate_assignment=True):
    """
    Attributes:
        success: Whether the request was successful.
        data: Information about the game.
    """
    success: Literal[True]
    data: StoreEntryData


class RawSteamGameInfo(BaseModel, validate_assignment=True):
    """
    Attributes:
        game_info: This contains the game info.
            Access it using *game_info[the_game_appid]*.
    """
    game_info: dict[str, RawStoreEntry]  # This is like this because the key in the dict is the appid


class SteamGameInfo(BaseModel, validate_assignment=True):
    """
    Attributes:
        game_info: This contains the game info.
            Access it using *game_info[the_game_appid]*.
    """
    game_info: dict[str, StoreEntry]  # This is like this because the key in the dict is the appid


class SteamGameReleaseDateIntFloat(AllowExtraBaseModel, validate_assignment=True):
    """
    Attributes:
        steam: DLC release date in epoch format for the platform.
        mac: DLC release date in epoch format for the OS.
        linux: DLC release date in epoch format for the OS.
    """
    steam: int | float | None = None
    mac: int | float | None = None
    linux: int | float | None = None


class SteamDLCEntry(AllowExtraBaseModel, validate_assignment=True):
    id: int
    name: str | None = None
    header_image: str | None = None
    price_overview: SteamPriceOverview | None = None
    platforms: SteamPlatforms | None = None
    release_date: SteamGameReleaseDateIntFloat | None = None
    controller_support: str | None = None


class SteamDLCInfo(AllowExtraBaseModel, validate_assignment=True):
    status: int
    appid: str
    name: str
    dlc: list[SteamDLCEntry]
