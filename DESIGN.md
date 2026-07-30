---
name: RINGKAS
description: Citation-first BPS publication search and question answering.
colors:
  primary: "#005b96"
  primary-deep: "#083b5c"
  primary-soft: "#e8f2f8"
  primary-wash: "#f1f7fb"
  accent: "#f58220"
  accent-deep: "#a94f0f"
  accent-soft: "#fff0e4"
  focus-ring: "#8dc4df"
  background: "#f4f8fb"
  surface: "#ffffff"
  panel: "#edf4f8"
  border: "#d6e3eb"
  field-border: "#b9ceda"
  card-border: "#d6e3eb"
  ink: "#102f43"
  ink-strong: "#062c45"
  text-body: "#345365"
  text-muted: "#67808e"
  field-label: "#345365"
  nav-muted: "#e6eff4"
  error: "#a73531"
  error-strong: "#8d2d29"
  error-border: "#d88984"
  warning: "#a94f0f"
  warning-soft: "#fff8f2"
  warning-strong: "#8e3d0b"
  success: "#216b4a"
typography:
  display:
    fontFamily: "Inter, system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif"
    fontSize: "clamp(1.8rem, 3vw, 2.4rem)"
    fontWeight: 400
    lineHeight: 1.15
  body:
    fontFamily: "Inter, system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif"
    fontSize: "1rem"
    fontWeight: 400
    lineHeight: 1.5
  title:
    fontFamily: "Inter, system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif"
    fontSize: "1.05rem"
    fontWeight: 400
    lineHeight: 1.5
  label:
    fontFamily: "Inter, system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif"
    fontSize: "0.75rem"
    fontWeight: 700
    lineHeight: 1.5
    letterSpacing: "0.12em"
rounded:
  xs: "10px"
  sm: "12px"
  md: "16px"
  lg: "20px"
  xl: "24px"
  pill: "999px"
spacing:
  2xs: "2px"
  xs: "4px"
  sm: "8px"
  md: "12px"
  lg: "16px"
  xl: "20px"
  2xl: "24px"
  3xl: "28px"
  4xl: "32px"
components:
  button-primary:
    backgroundColor: "{colors.accent}"
    textColor: "{colors.ink-strong}"
    rounded: "{rounded.xs}"
    padding: "11px 18px"
  button-primary-hover:
    backgroundColor: "{colors.accent-deep}"
    textColor: "{colors.surface}"
    rounded: "{rounded.xs}"
    padding: "11px 18px"
  field:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink-strong}"
    rounded: "{rounded.sm}"
    padding: "12px 14px"
  nav-link:
    backgroundColor: "{colors.nav-muted}"
    textColor: "{colors.text-body}"
    rounded: "{rounded.xs}"
    padding: "8px 13px"
  nav-link-active:
    backgroundColor: "{colors.primary-soft}"
    textColor: "{colors.ink-strong}"
    rounded: "{rounded.xs}"
    padding: "8px 13px"
  page-card:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.lg}"
    padding: "32px"
  panel:
    backgroundColor: "{colors.panel}"
    textColor: "{colors.ink}"
    rounded: "{rounded.md}"
    padding: "20px"
  document-card:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.sm}"
    padding: "16px"
---

# Design System: RINGKAS

## Overview

**Creative North Star: "Ruang Baca Fokus"**

RINGKAS is a light, single-sans research workspace inspired by the institutional clarity of Indonesian official statistics. The system places a focused conversation surface on a cool-white canvas, uses institutional blue for structure and navigation, and brings a more visible statistical orange into actions and evidence moments. Rounded controls, thin borders, and compact metadata make a dense research task feel approachable without turning it into a dashboard.

The tone is friendly, official, and educational, but never bureaucratic or theatrical. It should feel like a patient guide through a dense publication: direct enough for a researcher moving quickly, clear enough for someone learning how to verify a statistic. It borrows the blue-orange register of a public statistics institution without copying BPS marks or becoming a government portal clone. It explicitly rejects an overconfident AI voice and a generic corporate dashboard; the interface earns trust through visible evidence and honest states.

**Key Characteristics:**
- Institutional Blue + Statistical Orange + Quiet White palette
- One Inter-based type system
- Restrained, readable controls with soft rounded corners
- Flat surfaces with a single ambient page shadow
- Evidence, limitation, loading, and error states treated as first-class content

## Colors

The palette is structured around cool neutral surfaces, institutional blue for the frame of the product, and a more present orange accent for actions, evidence markers, and moments that need attention.

### Primary
- **Institutional Blue** (`{colors.primary}`): Navigation, structural actions, active routes, source links, and the persistent frame of the research workspace.
- **Deep Blue** (`{colors.primary-deep}`): Strong text, primary contrast, and high-confidence headings.
- **Blue Wash** (`{colors.primary-soft}`, `{colors.primary-wash}`): Active navigation, sidebar surfaces, and quiet information grouping.

### Secondary
- **Statistical Orange** (`{colors.accent}`): New chat, send action, evidence markers, selected source moments, and the RINGKAS signature mark. It is visible enough to give the product identity, but never becomes a full-page fill.
- **Deep Orange** (`{colors.accent-deep}`): Orange text on light surfaces where contrast is required.
- **Orange Wash** (`{colors.accent-soft}`): Citation markers, evidence excerpts, and low-pressure attention states.

### Neutral
- **Quiet White** (`{colors.background}`): The cool application canvas.
- **Surface White** (`{colors.surface}`): Page cards, document cards, citation cards, and form controls.
- **Panel White** (`{colors.panel}`): Tonal layer for answer, citation, search, and admin panels.
- **Ink** (`{colors.ink}`): Body text and answer content.
- **Strong Ink** (`{colors.ink-strong}`): Headings, primary button text contrast, and active navigation text.
- **Body Gray** (`{colors.text-body}`): Supporting paragraphs, navigation defaults, and blockquote text.
- **Muted Gray** (`{colors.text-muted}`): Session notes, metadata labels, hints, and quiet status copy.
- **Quiet Border** (`{colors.border}`): Page and panel boundaries.
- **Field Border** (`{colors.field-border}`): Input and textarea strokes.
- **Card Border** (`{colors.card-border}`): Document and citation card boundaries.

### Semantic States
- **Error Red** (`{colors.error}`, `{colors.error-strong}`, `{colors.error-border}`): Form errors, insufficient evidence, and destructive limitation states.
- **Warning Amber** (`{colors.warning}`, `{colors.warning-soft}`, `{colors.warning-strong}`): Partial evidence and cautionary limitation states.
- **Success Green** (`{colors.success}`): Sufficient evidence state text.

### Named Rules
**The Blue Structure, Orange Evidence Rule.** Institutional Blue owns the frame and navigation. Statistical Orange owns action and evidence moments. Never use either color as decorative wallpaper or as an inactive-state fill.

## Typography

**Display Font:** Inter (with system-ui, -apple-system, BlinkMacSystemFont, and Segoe UI fallbacks)
**Body Font:** Inter (with system-ui, -apple-system, BlinkMacSystemFont, and Segoe UI fallbacks)
**Label/Mono Font:** No distinct label or mono face; labels stay in the same Inter stack.

**Character:** One neutral sans family keeps the product familiar and easy to scan. Weight and spacing separate navigation labels, evidence metadata, and answer content rather than introducing display theatrics.

### Hierarchy
- **Display** (400, `clamp(1.8rem, 3vw, 2.4rem)`, `1.15`): App page headings that name the task, such as asking about or finding BPS publications.
- **Landing display** (800, `clamp(2.5rem, 5vw, 4.5rem)`, `1`): The public Home headline may carry more scale because its job is to explain RINGKAS before the research workspace opens.
- **Title** (400, `1.05rem`, `1.5`): Panel headings and short card titles.
- **Body** (400, `1rem`, `1.5`): Explanatory copy, answers, and general product text.
- **Label** (700, `0.75rem`, `0.12em`, uppercase): Eyebrows and state badges where compact classification is useful.
- **Supporting text** (400, `0.8rem` to `0.92rem`, `1.5`): Metadata, hints, provider notes, and source excerpts.

### Named Rules
**The One Sans Rule.** Keep interface labels, buttons, data, and prose in the same Inter stack. Create hierarchy with scale, weight, spacing, and color, never a novelty display face.

## Elevation

RINGKAS is flat by default. Thin borders and tonal layering establish the working hierarchy: the cool-white canvas holds a white working surface, which contains blue-tinted panels and white result content. The primary workspace uses one low-alpha ambient shadow; other surfaces remain visually quiet. No blur or translucent glass treatment is needed to establish the product's institutional clarity.

### Shadow Vocabulary
- **Page ambient** (`0 4px 8px rgba(6, 44, 69, 0.05)`): A quiet lift for the primary working surface only.

### Named Rules
**The Flat-by-Default Rule.** Surfaces are flat at rest. Add depth only when a layer needs to separate from its parent; do not stack shadows to make ordinary content look elevated.

## Components

### Buttons
- **Shape:** Compact rounded rectangle (`10px`) for a clear product action.
- **Primary:** Statistical Orange background with Deep Blue text, white text on the darker hover state, and compact padding. The button is an identity-bearing action rather than a generic black pill.
- **Hover / Focus:** Hover deepens Orange. Focus uses a blue-tinted ring; interactive controls must retain an obvious keyboard focus state.

### Cards / Containers
- **Corner Style:** Page cards use `20px`; panels use `16px`; document and citation cards use `12px`.
- **Background:** Surface White for the page and result cards; Panel White for grouped working regions.
- **Shadow Strategy:** Follow the Flat-by-Default Rule; only the page card receives the ambient shadow.
- **Border:** Quiet Border for page/panel boundaries and Card Border for result cards.
- **Internal Padding:** `32px` for page cards, `20px` for panels, and `16px` for result cards.

### Inputs / Fields
- **Style:** White background, Field Border stroke, `12px` radius, and `12px 14px` padding. Labels use Field Label color and a semibold weight.
- **Focus:** A `3px` blue-tinted outline plus an Institutional Blue border shift.
- **Error / Disabled:** Errors use Error Red; disabled controls reduce opacity and retain the same shape rather than changing vocabulary.

### Navigation
- **Style:** A full-width, bordered header uses a flexible two-part layout: brand block on the left, compact links on the right. The header keeps the product frame light and institutional rather than becoming a floating card.
- **Default / Active:** Default links use a blue-muted surface and Body Gray text. The active route uses Soft Blue and Deep Blue.
- **Mobile:** At `640px` and below, the header stacks brand and navigation and left-aligns the links.

### Route Roles
- **Home (`/`):** Landing page that explains what RINGKAS protects: publication-grounded answers, visible citations, and honest limits. It is the entry point for guests and first-time visitors, and remains accessible from the authenticated shell.
- **Landing composition:** The Home surface uses the "Ruang Bukti" direction: the RINGKAS wordmark leads into its full expansion, which sits above a smaller evidence tagline; Indonesian-first copy carries the voice, a blue institutional field frames the page, Statistical Orange signals evidence, and one citation artifact replaces a generic feature-card grid.
- **Chat (`/chat`):** Primary landing destination after authentication and the main research workspace.
- **Documents / Admin:** Protected surfaces. Their access boundary is explicit in Home and chat copy rather than presented as public navigation.

### Status Badges
- **Style:** Compact uppercase labels with `0.72rem` type and `0.08em` tracking. Neutral badges use Body Gray; sufficient, partial, and insufficient evidence use semantic green, amber, and red.
- **Behavior:** Badges label the current state of a panel; they do not replace the explanatory message.

### Evidence Cards
- **Style:** Citation and document cards use a white surface, `12px` radius, `16px` padding, and a thin card border. Orange marks the citation number and selected source state.
- **Content:** Keep title, year, region, page range, excerpt, and source link in a readable vertical order. The source link is a textual, underlined affordance rather than a hidden icon.

## Do's and Don'ts

### Do:
- **Do** keep the main working surface centered at a readable width and reserve the deepest hierarchy for the question, answer, and source evidence.
- **Do** use Institutional Blue for structure and navigation, and Statistical Orange for primary action and evidence moments; keep inactive surfaces neutral.
- **Do** preserve the one-family Inter stack and the existing `10px`, `12px`, `16px`, `20px`, and `24px` radius vocabulary.
- **Do** make loading, error, partial evidence, insufficient evidence, and empty states visible in the content area.
- **Do** keep the mobile collapse at `640px` structural: stack the header and reduce page-card padding to `24px`.

### Don't:
- **Don't** make RINGKAS feel like an AI that is "sok tahu"; never let visual certainty outrun the presence of a citation or limitation message.
- **Don't** turn the product into a generic corporate dashboard; metrics and operational panels must remain secondary to the research task.
- **Don't** use gradients, gradient text, decorative glass surfaces, or saturated inactive states. Do not turn the BPS-inspired orange into a full-page background.
- **Don't** add repeated card grids, nested cards, or ornamental section scaffolding when an inline panel or simple document list is clearer.
- **Don't** use a shadow vocabulary heavier than the single page ambient shadow or introduce a second font family for UI labels.
