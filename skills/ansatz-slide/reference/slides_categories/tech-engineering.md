# Tech and engineering

## Methodology

Explain inputs, outputs, dependencies, normal operation, failure paths and success criteria. Distinguish data flow, control flow and trust boundaries where relevant. Use logs, code and configuration only when they support the point.

Compare options against real requirements: performance, cost, complexity, operability, migration and failure recovery. Separate current state, proposed state, assumptions and tested behavior. Performance evidence needs environment, version, load and measurement basis; report distributions when relevant, not mandatory percentiles for every claim.

Rollout plans state validation gates, rollback conditions and ownership when known. Do not turn an untested architecture into a reliability guarantee.

## Visual defaults

External architecture/sequence figures should have clear labels and direction. Page annotations explain boundaries and trade-offs; there is no automatic SmartArt conversion. Keep code at readable size, use focused excerpts and preserve error context.

Neutral or brand-aligned colors are acceptable; semantic status colors need labels. Use the selected style without a blanket ban on blue/white, cards or equal columns.

## Acceptance

Can the reader trace what enters the system, what changes, what comes out, where it can fail and why the proposed choice is justified? Are tests distinguished from assumptions and deployment promises?
