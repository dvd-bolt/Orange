---
name: ORANGE Terminal Protocol
colors:
  surface: '#131313'
  surface-dim: '#131313'
  surface-bright: '#393939'
  surface-container-lowest: '#0e0e0e'
  surface-container-low: '#1b1b1b'
  surface-container: '#1f1f1f'
  surface-container-high: '#2a2a2a'
  surface-container-highest: '#353535'
  on-surface: '#e2e2e2'
  on-surface-variant: '#e3bfb1'
  inverse-surface: '#e2e2e2'
  inverse-on-surface: '#303030'
  outline: '#aa8a7d'
  outline-variant: '#5a4136'
  surface-tint: '#ffb596'
  primary: '#ffb596'
  on-primary: '#581e00'
  primary-container: '#ff6600'
  on-primary-container: '#561d00'
  inverse-primary: '#a33e00'
  secondary: '#c6c6c7'
  on-secondary: '#2f3131'
  secondary-container: '#454747'
  on-secondary-container: '#b4b5b5'
  tertiary: '#c8c6c5'
  on-tertiary: '#303030'
  tertiary-container: '#989696'
  on-tertiary-container: '#2f2f2f'
  error: '#ffb4ab'
  on-error: '#690005'
  error-container: '#93000a'
  on-error-container: '#ffdad6'
  primary-fixed: '#ffdbcd'
  primary-fixed-dim: '#ffb596'
  on-primary-fixed: '#360f00'
  on-primary-fixed-variant: '#7c2e00'
  secondary-fixed: '#e2e2e2'
  secondary-fixed-dim: '#c6c6c7'
  on-secondary-fixed: '#1a1c1c'
  on-secondary-fixed-variant: '#454747'
  tertiary-fixed: '#e4e2e1'
  tertiary-fixed-dim: '#c8c6c5'
  on-tertiary-fixed: '#1b1c1c'
  on-tertiary-fixed-variant: '#474746'
  background: '#131313'
  on-background: '#e2e2e2'
  surface-variant: '#353535'
typography:
  headline-lg:
    fontFamily: JetBrains Mono
    fontSize: 32px
    fontWeight: '700'
    lineHeight: 40px
    letterSpacing: -0.02em
  headline-md:
    fontFamily: JetBrains Mono
    fontSize: 24px
    fontWeight: '700'
    lineHeight: 32px
    letterSpacing: -0.01em
  body-lg:
    fontFamily: JetBrains Mono
    fontSize: 16px
    fontWeight: '400'
    lineHeight: 24px
    letterSpacing: 0em
  body-sm:
    fontFamily: JetBrains Mono
    fontSize: 14px
    fontWeight: '400'
    lineHeight: 20px
    letterSpacing: 0em
  label-caps:
    fontFamily: JetBrains Mono
    fontSize: 12px
    fontWeight: '800'
    lineHeight: 16px
    letterSpacing: 0.15em
  label-mono:
    fontFamily: JetBrains Mono
    fontSize: 11px
    fontWeight: '500'
    lineHeight: 14px
    letterSpacing: 0.05em
spacing:
  sidebar-width: 288px
  gutter: 1rem
  margin-page: 2rem
  stack-sm: 0.5rem
  stack-md: 1.5rem
---

## Brand & Style

This design system is built on a "Dry Cyberpunk" aesthetic—stripping away the neon fluff of the genre to focus on raw, high-velocity utility. It evokes the feeling of a high-clearance command line interface used for deep-system AI orchestration. The brand personality is clinical, urgent, and precise.

The style leans heavily into **Brutalism** and **Minimalism**. It rejects soft shadows and gradients in favor of high-contrast line work, rigid grids, and absolute black backgrounds. Every UI element exists to facilitate data density and rapid-fire interaction with the "ORANGE" agent.

## Colors

The palette is strictly functional. 
- **Deep Cyber Black (#000000):** Used for all primary backgrounds to ensure maximum contrast and "void" depth.
- **Pure Stark White (#FFFFFF):** The standard for user-generated content, primary data, and structural borders.
- **Neon Orange (#FF6600):** Reserved exclusively for the agent's output, system alerts, and critical interaction states.
- **Muted Charcoal (#262626):** Used for non-interactive dividers and secondary structural elements to prevent visual clutter.

## Typography

Typography is exclusively monospaced to reinforce the terminal environment. **JetBrains Mono** is utilized for its exceptional legibility in code-heavy or data-dense layouts.

- **Labels:** Use `label-caps` for all headers like `USER_DIRECTIVE` or `SYSTEM_STATUS`. The heavy tracking (letter spacing) is mandatory for these identifiers.
- **Content:** Standard body text uses a 1.5x line height to maintain readability against the high-contrast background.
- **Emphasis:** Do not use italics. Use font-weight increases or color shifts to Orange for emphasis.

## Layout & Spacing

The layout follows a **Fixed-Fluid hybrid** model. The sidebar is a constant 288px anchor on the left, separated by a 1px `Muted Charcoal` border. The main terminal feed is fluid, centered or left-aligned depending on the screen width.

- **Grid:** Use a strict 8px square grid for all internal component spacing.
- **Margins:** 32px (2rem) page margins on desktop.
- **Mobile:** On mobile devices, the sidebar collapses into a top-level drawer, and margins reduce to 16px. Content scales to 100% width.

## Elevation & Depth

This system ignores traditional shadows and Z-axis depth. Hierarchy is established through **Bold Borders** and **Tonal Layering**.

- **Level 0:** Background (#000000).
- **Level 1:** Containers defined by 1px borders.
- **Interactive Depth:** When an element is focused, it does not "rise"; instead, its border weight increases or its background fills with color (inversion).
- **Scanning Lines:** A subtle, static 2px horizontal pattern can be applied to the background to simulate a CRT/Terminal screen, but it must not interfere with text legibility.

## Shapes

Rounded corners are strictly forbidden. All UI elements—buttons, cards, input fields, and containers—must have a **0px radius**. This reinforces the "hard-ware" and "raw data" aesthetic of the terminal.

## Components

### Buttons
- **Default:** Transparent background, 1px `#FF6600` border, `label-caps` text.
- **Hover/Active:** Solid `#FF6600` background, `#000000` text.
- **Layout:** Use square icons (16px) or text.

### Chat Blocks
- **User Block:** 1px `#FFFFFF` border. Header: `USER_DIRECTIVE`.
- **Agent Block (ORANGE):** 1px `#FF6600` border. Header: `AGENT_RESPONSE`.
- **Padding:** All chat blocks have a fixed 16px internal padding.

### Input Fields
- **Terminal Prompt:** Prefixed with a `>` character. No container border except for the bottom edge (`#262626`). 
- **Active State:** Bottom edge turns `#FF6600` with a blinking block cursor.

### Chips/Tags
- Small rectangular boxes with `#262626` borders and `label-mono` text.

### Status Indicators
- **Online:** Solid `#FF6600` square (4px).
- **Processing:** Blinking `#FF6600` square.