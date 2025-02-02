import copy
import importlib.util
import sys
import types
from importlib.abc import Loader, MetaPathFinder
from importlib.machinery import ModuleSpec
from typing import Optional

from .update_manager import UpdateManager


_AUDIO_MOD_NAME = "redbot.cogs.audio"
_AUDIO_MANAGER_MOD_NAME = f"{_AUDIO_MOD_NAME}.manager"
_AUDIO_MANAGED_NODE_MOD_NAME = f"{_AUDIO_MOD_NAME}.managed_node"
_AUDIO_LL_SERVER_CONFIG_MOD_NAME = f"{_AUDIO_MANAGED_NODE_MOD_NAME}.ll_server_config"
_AUDIO_VERSION_PINS_MOD_NAME = f"{_AUDIO_MANAGED_NODE_MOD_NAME}.version_pins"
_AUDIO_AFFECTED_MODULES = (
    _AUDIO_MANAGER_MOD_NAME,
    _AUDIO_LL_SERVER_CONFIG_MOD_NAME,
    _AUDIO_VERSION_PINS_MOD_NAME,
)


class CoreExpAudioLavalinkUpdatesLoader(Loader):
    def __init__(self, update_manager: UpdateManager, /) -> None:
        self._update_manager = update_manager

    def create_module(self, spec: ModuleSpec) -> Optional[types.ModuleType]:
        actual_spec, _ = spec.loader_state
        return actual_spec.loader.create_module(actual_spec)

    def exec_module(self, module: types.ModuleType) -> None:
        actual_spec = module.__spec__
        if actual_spec.loader is self:
            actual_spec, _ = actual_spec.loader_state
        actual_spec.loader.exec_module(module)

        if actual_spec.name == _AUDIO_MANAGER_MOD_NAME:
            self._update_manager.update_manager(module)
        elif actual_spec.name == _AUDIO_LL_SERVER_CONFIG_MOD_NAME:
            self._update_manager.update_ll_server_config(module)
        elif actual_spec.name == _AUDIO_VERSION_PINS_MOD_NAME:
            self._update_manager.update_version_pins(module)


class CoreExpAudioLavalinkUpdatesFinder(MetaPathFinder):
    def __init__(self, update_manager: UpdateManager, /) -> None:
        self._update_manager = update_manager

    def find_spec(self, fullname, path, target=None) -> Optional[ModuleSpec]:
        """This is only supposed to print warnings, it won't ever return module spec."""
        if fullname not in _AUDIO_AFFECTED_MODULES:
            return None

        idx = sys.meta_path.index(self)
        sys.meta_path.pop(idx)
        actual_spec = importlib.util.find_spec(fullname)
        sys.meta_path.insert(idx, self)
        if actual_spec is None:
            return None

        spec = copy.copy(actual_spec)
        spec.loader = CoreExpAudioLavalinkUpdatesLoader(self._update_manager)
        spec.loader_state = (actual_spec, spec.loader_state)

        return spec
