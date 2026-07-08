# Design System — Template

This file is the authoritative source for visual decisions. Replace the copy in this file with the design language of your specific project, but keep the section structure so agents can reason about it.

## Product Context
- **What this is:** A stub design system for a Django + React template. Replace with your product's purpose.
- **Who it's for:** Describe the primary user persona.
- **Space/industry:** Peer products, category.
- **Project type:** Full-stack web app.

## Aesthetic Direction
- **Direction:** Clean, minimal, functional. Update to your desired direction.
- **Decoration level:** Intentional — no decorative filler.
- **Mood:** Confident, honest, restrained.

## Typography
- **Display/Hero:** system-ui fallback until you pick a display face.
- **Body:** system-ui.
- **UI/Labels:** system-ui.
- **Data/Tables:** system-ui with `font-variant-numeric: tabular-nums`.
- **Code/Monospace:** `ui-monospace`, `SFMono-Regular`, `Menlo`, `Monaco`, `Consolas`, monospace.
- **Loading:** Prefer Google Fonts CDN preconnect + `<link>` in `frontend/index.html`.
- **Scale:**
  ```
  --text-xs:    12px / 1.4   (metadata, badges)
  --text-sm:    13px / 1.5   (table rows, secondary labels)
  --text-base:  15px / 1.6   (body prose, form inputs)
  --text-md:    17px / 1.55  (card headings, sidebar items)
  --text-lg:    22px / 1.4   (section headings)
  --text-xl:    28px / 1.3   (page titles)
  --text-2xl:   36px / 1.2   (hero)
  ```

## Color
- **Approach:** Restrained — one accent, neutrals do the heavy lifting.
- **Accent (primary):** `#2563EB` — replace with your accent.
- **Background:** `#FFFFFF` (light) / `#0F172A` (dark).
- **Surface:** `#F8FAFC` (light) / `#1E293B` (dark).
- **Primary text:** `#0F172A` (light) / `#F1F5F9` (dark).
- **Muted text:** `#64748B`.
- **Border:** `#E2E8F0` (light) / `#334155` (dark).
- **Semantic:**
  - success: `#16A34A`
  - warning: `#D97706`
  - error: `#DC2626`
  - info: `#2563EB`

## Spacing
- **Base unit:** 8px.
- **Scale:** 4, 8, 12, 16, 20, 24, 32, 40, 48, 64 px.

## Layout
- **Grid:** 12 columns at ≥1200px; 4 columns at ≥600px; 1 column mobile.
- **Max content width:** 1280px.
- **Border radius:** 4 / 8 / 12 / 9999 px (sm / md / lg / full).

## Motion
- **Approach:** Minimal-functional — only transitions that aid comprehension.
- **Easing:** enter `cubic-bezier(0, 0, 0.2, 1)` / exit `cubic-bezier(0.4, 0, 1, 1)` / move `cubic-bezier(0.4, 0, 0.2, 1)`.
- **Duration:** micro 75ms / short 150ms / medium 250ms / long 400ms.

## Rules (enforced by CLAUDE.md)
- **Never hardcode colours.** Use `theme.palette.*`.
- **MUI imports are individual** (`@mui/material/Box`), never barrel.
- **Read this file before changing anything visual.**
