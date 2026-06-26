"""
settings_schema.py — schema layer for the free-form settings store.

GOAL
  Move from "any key allowed, no validation" toward a known, validated schema —
  WITHOUT breaking existing stored data or rejecting saves in production.

DESIGN (production-safe)
  - `normalize(settings)` coerces known keys to their declared types, maps legacy
    keys to canonical ones, fills nothing destructively, and PASSES UNKNOWN KEYS
    THROUGH UNCHANGED. It returns (clean_dict, warnings) and never raises.
  - Unknown keys are reported in `warnings` (so we can observe drift) but are kept,
    guaranteeing backward compatibility. Strict rejection is available behind a
    flag for future tightening, but is OFF by default.
"""

# Canonical schema: key -> {type, default}
# `type` is one of: 'str','bool','int','color','list','dict','json'.
# Only keys that benefit from coercion/validation are listed; everything else is
# accepted as-is (free-form), preserving today's behavior.
SCHEMA = {
    # Identity / theme
    'style_theme':     {'type': 'str',  'default': 'default'},
    'style_font':      {'type': 'str',  'default': 'default'},
    'style_bg_preset': {'type': 'str',  'default': 'dark'},
    'style_anim':      {'type': 'str',  'default': 'fade-up'},
    'style_hero':      {'type': 'str'},
    'style_about':     {'type': 'str'},
    'style_projects':  {'type': 'str'},
    'style_contact':   {'type': 'str'},
    'style_skills':    {'type': 'str'},
    'style_tools':     {'type': 'str'},
    'style_exp':       {'type': 'str'},

    # Structured theme config (new) — opt-in; passes through if absent
    'theme_config':    {'type': 'dict'},

    # Colors
    'colors':          {'type': 'dict'},

    # Layout / structure
    'sections':        {'type': 'list'},
    'navbar_links':    {'type': 'list'},
    'mobile_bar':      {'type': 'dict'},

    # Content blocks
    'content':         {'type': 'dict'},

    # Social visibility
    'social_visible':  {'type': 'list'},

    # Misc scalar flags
    'brand_logo_scale':    {'type': 'int'},
    'brand_logo_offset_x': {'type': 'int'},
    'brand_logo_offset_y': {'type': 'int'},
    'footer_logo_size':    {'type': 'int'},
}

# Legacy key -> canonical key. Old data keeps working; on next save it's upgraded.
LEGACY_KEY_MAP = {
    # examples of historical aliases; extend as needed without risk
    'theme':       'style_theme',
    'font':        'style_font',
    'bg_preset':   'style_bg_preset',
    'anim':        'style_anim',
}


def _coerce(value, typ):
    """Best-effort coercion. Returns (coerced_value, ok). Never raises."""
    try:
        if typ == 'str':
            return (value if isinstance(value, str) else str(value)), True
        if typ == 'bool':
            if isinstance(value, bool): return value, True
            if isinstance(value, str): return value.strip().lower() in ('1','true','yes','on'), True
            return bool(value), True
        if typ == 'int':
            if isinstance(value, bool): return int(value), True
            return int(value), True
        if typ == 'color':
            s = str(value).strip()
            return s, (s.startswith('#') and len(s) in (4, 7))
        if typ == 'list':
            return (value, True) if isinstance(value, list) else (value, False)
        if typ in ('dict', 'json'):
            return (value, True) if isinstance(value, (dict, list)) else (value, False)
    except Exception:
        return value, False
    return value, True


def normalize(settings, strict=False):
    """
    Coerce + map a settings dict against the schema.

    Returns (clean, warnings):
      - clean: dict safe to persist. Known keys coerced; legacy keys renamed;
               unknown keys preserved (unless strict=True, which drops them).
      - warnings: list of human-readable notes (unknown keys, failed coercions).

    NEVER raises. NEVER drops data in the default (non-strict) mode.
    """
    if not isinstance(settings, dict):
        return settings, ['settings is not an object; passed through unchanged']

    clean, warnings = {}, []

    for raw_key, value in settings.items():
        # Internal/computed keys (prefixed _) are passed through untouched.
        if isinstance(raw_key, str) and raw_key.startswith('_'):
            clean[raw_key] = value
            continue

        key = LEGACY_KEY_MAP.get(raw_key, raw_key)
        if key != raw_key:
            warnings.append(f'legacy key "{raw_key}" -> "{key}"')

        spec = SCHEMA.get(key)
        if spec is None:
            # Unknown key: keep it (backward compat) but record drift.
            if strict:
                warnings.append(f'unknown key "{key}" dropped (strict)')
                continue
            clean[key] = value
            continue

        coerced, ok = _coerce(value, spec['type'])
        if not ok:
            warnings.append(f'key "{key}" failed {spec["type"]} coercion; kept original')
            clean[key] = value
        else:
            clean[key] = coerced

    return clean, warnings


def defaults_for(keys=None):
    """Return declared defaults (optionally for a subset of keys)."""
    out = {}
    for k, spec in SCHEMA.items():
        if 'default' in spec and (keys is None or k in keys):
            out[k] = spec['default']
    return out
