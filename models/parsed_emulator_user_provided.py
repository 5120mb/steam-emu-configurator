from dataclasses import dataclass

from models.emulator_user_provided import (
    UserProvidedEmuConfigAppCloudSaveGeneral,
    UserProvidedEmuConfigAppCloudSaveLinux,
    UserProvidedEmuConfigAppCloudSaveWin,
    UserProvidedEmuConfigAppController,
    UserProvidedEmuConfigAppDLC,
    UserProvidedEmuConfigAppGeneral,
    UserProvidedEmuConfigAppPaths,
    UserProvidedEmuConfigMainConnectivity,
    UserProvidedEmuConfigMainGeneral,
    UserProvidedEmuConfigMainMisc,
    UserProvidedEmuConfigMainStats,
    UserProvidedEmuConfigOverlayAppearance,
    UserProvidedEmuConfigOverlayGeneral,
    UserProvidedEmuConfigOverlayHotkeys,
    UserProvidedEmuConfigUserGeneral,
    UserProvidedEmuConfigUserSaves,
)


# These are the parsed configuration data the user has provided; we allow None in each field because the user can
# specify only some options.


@dataclass
class ParsedUserProvidedEmuConfigApp:
    app__general: UserProvidedEmuConfigAppGeneral | None = None
    app__dlcs: UserProvidedEmuConfigAppDLC | None = None
    app__controller: UserProvidedEmuConfigAppController | None = None
    app__paths: UserProvidedEmuConfigAppPaths | None = None
    app__cloud_save__general: UserProvidedEmuConfigAppCloudSaveGeneral | None = None
    app__cloud_save__win: UserProvidedEmuConfigAppCloudSaveWin | None = None
    app__cloud_save__linux: UserProvidedEmuConfigAppCloudSaveLinux | None = None


@dataclass
class ParsedUserProvidedEmuConfigMain:
    main__general: UserProvidedEmuConfigMainGeneral | None = None
    main__stats: UserProvidedEmuConfigMainStats | None = None
    main__connectivity: UserProvidedEmuConfigMainConnectivity | None = None
    main__misc: UserProvidedEmuConfigMainMisc | None = None


@dataclass
class ParsedUserProvidedEmuConfigOverlay:
    overlay__general: UserProvidedEmuConfigOverlayGeneral | None = None
    overlay__hotkeys: UserProvidedEmuConfigOverlayHotkeys | None = None
    overlay__appearance: UserProvidedEmuConfigOverlayAppearance | None = None


@dataclass
class ParsedUserProvidedEmuConfigUser:
    user__general: UserProvidedEmuConfigUserGeneral | None = None
    user__saves: UserProvidedEmuConfigUserSaves | None = None
