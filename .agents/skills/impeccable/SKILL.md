---
name: impeccable
description: "Impeccable Design System & Critique Workflow for RINGKAS. Use when designing, auditing, building, or refining UI components, layouts, typography, color usage, and visual accessibility across apps/web. Enforces the Institutional Blue, Statistical Orange, single-sans Inter hierarchy, flat surfaces, and evidence-grounded UX principles from .impeccable/design.json and DESIGN.md."
---

# Impeccable Design System & Critique Skill (RINGKAS)

Skill ini mengatur standar desain visual, UI/UX, dan panduan audit/critique untuk proyek **RINGKAS** berdasarkan file spesifikasi [design.json](file:///d:/My%20Files/Personal%20Project/RINGKAS/.impeccable/design.json) dan [DESIGN.md](file:///d:/My%20Files/Personal%20Project/RINGKAS/DESIGN.md).

---

## 1. Core Principles (North Star: "Ruang Baca Fokus")

1. **Institutional Blue Structure, Statistical Orange Evidence**:
   - **Institutional Blue (`oklch(43% 0.12 245)`)**: Digunakan untuk navigasi, struktur header, dan frame utama.
   - **Statistical Orange (`oklch(68% 0.17 55)`)**: Digunakan khusus untuk primary action button, highlight sitasi/bukti, dan momen interaksi penting.
   - **Quiet White Background (`oklch(98% 0.008 245)`)**: Canvas latar bersih dan tenang.
   - Jangan gunakan warna-warna ini sebagai wallpaper dekoratif tanpa fungsi.

2. **The One-Sans Rule (Inter Only)**:
   - Gunakan satu font family: **Inter** (`Inter, system-ui, sans-serif`).
   - Hierarki dibangun melalui ukuran (scale), bobot (font-weight), line-height, dan kontras warna, bukan dengan mengganti font family.

3. **Flat-by-Default Elevation**:
   - Komponen & surface bertipe flat saat diam.
   - Hindari shadow tebal berlapis, gradien mencolok, glassmorphism berlebihan, atau neon glow.
   - Hanya gunakan single ambient shadow jika diperlukan: `0 4px 8px rgba(6, 44, 69, 0.05)`.

4. **Honest & Grounded States**:
   - Status bukti (*Sufficient*, *Partial*, *Insufficient*, *Loading*, *Error*) disajikan sebagai konten utama (*first-class content*).
   - Jangan menyembunyikan disclaimer atau citation warning.

---

## 2. Design System Tokens & Components

### Color Tokens (OKLCH mapping to Hex fallback)
- **Primary / Structure**: `oklch(43% 0.12 245)` / Hex: `#062c45` (Navy/Institutional Blue)
- **Primary Wash**: `oklch(95% 0.025 245)` / Hex: `#e6eff4` (Blue Tint)
- **Accent / Action**: `oklch(68% 0.17 55)` / Hex: `#f58220` (Statistical Orange)
- **Accent Hover**: `#a94f0f`
- **Background**: `oklch(98% 0.008 245)` / Hex: `#f7fafc`
- **Surface**: `oklch(100% 0 0)` / Hex: `#ffffff`
- **Ink / Text**: `oklch(27% 0.04 245)` / Hex: `#102f43`
- **Muted Text**: `#4f6a7a` / `#67808e`
- **Border**: `#d6e3eb` / `#b9ceda`

### Border Radius Vocabulary
- Small badge/link: `10px`
- Cards / Containers: `12px`, `16px`
- Main Page Card: `20px`

### Key UI Component Classes (Vanilla CSS / Tailwind Equivalents)
- `.ds-btn-primary`: Orange background (`#f58220`), navy text (`#062c45`), radius `10px`, bold `700`, smooth hover transition.
- `.ds-field`: Border `#b9ceda`, background `#fff`, radius `10px`, outline focus `#8dc4df`.
- `.ds-page-card`: White surface, max-width `720px`, padding `32px`, border `#d6e3eb`, radius `20px`, ambient shadow.
- `.ds-panel`: Tonal background `#edf4f8`, border `#d6e3eb`, radius `16px`, container jawaban/sitasi.
- `.ds-state-badge`: Label uppercase 0.72rem, font-weight 700. Green `#216b4a` (sufficient), Orange `#a94f0f` (partial), Red `#a73531` (insufficient).

---

## 3. Workflow Audit & Critique Checklist

Setiap kali agent merancang atau mengubah file frontend (`apps/web`), jalankan checklist audit Impeccable ini:

1. **Color Audit**:
   - [ ] Apakah tombol aksi utama menggunakan Statistical Orange?
   - [ ] Apakah struktur/navigasi menggunakan Institutional Blue?
   - [ ] Apakah ada gradien atau warna neon yang melanggar aturan flat design?
2. **Typography Audit**:
   - [ ] Apakah seluruh UI menggunakan font family Inter?
   - [ ] Apakah ukuran heading clamp responsif dan terbaca jelas?
3. **Layout & Space Audit**:
   - [ ] Apakah main card memiliki batas max-width yang nyaman dibaca (720px untuk research card)?
   - [ ] Apakah breakpoint mobile (640px) sudah mengurus responsive stacking dengan benar?
4. **State & Accessibility Audit**:
   - [ ] Apakah status bukti (*Sufficient*, *Partial*, *Insufficient*) terindikasi dengan badge yang jelas?
   - [ ] Apakah `:focus-visible` memiliki outline kontras (misal `3px solid #8dc4df`) untuk aksesibilitas keyboard?

---

## 4. References & Source Files
- System Spec: [design.json](file:///d:/My%20Files/Personal%20Project/RINGKAS/.impeccable/design.json)
- Human Readme: [DESIGN.md](file:///d:/My%20Files/Personal%20Project/RINGKAS/DESIGN.md)
