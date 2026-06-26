/*
 * theme-engine.js — ViralPX client theme engine (progressive enhancement).
 *
 * WHY
 *   Lets a theme defined ONLY in themes/registry.json render on the live site
 *   without editing the inline THEMES object in index.html. Also applies design
 *   tokens (accent, bg, radius, ...) as CSS variables.
 *
 * SAFETY
 *   - 100% opt-in. If a page never calls these functions, nothing changes.
 *   - All functions are guarded and never throw; on any failure they no-op so
 *     the existing applyStyle() path keeps working.
 *
 * USAGE (in a page that already has a THEMES map + applyStyle):
 *   await VPXTheme.hydrate(S.style_theme, THEMES);  // before applyStyle()
 *   VPXTheme.applyTokens(S.theme_config);            // optional token override
 */
(function (global) {
  'use strict';

  let _registryCache = null;

  async function _getRegistry() {
    if (_registryCache) return _registryCache;
    try {
      const r = await fetch('/api/theme-registry', { cache: 'no-store' });
      _registryCache = await r.json();
    } catch (e) {
      _registryCache = { themes: [], tokens_defaults: {} };
    }
    return _registryCache;
  }

  /**
   * If `themeId` is missing from the page's inline `themesMap`, fetch its
   * legacy style_* mapping from the registry and inject it, so the existing
   * renderer understands a JSON-only theme. Returns true if hydrated.
   */
  async function hydrate(themeId, themesMap) {
    try {
      if (!themeId || !themesMap) return false;
      if (themesMap[themeId]) return false; // already known inline → no-op
      const r = await fetch('/api/theme-registry/' + encodeURIComponent(themeId) + '/legacy', { cache: 'no-store' });
      const legacy = await r.json();
      if (legacy && typeof legacy === 'object') {
        // Strip helper hints (prefixed _) into accent application
        const map = {};
        Object.keys(legacy).forEach(k => { if (!k.startsWith('_')) map[k] = legacy[k]; });
        themesMap[themeId] = map;
        if (legacy._accent_hint) map.accent = legacy._accent_hint;
        return true;
      }
    } catch (e) { /* no-op */ }
    return false;
  }

  /**
   * Apply structured design tokens as CSS variables on :root.
   * `tokens` example: { accent:'#000', bg:'#0a0a0a', radius:'12px' }
   */
  function applyTokens(tokens) {
    try {
      if (!tokens || typeof tokens !== 'object') return;
      const root = document.documentElement.style;
      const M = {
        accent: '--accent', accent2: '--accent2', bg: '--bg', bg2: '--bg2',
        text: '--text', subtext: '--sub', radius: '--radius',
        radius_sm: '--radius-sm', radius_lg: '--radius-lg', space: '--space'
      };
      Object.keys(M).forEach(k => { if (tokens[k]) root.setProperty(M[k], tokens[k]); });
      // RGB companions for accent/bg (used by rgba() in existing CSS)
      const toRGB = (hex) => {
        const m = String(hex).replace('#', '').match(/^([0-9a-f]{6}|[0-9a-f]{3})$/i);
        if (!m) return '';
        let h = m[1]; if (h.length === 3) h = h.split('').map(c => c + c).join('');
        return parseInt(h.slice(0, 2), 16) + ', ' + parseInt(h.slice(2, 4), 16) + ', ' + parseInt(h.slice(4, 6), 16);
      };
      if (tokens.accent) { const v = toRGB(tokens.accent); if (v) root.setProperty('--accent-rgb', v); }
      if (tokens.bg) { const v = toRGB(tokens.bg); if (v) root.setProperty('--bg-rgb', v); }
    } catch (e) { /* no-op */ }
  }

  async function getTheme(themeId) {
    const reg = await _getRegistry();
    return (reg.themes || []).find(t => t && t.id === themeId) || null;
  }

  global.VPXTheme = { hydrate, applyTokens, getTheme, _getRegistry };
})(window);
