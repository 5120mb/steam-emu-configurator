from pydantic import ConfigDict, BaseModel, Field


class AllowExtraBaseModel(BaseModel):
    model_config = ConfigDict(extra="allow")


class AllowExtraStrBaseModel(BaseModel):
    # pyrefly: ignore [bad-override-mutable-attribute]
    __pydantic_extra__: dict[str, str] = Field(init=False)

    model_config = ConfigDict(extra="allow")


class ErrorOccurred(BaseModel, validate_assignment=True):
    value: bool = False


class FrozenModel(BaseModel):
    model_config = ConfigDict(frozen=True)


class FrozenModelWithExtra(AllowExtraBaseModel):
    model_config = ConfigDict(frozen=True, extra="allow")
