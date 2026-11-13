# Steam Emu Configurator

This app will create the Steam emulator configuration files automatically. It only needs to know the appid of the game
and a Steam API key if achievements are needed.

Supports both Windows and Linux games.

When using a Linux system, `git` is required to be installed as there is no portable build available.

## Usage

```
usage: steam-emu-configurator.exe [-h] [-v] [--help-advanced] [--appid APPID] [--output-dir OUTPUT_DIR]
                                  [--game-dir GAME_DIR] [--package-dir PACKAGE_DIR] [--api-key API_KEY]
                                  [--preferred-language LANGUAGE] [--do-not-ask] [--include-emulator]
                                  [--rename-package-dir] [--only-rename] [--add-language-flag-on-rename]
                                  [--add-early-access-label] [--custom-early-access-label CUSTOM_EARLY_ACCESS_LABEL]
                                  [--output-dir-is-base] [--archive-password ARCHIVE_PASSWORD] [--use-steam-for-stats]
                                  [--fallback-to-steam] [--fail-if-no-dll] [--compress-config]
                                  [--compressed-filename COMPRESSED_FILENAME] [--skip-achievements] [--skip-stats]
                                  [--update-config-package] [--add-user-config] [--cache-game-info]
                                  [--cache-location CACHE_LOCATION] [--force-achievement-icon-download]
                                  [--copy-cache-back] [--include-dll [INCLUDE_DLL ...]]
                                  [--log-level {TRACE,DEBUG,INFO,SUCCESS,WARNING,ERROR,CRITICAL}]
                                  [--log-file LOG_FILE]

Build Steam emulator configuration

Options:
  -h, --help            show this help message and exit
  -v, --version         show program's version number and exit
  --help-advanced       Show help for the extra arguments.
  --appid APPID         Game's Steam app ID. If not specified it is extracted from the provided directories if
                        possible.
  --output-dir OUTPUT_DIR
                        Where to store the configuration. If not specified it is inferred based on the provided
                        directory.
  --game-dir GAME_DIR   Path to the (extracted/installed) game directory.
  --package-dir PACKAGE_DIR
                        Path to the game package directory. Can either be packaged or unpackaged.
  --api-key API_KEY     Steam API key. Can also be specified with the env var STEAM_API_KEY
  --preferred-language LANGUAGE
                        The preferred language to use to retrieve achievements. Not all are supported, it fallbacks to
                        English.
  --do-not-ask          Don't ask for the Steam app ID when it can't be automatically extracted and simply exit.
  --include-emulator    Include the emulator files in the package.
  --rename-package-dir  Rename package directory to the game's name and release year. E.g. 'The Game (2025)'.
  --only-rename         Do not write anything, only rename.
  --add-language-flag-on-rename
                        On renaming when a language is provided if the game doesn't support said language (nor their
                        fallback) an "[eng]" flag will be appended to the name.
  --add-early-access-label, --add-ea-label
                        Add early access label to the new name if game is early access.
  --custom-early-access-label, --custom-ea-label CUSTOM_EARLY_ACCESS_LABEL
                        Custom early access label to use instead of the default one. (Default: "[Early Access]")
  --output-dir-is-base  Treat the specified output directory as a base for building the output directory.
  --archive-password ARCHIVE_PASSWORD
                        Password to open compressed files.
  --use-steam-for-stats
                        Use Steam for stats (not achievements) retrieval.
  --fallback-to-steam   Fallback to Steam when no stat has been found on the GitHub stats package.
  --fail-if-no-dll      Fail earlier if no DLL/SO file is found. Otherwise only fails if no DLL/SO is found and
                        --include-emulator is used.
  --compress-config     Compress configuration directory using the --compressed-filename specified name
  --compressed-filename COMPRESSED_FILENAME
                        Filename of the resulting compressed file.
  --skip-achievements   Skip downloading and configuring the game's achievements.
  --skip-stats          Skip configuring the game's stats.
  --update-config-package
                        Update compressed configuration package if found. The name is taken from --compressed-filename
                        so it must be supplied.
  --add-user-config     Add user config to setup the language.
  --cache-game-info     Cache the downloaded game info and achievement icon files
  --cache-location CACHE_LOCATION
                        Path where to store the cache
  --force-achievement-icon-download
                        When using --cache-game-info, force download the icon files for the achievements and cache
                        them.
  --copy-cache-back     Copy downloaded icons back to the cache when they exist in the existing config but not in the
                        cache location. This is only useful when updating old configs
  --include-dll [INCLUDE_DLL ...]
                        Include the specified DLL/SO files into the configuration for the emulator to load.
  --log-level {TRACE,DEBUG,INFO,SUCCESS,WARNING,ERROR,CRITICAL}
                        How much stuff is logged.
  --log-file LOG_FILE   Where to store the log file. By default in the program dir.
```

## How it works

First, we need a Steam API key, either by specifying it with `--api-key` or by setting the `STEAM_API_KEY` env var.

The app needs either the `game-dir` or `package-dir` to be specified. Use `game-dir` if the directory contains the
extracted/installed game, and `package-dir` if it contains the packaged (compressed) game files.

The difference between the two is that:

- With `game-dir` we don't even try to extract the build ID (which in fact is not used at the moment), and the only
  method to get the appid is by reading the `steam_appid.txt` file if one exists.
- With `package-dir` we can extract the compressed files and use the manifest files, the `steam_appid.txt` file and the
  compressed filenames to search for the appid and buildid, and we need to differentiate between the two to figure out a
  couple of other things.

We can also specify the appid directly with `--appid` and prevent the app from asking for it with `--do-not-ask`.

If no `--preferred-language` is specified, it uses English. The app falls back to variations of languages if the
preferred one is not found or supported by the game, and then later it falls back to English.

To include the emulator files in the package, use `--include-emulator`.

The package directory (if specified) can be renamed to the game's name and release year with `--rename-package-dir`, and
an early access label can be added with `--add-early-access-label` which can be customized with
`--custom-early-access-label`. In addition to the game's name and release year if the preferred language (or its
fallback if any) is not supported by the game, " [eng]" is appended to the name.

> So an early access game that doesn't support Spanish will be named: `The Game (2025) [eng] [Early Access]`

We can use the app to only rename the directory with `--only-rename` and skip any configuration creation.

If `--output-dir-is-base` is specified, the provided output directory is treated as a base directory for the
configuration files, and we build the correct directory structure; otherwise all the files are placed directly in the
output directory. So if you don't use this option and the game has multiple DLL locations, only one of them will be used
since the output of this app is going directly to the specified output directory.  
This argument has no effect is no output directory is specified.

When using `--package-dir` you can also specify `--archive-password` which can be used to open the compressed files.

We can fall back to Steam for stat retrieval if the game is not found on the GitHub stats package created by nemirtingas
by using `--fallback-to-steam` or directly use it with `--use-steam-for-stats` and skip the GitHub package.

If no Steam DLL/SO file is found, we can fail earlier with `--fail-if-no-dll`, otherwise everything is created normally,
though the game won't even use the emulator, so no need for any configuration.

We can compress the configuration directory with `--compress-config` and specify the name of the resulting compressed
file with `--compressed-filename`. This doesn't work when the output directory is either the `game-dir` or the
`package-dir`. The compressed file will be a 7z file.

We can skip achievements with `--skip-achievements` and stats with `--skip-stats`. If `--update-config-package` is
specified, if a configuration package is found, it will be extracted and its contents updated.

By default, the app doesn't add the user config to the configuration files, we can do it with `--add-user-config`, the
only configuration it will contain is the language.

We can cache the game info and achievement icon files with `--cache-game-info` and change the default store location
with `--cache-location`. We can also force the download of the achievements' icon files with
`--force-achievement-icon-download` to bypass the cached files, this will not refresh the cached data though.

And finally, we can specify the log level and the log file with `--log-level` and `--log-file` respectively.

> [!WARNING]
> The log files are not safe to be shared. They contain the Steam API key in plain text if the log level is set
> to debug.

---

## Specify the emulator configuration

Configuring the emulator is supported by specifying the appropriate arguments.  
You can see which ones are supported by using `--help-advanced`.

You should carefully read the help before using any of the arguments.

Almost all options can be configured with arguments, there are some that are not yet implemented related to the
appearance of the overlay.
