"""Shared emulator fixtures for the live synth regression tests."""
import unicorn

# These services are substituted only at their exact call addresses so the
# installed audio and native envelope code still execute in the emulator.
_hook_add = unicorn.Uc.hook_add


def _service_hooks(self, kind, callback, *args, **kwargs):
    if kind == unicorn.UC_HOOK_CODE and not args and not kwargs:
        name = getattr(callback, "__qualname__", "")
        if name == "Kick.extra":
            handle = None
            for address in (0x081be010, 0x081be020, 0x08092d00):
                handle = _hook_add(self, kind, callback, begin=address, end=address)
            return handle
        if name == "AudioProbe.__init__.<locals>.<lambda>":
            address = callback.__closure__[0].cell_contents.stop
            return _hook_add(self, kind, callback, begin=address, end=address)
    return _hook_add(self, kind, callback, *args, **kwargs)


unicorn.Uc.hook_add = _service_hooks

from test_engines import engine, run, SYMS, _k16, Synth  # noqa: E402

_KEEP = []
_synth_init = Synth.__init__


def _retain_synth(self, **kwargs):
    _synth_init(self, **kwargs)
    _KEEP.append(self)


Synth.__init__ = _retain_synth
_ui_init = _k16.UI.__init__


def _retain_ui(self):
    _ui_init(self)
    _KEEP.append(self)


_k16.UI.__init__ = _retain_ui
