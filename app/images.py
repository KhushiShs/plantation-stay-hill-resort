import json
from pathlib import Path
from typing import Dict, Any, Optional

MANIFEST_PATH = Path("app/static/img/manifest.json")
_MANIFEST: Optional[Dict[str, Any]] = None


def load_manifest() -> Dict[str, Any]:
    global _MANIFEST
    if _MANIFEST is None:
        if MANIFEST_PATH.exists():
            with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
                _MANIFEST = json.load(f)
        else:
            _MANIFEST = {}
    return _MANIFEST


def get_image_info(image_key: str) -> Dict[str, Any]:
    manifest = load_manifest()
    return manifest.get(image_key, {})

