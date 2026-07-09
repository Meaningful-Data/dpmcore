"""Thin Arelle adapter for loading taxonomy DTSes.

Everything Arelle-specific that is not reading model content lives
here: lazy imports (so dpmcore works without the ``xbrl`` extra),
web-cache and offline wiring, and error surfacing. The readers
receive a loaded ``ModelXbrl`` and never touch the controller.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, List, Optional

from dpmcore.loaders.xbrl.model import XbrlImportError

_INSTALL_HINT = (
    "Arelle is required for XBRL taxonomy imports. "
    "Install it with: pip install dpmcore[xbrl]"
)


class ArelleEngine:
    """Load taxonomy entry points through an Arelle controller.

    Args:
        offline: Refuse web access; unresolved remote references
            become import errors instead of downloads.
        cache_dir: Directory used as the Arelle web cache. Remote
            schemas already present there are served locally, which
            (with *offline*) enables fully offline imports.
    """

    def __init__(
        self,
        *,
        offline: bool = False,
        cache_dir: Optional[Path] = None,
    ) -> None:
        """Initialise the adapter; the controller starts lazily."""
        self._offline = offline
        self._cache_dir = cache_dir
        self._cntlr: Optional[Any] = None

    def _controller(self) -> Any:
        if self._cntlr is not None:
            return self._cntlr
        try:
            from arelle import Cntlr
        except ImportError as exc:  # pragma: no cover - env specific
            raise XbrlImportError(_INSTALL_HINT) from exc

        cntlr = Cntlr.Cntlr(logFileName="logToBuffer")
        if self._cache_dir is not None:
            cntlr.webCache.cacheDir = str(self._cache_dir)
        cntlr.webCache.workOffline = self._offline
        self._cntlr = cntlr
        return cntlr

    def load(self, entry_path: Path) -> Any:
        """Load the DTS rooted at *entry_path*.

        Args:
            entry_path: Filesystem path of the entry ``.xsd``.

        Returns:
            The loaded Arelle ``ModelXbrl``.

        Raises:
            XbrlImportError: If the entry point does not exist or
                the DTS cannot be resolved.
        """
        path = Path(entry_path)
        if not path.is_file():
            raise XbrlImportError(
                f"Entry point '{path}' does not exist."
            )
        cntlr = self._controller()
        model_xbrl = cntlr.modelManager.load(str(path))
        errors: List[str] = list(model_xbrl.errors)
        if errors:
            model_xbrl.close()
            hint = ""
            if any("IOerror" in error for error in errors):
                hint = (
                    " Remote DTS references could not be resolved; "
                    "retry online or pass a pre-seeded --cache-dir."
                )
            raise XbrlImportError(
                f"Arelle could not load '{path.name}': "
                f"{', '.join(errors[:10])}.{hint}"
            )
        return model_xbrl

    def close(self) -> None:
        """Release the controller and any loaded models."""
        if self._cntlr is not None:
            self._cntlr.modelManager.close()
            self._cntlr = None
