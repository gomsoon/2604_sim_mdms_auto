# Development Guide

## Goal

This guide defines how engineers should implement changes in the repository during the minimal stage.

## Mandatory implementation workflow

For every feature or behavior change, follow this sequence:

1. Analyze the existing source structure before writing feature code.
2. Identify whether the change exposes structural weakness such as duplication, poor boundaries, or misplaced logic.
3. If structural weakness exists, refactor first.
4. Add or update the feature behavior.
5. Add or update tests.
6. Run regression testing.
7. Update documentation if behavior, architecture, or contracts changed.

This sequence is mandatory, not advisory.

## Structural analysis checklist

Before feature work begins, review the affected code for the following:

- Is the responsibility of each touched module clear?
- Is business logic living in route handlers or templates?
- Are similar branches of logic duplicated?
- Will the change make later HES or external integration harder?
- Will the change make English/Korean support harder?
- Does the existing structure still reflect the domain model accurately?

If the answer reveals structural risk, refactor before implementing the new feature.

## Refactoring policy

- Refactoring is allowed and expected when it makes the next change safer, clearer, or easier to test.
- Refactoring should preserve behavior unless the work item explicitly changes behavior.
- Refactoring should be separated conceptually in commit messages and pull request descriptions where feasible.
- Feature work must not hide structural debt that was already visible during analysis.

## Coding guidelines

### General

- Prefer small, purpose-driven functions.
- Keep route handlers thin and delegate processing to service-level functions.
- Preserve raw lineage and avoid destructive overwrite behavior.
- Use clear, domain-oriented names instead of generic helper names.

### Layering

- Blueprints should handle HTTP concerns only.
- Services should own application flow and decision logic.
- Data access and model concerns should remain explicit and predictable.
- External integration logic should be isolated from templates and route formatting.

### Internationalization

- New user-facing text should be written with future English/Korean localization in mind.
- Do not spread hard-coded messages across many files when a shared message strategy is possible.
- Prefer stable machine-readable error codes plus human-readable messages.

### Encoding and text safety

- All documentation and source files must be saved as UTF-8.
- Before finalizing a change, review any Korean text for corruption, broken characters, mojibake, or accidental encoding conversion.
- If a file contains multilingual content, confirm that both English and Korean render correctly in the editor, diff, and runtime surface where applicable.
- Do not accept a change as complete if Korean text appears broken, even when the underlying functional behavior is correct.

### External integration awareness

- Even if a feature is built with local demo data, design its boundaries as if real HES integration will follow.
- Avoid assumptions that data always arrives in perfect order or complete form.

## Documentation update rules

Update documentation when any of the following change:

- API payload contract
- Data model meaning
- User-visible behavior
- Architectural boundary
- Test strategy or execution steps

## Definition of done

A change is not complete unless all of the following are true:

- Structural analysis was performed first.
- Required refactoring was completed before the feature change.
- Tests were added or updated.
- Regression testing was executed.
- Documentation was updated if needed.
- English/Korean support implications were reviewed.
- UTF-8 encoding and Korean text integrity were reviewed.
- External integration implications were reviewed.

## Suggested commit discipline

- Keep commits focused and readable.
- Prefer commit messages that describe intent rather than only file movement.
- If a change contains both refactoring and behavior change, the description should make that distinction obvious.
