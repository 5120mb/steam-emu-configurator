import re
from collections import defaultdict
from typing import Annotated, TypedDict

from pydantic import StringConstraints

NonEmptyStr = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
    ),
]
KeyComboStr = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        pattern=re.compile(
            r"^(shift|ctrl|alt|tab|fn1|fn2|fn3|fn4|fn5|fn6|fn7|fn8|fn9|fn10|fn11|fn12)(\s\+\s"
            r"(shift|ctrl|alt|tab|fn1|fn2|fn3|fn4|fn5|fn6|fn7|fn8|fn9|fn10|fn11|fn12))*$",
        ),
    ),
]
OutputDirRelations = dict[str, list[str]] | dict[str, None]


class OutputDirResult(TypedDict):
    output_dir_relations: OutputDirRelations
    lib_locations: list[str] | None
    directory_to_compress: str | None
    output_dir: str | None
    extracted_files_path: str | None
    is_linux: bool


class ExtractIdsResult(TypedDict):
    appid: str | None
    buildid: str | None
    extracted_files_path: str | None
    resulting_acf_files: set[str] | None
    tried_extracting_package_files: bool


class ExtractOrAskIdsResult(TypedDict):
    appid: str
    buildid: str | None
    extracted_files_path: str | None
    resulting_acf_files: set[str] | None
    tried_extracting_package_files: bool


class ExtractFromPackageFilesResult(TypedDict):
    appid: str | None
    buildid: str | None
    temp_path: str | None
    acf_files: set[str] | None
    tried_extracting_package_files: bool


class GetSteamLibLocationResult(TypedDict):
    relative_lib_location: dict[str, str] | None
    lib_locations: list[str] | None
    extracted_files_path: str | None
    is_linux: bool


class ExtractIdFromAcfResult(TypedDict):
    appid: str | None
    buildid: str | None
    acf_files: set[str] | None


def tree():
    return defaultdict(tree)
