"""
theme_engine.py — ViralPX structured theme registry loader.

PURPOSE
  Externalize theme definitions out of the frontend (index.html) into a JSON
  registry so a NEW THEME can be added by editing `themes/registry.json` only —
  zero core-code changes.

SAFETY / BACKWARD COMPAT
  - This module is purely additive. Nothing imports it by force; the server
    exposes it via a new read-only endpoint. If the registry file is missing or
    malformed, callers get an empty-but-valid structure and the existing inline
    THEMES in index.html continue to work unchanged.
  - Loaded once and cached by file mtime (same pattern as _load_html).
"""

import os, json, threading

_REGISTRY_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'themes', 'registry.json')
_cache = {'mtime': None, 'data': None}
_lock = threading.Lock()

# Minimal valid fallback if the file is missing/corrupt — keeps the API contract stable.
_EMPTY = {
    '_meta': {'version': 1},
    'tokens_defaults': {},
    'component_variants': {},
    'layout_presets': {},
    'themes': [],
}


def _load_raw():
    """Read + parse the registry file with mtime caching. Never raises."""
    try:
        mtime = os.path.getmtime(_REGISTRY_PATH)
    except OSError:
        return _EMPTY
    with _lock:
        if _cache['mtime'] == mtime and _cache['data'] is not None:
            return _cache['data']
        try:
            with open(_REGISTRY_PATH, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if not isinstance(data, dict) or 'themes' not in data:
                data = _EMPTY
        except Exception as e:
            print(f'[theme_engine] registry load error: {e}')
            data = _EMPTY
        _cache['mtime'] = mtime
        _cache['data'] = data
        return data


def get_registry():
    """Full registry dict (meta + defaults + variants + presets + themes)."""
    return _load_raw()


def list_themes():
    """Lightweight list of {id, name} for pickers in the dashboard."""
    reg = _load_raw()
    return [{'id': t.get('id'), 'name': t.get('name', {})}
            for t in reg.get('themes', []) if isinstance(t, dict) and t.get('id')]


def get_theme(theme_id):
    """Return a single theme config by id, or None."""
    if not theme_id:
        return None
    for t in _load_raw().get('themes', []):
        if isinstance(t, dict) and t.get('id') == theme_id:
            return t
    return None


def theme_to_legacy_settings(theme_id):
    """
    Translate a structured theme into the existing style_* settings the current
    renderer already understands. This is the bridge that lets a JSON-only theme
    drive the live engine WITHOUT touching index.html.

    Returns a dict of style_* keys (possibly empty). Never raises.
    """
    t = get_theme(theme_id)
    if not t:
        return {}
    out = dict(t.get('legacy_map') or {})
    # Tokens that map to the existing `colors` override path
    tokens = t.get('tokens') or {}
    if tokens.get('accent'):
        out.setdefault('_accent_hint', tokens['accent'])
    return out
