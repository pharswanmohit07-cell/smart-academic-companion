# Balanced Multi-Colour UI System Design

**Date:** 2026-11-20  
**Project:** Smart Academic Companion  
**Target branch:** `feat/supabase-auth-render`  
**Status:** Proposed for user review; implementation not started

## 1. Goal

Introduce restrained colour variety across the existing Smart Academic Companion interface so that its modules are easier to distinguish and the product feels polished without looking exaggerated, artificial, or overly decorative.

This is a visual refinement of the existing application, not a page redesign. Preserve the current information architecture, layouts, responsive behaviour, light/dark theme switcher, application workflows, and role/permission rules.

## 2. Design principles

- Keep page backgrounds and most content surfaces neutral.
- Use colour as a functional accent, not as decoration.
- Prefer muted, coordinated shades with sufficient contrast over saturated or neon colours.
- Apply the same semantic colour meaning in light and dark themes, adjusting brightness for readability.
- Keep existing component shapes and spacing; do not introduce oversized pill buttons, glowing effects, gradient-heavy backgrounds, or excessive animation.
- Do not add decorative metrics, fake data, or emoji-based iconography.

## 3. Colour direction

The following values are starting tokens. During implementation, verify contrast and tune nearby shades if needed to maintain accessible text and control contrast.

| Semantic role | Light theme | Dark theme |
|---|---|---|
| Attendance / primary blue | `#315B83` | `#8EAFD0` |
| Classroom Finder / teal | `#287D78` | `#72B9B0` |
| Study Planner / amber | `#B77932` | `#D7A967` |
| Academic Progress / green | `#477B61` | `#83B69A` |
| Faculty tools / muted violet | `#765D9B` | `#AE9ACF` |

Neutral backgrounds, surfaces, borders, primary text, and muted text remain the foundation of both themes. The existing blue remains the main general-purpose action/link colour unless a component has a clear module-specific meaning.

## 4. Application

### Shared design tokens

Extend the existing CSS custom-property system in `templates/base.html` with semantic accent tokens and their subtle surface/background variants for both themes. Keep Bootstrap variable overrides and existing theme initialisation compatible with the current theme switcher.

### Module accents

- Attendance Calculator: blue.
- Empty Classroom Finder: teal.
- Study Planner: amber.
- Academic Progress / risk insights: green.
- Faculty-facing tools and sections: muted violet.

Use these accents sparingly for icon containers, small section labels, chart series, active navigation or tab indicators, and relevant status markers. Do not recolour whole pages or large card surfaces.

### Components

- Cards remain neutral with subtle borders and surfaces.
- Buttons retain their current shape and hierarchy. Primary actions remain consistent; module colours may be used for secondary contextual cues where appropriate.
- Tables and forms retain readable neutral surfaces.
- Charts use the relevant semantic accent and preserve legibility in both themes.
- Status colours must remain distinguishable from module identity colours where their meanings differ (for example, success, warning, and error).

## 5. Scope and non-goals

**In scope**
- CSS colour tokens and theme-specific semantic variants.
- Small, targeted template class additions where needed to apply module accents consistently.
- Visual checks of representative shared, student, and faculty pages in light and dark themes.
- Focused UI tests for token presence and theme/module styling hooks.

**Out of scope**
- Changing business logic, calculations, prediction behaviour, database schema, authentication, roles, or permissions.
- Reworking page layouts, navigation structure, or user journeys.
- Adding new features, charts, metrics, or sample data.
- Replacing the current theme switcher or changing its persistence behaviour.

## 6. Implementation and verification approach

1. Inspect the existing templates and CSS classes before editing; reuse existing component patterns.
2. Add semantic colour tokens to the shared theme system and apply module accents only where the relevant module identity is clear.
3. Keep dark-mode variants coordinated with light mode and check text, borders, focus indicators, and chart contrast.
4. Run the existing UI/theme tests and the relevant full test suite.
5. Inspect the rendered application in both themes at desktop and narrow viewport widths. Confirm that existing navigation, forms, cards, and permissions are unchanged.

## 7. Acceptance criteria

- Light and dark themes both retain neutral, comfortable page backgrounds.
- The five module areas are distinguishable through restrained, consistent accents.
- Colour is concentrated in small semantic elements rather than large saturated blocks.
- Text, controls, borders, focus indicators, and chart labels remain readable in both themes.
- No gradients, neon/glow effects, decorative fake metrics, emoji icons, or oversized pill-shaped controls are introduced.
- Existing functionality, layouts, theme switching, and access controls continue to work.
- Relevant automated tests pass, and both themes receive a manual visual check.

## 8. Risks and mitigations

- **Colour contrast may vary by theme:** verify foreground/background pairs and adjust shades rather than sacrificing readability.
- **Accents may become inconsistent across templates:** define semantic tokens centrally and reuse them instead of hardcoding arbitrary shades.
- **Existing Bootstrap styles may override custom colours:** retain the current CSS variable strategy and scope module styles narrowly.
- **Unintended functional changes:** limit edits to CSS and presentation-level template classes; run existing tests.

---

**Review request:** Please review this design specification. Implementation planning will begin only after you approve the written spec.
