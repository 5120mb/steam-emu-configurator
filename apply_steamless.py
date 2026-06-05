import argparse
import glob
import os.path
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from email.utils import parsedate_to_datetime

from loguru import logger
from pydantic import BaseModel, ValidationError, field_validator
from requests import Response, HTTPError

from common import (get_program_dir,
                    SESSION,
                    LOCKFILE_WAIT_TIME,
                    CURRENT_DATE,
                    EXECUTABLES_TO_IGNORE_PATTERNS, load_data_file)
from models.common import ErrorOccurred
from utils import (check_python_version,
                   search_for_package_file,
                   list_compressed_file_content,
                   extract_paths_from_7z_listing,
                   extract_compressed_file_content,
                   sanitize_name,
                   remove_readonly_flag,
                   process_errors,
                   ensure_sevenzip,
                   compress_directory_content,
                   delete_old_caches,
                   get_latest_stored_version,
                   get_previous_stored_version)


class Config(BaseModel):
    package_path: str | None
    game_path: str | None
    tools_path: str
    archive_password: str | None
    output_path: str | None
    log_level: str
    log_file: str | None
    compress_output: bool
    compressed_file_name: str | None

    @field_validator("package_path",
                     "game_path",
                     "tools_path",
                     "output_path",
                     "log_file",
                     mode="after")
    @classmethod
    def sanitize_path(cls,
                      value: str | None) -> str | None:
        if isinstance(value, str):
            return os.path.abspath(os.path.normpath(value))
        return value


PROGRAM_DIR: str = get_program_dir()

error_occurred = ErrorOccurred()

__version__ = "0.7.0"


def error_sink(message):
    record = message.record
    if record["level"].no >= logger.level("ERROR").no:
        error_occurred.value = True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("-v", "--version",
                        action="version",
                        version=f"%(prog)s v{__version__}")

    parser.add_argument("--package-path",
                        required=False,
                        help="Path to package directory",
                        type=str)
    parser.add_argument("--game-path",
                        required=False,
                        help="Path to game directory",
                        type=str)
    parser.add_argument("--archive-password",
                        required=False,
                        help="Password of the package compressed file",
                        type=str)
    parser.add_argument("--output-path",
                        required=False,
                        help="Path to output the steamless executable",
                        type=str)
    parser.add_argument("--compress-output",
                        action="store_true",
                        help="Compress output files. Only works with package paths.")
    parser.add_argument("--compressed-file-name",
                        required=False,
                        help="Compressed output file name.",
                        type=str)

    # noinspection PyTypeChecker
    parser.add_argument("--log-level",
                        help="How much stuff is logged.",
                        default="INFO",
                        choices=["TRACE", "DEBUG", "INFO", "SUCCESS", "WARNING", "ERROR", "CRITICAL"],
                        type=str.upper)
    parser.add_argument("--log-file",
                        help="Where to store the log file. By default in the program dir.",
                        required=False,
                        type=str)

    args = parser.parse_args()

    try:
        config = Config(**vars(args), tools_path=os.path.join(PROGRAM_DIR, "tools"))
    except ValidationError as err:
        logger.critical(f"Error validating game information:\n{process_errors(error_details=err.errors())}")
        logger.opt(exception=True).debug("Traceback:")
        sys.exit(6)

    logger.remove()
    logger.add(sys.stderr, level=config.log_level)

    if config.log_file is None:
        config.log_file = os.path.join(PROGRAM_DIR, f"apply-steamless_{CURRENT_DATE}.log")

    if logger.level(config.log_level).no > logger.level("WARNING").no:
        logger.add(config.log_file, level="WARNING")
    else:
        logger.add(config.log_file, level=config.log_level)

    logger.add(error_sink, level="ERROR")

    check_python_version()

    if config.package_path is None and config.game_path is None:
        logger.error("Must specify either --package-path or --game-path")
        sys.exit(1)

    if config.package_path is not None and config.game_path is not None:
        logger.error("Only one of --package-path or --game-path can be specified")
        sys.exit(1)

    if config.compress_output:
        if config.compressed_file_name is None or config.compressed_file_name.strip() == "":
            logger.error("Must specify --compressed-file-name")
            sys.exit(1)

    if config.game_path is not None:
        config.output_path = None

    if config.package_path is not None and config.output_path is None:
        logger.error("Must specify --output-path when using --package-path")
        sys.exit(1)

    thread = threading.Thread(target=delete_old_caches,
                              kwargs={
                                  "product_name": "apply-steamless",
                                  "current_version": __version__,
                              },
                              daemon=False,
                              name="cache_deleter")
    thread.start()

    for specified_path in (config.package_path, config.game_path):
        if specified_path is not None:
            specified_path = os.path.abspath(os.path.normpath(specified_path))
            if not os.path.exists(specified_path):
                logger.critical(f"Path \"{specified_path}\" does not exist.")
                sys.exit(1)

    load_data_file()

    start_processing(config=config)


def start_processing(config: Config) -> None:
    logger.info("Starting...")

    sevenzip_path = ensure_sevenzip(tools_path=config.tools_path)

    if sevenzip_path is None:
        logger.critical("Couldn't get 7-zip, aborting...")
        sys.exit(1)

    tmp_dir: str = tempfile.mkdtemp()

    if config.game_path is not None:
        parent_path = config.game_path
        working_path = config.game_path
        executable_list = process_game_dir(game_path=config.game_path)
    elif config.package_path is not None:
        parent_path = tmp_dir
        working_path = config.package_path
        executable_list = process_package_dir(package_path=config.package_path,
                                              output_path=tmp_dir,
                                              sevenzip_path=sevenzip_path,
                                              archive_password=config.archive_password)
    else:
        # We should never get here, but just in case...
        logger.critical("No game path or package path specified.")
        sys.exit(3)

    if len(executable_list) == 0:
        logger.critical(f"Couldn't find any executable for \"{working_path}\"")
        sys.exit(2)

    logger.debug(f"Executables: {executable_list}")

    if not update_steamless(sevenzip_path=sevenzip_path,
                            tools_path=config.tools_path):
        sys.exit(1)

    found_at_least_one_executable: bool = False
    for exe in executable_list:
        if not remove_steamstub(filepath=exe,
                                steamless_path=os.path.join(config.tools_path, "steamless"),
                                parent_path=parent_path):
            if config.package_path is not None:
                logger.info(f"Removing extracted executable: {exe}")
                os.remove(remove_readonly_flag(exe))

                parent_dir = os.path.dirname(exe)
                while parent_dir != tmp_dir:
                    if len(os.listdir(parent_dir)) == 0:
                        logger.debug(f"Removing empty directory: {parent_dir}")
                        shutil.rmtree(parent_dir)
                    else:
                        break

                    parent_dir = os.path.dirname(parent_dir)
        else:
            found_at_least_one_executable = True

    if config.package_path is not None:
        if config.output_path is None:
            # This has already been guarded in main(), we shouldn't normally get here...'
            logger.error("Must specify --output-path when using --package-path")
            sys.exit(1)

        if not found_at_least_one_executable:
            logger.info("No executable found with Steam Stub DRM.")
            logger.debug(f"Removing empty output directory: {tmp_dir}")

            shutil.rmtree(tmp_dir)
            return

        if config.compress_output:
            logger.info("Compressing output...")

            if config.compressed_file_name is None:
                # This has already been guarded in main(), we shouldn't normally get here...
                logger.critical("Must specify --compressed-file-name when compressing output")
                sys.exit(1)

            os.makedirs(config.output_path, exist_ok=True)

            output_filepath = os.path.join(config.output_path, config.compressed_file_name)

            if not output_filepath.lower().endswith(".7z"):
                output_filepath += ".7z"

            if os.path.isfile(output_filepath):
                os.rename(output_filepath, output_filepath + ".bak")

            if compress_directory_content(sevenzip_path=sevenzip_path,
                                          output_path=os.path.join(config.output_path, config.compressed_file_name),
                                          directory_to_compress=tmp_dir):
                try:
                    os.remove(output_filepath + ".bak")
                except FileNotFoundError:
                    pass
            else:
                logger.error(f"Couldn't compress output. Output lives here: {tmp_dir}")

                try:
                    os.remove(output_filepath)
                except FileNotFoundError:
                    pass

                try:
                    os.rename(output_filepath + ".bak", output_filepath)
                except FileNotFoundError:
                    pass
        else:
            logger.info("Moving files to output directory...")
            if os.path.exists(config.output_path):
                for item in os.listdir(tmp_dir):
                    shutil.move(os.path.join(tmp_dir, item), config.output_path)
            else:
                shutil.move(tmp_dir, config.output_path)
    else:
        if not found_at_least_one_executable:
            logger.info("No executable found with Steam Stub DRM.")
            return

    logger.info("Done.")


def process_package_dir(package_path: str,
                        output_path: str,
                        sevenzip_path: str,
                        archive_password: str | None = "") -> list[str]:
    logger.info(f"Processing package directory: {package_path}")

    main_package_file = search_for_package_file(directory=package_path)

    if main_package_file is None:
        logger.critical("No package file found in the specified directory.")
        sys.exit(2)

    package_file_content = list_compressed_file_content(sevenzip_path=sevenzip_path,
                                                        compressed_file_path=main_package_file,
                                                        patterns=["*.exe"],
                                                        archive_password=archive_password)

    logger.debug(f"Package file content: {package_file_content}")

    if package_file_content is None:
        logger.critical("No executables found in the package file.")
        sys.exit(2)

    found_paths = extract_paths_from_7z_listing(sevenzip_output=package_file_content)

    logger.debug(f"Found paths: {found_paths}")

    logger.info("Filtering executables...")

    game_exes: list[str] = []

    for path in found_paths:
        skip: bool = False
        for pattern in EXECUTABLES_TO_IGNORE_PATTERNS:
            if pattern.match(os.path.basename(path)) is not None:
                skip = True
                break

        if skip:
            continue

        game_exes.append(path)

    logger.info("Finished filtering executables.")

    logger.info("Extracting executables...")

    tmp_dir = extract_compressed_file_content(sevenzip_path=sevenzip_path,
                                              compressed_file_path=main_package_file,
                                              file_list=game_exes,
                                              archive_password=archive_password,
                                              output_path=output_path)

    if tmp_dir is None:
        sys.exit(1)

    logger.info("Finished extracting executables.")

    logger.info("Sanitizing output structure...")

    steamapps_common_path = os.path.join(output_path, "steamapps", "common")

    if os.path.exists(steamapps_common_path):
        dir_content = os.listdir(steamapps_common_path)
        for item in dir_content:
            shutil.move(os.path.join(steamapps_common_path, item), output_path)

        shutil.rmtree(os.path.join(output_path, "steamapps"))

        for idx, exe in enumerate(game_exes.copy()):
            exe_split = exe.split(os.path.sep)
            exe_split.pop(0)
            exe_split.pop(0)
            game_exes[idx] = os.path.sep.join(exe_split)

    logger.info("Finished sanitizing output structure.")

    executable_list: list[str] = []

    for exe in game_exes:
        executable_list.append(os.path.join(output_path, os.path.normpath(exe)))

    logger.info("Finished processing package directory.")

    return executable_list


def process_game_dir(game_path: str) -> list[str]:
    logger.info(f"Processing game directory: {game_path}")

    game_items: list[str] = os.listdir(game_path)

    game_sub_dirs: list[str] = []
    game_exes: list[str] = []
    for item in game_items:
        match item.lower():
            case "engine" | "monobleedingedge":
                continue
            case x if x.endswith("_data"):
                continue
            case y:
                if os.path.isfile(os.path.join(game_path, item)):
                    if not y.endswith(".exe"):
                        continue

                    skip: bool = False
                    for pattern in EXECUTABLES_TO_IGNORE_PATTERNS:
                        if pattern.match(item) is not None:
                            skip = True
                            break

                    if skip:
                        continue

        full_path = os.path.join(game_path, item)

        if os.path.isdir(full_path):
            game_sub_dirs.append(full_path)
        else:
            game_exes.append(full_path)

    for sub_dir in game_sub_dirs:
        result = glob.glob(f"**{os.path.sep}*.exe", root_dir=sub_dir, recursive=True, include_hidden=True)

        for exe_path in result:
            skip: bool = False
            for pattern in EXECUTABLES_TO_IGNORE_PATTERNS:
                if pattern.match(os.path.basename(exe_path)) is not None:
                    skip = True
                    break

            if skip:
                continue

            game_exes.append(os.path.join(sub_dir, exe_path))

    logger.info("Finished processing game directory.")

    return game_exes


def update_steamless(sevenzip_path: str,
                     tools_path: str, ) -> bool:
    logger.info("Checking for Steamless...")

    steamless_lock_file: str = os.path.join(tools_path, "steamless.lock")

    if os.path.exists(steamless_lock_file):
        logger.info("Lock file found, waiting for Steamless to be available...")

        while os.path.exists(steamless_lock_file):
            time.sleep(LOCKFILE_WAIT_TIME)

        return True

    check_file: str = os.path.join(tools_path, "last-steamless-check")

    if os.path.exists(check_file):
        with open(check_file, "r", encoding="utf-8") as stream:
            last_time = float(stream.read())

        if time.time() - last_time <= 24 * 60 * 60:
            logger.info("Update check for Steamless has been performed recently (less than 24 hours ago), "
                        "skipping updating it...")

            return True

    try:
        logger.info("Updating Steamless...")

        open(steamless_lock_file, "w").close()

        if os.path.exists(os.path.join(tools_path, "last-steamless-version")):
            with open(os.path.join(tools_path, "last-steamless-version"), "r", encoding="utf-8") as stream:
                current_version = stream.read()
        else:
            current_version = None

        success: bool = get_latest_steamless(sevenzip_path=sevenzip_path,
                                             tools_path=tools_path,
                                             current_version=current_version)

        logger.info("Finished updating Steamless.")

        return success
    finally:
        os.remove(steamless_lock_file)


def download_all_steamless_versions(sevenzip_path: str,
                                    tools_path: str) -> bool:
    response: Response = SESSION.get("https://api.github.com/repos/atom0s/Steamless/releases",
                                     allow_redirects=True)
    response.raise_for_status()

    json_response: list[dict] = response.json()

    at_least_one_downloaded = False
    latest_version_set = False

    for release in json_response:
        if release["prerelease"] or release["draft"]:
            continue

        release_version = release["tag_name"]

        if os.path.exists(os.path.join(tools_path, "steamless", sanitize_name(release_version))):
            at_least_one_downloaded = True
            if not latest_version_set:
                with open(os.path.join(tools_path, "last-steamless-version"), "w", encoding="utf-8") as stream:
                    stream.write(release_version)

                with open(os.path.join(tools_path, "last-steamless-check"), "w", encoding="utf-8") as stream:
                    stream.write(str(time.time()))

                latest_version_set = True
            continue

        logger.info(f"Downloading Steamless {release_version}...")

        if download_steamless(release_data=release, sevenzip_path=sevenzip_path, tools_path=tools_path):
            at_least_one_downloaded = True

            if not latest_version_set:
                with open(os.path.join(tools_path, "last-steamless-version"), "w", encoding="utf-8") as stream:
                    stream.write(release_version)

                with open(os.path.join(tools_path, "last-steamless-check"), "w", encoding="utf-8") as stream:
                    stream.write(str(time.time()))

                latest_version_set = True

    return at_least_one_downloaded


def get_latest_steamless(sevenzip_path: str,
                         tools_path: str,
                         current_version: str | None = None) -> bool:
    if current_version is None:
        logger.info("Downloading Steamless...")
        return download_all_steamless_versions(sevenzip_path=sevenzip_path,
                                               tools_path=tools_path)
    else:
        logger.info("Checking for new version...")

    response: Response = SESSION.get("https://api.github.com/repos/atom0s/Steamless/releases/latest",
                                     allow_redirects=True)
    response.raise_for_status()

    json_response: dict = response.json()

    latest_version = json_response["tag_name"]

    if current_version is not None and latest_version == current_version:
        logger.info("Steamless is already up to date.")

        with open(os.path.join(tools_path, "last-steamless-check"), "w", encoding="utf-8") as stream:
            stream.write(str(time.time()))

        return True

    if download_steamless(release_data=json_response, sevenzip_path=sevenzip_path, tools_path=tools_path):
        with open(os.path.join(tools_path, "last-steamless-version"), "w", encoding="utf-8") as stream:
            stream.write(latest_version)

        with open(os.path.join(tools_path, "last-steamless-check"), "w", encoding="utf-8") as stream:
            stream.write(str(time.time()))

        return True

    return False


def download_steamless(release_data: dict,
                       sevenzip_path: str,
                       tools_path: str) -> bool:
    download_url: str | None = None
    package_extension: str | None = None
    for asset in release_data["assets"]:
        if re.match(r"Steamless\..+[.\-_]by.atom0s.(?:zip|7z)", asset["name"], flags=re.IGNORECASE) is not None:
            download_url = asset["browser_download_url"]
            package_extension = os.path.splitext(str(asset["name"]))[1]
            break

    if download_url is None or package_extension is None:
        logger.error("Couldn't extract the latest download URL from the API response.")
        return False

    release_version = release_data["tag_name"]

    os.makedirs(os.path.join(tools_path, "temp"), exist_ok=True)

    tries = 0
    while True:
        try:
            stream_response: Response = SESSION.get(download_url, allow_redirects=True, stream=True)
            stream_response.raise_for_status()

            break
        except HTTPError as e:
            if e.response.status_code == 404:
                logger.error(f"Failed to download Steamless {release_version} because the file was not found.")
                return False

            tries += 1
            if tries >= 3:
                logger.error(f"Failed to download Steamless {release_version} after 3 attempts.")
                return False
            else:
                logger.warning(f"Failed to download Steamless {release_version}. Retrying ({tries}/3).")
                time.sleep(tries)
                continue

    download_path: str = os.path.join(tools_path, "temp",
                                      sanitize_name(f"Steamless-win_{release_version}{package_extension}"))

    with open(download_path, "wb") as stream:
        for chunk in stream_response.iter_content(4096):
            if chunk is not None:
                stream.write(chunk)

    online_mtime: str | None = stream_response.headers.get("last-modified")
    if online_mtime is not None:
        float_online_mtime = parsedate_to_datetime(online_mtime).timestamp()
        os.utime(download_path, times=(float_online_mtime, float_online_mtime))

    tmp_dir = extract_compressed_file_content(sevenzip_path=sevenzip_path,
                                              compressed_file_path=download_path,
                                              file_list=[],
                                              output_path=os.path.join(tools_path,
                                                                       "temp",
                                                                       "steamless",
                                                                       sanitize_name(release_version)))

    if tmp_dir is None:
        return False

    shutil.move(os.path.join(tools_path, "temp", "steamless", sanitize_name(release_version)),
                os.path.join(tools_path, "steamless", sanitize_name(release_version)))

    os.remove(download_path)

    return True


def remove_steamstub(filepath: str,
                     steamless_path: str,
                     parent_path: str,
                     version_to_use: str = "latest",
                     use_experimental: bool = False) -> bool:
    logger.info(f"Removing Steam Stub from \"{filepath}\"...")

    if version_to_use == "latest":
        version = get_latest_stored_version(path_to_check=steamless_path)
    else:
        version = version_to_use

    cli_path = os.path.join(steamless_path, version, "Steamless.CLI.exe")

    if use_experimental:
        steamless_cmd = [
            cli_path,
            "--quiet",
            "--exp",
            filepath,
        ]
    else:
        steamless_cmd = [
            cli_path,
            "--quiet",
            filepath
        ]

    try:
        subprocess.run(steamless_cmd,
                       check=True,
                       encoding="utf-8",
                       capture_output=True,
                       text=True)
    except subprocess.CalledProcessError as e:
        logger.warning(f"Failed to remove Steam Stub from: \"{os.path.relpath(filepath, parent_path)}\" with "
                       f"Steamless {version}.")
        logger.opt(exception=True).debug("Traceback:")

        if e.returncode != 1:
            previous_version = get_previous_stored_version(path_to_check=steamless_path, version_to_use=version)
            if previous_version is not None:
                logger.info(f"Trying with Steamless version: {previous_version}...")
                return remove_steamstub(filepath=filepath,
                                        steamless_path=steamless_path,
                                        parent_path=parent_path,
                                        version_to_use=previous_version)
        else:
            if "No plugins were loaded; be sure to fully extract Steamless before running!" in e.stderr:
                logger.critical("STEAMLESS: No plugins were loaded; be sure to fully extract Steamless before running!")
                sys.exit(10)
            elif "Invalid input file given; cannot continue." in e.stderr:
                logger.critical("STEAMLESS: Invalid input file given; cannot continue.")
                sys.exit(11)

        return False

    output_file = filepath + ".unpacked.exe"
    original_file = filepath

    os.remove(remove_readonly_flag(original_file))
    os.rename(output_file, original_file)

    logger.info("Finished removing Steam Stub.")

    return True


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.warning("Interrupted by user.")
        sys.exit(1)
    except Exception:
        logger.opt(exception=True).critical("An unexpected error occurred:")
        sys.exit(2)
