# Academic Skill behavioral cases

These are manual behavioral evaluations, not compiler unit tests. Give an author
only the request, raw material and Skill entrypoint, in an isolated workspace.
Keep the assessment criteria with the reviewer. Inspect the actual outline or
pages; matching these words or filling fields is not a pass. Record scope and
artifacts, and distinguish planning from rendered-PPTX evaluation.

## A. Short progress report with confounded numerical controls

Request: prepare an eight-minute Chinese progress report for PhD students outside
the specialty. Deliver a producible page outline and detailed content/layout
briefs for the two hardest pages; do not generate PPTX. The group should help
decide what to test next.

Supplied illustrative observations (not real experimental evidence):

| Setting | Bond dimension | Time step | Total runtime | Energy drift at t=10 |
| --- | ---: | ---: | ---: | ---: |
| A | 32 | 0.05 | 80 s | 0.020 |
| B | 64 | 0.025 | 190 s | 0.004 |

Model and initial state are the same. No time series, exact reference or other
runs are available. Reading notes contain definitions of MPS, MPO, SVD, TDVP and
Trotter expansion plus twelve derivations. Energy/time units and the precise
drift definition are not supplied.

Assess whether the report:

- Selects a discussion about the next test rather than presenting every reading
  topic, and explains necessary numerical controls to the specified audience.
- Preserves the observations while recognizing that two controls changed.
  Does not attribute the difference to one control, prove convergence or equate
  smaller energy drift with exact dynamics.
- Uses a table or other honest comparison rather than inventing time-series
  curves, uncertainty bars, units or experimental results.
- Proposes comparisons that separate the controls, labels them unrun, and says
  how their possible outcomes would inform the decision.
- Chooses visual relationships that explain the comparison and proposed test;
  empty two-column prose or a generic “more simulations” ending is insufficient.

## B. Local typography repair

Request: fix the rendering of one supplied equation on page 7 of an existing
deck; preserve wording, order, all other pages and scientific meaning.

Provide the baseline PPTX, page source and correct source equation. Assess actual
page-preservation evidence and the final equation rendering. Reject unnecessary
whole-report reorganization or a new approval gate for a report outline.

## C. Supplied full-coverage teaching outline

Request: retain all twelve derivation steps and the user's page count for a
methods teaching session. Audience already knows the notation. Improve the
explanation without deleting steps or moving requested content to backup.

Assess whether assumptions and mathematical transitions become clear while the
explicit coverage survives. Do not reward shortening at the expense of scope,
invented takeaway claims on setup pages or arbitrary layout variation.

## D. Finished academic deck

Use an authorized source paper and a concrete audience/duration. Generate the
requested PPTX, render the exact file and review every page. Check the argument,
physical-model explanation, evidence labels, mathematical typography and limits,
in addition to structural and visual correctness. Record specific rejected and
revised pages. An outline-only trial cannot pass this case or establish reliable
academic-product quality across tasks.

## E. A tidy page that conveys the wrong relationship

Supply a slide with readable labels and all objects inside the canvas, but the
result caption names a different source panel, a tree connector ends on the wrong
node, and the crop omits the horizontal-axis label. Also supply the original
figure. Ask for a local review and repair without changing other accepted pages.

Assess whether the reviewer identifies the actual panel/connector/crop defects
in the rendered page, uses source evidence to repair them, and rechecks the new
render. Geometric containment, a contact sheet or a completed checklist is not
a pass. Accept intentional overlaps that serve the explanation; do not reward
removing them merely to eliminate all bounding-box intersections.

## F. Individually coherent pages, incomplete deck argument

Supply three legible pages: a model introducing a parameter, a result obtained
at a different unmentioned parameter, and a conclusion claiming universality.
Ask for review of the presentation as a whole. Assess whether the reviewer
separates each page's local readability from the missing comparison conditions
and unsupported scope of the ending, and changes only affected premises/pages.

## G. Formula appearance and actual source

Supply an expression with fractions, a square root, a hat and hbar; also provide
an apparently successful PNG/SVG containing flattened text. Request genuine
mathematical typesetting in one page. Inspect the Office Math implementation or
the retained TeX/MathJax source and high-resolution PNG output, then the actual PPTX consumer
render. Test a wide/narrow placement box: glyph proportions must survive.
An image extension, pixel count or successful conversion alone cannot establish
mathematical correctness or consumer compatibility.
