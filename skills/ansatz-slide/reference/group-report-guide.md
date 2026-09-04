# Research Group Report Guide

Use this reference for research group meetings, progress reports, method reviews, and other evidence-heavy academic presentations. It captures the reusable production principles and visual language of the designated guide deck. Do not reproduce defects from the source deck, such as crowded figures, weak contrast, or overlapping objects.

## Section A — Production Methodology

### Communication objective

- Treat the deck as a tool for making work understandable, discussable, and open to scrutiny. A work log is not a substitute for a presentation.
- Optimize for clarity, directness, completeness, logical continuity, emphasis, and useful information density. Visual polish serves comprehension.
- Explain the main work in two or three sentences before designing pages. The audience should understand the central problem, current progress, and the logic of the report within the first two or three slides.

### Story construction

- Choose one global narrative: problem solving, method exploration, progress review, or topic selection. Do not switch narrative logic without an explicit transition.
- Assign every slide one primary function, such as context, transition, evidence, argument, comparison, conclusion, next experiment, or request for help.
- Write one claim sentence for every slide before laying it out. Reading these sentences in order should form a coherent account.
- Lead with the conclusion or judgment, then place the evidence and explanation that support it. Do not make the audience infer the point from a pile of materials.
- Write from the audience's perspective. Define unfamiliar objects and relationships instead of assuming prior project knowledge.

### Evidence and reasoning

- Group related evidence and give each parallel block a short heading. Use whitespace and simple divider lines to expose structure.
- Every figure, screenshot, image, diagram, chart, and table needs a nearby label or caption and a sentence explaining what the audience should notice. Put the source close to the evidence.
- Use externally produced or supplied flow diagrams for plans, technical routes, causal chains, and experiment sequences; retain their editable source when available. Native arrows and leader lines may annotate the evidence when they clarify reading order or correspondence.
- When results are sparse or negative, report them honestly: state what was attempted, what was observed, the likely causes, what remains unknown, and the next experiment or help needed. Never invent a successful result to fill a page.
- When the logic is stuck, study a strong predecessor for its argumentative frame and page functions; do not merely copy its decoration.

### Review gates

- Verify that the first two or three slides establish the main question and report logic.
- Verify that every slide has one explicit claim and one primary function.
- Verify that each evidence object has a label, interpretation, and source where applicable.
- Verify that conclusions are supported by visible evidence and that uncertainty is stated honestly.
- Reject pages with overlap, clipping, illegible evidence, unexplained screenshots, or decorative material unrelated to the claim.

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

- Use a clear Chinese sans-serif with a compatible Latin sans-serif. Prefer fonts that are already available on the delivery machine; embedding is optional and must not be assumed.
- Reference scale: cover title 80–96 pt, section title 48–60 pt, content title about 32–40 pt, body 18–24 pt, captions and sources 9–12 pt. Adjust for actual viewing distance and density.
- Establish emphasis with weight, size, accent color, outline, underline, or a nearby arrow. Do not combine every emphasis method on the same phrase.

### Layout and components

- Use conclusion-first headlines, unequal evidence/text proportions, simple lines, and deliberate whitespace as the default structure.
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

- Use native PPTD text, shapes, and lines for page framing and annotation. Figures, charts, and finished tables are produced by a dedicated tool or supplied by the user, then placed as PNG/SVG assets with readable captions and sources; PPTX arranges them rather than drawing them. If an asset is unavailable, create a clearly labeled placeholder frame.
- The native chart/table DSL remains a tested compatibility surface, not the default production path. Never emit unsupported chart DSL or present an empty/misleading chart as success. For delivery icons, likewise use supplied PNG/SVG image elements; the `icon` DSL may expose only its generic fallback shape in standard Office consumers.
- A reference shape containing text must be reconstructed as separate Shape and Text elements. Grouped source objects may be flattened into independent elements or, when editability is unnecessary, retained as one image.
- Use only DSL constructs defined by `reference/pptd.md`. Export success alone is not evidence that an input is valid.
