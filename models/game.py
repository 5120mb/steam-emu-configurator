from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from custom_types.common import NonEmptyStr


class AchievementInfo(BaseModel, validate_assignment=True):
    """
    Attributes:
        name: The ID of the achievement.
        displayName: The name of the achievement, sometimes localized.
        description: The description of the achievement, sometimes localized.
        icon: The achievement's icon URL.
        icongray: The achievement's gray icon URL.
        hidden: Whether the achievement is hidden (1) or not (0).
    """

    # From the gbe_fork code, `name` is required, and it must contain unique values as it is used as a key later on so
    # multiple achievements with the same name (i.e., empty) will collide. `displayName` and `description` both can be
    # null, and the emulator also accepts dicts with the language as the key and the localized text as values.
    # `hidden` can only be either 0 or 1.
    # Each field should either be missing or have a proper value, avoid None. We allow it in the model because, when
    # dumping it, we exclude all None values.

    name: NonEmptyStr
    displayName: NonEmptyStr | None = None
    description: NonEmptyStr | None = None
    icon: NonEmptyStr | None = None
    icongray: NonEmptyStr | None = None
    hidden: Literal[0, 1] = Field(default=0, ge=0, le=1)

    @field_validator("description", "displayName", mode="before")
    @classmethod
    def empty_str_to_none(cls,
                          value: Any) -> Any | None:
        if isinstance(value, str) and value.strip() == "":
            return None
        return value


class GameStat(BaseModel, validate_assignment=True):
    # From gbe_fork source code, it expects all values to be strings, and only `name` and `type` are actually
    # required, the others fallback to `"0"` if missing; they shouldn't be null, only strings are accepted.
    #
    # Similar to the achievements, the `name` should not be empty, and it should be unique as it's used as a key
    # later so multiple with the same value will collide.

    name: NonEmptyStr
    type: Literal["float", "int", "avgrate"]
    default_val: NonEmptyStr | None = Field(default=None, serialization_alias="default")
    global_val: NonEmptyStr | None = Field(default=None, serialization_alias="global")

    def __hash__(self):
        return hash(self.name)

    def __eq__(self,
               other):
        if isinstance(other, GameStat):
            return self.name == other.name
        return False
