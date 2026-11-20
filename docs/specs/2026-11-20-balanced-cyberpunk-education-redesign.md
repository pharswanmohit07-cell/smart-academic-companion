# Smart Academic Companion — Full UI Redesign Specification

**Direction:** Balanced cyberpunk + vibrant educational platform. **Default:** Light Mode.

## Goals
Deliver a polished, readable education platform with a consistent visual system across landing, authentication, student, faculty, admin, and error pages. Accessibility and text contrast take priority over decorative effects.

## Visual system
- Light theme: clean warm-neutral canvas, white surfaces, dark slate text, electric-blue primary actions, cyan and violet secondary accents, restrained coral highlights, mint success states.
- Dark theme: midnight navy surfaces, high-contrast near-white text, muted slate secondary text, bright but controlled blue/cyan accents.
- Neon colours are reserved for accents, focus rings, and selected states; never use them as low-contrast body text.
- Use clear typography, moderate radii, consistent spacing, restrained shadows, subtle gradients, and no excessive glow.
- Avoid emoji icons, fake metrics, gradient-heavy backgrounds, oversized pill buttons, and unnecessary animation.
- Keep visible keyboard focus, legible placeholders and disabled states, reduced-motion support, and responsive layouts.

## Theme behaviour
Light Mode is the first-visit default. Keep the existing `sac-theme` localStorage key and theme toggle. Respect a saved selection and do not use OS preference to override it.

## Scope
Redesign the landing page, login/signup/password recovery, student dashboard, attendance calculator, classroom finder, study planner, faculty dashboard, faculty class/record management, admin screens, error pages, and shared navigation/settings surfaces.

## Non-regression boundaries
Preserve Flask routes, Jinja form names and actions, CSRF fields, Supabase authentication, roles and permissions, data operations, calculations, C core integrations, database schema, and all existing workflows. No backend or schema changes.

## Verification
Test both themes, readable text and controls, focus visibility, mobile layouts, page rendering, authentication, routes, calculations, and existing Python/C test suites. Work on a feature branch; do not merge or deploy production without approval.
