import datetime
import json
import logging
import os
import shutil
import sys
from distutils.version import StrictVersion

import voluptuous as vol

from ledfx.consts import CONFIGURATION_VERSION

CONFIG_DIRECTORY = ".ledfx"
CONFIG_FILE_NAME = "config.json"
PRESETS_FILE_NAME = "presets.json"

PRIVATE_KEY_FILE = "privkey.pem"
CHAIN_KEY_FILE = "fullchain.pem"

_default_wled_settings = {
    "wled_preferred_mode": "UDP",
    "realtime_gamma_enabled": False,
    "force_max_brightness": False,
    "realtime_dmx_mode": "MultiRGB",
    "start_universe_setting": 1,
    "dmx_address_start": 1,
    "inactivity_timeout": 1,
}


# adds the {setting: ..., user: ...} thing to the defaults dict
def parse_default_wled_setting(setting):
    key, value = setting
    return (key, {"setting": value, "user_enabled": False})


# creates validators for the different wled preferences
def wled_validator_generator(data_type):
    return vol.Schema(
        {
            vol.Optional("setting"): data_type,
            vol.Optional("user_enabled"): bool,
        }
    )


# creates the vol.optionals using the above two functions
def wled_optional_generator(setting):
    key, default = setting
    return (
        vol.Optional(key, default=default),
        wled_validator_generator(type(default["setting"])),
    )


# generate the default settings with the setting, user enabled dict thing
_default_wled_settings = dict(
    map(parse_default_wled_setting, _default_wled_settings.items())
)

# generate the config schema to validate changes
WLED_CONFIG_SCHEMA = vol.Schema(
    dict(map(wled_optional_generator, _default_wled_settings.items()))
)

CORE_CONFIG_SCHEMA = vol.Schema(
    {
        vol.Optional("host", default="0.0.0.0"): str,
        vol.Optional("port", default=8888): int,
        vol.Optional("port_s", default=8443): int,
        vol.Optional("dev_mode", default=False): bool,
        vol.Optional("devices", default=[]): list,
        vol.Optional("virtuals", default=[]): list,
        vol.Optional("audio", default={}): dict,
        vol.Optional("melbanks", default={}): dict,
        vol.Optional("ledfx_presets", default={}): dict,
        vol.Optional("user_presets", default={}): dict,
        vol.Optional("scenes", default={}): dict,
        vol.Optional("integrations", default=[]): list,
        vol.Optional("visualisation_fps", default=30): vol.All(
            int, vol.Range(1, 60)
        ),
        vol.Optional("visualisation_maxlen", default=50): vol.All(
            int, vol.Range(5, 300)
        ),
        vol.Optional("scan_on_startup", default=False): bool,
        vol.Optional("wled_preferences", default={}): dict,
        vol.Optional(
            "configuration_version", default=CONFIGURATION_VERSION
        ): str,
    },
    extra=vol.ALLOW_EXTRA,
)


def load_logger():
    global _LOGGER
    _LOGGER = logging.getLogger(__name__)


def get_default_config_directory() -> str:
    """Get the default configuration directory"""

    base_dir = (
        os.getenv("APPDATA") if os.name == "nt" else os.path.expanduser("~")
    )
    return os.path.join(base_dir, CONFIG_DIRECTORY)


def get_config_file(config_dir: str) -> str:
    """Finds a supported configuration file in the provided directory"""

    json_path = os.path.join(config_dir, CONFIG_FILE_NAME)
    if os.path.isfile(json_path) is False:  # Can't find a JSON file
        return None  # No Valid Configs, return None to build another one
    return json_path  # Return the JSON file if we find one.


def get_preset_file(config_dir: str) -> str:
    """Finds a supported preset file in the provided directory"""

    json_path = os.path.join(config_dir, PRESETS_FILE_NAME)
    if os.path.isfile(json_path) is False:  # Can't find a JSON file
        return None  # No Valid Configs, return None to build another one
    return json_path  # Return the JSON file if we find one.


def get_profile_dump_location() -> str:
    config_dir = get_default_config_directory()
    date_time = datetime.datetime.now().strftime("%d-%m-%y_%H-%M-%S")
    return os.path.join(config_dir, f"LedFx_{date_time}.profile")


def get_log_file_location():
    config_dir = get_default_config_directory()
    log_file_path = os.path.abspath(os.path.join(config_dir, "LedFx.log"))
    return log_file_path


def get_ssl_certs() -> tuple:
    """Finds ssl certificate files in config dir"""
    ssl_dir = os.path.join(get_default_config_directory(), "ssl")

    if not os.path.exists(ssl_dir):
        return None

    key_path = os.path.join(ssl_dir, PRIVATE_KEY_FILE)
    chain_path = os.path.join(ssl_dir, CHAIN_KEY_FILE)

    if os.path.isfile(key_path) and os.path.isfile(key_path):
        return (chain_path, key_path)
    return None


def create_default_config(config_dir: str) -> str:
    """Creates a default configuration in the provided directory"""

    config_path = os.path.join(config_dir, CONFIG_FILE_NAME)
    try:
        with open(config_path, "w", encoding="utf-8") as file:
            json.dump(
                CORE_CONFIG_SCHEMA({}),
                file,
                ensure_ascii=False,
                sort_keys=True,
                indent=4,
            )
        return config_path

    except OSError:
        print(f"Unable to create default configuration file {config_path}.")

        return None


def ensure_config_file(config_dir: str) -> str:
    """Checks if a config file exists, and otherwise creates one"""

    ensure_config_directory(config_dir)
    config_path = get_config_file(config_dir)
    if config_path is None:
        config_path = create_default_config(config_dir)

    return config_path


def check_preset_file(config_dir: str) -> str:

    ensure_config_directory(config_dir)
    presets_path = get_preset_file(config_dir)
    if presets_path is None:
        return None

    return presets_path


def ensure_config_directory(config_dir: str) -> None:
    """Validate that the config directory is valid."""

    # If an explicit path is provided simply check if it exist and failfast
    # if it doesn't. Otherwise, if we have the default directory attempt to
    # create the file
    if not os.path.isdir(config_dir):
        if config_dir != get_default_config_directory():
            print(
                ("Error: Invalid configuration directory {}").format(
                    config_dir
                )
            )
            sys.exit(1)

        try:
            os.mkdir(config_dir)
        except OSError:
            print(
                ("Error: Unable to create configuration directory {}").format(
                    config_dir
                )
            )
            sys.exit(1)


def load_config(config_dir: str) -> dict:
    """Validates and loads the configuration file in the provided directory"""

    config_file = ensure_config_file(config_dir)
    print(
        f"Loading configuration file: {os.path.join(config_dir, CONFIG_FILE_NAME)}"
    )
    try:

        with open(config_file, encoding="utf-8") as file:
            config_json = json.load(file)
            try:
                # If there's no config version in the config, it's pre-1.0.0 and won't work
                # Probably scope to iterate through it and create a virtual for every device, but that's beyond me
                _LOGGER.info(
                    f"LedFx Configuration Version: {config_json['configuration_version']}"
                )
                assert StrictVersion(
                    config_json["configuration_version"]
                ) == StrictVersion(CONFIGURATION_VERSION)
                return CORE_CONFIG_SCHEMA(config_json)
            except (KeyError, AssertionError):
                create_backup(config_dir, config_file, "VERSION")
                try:
                    config = migrate_config(config_json)
                except Exception as e:
                    _LOGGER.error(
                        f"Failed to migrate your config to the new standard :( Your old config is backed up safely. Please let a developer know what happened: {e}"
                    )
                    config = {}
                return CORE_CONFIG_SCHEMA(config)
    except json.JSONDecodeError:
        create_backup(config_dir, config_file, "DECODE")
        return CORE_CONFIG_SCHEMA({})
    except OSError:
        create_backup(config_dir, config_file, "OSERROR")
        return CORE_CONFIG_SCHEMA({})


def migrate_config(old_config):
    """
    attempts to update an old config to a working state
    """
    _LOGGER.warning("Attempting to migrate old config to new version...")

    import copy

    new_config = copy.deepcopy(old_config)

    # if not using new config "audio_device", delete audio config
    if not old_config.get("audio", {}).get("audio_device", None):
        new_config.pop("audio", None)

    # remove old transition things
    new_config.pop("crossfade", None)
    new_config.pop("fade", None)

    # update devices
    new_config["devices"] = []
    for device in old_config.get("devices", ()):
        if device["type"].lower() == "fxmatrix":
            _LOGGER.warning(
                "FXMatrix devices are no longer supported. Add it as plain UDP or WLED."
            )
            continue
        device.pop("effect", None)
        new_config["devices"].append(device)

    # if no virtuals saved, create virtuals for all the devices
    from ledfx.utils import generate_id

    if not new_config.get("virtuals", None):
        new_config["virtuals"] = []
        for device in new_config["devices"]:
            # Generate virtual configuration for the device
            name = device["config"]["name"]
            _LOGGER.info(f"Creating a virtual for device {name}")

            virtual_config = {
                "name": name,
                # "icon_name": device_config["icon_name"],
            }
            segments = [
                [device["id"], 0, device["config"]["pixel_count"] - 1, False]
            ]

            new_config["virtuals"].append(
                {
                    "id": generate_id(name),
                    "is_device": device["id"],
                    "config": virtual_config,
                    "segments": segments,
                }
            )

    # initialise some things that will help us match up old effect info to new effect info
    def get_matching_effect_id(effect_id):
        def clean_effect_id(effect_id):
            return effect_id.lower().replace("(reactive)", "").replace("_", "")

        effect_id = clean_effect_id(effect_id)
        for effect_type in effects:
            if effect_type == effect_id:
                return effect_type
        else:
            return None

    def sanitise_effect_config(effect_type, old_config):
        # checks each config key against the current schema, discarding any values that dont match
        schema = effects[effect_type].schema().schema
        new_config = {}
        for key in old_config:
            if key in schema:
                try:
                    schema[key](old_config[key])
                    new_config[key] = old_config[key]
                except vol.MultipleInvalid:
                    _LOGGER.warning(
                        f"Preset for {effect_type} with config item {key} : {old_config[key]} is invalid. Discarding."
                    )
                    continue
            else:
                _LOGGER.warning(
                    f"Preset for {effect_type} no longer has config item {key}. Discarding."
                )
                continue
        return new_config

    class DummyLedfx:
        def dev_enabled(_):
            return False

    import voluptuous as vol

    from ledfx.effects import Effects

    effects = Effects(DummyLedfx()).classes()

    # clean up user presets. effect names have changed, we'll try to clean them up here
    user_presets = new_config.pop(
        "custom_presets", new_config.pop("user_presets", ())
    )
    new_config["user_presets"] = {}
    for effect_id in user_presets:
        new_effect_id = get_matching_effect_id(effect_id)
        if not new_effect_id:
            _LOGGER.warning(
                f"Could not match effect id {effect_id} to any current effects. Discarding presets for this effect."
            )
            continue
        new_config["user_presets"][new_effect_id] = {}
        for preset_id in user_presets[effect_id]:
            new_config["user_presets"][new_effect_id][preset_id] = {
                "name": user_presets[effect_id][preset_id]["name"],
                "config": sanitise_effect_config(
                    new_effect_id, user_presets[effect_id][preset_id]["config"]
                ),
            }

    # clean up scenes
    scenes = new_config.pop("scenes", ())
    new_config["scenes"] = {}
    for scene in scenes:
        devices = scenes[scene].pop("devices", ())
        virtuals = {}
        for device in devices:
            corresponding_virtual = next(
                (virtual["id"] for virtual in new_config["virtuals"]), None
            )
            if not corresponding_virtual:
                _LOGGER.warning(
                    f"Could not match device id {device} to any virtuals. Discarding this device from scene {scene}."
                )
                continue
            effect_id, effect_config = (
                devices[device]["type"],
                devices[device]["config"],
            )
            new_effect_id = get_matching_effect_id(effect_id)
            if not new_effect_id:
                _LOGGER.warning(
                    f"Could not match effect id {effect_id} to any current effects. Discarding this effect from scene {scene}."
                )
                continue
            virtuals[corresponding_virtual] = {
                "config": effect_config,
                "type": new_effect_id,
            }
        scene_config = {"virtuals": virtuals, "name": scenes[scene]["name"]}
        new_config["scenes"][scene] = scene_config

    _LOGGER.info("Finished migrating config.")
    return new_config


def create_backup(config_dir, config_file, errortype):
    """This function creates a backup of the current configuration file - it uses the format dd-mm-yyyy_hh-mm-ss for the backup file.

    Args:
        config_dir (path): The path to the current configuration directory
        config_file (path): The path to the current configuration file
        errortype (string): The type of error we encounter to allow for better logging
    """

    date = datetime.datetime.now().strftime("%d-%m-%y_%H-%M-%S")
    backup_location = os.path.join(config_dir, f"config_backup_{date}.json")
    try:
        os.rename(config_file, backup_location)
    except OSError:
        shutil.copy2(config_file, backup_location)

    if errortype == "DECODE":
        _LOGGER.warning(
            "Error loading configuration. Backup created, empty configuration used."
        )

    if errortype == "VERSION":
        _LOGGER.warning("Incompatible Configuration Detected. Backup Created.")

    if errortype == "OSERROR":
        _LOGGER.warning(
            "Unable to Open Configuration. Backup Created, empty configuration used."
        )

    _LOGGER.warning(f"Backup Located at: {backup_location}")


def save_config(config: dict, config_dir: str) -> None:
    """Saves the configuration to the provided directory"""

    config_file = ensure_config_file(config_dir)
    _LOGGER.info(("Saving configuration file to {}").format(config_dir))
    config["configuration_version"] = CONFIGURATION_VERSION
    config_view = dict(config)
    unneeded_keys = ["ledfx_presets"]
    for key in [key for key in config_view if key in unneeded_keys]:
        del config_view[key]

    with open(config_file, "w", encoding="utf-8") as file:
        json.dump(
            config_view, file, ensure_ascii=False, sort_keys=True, indent=4
        )


def save_presets(config: dict, config_dir: str) -> None:
    """Saves the configuration to the provided directory"""

    presets_file = check_preset_file(config_dir)
    _LOGGER.info(("Saving user presets to {}").format(config_dir))

    config_view = dict(config)
    for key in [key for key in config_view if key != "user_presets"]:
        del config_view[key]

    with open(presets_file, "w", encoding="utf-8") as file:
        json.dump(
            config_view, file, ensure_ascii=False, sort_keys=True, indent=4
        )
