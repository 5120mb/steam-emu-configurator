from typing import Literal

from pydantic import Field

from models.common import AllowExtraBaseModel
from models.game import GameStat


class GHGameStat(AllowExtraBaseModel, validate_assignment=True):
    """
    Each of the keys can be missing from the game stat, which is why they are all optional.
    The ones that indeed can be null (None) are specified as such.
    """
    aggregated: bool | None = None
    default: int | str | float | None = None
    defaultvalue: int | None = Field(default=0)
    displayName: str | None = ""  # Might be None
    incrementonly: bool | None = None
    max: float | int | str | None = None
    maxchange: float | int | str | None = None
    min: int | str | float | None = None
    name: str | None = None  # Might be None
    type: Literal[0, "avgrate", "float", "0", "int"] | None = None
    windowsize: float | None = None

    def __hash__(self):
        return hash(self.name)

    def __eq__(self,
               other):
        if isinstance(other, GameStat):
            return self.name == other.name
        return False


class GHGameDLCEntry(AllowExtraBaseModel, validate_assignment=True):
    Name: str = ""
    AppId: int
    ImageUrl: str | None = None
    Languages: list[str] | None = None
    MainAppId: int | None = None
    Type: str = "dlc"


class GHGameInfo(AllowExtraBaseModel, validate_assignment=True):
    Dlcs: dict[str, GHGameDLCEntry] = Field(default_factory=dict)
    Name: str = ""
    AppId: int
    Type: str
    ImageUrl: str | None = None
    Languages: list[str] = Field(default_factory=list)
