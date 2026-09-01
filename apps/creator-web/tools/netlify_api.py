#!/usr/bin/env python3

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys


_SOURCE = Path(__file__).resolve().parents[2] / "web-runtime-host/tools/netlify_api.py"
_SPEC = importlib.util.spec_from_file_location("_lmdj_netlify_api", _SOURCE)
if _SPEC is None or _SPEC.loader is None:
    raise RuntimeError("shared Netlify API implementation is unavailable")
_MODULE = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _MODULE
_SPEC.loader.exec_module(_MODULE)

DraftDeploy = _MODULE.DraftDeploy
NetlifyClient = _MODULE.NetlifyClient
NetlifyError = _MODULE.NetlifyError
PublishedSite = _MODULE.PublishedSite
