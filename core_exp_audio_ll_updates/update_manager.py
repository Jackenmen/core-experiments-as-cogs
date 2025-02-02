import dataclasses
import enum
import functools
import types
from copy import deepcopy
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple, Union

import aiohttp
from typing_extensions import Self, TypeAlias
from packaging.specifiers import InvalidSpecifier, SpecifierSet
from packaging.version import Version


_RELEASES_URL = "https://cog-creators.github.io/Lavalink-Jars/index.0.json"


def _deep_merge(destination: Dict[str, Any], source: Dict[str, Any]) -> None:
    for key in source:
        if (
            key in destination
            and isinstance(destination[key], dict)
            and isinstance(source[key], dict)
        ):
            _deep_merge(destination[key], source[key])
            continue

        destination[key] = deepcopy(source[key])


def _get_and_validate_key(data: Dict[str, Any], key: str, value_type: TypeAlias) -> Any:
    """
    Get `key` from `data` dictionary and validate the value's type matches `value_type`.

    Matches following classes of type expressions:
    - type (e.g. `int` or `str`)
    - typing.Union[type1, type2] (e.g. `typing.Union[int, str]`)
    - typing.List[type] (e.g. `typing.List[str]`)
    - typing.List[typing.Union[type1, type2]] (e.g. `typing.List[typing.Union[int, str]]`)

    Raises
    ------
    KeyError
        When `key` is not in `data`.
    """
    value = data[key]
    if value_type is Any:
        return value

    origin = getattr(value_type, "__origin__", value_type)
    if origin is Union:
        types = value_type.__args__
    else:
        types = (origin,)

    if not isinstance(value, types):
        raise TypeError(f"expected {types} under {key!r} key, got {type(value)} instead")

    if origin is List:
        type_args = getattr(value_type, "__args__", ())
        if not type_args:
            return value

        origin = getattr(type_args[0], "__origin__", type_args[0])
        if origin is Union:
            types = value_type.__args__
        else:
            types = (origin,)

        if not all(isinstance(item, types) for item in value):
            raise TypeError(
                f"expected items under {key!r} key to be of type {types},"
                f" got {type(value)} instead"
            )

    return value


def _generate_ll_version_line(raw_version: str) -> bytes:
    return b"Version: " + raw_version.encode()


class ReleaseStream(enum.Enum):
    STABLE = "stable"
    PREVIEW = "preview"


@dataclasses.dataclass()
class ReleaseInfo:
    release_name: str
    jar_version: str
    jar_url: str
    yt_plugin_version: str
    java_versions: Tuple[int, ...]
    red_version: SpecifierSet
    release_stream: ReleaseStream
    application_yml_overrides: Dict[str, Any] = dataclasses.field(default_factory=dict)

    @classmethod
    def from_json_dict(cls, data: Dict[str, Any]) -> Self:
        raw_release_stream = _get_and_validate_key(data, "release_stream", str)
        try:
            release_stream = ReleaseStream(raw_release_stream)
        except InvalidSpecifier as exc:
            raise TypeError(
                "expected a valid release stream under 'release_stream' key,"
                f" got {raw_release_stream!r} instead"
            ) from exc

        raw_red_version = _get_and_validate_key(data, "red_version", str)
        try:
            red_version = SpecifierSet(raw_red_version)
        except InvalidSpecifier as exc:
            raise TypeError(
                "expected a specifier set under 'red_version' key,"
                f" got {raw_red_version!r} instead"
            ) from exc

        raw_jar_version = _get_and_validate_key(data, "jar_version", str)

        return cls(
            release_name=_get_and_validate_key(data, "release_name", str),
            jar_version=raw_jar_version,
            jar_url=_get_and_validate_key(data, "jar_url", str),
            yt_plugin_version=_get_and_validate_key(data, "yt_plugin_version", str),
            java_versions=tuple(_get_and_validate_key(data, "java_versions", List[int])),
            red_version=red_version,
            release_stream=release_stream,
            application_yml_overrides=_get_and_validate_key(
                data, "application_yml_overrides", Dict[str, Any]
            ),
        )

    def as_json_dict(self) -> Dict[str, Any]:
        return {
            "release_name": self.release_name,
            "jar_version": self.jar_version,
            "jar_url": self.jar_url,
            "yt_plugin_version": self.yt_plugin_version,
            "java_versions": list(self.java_versions),
            "red_version": str(self.red_version),
            "release_stream": self.release_stream.value,
            "application_yml_overrides": self.application_yml_overrides,
        }


class ReleaseIndex:
    def __init__(self, releases: Iterable[ReleaseInfo]) -> None:
        self.releases = [release for release in releases]

    @classmethod
    def from_json_array(cls, data: List[Dict[str, Any]]) -> Self:
        return cls(ReleaseInfo.from_json_dict(release_data) for release_data in data)

    def get_latest_release(
        self, release_stream: ReleaseStream, *, red_version: Optional[Version] = None
    ) -> ReleaseInfo:
        streams: tuple[ReleaseStream, ...] = (release_stream,)
        if release_stream is ReleaseStream.PREVIEW:
            streams += (ReleaseStream.STABLE,)

        for release in self.releases:
            if release.release_stream not in streams:
                continue
            if red_version is not None and not release.red_version.contains(
                red_version, prereleases=True
            ):
                continue
            return release

        raise ValueError("could not find any release matching the given conditions")


class UpdateManager:
    def __init__(self, release_info: Optional[ReleaseInfo]) -> None:
        self._session = aiohttp.ClientSession()
        self.release_info = release_info

    async def close(self) -> None:
        await self._session.close()

    async def fetch_release_index(self) -> ReleaseIndex:
        async with self._session.get(_RELEASES_URL) as resp:
            data = await resp.json()

        return ReleaseIndex.from_json_array(data)

    def update_manager(self, module: types.ModuleType) -> None:
        if self.release_info is None:
            return
        module.ServerManager.LAVALINK_DOWNLOAD_URL = self.release_info.jar_url

    def update_ll_server_config(self, module: types.ModuleType) -> None:
        if self.release_info is None:
            return
        orig_func = module.generate_server_config
        if getattr(orig_func, "func", None) is _generate_server_config:
            return

        @functools.wraps(orig_func)
        def generate_server_config(config_data: Dict[str, Any]) -> Dict[str, Any]:
            return _generate_server_config(orig_func, self, config_data)

        generate_server_config.func = _generate_server_config
        module.generate_server_config = generate_server_config

    def update_version_pins(self, module: types.ModuleType) -> None:
        if self.release_info is None:
            return
        module.JAR_VERSION = module.LavalinkVersion.from_version_output(
            _generate_ll_version_line(self.release_info.jar_version)
        )
        module.YT_PLUGIN_VERSION = self.release_info.yt_plugin_version
        java_versions = self.release_info.java_versions
        module.SUPPORTED_JAVA_VERSIONS = java_versions
        module.LATEST_SUPPORTED_JAVA_VERSION = java_versions[-1]
        module.OLDER_SUPPORTED_JAVA_VERSIONS = java_versions[:-1]


def _generate_server_config(
    orig_func: Callable[[Dict[str, Any]], Dict[str, Any]],
    update_manager: UpdateManager,
    config_data: Dict[str, Any],
) -> Dict[str, Any]:
    data = orig_func(config_data)
    release_info = update_manager.release_info
    if release_info is not None:
        _deep_merge(data, release_info.application_yml_overrides)
        _deep_merge(data, config_data)
    return data
