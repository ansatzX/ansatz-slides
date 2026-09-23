# Research Group Report Guide

Use this reference for research group meetings, progress reports, method reviews, and other evidence-heavy academic presentations. It captures the reusable production principles and visual language of the designated guide deck. Do not reproduce defects from the source deck, such as crowded figures, weak contrast, or overlapping objects.

## Section A — Production methodology

Use [academic authoring](academic-authoring.md) for the actual sequence from reading material to a report, including worked failure/correction examples and audience review. The following group-meeting choices specialize that workflow:

- State the main work in two or three sentences. The first two or three slides should orient the audience to the question, current progress and purpose of the discussion.
- Select a narrative that fits the work: problem solving, method exploration, progress review or topic selection. A report with negative results can center on diagnosis and a request for help.
- Report observed failures, competing explanations and a feasible discriminating experiment. Do not convert effort, code execution or a proposed test into a successful scientific result.
- Borrow a predecessor's argumentative moves and evidence relationships when useful. Its colors and equal-width panels are not the method.

The source guide is Zhang Wenjie's *2025 帅组组会报告不完全指南*: purpose and narrative (pp. 5–9), expression (pp. 12–18), concrete visual tools (pp. 20–24), and negative-result discussion (p. 26). Its emergency suggestions on pp. 27–28 are explicitly qualified by the author and are not an automatic content-generation strategy. The source deck is not required at runtime.

## Section B — Visual System

### Canvas and page skeleton

- Use a 16:9 canvas. Keep a stable outer margin and a consistent title baseline.
- A research group report may use a narrow top section rail containing the section name, a compact icon, and the page number. A user-provided template or reference takes precedence over generic prohibitions against repeated rails.
- Use full-color section dividers sparingly to signal major narrative changes. Keep ordinary content pages predominantly light so evidence remains readable.

### Color

- Preferred reference palette: primary red `#BD2333`, burgundy `#931A2B`, deep burgundy `#3A0C11`, amber `#FFC000`, with black, white, and restrained neutral grays.
- Use related colors to show belonging and contrasting colors to show differences. Deep panels use white text; light panels use black or near-black text.
- Accent color should identify the conclusion, key term, selected path, or exception. Do not distribute emphasis colors evenly across all content.

### Typography

- Use a clear Chinese sans-serif with a compatible Latin sans-serif. Prefer fonts that are already available on the delivery machine; the exporter does not embed fonts.
- Reference scale: cover title 80–96 pt, section title 48–60 pt, content title about 32–40 pt, body 18–24 pt, captions and sources 9–12 pt. Adjust for actual viewing distance and density.
- Establish emphasis with weight, size, accent color, outline, underline, or a nearby arrow. Do not combine every emphasis method on the same phrase.

### Layout and components

- Give argument pages a supported takeaway; setup pages may have a concise subject or question title. Use evidence/text proportions, simple lines and whitespace to expose the actual relationship.
- Cards and equal splits are allowed when they express genuine parallelism, comparison, or staged reasoning. They are not default filler and must not become a generic dashboard grid.
- Use real screenshots, papers, experimental figures, interfaces, or object images as evidence. Preserve enough scale for the relevant detail to be readable.
- Use native labeled blocks for parallel text, dark-versus-light panels for binary comparison, and external flow-diagram assets for procedures or technical routes. Do not promise that a placed diagram image is editable inside PowerPoint.
- Progressive disclosure may be represented through consecutive slides and translucent masks. The unmasked state must remain available, and masked text must not be mistaken for final unreadable content.
- Reuse a small set of shapes: rectangles, rounded rectangles, simple lines, arrows, image frames, and restrained icons. Avoid decorative geometry without a communication role.

### Visual acceptance

- Inspect every slide at full resolution, not only in a contact sheet.
- Reject text or images that cross their intended region, collide with headings, become unreadable at presentation distance, or lose necessary labels.
- Do not mechanically reproduce visual defects in a reference deck. Preserve its communication grammar, not its accidental overlap, crowding, or low contrast.

## Section C — Supported Construction Strategy

- Use native pptx.yaml text, shapes, and lines for page framing and annotation. Figures, charts, and finished tables are produced by a dedicated tool or supplied by the user, then placed as PNG/SVG assets with readable captions and sources; PPTX arranges them rather than drawing them. If an asset is unavailable, create a clearly labeled placeholder frame.
- The native chart/table DSL remains a tested compatibility surface, not the default production path. Never emit unsupported chart DSL or present an empty/misleading chart as success. For delivery icons, likewise use supplied PNG/SVG image elements; the `icon` DSL may expose only its generic fallback shape in standard Office consumers.
- A reference shape containing text must be reconstructed as separate Shape and Text elements. Grouped source objects may be flattened into independent elements or, when editability is unnecessary, retained as one image.
- Use only DSL constructs in [the field reference](presentation-schema.md). Export success alone is not evidence that an input is valid.
