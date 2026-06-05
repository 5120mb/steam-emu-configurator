from typing import TypedDict

from models.parsed_emulator_user_provided import (ParsedUserProvidedEmuConfigUser,
                                                  ParsedUserProvidedEmuConfigOverlay,
                                                  ParsedUserProvidedEmuConfigMain,
                                                  ParsedUserProvidedEmuConfigApp)


class ParseEmuConfigArgsResult(TypedDict):
    ec_app: ParsedUserProvidedEmuConfigApp | None
    ec_main: ParsedUserProvidedEmuConfigMain | None
    ec_overlay: ParsedUserProvidedEmuConfigOverlay | None
    ec_user: ParsedUserProvidedEmuConfigUser | None
