---
name: Obsidian Kinetic
colors:
  surface: '#131316'
  surface-dim: '#131316'
  surface-bright: '#39393c'
  surface-container-lowest: '#0e0e11'
  surface-container-low: '#1b1b1e'
  surface-container: '#1f1f22'
  surface-container-high: '#2a2a2d'
  surface-container-highest: '#353438'
  on-surface: '#e4e1e6'
  on-surface-variant: '#c2c6d6'
  inverse-surface: '#e4e1e6'
  inverse-on-surface: '#303033'
  outline: '#8c909f'
  outline-variant: '#424754'
  surface-tint: '#adc6ff'
  primary: '#adc6ff'
  on-primary: '#002e6a'
  primary-container: '#4d8eff'
  on-primary-container: '#00285d'
  inverse-primary: '#005ac2'
  secondary: '#c0c1ff'
  on-secondary: '#1000a9'
  secondary-container: '#3131c0'
  on-secondary-container: '#b0b2ff'
  tertiary: '#ffb786'
  on-tertiary: '#502400'
  tertiary-container: '#df7412'
  on-tertiary-container: '#461f00'
  error: '#ffb4ab'
  on-error: '#690005'
  error-container: '#93000a'
  on-error-container: '#ffdad6'
  primary-fixed: '#d8e2ff'
  primary-fixed-dim: '#adc6ff'
  on-primary-fixed: '#001a42'
  on-primary-fixed-variant: '#004395'
  secondary-fixed: '#e1e0ff'
  secondary-fixed-dim: '#c0c1ff'
  on-secondary-fixed: '#07006c'
  on-secondary-fixed-variant: '#2f2ebe'
  tertiary-fixed: '#ffdcc6'
  tertiary-fixed-dim: '#ffb786'
  on-tertiary-fixed: '#311400'
  on-tertiary-fixed-variant: '#723600'
  background: '#131316'
  on-background: '#e4e1e6'
  surface-variant: '#353438'
typography:
  headline-xl:
    fontFamily: Geist
    fontSize: 36px
    fontWeight: '600'
    lineHeight: 44px
    letterSpacing: -0.03em
  headline-xl-mobile:
    fontFamily: Geist
    fontSize: 28px
    fontWeight: '600'
    lineHeight: 34px
    letterSpacing: -0.025em
  headline-lg:
    fontFamily: Geist
    fontSize: 24px
    fontWeight: '600'
    lineHeight: 32px
    letterSpacing: -0.02em
  headline-lg-mobile:
    fontFamily: Geist
    fontSize: 20px
    fontWeight: '600'
    lineHeight: 28px
    letterSpacing: -0.02em
  headline-md:
    fontFamily: Geist
    fontSize: 18px
    fontWeight: '500'
    lineHeight: 26px
    letterSpacing: -0.015em
  body-lg:
    fontFamily: Geist
    fontSize: 15px
    fontWeight: '400'
    lineHeight: 24px
    letterSpacing: -0.01em
  body-md:
    fontFamily: Geist
    fontSize: 13px
    fontWeight: '400'
    lineHeight: 20px
    letterSpacing: -0.005em
  body-sm:
    fontFamily: Geist
    fontSize: 12px
    fontWeight: '400'
    lineHeight: 18px
    letterSpacing: 0em
  label-md:
    fontFamily: JetBrains Mono
    fontSize: 12px
    fontWeight: '500'
    lineHeight: 16px
    letterSpacing: 0.02em
  label-sm:
    fontFamily: JetBrains Mono
    fontSize: 11px
    fontWeight: '400'
    lineHeight: 14px
    letterSpacing: 0.04em
  code-inline:
    fontFamily: JetBrains Mono
    fontSize: 12px
    fontWeight: '400'
    lineHeight: 18px
    letterSpacing: 0em
rounded:
  sm: 0.125rem
  DEFAULT: 0.25rem
  md: 0.375rem
  lg: 0.5rem
  xl: 0.75rem
  full: 9999px
spacing:
  gutter: 1rem
  margin: 1.5rem
  space-xs: 0.25rem
  space-sm: 0.5rem
  space-md: 0.75rem
  space-lg: 1.25rem
  space-xl: 2rem
---

## Brand & Style

This design system embodies high-velocity computational intelligence, crafted for technical builders, researchers, and power users who expect desktop-class responsiveness and frictionless execution. Drawing inspiration from modern utilitarian mastery—specifically Linear’s hyper-structured clarity, Raycast’s keyboard-first agility, and Perplexity’s ambient citation density—the aesthetic rejects unnecessary decorative churn in favor of calibrated precision.

### Design Movements & Philosophy
- **Dark-Surface Technical Utility:** Deep, light-absorbing obsidian backdrops prioritize ocular comfort during extended focus sessions, framing generative streams, code, and source topologies with surgical contrast.
- **Micro-Luminescent Accents:** High-energy electric blue and deep indigo signals are treated as focused lasers rather than wash floods. They communicate state changes, AI reasoning trajectories, token generation pulses, and active selection states.
- **Keyboard-First Ergonomics:** Dense information architecture, minimal visual noise, and spatial predictability enable high-speed mental flow.

## Colors

The palette is engineered around pure value-layered zinc and slate carbons, avoiding muddy browns or oversaturated chromatic darks.

### Core Architecture
- **Canvas Base (`#09090b`):** The primary view-space background; an ultra-deep void that absorbs ambient light and maximizes typographic legibility.
- **Surface Level 1 (`#121215`):** Sidebars, utility trays, docked prompts, and modal backdrops.
- **Surface Level 2 (`#18181b`):** Cards, elevated menu overlays, source chips, and interactive workspace blocks.
- **Surface Level 3 / Hover (`#222227`):** Transient active hover states, table headers, and focused list nodes.

### Structural Contours
- **Subtle Hairline (`#27272a`):** Standard 1px perimeter border across cards, split panels, and persistent chrome.
- **Interactive Hairline (`#3f3f46`):** Focused states, active tabs, and hovering boundaries.

### Accents & Micro-Glow
- **Electric Blue (`#3b82f6`):** Primary command anchor, streaming telemetry cursors, and definitive affirmative actions.
- **Indigo Glow (`#6366f1`):** AI synthesis indicators, contextual suggestions, multi-source ingestion highlights, and keyboard-command triggers.

## Typography

Typography relies on geometric balance and mono-spaced utility to construct an uncompromising developer-grade environment.

### Typographic Hierarchy Rules
- **Geist (Headlines & Body):** Employs tight optical letter-spacing (`-0.01em` to `-0.03em`) on larger scale headings to yield an authoritative editorial stance, while remaining razor-sharp at compact 13px base body sizing for dense analytical summaries.
- **JetBrains Mono (Telemetry, Metadata & Shortcuts):** Reserved exclusively for structural data points: latency metrics, source token counts, keyboard hotkeys (`⌘K`), schema tags, and code viewports.
- **Vertical Flow:** Paragraph spacing must consistently match line-height intervals to maintain strict rhythmic vertical alignment across dual-pane code and chat flows.

## Layout & Spacing

This design system uses a flexible, pane-based layout model engineered around modular, resizable workspaces.

### Panel & Screen Composition
- **Desktop (>= 1280px):** 3-tier dock architecture. Persistent narrow utility rail (48px), dynamic collapsable workspace navigation tree (240px fixed), primary streaming reasoning canvas (flexible fluid width with 768px maximum reading bounds), and an optional collapsible contextual inspector (360px fixed) for source verification and quiz engines.
- **Tablet (768px - 1279px):** Collapsible off-canvas navigation drawer, full-width chat and workspace canvas, overlay slide-over for sources.
- **Mobile (< 768px):** Strict single-column stack. Bottom-pinned compact command bar dock, vertical modal sheets for source inspections and file attachments.

### Internal Spacing Cadence
Density is tight and intentional. Elements utilize a base-4 spatial matrix where `0.25rem` (4px) and `0.5rem` (8px) govern the interior grouping of pills, icons, and labels, while `0.75rem` (12px) to `1.25rem` (20px) define modular component encapsulation.

## Elevation & Depth

Depth is established strictly through tonal layering and low-contrast borders rather than diffuse drop shadows.

### The Tier Hierarchy
- **Base Canvas (`#09090b`):** Recessed ground plane, completely flat.
- **Panel Surface (`#121215`):** Offset using a precise border: `1px solid #27272a`.
- **Floating Overlays & Docks (`#18181b`):** 
  - Rim lighting: `1px solid #3f3f46`.
  - Ambient base shadow: `0 8px 32px -4px rgba(0, 0, 0, 0.7)`.
  - Subtle top-edge inner highlight: `inset 0 1px 0 0 rgba(255, 255, 255, 0.06)`.

### Micro-Glow Telemetry
When an element enters an active generative or focused state:
- **Interactive AI Prompt Glow:** `0 0 0 1px #3b82f6, 0 0 20px -2px rgba(59, 130, 246, 0.25)`.
- **Streaming Indicator Pulse:** An un-blurred core surrounded by `box-shadow: 0 0 12px 1px rgba(99, 102, 241, 0.4)`.

## Shapes

The geometric framework favors controlled, disciplined corners that suggest structural rigor.

- **Base Radius (`0.25rem` / 4px):** Applied to inline code badges, keyboard hotkey indicators (`KBD`), small source badges, and context menu items.
- **Component Radius (`0.5rem` / 8px):** Applied to standard buttons, input fields, interactive list rows, cards, and modal dialogs.
- **Dock & Floating Radius (`0.75rem` / 12px):** Applied to the persistent floating chat dock and elevated toolbars.
- **Pill Radius (Full / 9999px):** Applied strictly to status tags (e.g., model tags `gpt-4o`, `claude-3-5-sonnet`), verified source pills, and file attachment chips.

## Components

### Buttons & Trigger Controls
- **Primary:** High-contrast solid fill with `#3b82f6` transitioning to `#2563eb` on hover. Pure white typography (`#ffffff`), `0.5rem` radius, with a subtle top-edge inner highlight (`inset 0 1px 0 rgba(255,255,255,0.2)`).
- **Secondary / Ghost:** Transparent base with `#18181b` hover background, hairline border (`1px solid #27272a`), `#a1a1aa` label text elevating to `#f4f4f5` on hover.
- **Keyboard Trigger:** Right-aligned inline mini-pill displaying key combinations via `JetBrains Mono` at `11px`, with background `#27272a` and text `#71717a`.

### Interactive Chat & Prompt Input Dock
- Pinned to bottom viewport center with max width 768px.
- Background `#121215` with `1px solid #27272a` border and `0.75rem` radius.
- Features multi-line expanding input, inline attachment list, model switcher pill, and an active submit icon that transitions from `#27272a` to electric blue (`#3b82f6`) once input is valid.
- Active focus state applies a subtle electric blue hairline ring and micro-glow.

### Pill Tags & Source Chips
- **Source Pill:** `#18181b` surface, `1px solid #27272a`, fully rounded (pill-shaped). Contains a 12px favicon or domain icon, truncated site name, and numeric reference citation index in indigo (`#6366f1`).
- **Status Badges:** Compact monospace labels for tokens, model names, and streaming latency (e.g., `24ms`, `4.2k tokens`).

### Sleek Tabs & Navigation Segments
- Zero-gap segmented controls enclosed in a `#121215` track.
- Active tab features a subtle background lift (`#27272a`), bright white text, and a crisp hairline bottom accent or uniform container fill. Inactive tabs use `#71717a` text without borders.

### Cards & Quiz/Knowledge Modules
- Structured panels built with `#121215` background and `#27272a` boundary line.
- **Quiz Nodes:** Multi-choice rows with distinct radio outlines (`1px solid #3f3f46`). Selected answer transitions to blue-tinted container (`rgba(59, 130, 246, 0.08)`) with `1px solid #3b82f6` border.
- **File Upload Drop-Zones:** Dashed border (`1px dashed #3f3f46`), active drag state triggers Indigo wash (`rgba(99, 102, 241, 0.05)`) with electric blue boundary highlight.