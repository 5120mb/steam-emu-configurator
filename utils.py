import glob
import os
import random
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import time
from argparse import Namespace
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime
from http.client import RemoteDisconnected
from pathlib import Path
from subprocess import Popen
from tempfile import mkdtemp
from typing import overload, Callable, Iterable

from PIL import Image
from loguru import logger
from packaging.version import Version
from pydantic_core import ErrorDetails
from requests import Response, HTTPError

from common import (GIT_EXE_NAME,
                    PATHS_TO_CLEANUP,
                    GIT_FOR_WINDOWS_NAME,
                    GIT_FOR_WINDOWS_URL,
                    ELF_CLASS,
                    EMULATOR_URL,
                    SEVENZIP_URL,
                    CACHE_DELETING_SIGNAL,
                    SYSTEM_PLATFORM,
                    LOCKFILE_WAIT_TIME,
                    SESSION,
                    PACKAGE_FILES_VALID_EXTENSIONS,
                    EXTRACT_FROM_PACKAGE_NAME_PATTERN,
                    PACKAGE_LIST_PATH_EXTRACT_PATTERN,
                    SEVENZIP_EXE_NAME,
                    SYSTEM_BITNESS)
from custom_types.common import tree
from custom_types.emulator_user_provided import ParseEmuConfigArgsResult
from models.emulator_user_provided import (UserProvidedEmuConfigAppGeneral,
                                           UserProvidedEmuConfigAppDLC,
                                           UserProvidedEmuConfigAppController,
                                           UserProvidedEmuConfigAppPaths,
                                           UserProvidedEmuConfigAppCloudSaveGeneral,
                                           UserProvidedEmuConfigAppCloudSaveWin,
                                           UserProvidedEmuConfigAppCloudSaveLinux,
                                           UserProvidedEmuConfigMainGeneral,
                                           UserProvidedEmuConfigMainStats,
                                           UserProvidedEmuConfigMainConnectivity,
                                           UserProvidedEmuConfigMainMisc,
                                           UserProvidedEmuConfigOverlayGeneral,
                                           UserProvidedEmuConfigOverlayHotkeys,
                                           UserProvidedEmuConfigOverlayAppearance,
                                           UserProvidedEmuConfigUserGeneral,
                                           UserProvidedEmuConfigUserSaves)
from models.parsed_emulator_user_provided import (ParsedUserProvidedEmuConfigApp,
                                                  ParsedUserProvidedEmuConfigMain,
                                                  ParsedUserProvidedEmuConfigOverlay, ParsedUserProvidedEmuConfigUser)


def search_for_package_file(directory: str) -> str | None:
    """
    Search for the compressed package file in the provided directory.

    Args:
        directory: The directory to search in.

    Returns:
        The path if found, `None` otherwise.
    """

    logger.info("Trying to find correct compressed file...")

    compressed_file: str | None = None

    for extension in PACKAGE_FILES_VALID_EXTENSIONS:
        package_files: list[str] = glob.glob(f"*.{extension}", recursive=False, root_dir=directory)
        if len(package_files) > 1:
            found: bool = False
            for package in package_files:
                if EXTRACT_FROM_PACKAGE_NAME_PATTERN.search(package) is not None:
                    compressed_file = os.path.join(directory, package)
                    logger.info(f"Using the {extension} file: {package}")
                    found = True
                    break

            if found:
                break

            logger.info(f"More than one file with the extension {extension} was found, "
                        f"and no filename matched the package pattern \"Game Name (#####) [Build ######].ext\", "
                        f"trying with another extension...")
        elif len(package_files) == 0:
            logger.info(f"No file with the extension {extension} was found, trying with another extension...")
        else:
            compressed_file = os.path.join(directory, package_files[0])
            logger.info(f"Using the {extension} file: {package_files[0]}")
            break

    logger.info("Finished processing package directory.")

    return compressed_file


def list_compressed_file_content(sevenzip_path: str,
                                 compressed_file_path: str,
                                 patterns: Iterable[str],
                                 archive_password: str | None = "") -> str | None:
    """
    List the contents of a compressed package file matching the provided wildcard patterns.

    Args:
        sevenzip_path: Path to the 7-zip binary
        compressed_file_path: Path to the compressed file
        patterns: Wildcard patterns
        archive_password: Compressed file password

    Returns:
        7-zip output or `None` if an error occurred.
    """
    if archive_password is None:
        archive_password = ""

    sevenzip_list_cmd: tuple[str, ...] = (
        sevenzip_path,
        "l",
        compressed_file_path,
        "-r",
        *patterns,
        "-ba",
        "-bd",
        f"-p{archive_password}",
        "-sccUTF-8",
        "-slt"
    )

    try:
        logger.info("Listing compressed files contents...")
        logger.debug(f"7-zip listing command: {' '.join(sevenzip_list_cmd)}")
        sevenzip_output = subprocess.check_output(sevenzip_list_cmd, encoding="utf-8", bufsize=1)
    except subprocess.CalledProcessError:
        logger.error("Couldn't retrieve the compressed files contents.")
        logger.opt(exception=True).debug("Traceback:")
        return None

    logger.info("Finished listing compressed files contents.")

    return sevenzip_output.strip()


def extract_compressed_file_content(sevenzip_path: str,
                                    compressed_file_path: str,
                                    file_list: Iterable[str],
                                    archive_password: str | None = "",
                                    output_path: str | None = None) -> str | None:
    """
    Extract the compressed file contents to the specified directory or a temp dir if not specified.

    Args:
        sevenzip_path: Path to the 7-zip binary.
        compressed_file_path: Path to the compressed file.
        file_list: List of items to extract.
        archive_password: Compressed file password.
        output_path: Directory where to extract the files.

    Returns:
        The output directory if extraction is successful, otherwise `None`.
    """

    # TODO: Maybe support using password list file instead of a single password

    if output_path is None:
        extract_dir: str = mkdtemp()
    else:
        extract_dir = os.path.abspath(os.path.normpath(output_path))

    if archive_password is None:
        archive_password = ""

    sevenzip_extract_cmd: tuple[str, ...] = (
        sevenzip_path,
        "x",
        compressed_file_path,
        f"-o{extract_dir}",
        *file_list,
        "-r",
        "-ba",
        f"-p{archive_password}",
        "-y",
        "-sccUTF-8",
    )

    try:
        subprocess.run(sevenzip_extract_cmd,
                       check=True,
                       encoding="utf-8",
                       cwd=os.path.dirname(compressed_file_path),
                       stdout=subprocess.DEVNULL,
                       stderr=subprocess.STDOUT,
                       bufsize=1)
    except subprocess.CalledProcessError:
        logger.error("Couldn't extract the compressed file contents.")
        logger.opt(exception=True).debug("Traceback:")
        return None

    return extract_dir


def compress_directory_content(sevenzip_path: str,
                               output_path: str,
                               directory_to_compress: str,
                               exclude_pattern: str | None = None) -> bool:
    """
    Compress directory content (not the directory itself) into a .7z file to the specified output path.
    The directory content is removed once the compressed file is created successfully.

    Args:
        sevenzip_path: Path to the 7-zip binary
        output_path: Path to the output file
        directory_to_compress: Path to the directory whose contents compress
        exclude_pattern: Wildcard pattern to exclude from compression

    Returns:
        Whether the compression was successful
    """

    if exclude_pattern is not None:
        exclusion_arg: tuple[str, ...] = (f"-xr!{exclude_pattern}", "--")
    else:
        exclusion_arg = ("--",)

    compress_cmd: tuple[str, ...] = (
        sevenzip_path,
        "a",
        "-m0=LZMA2",
        "-mmt=2",
        "-mmc=1000000000",
        "-mx=9",
        "-myx=9",
        "-md=1024m",
        "-mfb=273",
        "-ms=on",
        "-mf=on",
        "-mqs=on",
        "-sccUTF-8",
        "-mtm",
        "-mtc",
        "-slp",
        "-stl",
        "-snh",
        "-snl",
        "-sse",
        "-ssp",
        "-t7z",
        "-sdel",
        *exclusion_arg,
        output_path,
        os.path.join(directory_to_compress, "*"),
    )

    try:
        if os.path.exists(output_path):
            os.remove(output_path)

        subprocess.run(compress_cmd,
                       check=True,
                       bufsize=1,
                       encoding="utf-8",
                       stdout=subprocess.PIPE,
                       stderr=subprocess.STDOUT)
    except subprocess.CalledProcessError as err:
        logger.error(f"Error compressing directory.\n{err.output}")
        logger.opt(exception=True).debug("Traceback:")
        return False

    return True


def ensure_sevenzip(tools_path: str) -> str | None:
    """
    Search for the 7-zip binary on system PATH and if not found, try to download it.

    Args:
        tools_path: Path to the tools folder.

    Returns:
        Path to the 7-zip binary or `None` if it couldn't be downloaded.
    """

    seven_zip_path: str | None = shutil.which(SEVENZIP_EXE_NAME)
    if seven_zip_path is None:
        if get_7zip(tools_path=tools_path):
            seven_zip_path = os.path.join(tools_path, "7z", SEVENZIP_EXE_NAME)
        else:
            return None

    return seven_zip_path


def extract_paths_from_7z_listing(sevenzip_output: str) -> list[str]:
    """
    Parse the 7-zip listing output to extract all the paths.
    """
    logger.info("Parsing paths from 7-zip listing output...")

    found_files: list[str] = []

    for line in sevenzip_output.splitlines():
        line = line.strip()

        match = PACKAGE_LIST_PATH_EXTRACT_PATTERN.match(line)

        if match is None:
            continue

        try:
            path = match.group(1)
            found_files.append(path)
        except (IndexError, AttributeError):
            continue

    logger.info("Finished parsing output.")

    return found_files


def get_emulator(tools_path: str,
                 check_version: int | None,
                 current_version: str | None = None) -> bool:
    logger.info("Downloading emulator...")

    response = get_with_retry(url=EMULATOR_URL, allow_redirects=True)

    json_response: dict = response.json()

    latest_version = json_response["tag_name"]

    if (check_version is not None
            and check_version >= 2
            and current_version is not None
            and latest_version == current_version):
        logger.info("Emulator is already up to date.")

        with open(os.path.join(tools_path, "last-check"), "w", encoding="utf-8") as stream:
            stream.write(str(time.time()) + ";2")

        return True

    assets_to_download: list[dict[str, str]] = []
    for asset in json_response["assets"]:
        if asset["name"] == "emu-win-release.7z" or asset["name"] == "emu-win-release-vs26.7z":
            logger.info("Getting new version filename for Windows...")
            new_version_name = sanitize_name(f"emu-win-release_{latest_version}.7z")

            logger.info("Getting current version filename for Windows...")
            current_version_name = sanitize_name(f"emu-win-release_{current_version}.7z")

            assets_to_download.append({
                "url": asset["browser_download_url"],
                "compressed_file_path": os.path.join(tools_path,
                                                     "temp",
                                                     new_version_name),
                "file_to_delete": os.path.join(tools_path,
                                               "temp",
                                               current_version_name),
                "output_path": os.path.join(tools_path, "windows"),
                "system": "windows",
            })
        elif asset["name"] == "emu-linux-release.tar.bz2":
            logger.info("Getting new version filename for Linux...")
            new_version_name = sanitize_name(f"emu-linux-release_{latest_version}.7z")

            logger.info("Getting current version filename for Linux...")
            current_version_name = sanitize_name(f"emu-linux-release_{current_version}.7z")

            assets_to_download.append({
                "url": asset["browser_download_url"],
                "compressed_file_path": os.path.join(tools_path,
                                                     "temp",
                                                     new_version_name),
                "file_to_delete": os.path.join(tools_path,
                                               "temp",
                                               current_version_name),
                "output_path": os.path.join(tools_path, "linux"),
                "system": "linux",
            })

        if len(assets_to_download) == 2:
            break

    if len(assets_to_download) != 2:
        logger.error("Couldn't extract the latest download URLs from the API response.")
        return False

    os.makedirs(os.path.join(tools_path, "temp"), exist_ok=True)

    for asset_to_download in assets_to_download:
        stream_response = get_with_retry(url=asset_to_download["url"], allow_redirects=True, stream=True)

        with open(asset_to_download["compressed_file_path"], "wb") as stream:
            for chunk in stream_response.iter_content(4096):
                if chunk is not None:
                    stream.write(chunk)

        online_mtime: str | None = stream_response.headers.get("last-modified")
        if online_mtime is not None:
            parsed_online_mtime = parsedate_to_datetime(online_mtime).timestamp()
            os.utime(asset_to_download["compressed_file_path"], times=(parsed_online_mtime, parsed_online_mtime))

        sevenzip_path: str | None = ensure_sevenzip(tools_path=tools_path)
        if sevenzip_path is None:
            logger.error("Couldn't download 7-zip.")
            return False

        if asset_to_download["system"] == "linux":
            extract_compressed_file_content(sevenzip_path=sevenzip_path,
                                            compressed_file_path=asset_to_download["compressed_file_path"],
                                            file_list=[],
                                            output_path=os.path.dirname(asset_to_download["compressed_file_path"]))

            os.remove(remove_readonly_flag(asset_to_download["compressed_file_path"]))

            asset_to_download["compressed_file_path"] = os.path.splitext(asset_to_download["compressed_file_path"])[0]

        tmp_dir = extract_compressed_file_content(sevenzip_path=sevenzip_path,
                                                  compressed_file_path=asset_to_download["compressed_file_path"],
                                                  file_list=["release/experimental",
                                                             "release/steam_settings.EXAMPLE/sounds.EXAMPLE"],
                                                  output_path=asset_to_download["output_path"])

        if tmp_dir is None:
            return False

        try:
            shutil.rmtree(os.path.join(asset_to_download["output_path"], "gbe_fork_experimental"))
        except FileNotFoundError:
            pass

        shutil.move(os.path.join(asset_to_download["output_path"], "release", "experimental"),
                    os.path.join(asset_to_download["output_path"], "gbe_fork_experimental"))
        shutil.move(os.path.join(asset_to_download["output_path"],
                                 "release",
                                 "steam_settings.EXAMPLE",
                                 "sounds.EXAMPLE"),
                    os.path.join(asset_to_download["output_path"], "gbe_fork_experimental", "sounds"))

        shutil.rmtree(os.path.join(asset_to_download["output_path"], "release"))

        os.remove(os.path.join(asset_to_download["output_path"], "gbe_fork_experimental", "sounds", "LICENSE.md"))
        os.remove(os.path.join(asset_to_download["output_path"], "gbe_fork_experimental", "sounds", "README.md"))

        with open(os.path.join(tools_path, "last-version"), "w", encoding="utf-8") as stream:
            stream.write(latest_version)

        with open(os.path.join(tools_path, "last-check"), "w", encoding="utf-8") as stream:
            stream.write(str(time.time()) + ";2")

        os.remove(asset_to_download["compressed_file_path"])

        if os.path.exists(asset_to_download["file_to_delete"]):
            os.remove(asset_to_download["file_to_delete"])

    logger.info("Finished downloading emulator.")
    return True


def get_7zip(tools_path: str) -> bool:
    """
    Try to download the 7-zip binary and store it in the specified path.

    Args:
        tools_path: Path where to store the 7-zip binary

    Returns:
        Whether the download was successful.
    """
    if os.path.exists(os.path.join(tools_path, "7z", SEVENZIP_EXE_NAME)):
        return True

    logger.info("Downloading 7-zip...")

    sevenzip_lock_file: str = os.path.join(tools_path, "7zip.lock")

    if os.path.exists(sevenzip_lock_file):
        logger.info("Lock file found, waiting for 7-zip to be available...")

        while os.path.exists(sevenzip_lock_file):
            time.sleep(LOCKFILE_WAIT_TIME)

        if os.path.exists(os.path.join(tools_path, "7z", SEVENZIP_EXE_NAME)):
            return True

    try:
        open(sevenzip_lock_file, "w").close()

        if SYSTEM_PLATFORM == "windows":
            return get_7zip_for_windows(tools_path=tools_path)
        else:
            return get_7zip_for_linux(tools_path=tools_path)
    finally:
        if os.path.exists(sevenzip_lock_file):
            os.remove(sevenzip_lock_file)


def get_7zip_for_windows(tools_path: str) -> bool:
    gh_response = get_with_retry(url=SEVENZIP_URL, allow_redirects=True)

    download_url_7zr = get_gh_asset(response=gh_response, name="7zr.exe")

    if download_url_7zr is None:
        logger.error("Couldn't extract the latest download URL for 7zr from the API response.")
        return False

    sevenzip_reduced_path: str = os.path.join(tools_path, "7zr.exe")
    download_data(download_url=download_url_7zr, output=sevenzip_reduced_path)

    if SYSTEM_BITNESS == 64:
        sevenzip_filename = "7z" + gh_response.json()["tag_name"].replace(".", "") + "-x64.exe"
    else:
        sevenzip_filename = "7z" + gh_response.json()["tag_name"].replace(".", "") + ".exe"

    download_url_7z = get_gh_asset(response=gh_response, name=sevenzip_filename)

    if download_url_7z is None:
        logger.error("Couldn't extract the latest download URL for 7z from the API response.")
        return False

    sevenzip_path: str = os.path.join(tools_path, "7z", sevenzip_filename)
    download_data(download_url=download_url_7z, output=sevenzip_path)

    output_path = extract_compressed_file_content(sevenzip_path=sevenzip_reduced_path,
                                                  compressed_file_path=sevenzip_path,
                                                  file_list=[],
                                                  output_path=os.path.join(tools_path, "7z"))

    if output_path is None:
        logger.error("Couldn't extract the 7-zip files.")
        return False
    else:
        logger.info("Finished downloading 7-zip.")
        return True


def get_7zip_for_linux(tools_path: str) -> bool:
    gh_response = get_with_retry(url=SEVENZIP_URL, allow_redirects=True)

    if SYSTEM_BITNESS == 64:
        sevenzip_filename = "7z" + gh_response.json()["tag_name"].replace(".", "") + "-linux-x64.tar.xz"
    else:
        sevenzip_filename = "7z" + gh_response.json()["tag_name"].replace(".", "") + "-linux-x86.tar.xz"

    download_url_7z = get_gh_asset(response=gh_response, name=sevenzip_filename)

    if download_url_7z is None:
        logger.error("Couldn't extract the latest download URL for 7z from the API response.")
        return False

    sevenzip_path: str = os.path.join(tools_path, "7z", sevenzip_filename)
    download_data(download_url=download_url_7z, output=sevenzip_path)

    output_path = extract_xz_file_content(compressed_file_path=sevenzip_path,
                                          output_path=os.path.join(tools_path, "7z"))

    if output_path is None:
        logger.error("Couldn't extract the 7-zip files.")
        return False
    else:
        logger.info("Finished downloading 7-zip.")
        return True


def update_emulator(tools_path: str) -> bool:
    emulator_lock_file: str = os.path.join(tools_path, "emulator.lock")

    if os.path.exists(emulator_lock_file):
        logger.info("Lock file found, waiting for the emulator to be available...")

        while os.path.exists(emulator_lock_file):
            time.sleep(LOCKFILE_WAIT_TIME)

        return True

    check_file: str = os.path.join(tools_path, "last-check")

    if not os.path.exists(check_file):
        return get_emulator(tools_path=tools_path, check_version=None)
    else:
        with open(check_file, "r", encoding="utf-8") as stream:
            last_check_content = stream.read()

        last_check_parts = last_check_content.split(";")
        if len(last_check_parts) == 2:
            last_time = float(last_check_parts[0])
            check_version = int(last_check_parts[1])

            if time.time() - last_time <= 24 * 60 * 60:
                logger.info("Update check for the emulator has been performed recently (less than 24 hours ago), "
                            "skipping updating it...")

                return True
        else:
            check_version = None

    try:
        logger.info("Updating emulator...")

        open(emulator_lock_file, "w").close()

        if os.path.exists(os.path.join(tools_path, "last-version")):
            with open(os.path.join(tools_path, "last-version"), "r", encoding="utf-8") as stream:
                current_version = stream.read()
        else:
            current_version = None

        success: bool = get_emulator(tools_path=tools_path,
                                     current_version=current_version,
                                     check_version=check_version)

        logger.info("Finished updating emulator.")

        return success
    finally:
        os.remove(emulator_lock_file)


def sanitize_name(name: str,
                  do_not_use_unicode: bool = False) -> str:
    logger.info(f"Sanitizing name: {name}")
    logger.debug(f"Detected OS: {SYSTEM_PLATFORM}")

    illegal_characters: dict[str, str]
    if SYSTEM_PLATFORM == "windows":
        illegal_characters = {
            "<": "\uFE64",
            ">": "\uFE65",
            ":": "\uFE55",
            "\"": "\uFF02",
            "/": "\uFF0F",
            "\\": "\uFF3C",
            "|": "\uFF5C",
            "?": "\uFF1F",
            "*": "\uFF0A"
        }
    elif SYSTEM_PLATFORM == "darwin" or SYSTEM_PLATFORM == "linux":
        illegal_characters = {
            "/": "\uFF0F"
        }
    else:
        return name

    logger.debug(f"Illegal characters:\n{list(illegal_characters.keys())}")

    for character in illegal_characters:
        if character in name:
            if do_not_use_unicode:
                legal_character = "_"
            else:
                legal_character = illegal_characters[character].encode("utf-8").decode("utf-8")

            name = name.replace(character, legal_character)

    logger.info("Finished sanitizing name.")
    logger.debug(f"Sanitized name: {name}")

    return name


def pad_filename(filename: str,
                 parent_path: str = "") -> str:
    logger.info(f"Padding filename... {filename}")
    pad_number = 1

    if parent_path != "":
        filename = os.path.join(parent_path, filename)

    orig_filename = filename

    while os.path.exists(filename):
        name, ext = os.path.splitext(orig_filename)
        filename = name + "_" + str(pad_number).zfill(2) + ext
        pad_number += 1

    logger.info("Finished padding filename.")
    logger.debug(f"Padded filename: {filename}")

    return filename


def pad_directory(dirname: str,
                  parent_path: str = "") -> str:
    logger.info(f"Padding directory: {dirname}")

    pad_number = 1
    dirname = dirname.strip()
    parent_path = parent_path.strip()

    if parent_path != "":
        dirname = os.path.join(parent_path, dirname)

    orig_dirname = dirname

    while os.path.exists(dirname):
        dirname = orig_dirname + "_" + str(pad_number).zfill(2)
        pad_number += 1

    if dirname != orig_dirname:
        logger.info(f"Finished padding directory: {dirname}")
    else:
        logger.info("No padding needed.")

    return dirname


def process_errors(error_details: list[ErrorDetails]) -> str:
    msg: str = ""
    for detail in error_details:
        if detail["type"] == "missing":
            missing_opts = ""
            for option in detail["loc"]:
                missing_opts += f"{option} "

            msg += f"Missing options: {missing_opts}\n"
        elif detail["type"] == "json_invalid":
            msg += "Invalid JSON file."
        elif detail["type"] == "value_error":
            invalid_opts = ""
            for option in detail["loc"]:
                invalid_opts += f"{option} "

            msg += f"The values of these options are invalid: {invalid_opts}\n"
        else:
            invalid_opts = ""
            for option in detail["loc"]:
                invalid_opts += f"{option} "

            msg += f"\n{detail['msg']}: {invalid_opts}\n"

    return msg


def _handle_ro(func: Callable[..., object],
               path: str,
               exc_info: BaseException):
    if not isinstance(exc_info, PermissionError):
        raise exc_info

    remove_readonly_flag(path=path)

    func(path)


@overload
def remove_readonly_flag(path: os.PathLike) -> os.PathLike:
    ...


@overload
def remove_readonly_flag(path: str) -> str:
    ...


@overload
def remove_readonly_flag(path: bytes) -> bytes:
    ...


def remove_readonly_flag(path: os.PathLike | str | bytes) -> os.PathLike | str | bytes:
    if SYSTEM_PLATFORM == "windows":
        if os.path.exists(path):
            os.chmod(path, stat.S_IWRITE)

    return path


def delete_old_caches(product_name: str,
                      current_version: str) -> None:
    if "__compiled__" not in globals():
        logger.debug("Not in a compiled environment, skipping deleting old caches.")
        return

    logger.debug("Deleting old caches...")

    # From Nuitka source-code:
    # Typical user log directories are:
    #      Mac OS X:   ~/Library/Logs/<AppName>
    #      Unix:       ~/.cache/<AppName>/log  # or under $XDG_CACHE_HOME if defined
    #      Win XP:     C:\Documents and Settings\<username>\Local Settings\Application Data\<AppAuthor>\<AppName>\Logs
    #      Vista:      C:\Users\<username>\AppData\Local\<AppAuthor>\<AppName>\Logs

    appdata_path = os.getenv("LOCALAPPDATA")

    if appdata_path is None:
        logger.error("Couldn't find the user's AppData directory.")
        return

    cache_path: str = os.path.join(appdata_path, "5120mb", product_name)

    signal_path = os.path.join(os.path.dirname(cache_path), CACHE_DELETING_SIGNAL)

    if os.path.exists(signal_path):
        logger.debug("Already deleting old caches...")
        sys.exit(0)

    open(signal_path, "w", encoding="utf-8").close()

    try:
        cache_content: list[str] = os.listdir(cache_path)

        paths_to_delete: list[str] = []
        for cache_dir in cache_content:
            if cache_dir != current_version:
                paths_to_delete.append(os.path.join(cache_path, cache_dir))

        if len(paths_to_delete) == 0:
            logger.debug("No old caches to delete.")
            sys.exit(0)

        logger.debug(f"Cache paths to delete:\n{paths_to_delete}")

        for path_to_delete in paths_to_delete:
            try:
                shutil.rmtree(path_to_delete)
            except FileNotFoundError:
                pass
            except OSError:
                logger.error(f"Failed to remove {path_to_delete}")
                logger.opt(exception=True).error("Traceback:")

        logger.debug("Finished deleting old caches.")
    finally:
        os.remove(signal_path)


def get_gray_icon_from_normal(color_icon: str,
                              output_path: str) -> bool:
    try:
        pil_image = Image.open(color_icon)
        pil_image = pil_image.convert("L")
        pil_image.save(output_path)
        return True
    except Exception:
        logger.error("Couldn't convert the icon to grayscale.")
        logger.opt(exception=True).debug("Traceback:")
        return False


def read_file_content(file_path: str) -> str | None:
    if not os.path.exists(file_path):
        return None

    if os.path.isdir(file_path):
        raise TypeError(f"\"{file_path}\" is a directory.")

    with open(file_path, "r", encoding="utf-8") as stream:
        content = stream.read()

    return content.strip()


def get_with_retry(url: str,
                   allow_redirects: bool = False,
                   stream: bool = False,
                   max_tries: int = 5) -> Response:
    """
    Perform get request with retry. If the response is 404, the request won't be retried and simply except.

    Args:
        url: URL to request
        allow_redirects: Whether to allow redirects.
        stream: Whether to use streaming for the request.
        max_tries: Maximum number of tries.

    Returns:
        The request response.
    """

    tries: int = 0
    get_response: Response
    last_wait: int = 0

    while True:
        tries += 1
        get_response = SESSION.get(url, allow_redirects=allow_redirects, stream=stream)

        try:
            get_response.raise_for_status()
        except HTTPError as err:
            if tries == max_tries:
                logger.error(f"Failed to get response from {url}. HTTP error code: {err.response.status_code}")
                logger.opt(exception=True).debug("Traceback:")

                raise

            if err.response.status_code == 404:
                logger.error(f"Failed to get response from {url}. HTTP error code: {err.response.status_code}")
                logger.opt(exception=True).debug("Traceback:")

                raise

            logger.opt(exception=True).debug(f"Error while getting response from {url}."
                                             f" HTTP error code: {err.response.status_code}. Traceback:")

            last_wait += random.randint(3, 20)
            logger.debug(f"Waiting for {last_wait} seconds...")
            time.sleep(last_wait)
            continue
        except RemoteDisconnected as err:
            if tries == max_tries:
                logger.error(f"Failed to get response from {url}. {err.strerror}")
                logger.opt(exception=True).debug("Traceback:")

                raise

            logger.opt(exception=True).debug(f"Error while getting response from {url}.")

            last_wait += random.randint(3, 20)
            logger.debug(f"Waiting for {last_wait} seconds...")
            time.sleep(last_wait)
            continue

        break

    return get_response


def get_latest_stored_version(path_to_check: str) -> str:
    versions: dict[Version, str] = {}

    for item in os.listdir(path_to_check):
        if not os.path.isdir(os.path.join(path_to_check, item)):
            continue

        if not item.startswith("v"):
            continue

        versions[Version(item)] = item

    if len(versions) == 0:
        raise ValueError("No versions found in the specified path.")

    return versions[max(versions)]


def get_previous_stored_version(path_to_check: str,
                                version_to_use: str | Version) -> str | None:
    versions: dict[Version, str] = {}
    found_previous_version: Version | None = None

    if isinstance(version_to_use, str):
        version_to_use = Version(version_to_use)

    for item in os.listdir(path_to_check):
        if not os.path.isdir(os.path.join(path_to_check, item)):
            continue

        if not item.startswith("v"):
            continue

        versions[Version(item)] = item

    if len(versions) == 0:
        raise ValueError("No versions found in the specified path.")

    for version in versions:
        if version < version_to_use:
            if found_previous_version is None:
                found_previous_version = version
            elif found_previous_version < version:
                found_previous_version = version

    if found_previous_version is None:
        return None

    return versions[found_previous_version]


def get_elf_lib_bitness(path: str) -> int:
    with open(path, "rb") as f:
        header = f.read(5)

    if header[:4] != b"\x7fELF":
        raise ValueError("Not ELF")

    return ELF_CLASS[header[4]]


def check_python_version() -> None:
    current_python_version = sys.version_info[:2]
    if current_python_version < (3, 10):
        logger.critical("Python 3.10 or higher is required.")
        sys.exit(1)


@overload
def get_gh_asset(*,
                 name: str,
                 response: Response,
                 url: None = None,
                 is_regex: bool = False) -> str | None:
    ...


@overload
def get_gh_asset(*,
                 name: str,
                 response: None = None,
                 url: str,
                 is_regex: bool = False) -> str | None:
    ...


def get_gh_asset(*,
                 name: str,
                 response: Response | None = None,
                 url: str | None = None,
                 is_regex: bool = False) -> str | None:
    """
    Retrieve a GitHub release asset by name.

    Returns:
        The download URL of the asset if found, otherwise `None`.
    """
    if url is not None:
        response = get_with_retry(url=url, allow_redirects=True)
    elif response is None:
        raise ValueError("Either response or url must be provided.")

    json_response: dict = response.json()

    if url is not None:
        response.close()

    for asset in json_response["assets"]:
        if is_regex:
            match = re.search(name, asset["name"])
            if match is not None:
                return asset["browser_download_url"]
        else:
            if asset["name"] == name:
                return asset["browser_download_url"]

    return None


def get_git_path(tools_path: str) -> str | None:
    system_git_path = shutil.which(GIT_EXE_NAME)

    if system_git_path is not None:
        return os.path.abspath(os.path.normpath(system_git_path))
    elif SYSTEM_PLATFORM != "windows":
        logger.critical("Git is not installed on the system, "
                        "in Linux the only way is to install it from the package manager.")
        return None

    git_path = os.path.join(tools_path, "git-portable")
    git_exe_path = os.path.join(git_path, "bin", "git.exe")

    if os.path.isfile(git_exe_path):
        return git_exe_path

    sevenzip_path = ensure_sevenzip(tools_path=tools_path)

    if sevenzip_path is None:
        logger.critical("Couldn't get 7-zip, aborting...")
        sys.exit(4)

    download_url = get_gh_asset(url=GIT_FOR_WINDOWS_URL, name=GIT_FOR_WINDOWS_NAME, is_regex=True)

    if download_url is None:
        logger.critical("Couldn't get the latest Git for Windows version, aborting...")
        sys.exit(4)

    git_portable_temp_path = os.path.join(tools_path, "temp", "git-portable.exe")

    with (get_with_retry(url=download_url, stream=True, allow_redirects=True) as stream_response,
          open(git_portable_temp_path, "wb") as stream):
        for chunk in stream_response.iter_content(4096):
            if chunk is not None:
                stream.write(chunk)

    git_path = extract_compressed_file_content(sevenzip_path=sevenzip_path,
                                               compressed_file_path=git_portable_temp_path,
                                               file_list=[],
                                               output_path=git_path)

    if git_path is not None:
        os.remove(git_portable_temp_path)
        return git_exe_path
    else:
        return None


class ProcessResult:
    def __init__(self,
                 process: Popen[bytes],
                 stdout_path: Path,
                 stderr_path: Path):
        self.process = process
        self.stdout_path = stdout_path
        self.stderr_path = stderr_path

    def wait(self) -> int:
        return self.process.wait()

    def read_stdout(self) -> str:
        return self.stdout_path.read_text()

    def read_stderr(self) -> str:
        return self.stderr_path.read_text()


def run_command(cmd: list[str],
                cwd: str | None = None) -> ProcessResult:
    stdout_fd, stdout_path = tempfile.mkstemp()
    stderr_fd, stderr_path = tempfile.mkstemp()

    PATHS_TO_CLEANUP.add(stdout_path)
    PATHS_TO_CLEANUP.add(stderr_path)

    process = Popen(cmd,
                    cwd=cwd,
                    stdout=stdout_fd,
                    stderr=stderr_fd,
                    creationflags=subprocess.CREATE_NO_WINDOW)

    os.close(stdout_fd)
    os.close(stderr_fd)

    result = ProcessResult(
            process=process,
            stdout_path=Path(stdout_path),
            stderr_path=Path(stderr_path),
    )

    result.wait()

    return result


class GitRepo:
    """
    Creates a simple git object supporting clone and pull.
    """
    _git_path: str
    _repo_path: str
    _repo_url: str | None

    def __init__(self,
                 git_path: str,
                 repo_path: str,
                 repo_url: str | None = None) -> None:
        self._git_path = git_path
        self._repo_path = repo_path
        self._repo_url = repo_url

    def _git(self,
             *args: str,
             cwd: str | None = None) -> ProcessResult:
        return run_command([self._git_path, *args],
                           cwd=cwd)

    def clone(self) -> ProcessResult:
        if self._repo_url is None:
            raise ValueError("No repo URL specified.")

        return self._git("clone",
                         "--depth",
                         "1",
                         "--single-branch",
                         "--branch",
                         "main",
                         self._repo_url,
                         self._repo_path)

    def pull(self) -> ProcessResult:
        """
        This is not really a pull operation; we fetch the minimal needed, then reset.
        """
        fetch_result = self._git("fetch",
                                 "--depth",
                                 "1",
                                 "origin",
                                 "main",
                                 cwd=self._repo_path)

        if fetch_result.process.returncode != 0:
            return fetch_result

        return self._git("reset",
                         "--hard",
                         "origin/main",
                         cwd=self._repo_path)


def cleanup() -> None:
    for file in PATHS_TO_CLEANUP:
        try:
            if os.path.isfile(file):
                os.remove(file)
            elif os.path.isdir(file):
                shutil.rmtree(file, ignore_errors=True)
        except OSError:
            pass


def should_refresh_cache(date: str) -> bool:
    parsed_date = datetime.strptime(date, "%Y%m%d")

    if datetime.now() - parsed_date > timedelta(days=14):
        return True
    else:
        return False


def write_last_retrieval_flag(path: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)

    with open(path, "w", encoding="utf-8") as stream:
        stream.write(datetime.now().strftime("%Y%m%d"))


def custom_copy(src: str,
                dst: str) -> None:
    os.makedirs(os.path.dirname(dst), exist_ok=True)

    if os.path.isdir(src):
        shutil.copytree(src, remove_readonly_flag(dst), dirs_exist_ok=True)
    else:
        shutil.copy2(src, remove_readonly_flag(dst))


def download_data(download_url: str,
                  output: str,
                  set_modtime: bool = True) -> None:
    """
    Download data from a URL and save it to a file, optionally setting the original modification time.
    """

    os.makedirs(os.path.dirname(output), exist_ok=True)

    with (get_with_retry(url=download_url, allow_redirects=True, stream=True) as stream_response,
          open(output, "wb") as file_stream):
        for chunk in stream_response.iter_content(4096):
            if chunk is not None:
                file_stream.write(chunk)

        if set_modtime:
            online_mtime: str | None = stream_response.headers.get("last-modified")
            if online_mtime is not None:
                parsed_online_mtime = parsedate_to_datetime(online_mtime).timestamp()
                os.utime(output, times=(parsed_online_mtime, parsed_online_mtime))


def extract_xz_file_content(compressed_file_path: str,
                            output_path: str | None = None) -> str | None:
    """
    Extract the XZ contents to the specified directory or a temp dir if not specified.

    Args:
        compressed_file_path: Path to the compressed file.
        output_path: Directory where to extract the files.

    Returns:
        The output directory if extraction is successful, otherwise `None`.
    """

    if output_path is None:
        extract_dir: str = mkdtemp()
    else:
        extract_dir = os.path.abspath(os.path.normpath(output_path))

    os.makedirs(extract_dir, exist_ok=True)

    extract_cmd: tuple[str, ...] = (
        "tar",
        "-xJf",
        compressed_file_path,
        "-C",
        extract_dir,
    )

    try:
        subprocess.run(extract_cmd,
                       check=True,
                       encoding="utf-8",
                       stdout=subprocess.DEVNULL,
                       stderr=subprocess.STDOUT)
    except subprocess.CalledProcessError:
        logger.error("Couldn't extract the XZ file contents.")
        logger.opt(exception=True).debug("Traceback:")
        return None

    return extract_dir


def parse_emu_config_args(args: Namespace) -> ParseEmuConfigArgsResult:
    args_dict = vars(args)

    raw_emu_config_args = {}

    for arg_name, arg_value in args_dict.items():
        if arg_value is None:
            continue

        if arg_name.startswith("ec__"):
            raw_emu_config_args[arg_name[4:]] = arg_value

    emu_config_args = tree()

    for arg_name, arg_value in raw_emu_config_args.items():
        arg_name_parts = arg_name.split("__")

        if len(arg_name_parts) <= 1:
            raise ValueError(f"Invalid argument name: {arg_name}")

        config_name = arg_name_parts.pop(-1)

        config_path = None
        for part in arg_name_parts:
            if config_path is None:
                config_path = emu_config_args[part]
            else:
                config_path = config_path[part]

        if config_path is None:
            raise ValueError(f"Invalid argument name: {arg_name}")

        config_path[config_name] = arg_value

    ec_app: ParsedUserProvidedEmuConfigApp | None = None
    ec_main: ParsedUserProvidedEmuConfigMain | None = None
    ec_overlay: ParsedUserProvidedEmuConfigOverlay | None = None
    ec_user: ParsedUserProvidedEmuConfigUser | None = None

    if "app" in emu_config_args:
        ec_app = ParsedUserProvidedEmuConfigApp()
        if "general" in emu_config_args["app"]:
            ec_app.app__general = UserProvidedEmuConfigAppGeneral.model_validate(emu_config_args["app"]["general"])

        if "dlcs" in emu_config_args["app"]:
            dlc_data = {}

            if "unlock_all" in emu_config_args["app"]["dlcs"]:
                dlc_data["unlock_all"] = emu_config_args["app"]["dlcs"]["unlock_all"]

            if "add_dlcs" in emu_config_args["app"]["dlcs"]:
                dlc_tuple_pattern = re.compile(r"^\((\d+),\s*(.+)\)$")
                for dlc_tuple in emu_config_args["app"]["dlcs"]["add_dlcs"]:
                    match = dlc_tuple_pattern.match(dlc_tuple)

                    if match is None:
                        raise ValueError(f"Invalid DLC tuple: {dlc_tuple}")

                    dlc_data[match.group(1)] = match.group(2)

            ec_app.app__dlcs = UserProvidedEmuConfigAppDLC.model_validate(dlc_data)

        if "controller" in emu_config_args["app"]:
            ec_app.app__controller = UserProvidedEmuConfigAppController.model_validate(
                    emu_config_args["app"]["controller"])

        if "paths" in emu_config_args["app"]:
            paths: dict[str, str] = {}
            appid_tuple_pattern = re.compile(r"^\((\d+),\s*([\w\-:Á-Úá-úÑñ\\/]+)?\)$")
            for appid_tuple in emu_config_args["app"]["paths"]:
                match = appid_tuple_pattern.match(appid_tuple)
                if match is None:
                    raise ValueError(f"Invalid appid tuple: {appid_tuple}")

                appid = match.group(1)
                try:
                    path = match.group(2)

                    if path is None:
                        path = ""
                except IndexError:
                    path = ""

                paths[appid] = path

            ec_app.app__paths = UserProvidedEmuConfigAppPaths.model_validate(paths)

        if "cloud_save" in emu_config_args["app"]:
            if "general" in emu_config_args["app"]["cloud_save"]:
                ec_app.app__cloud_save__general = UserProvidedEmuConfigAppCloudSaveGeneral.model_validate(
                        emu_config_args["app"]["cloud_save"]["general"])

            if "win" in emu_config_args["app"]["cloud_save"]:
                win_paths: dict[str, str] = {}

                for idx, path in enumerate(emu_config_args["app"]["cloud_save"]["win"], 1):
                    win_paths[f"dir{idx}"] = path

                ec_app.app__cloud_save__win = UserProvidedEmuConfigAppCloudSaveWin.model_validate(win_paths)

            if "linux" in emu_config_args["app"]["cloud_save"]:
                linux_paths: dict[str, str] = {}

                for idx, path in enumerate(emu_config_args["app"]["cloud_save"]["linux"], 1):
                    linux_paths[f"dir{idx}"] = path

                ec_app.app__cloud_save__linux = UserProvidedEmuConfigAppCloudSaveLinux.model_validate(linux_paths)

    if "main" in emu_config_args:
        ec_main = ParsedUserProvidedEmuConfigMain()
        if "general" in emu_config_args["main"]:
            ec_main.main__general = UserProvidedEmuConfigMainGeneral.model_validate(emu_config_args["main"]["general"])

        if "stats" in emu_config_args["main"]:
            ec_main.main__stats = UserProvidedEmuConfigMainStats.model_validate(emu_config_args["main"]["stats"])

        if "connectivity" in emu_config_args["main"]:
            ec_main.main__connectivity = UserProvidedEmuConfigMainConnectivity.model_validate(
                    emu_config_args["main"]["connectivity"])

        if "misc" in emu_config_args["main"]:
            ec_main.main__misc = UserProvidedEmuConfigMainMisc.model_validate(emu_config_args["main"]["misc"])

    if "overlay" in emu_config_args:
        ec_overlay = ParsedUserProvidedEmuConfigOverlay()
        if "general" in emu_config_args["overlay"]:
            ec_overlay.overlay__general = UserProvidedEmuConfigOverlayGeneral.model_validate(
                    emu_config_args["overlay"]["general"])

        if "hotkeys" in emu_config_args["overlay"]:
            ec_overlay.overlay__hotkeys = UserProvidedEmuConfigOverlayHotkeys.model_validate(
                    emu_config_args["overlay"]["hotkeys"])

        if "appearance" in emu_config_args["overlay"]:
            ec_overlay.overlay__appearance = UserProvidedEmuConfigOverlayAppearance.model_validate(
                    emu_config_args["overlay"]["appearance"])

    if "user" in emu_config_args:
        ec_user = ParsedUserProvidedEmuConfigUser()
        if "general" in emu_config_args["user"]:
            ec_user.user__general = UserProvidedEmuConfigUserGeneral.model_validate(emu_config_args["user"]["general"])

        if "saves" in emu_config_args["user"]:
            ec_user.user__saves = UserProvidedEmuConfigUserSaves.model_validate(emu_config_args["user"]["saves"])

    return {
        "ec_app": ec_app,
        "ec_main": ec_main,
        "ec_overlay": ec_overlay,
        "ec_user": ec_user
    }
