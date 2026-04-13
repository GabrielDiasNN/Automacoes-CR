# HTML/CSS Architecture ADR Template

## Title

Short decision title.

## Status

Proposed | Accepted | Deprecated | Superseded

## Context

Describe the product context, scale, team constraints, and the main architectural pressure.

## Decision

State the chosen HTML/CSS architecture direction.

Examples:

- Layered SCSS with tokens, objects, components, and utilities.
- Token-driven theming with semantic aliases.
- Responsive dashboard shell based on grid primitives.

## Consequences

### Positive

- Expected maintainability gains.
- Accessibility and performance benefits.
- Governance simplification.

### Negative

- Migration cost.
- Learning curve.
- Temporary dual-pattern support.

## Rules Introduced

- Naming rules.
- Allowed and forbidden selector patterns.
- State modeling approach.
- Token ownership and review expectations.

## Validation Plan

- How the team will verify semantic quality.
- How the team will review accessibility.
- How CSS size and layout behavior will be monitored.

## Sunset or Revisit Trigger

State what would force this decision to be revisited.
