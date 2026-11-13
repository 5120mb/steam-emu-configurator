from typing import TypedDict

from models.parsed_emulator_user_provided import (
    ParsedUserProvidedEmuConfigApp,
    ParsedUserProvidedEmuConfigMain,
    ParsedUserProvidedEmuConfigOverlay,
    ParsedUserProvidedEmuConfigUser,
)


class ParseEmuConfigArgsResult(TypedDict):
    ec_app: ParsedUserProvidedEmuConfigApp | None
    ec_main: ParsedUserProvidedEmuConfigMain | None
    ec_overlay: ParsedUserProvidedEmuConfigOverlay | None
    ec_user: ParsedUserProvidedEmuConfigUser | None
