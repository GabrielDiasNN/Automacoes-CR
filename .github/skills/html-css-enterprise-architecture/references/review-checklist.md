# HTML/CSS Architectural Review Checklist

## Scope and Intent

- The page or feature has a clear structural purpose.
- Shared concerns are separated from feature-specific concerns.
- Repeated patterns are identified before local exceptions are accepted.

## HTML Contract

- Landmark structure is correct.
- Heading hierarchy is coherent.
- Native elements are used whenever possible.
- Reading order matches keyboard and assistive-technology expectations.

## CSS and Sass Structure

- Tokens, base, objects, components, and utilities are clearly separated.
- Sass partials express ownership boundaries instead of arbitrary file splitting.
- Selector specificity remains controlled.
- Nesting is shallow and does not depend on fragile DOM depth.

## Responsiveness

- Layout works under narrow, medium, and wide constraints.
- Dense data views degrade acceptably on smaller screens.
- Wrapping, truncation, empty states, and overflow are handled deliberately.

## Accessibility

- Focus states are visible.
- Keyboard navigation is complete.
- Contrast is acceptable.
- Motion is reduced when necessary.
- Zoom and reflow do not break task completion.

## Performance

- CSS output size is justified.
- Fonts and animations follow a budget.
- Layout behavior avoids unnecessary instability.
- Sass compilation does not generate repeated or dead rules.

## Governance

- New patterns map back to an existing token, object, or component contract.
- Near-duplicate components are rejected.
- Exceptions have an owner and removal intent.
