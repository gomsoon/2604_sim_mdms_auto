# Internationalization Strategy

## Purpose

This document defines the internationalization baseline for the minimal stage.

## Baseline decision

- All operator-facing features must support English and Korean.
- The repository must remain UTF-8 throughout source code, templates, fixtures, and documentation.
- Stable machine-readable codes must remain language-independent.
- Human-readable text must be designed for localization rather than embedded ad hoc in business logic.

## Scope for the minimal stage

The minimal stage does not need a fully mature localization platform, but it must avoid decisions that would block one later.

### In scope now

- English and Korean support for operator UI text
- English and Korean support for validation and error messages
- Locale-aware response messaging where needed
- Message-key oriented design
- Locale testing expectations

### Out of scope for now

- Full translation management platform
- Runtime translation editing UI
- Pluralization rules beyond what the minimal stage needs
- Third-language support

## Supported locales

- `en`
- `ko`

If an unsupported locale is requested, the system should fall back predictably.

## Fallback behavior

- Default fallback locale should be `en`
- Unsupported locale inputs should not break processing
- API responses should retain stable error codes even when locale fallback occurs
- Locale fallback should be testable and visible in logs where useful

## Design principles

### Separate codes from messages

- Validation and error logic should produce stable machine-readable codes
- User-facing English and Korean messages should be resolved separately from those codes

### Keep text out of business logic

- Avoid scattering human-readable messages directly inside service logic
- Prefer message keys or centrally managed message maps

### Design for both API and UI

- UI labels, headings, and notices should be localizable
- API error payloads should be able to return locale-aware messages while preserving stable codes

### Treat encoding as a quality gate

- UTF-8 must be used consistently
- Korean corruption, mojibake, or partial character breakage must block completion of a change

## Suggested minimal implementation shape

The minimal stage can start with a simple application-level message catalog approach.

### Suggested structure

- `app/i18n/` for locale files or message maps
- message keys grouped by concern such as `common`, `validation`, `ingest`, and `ui`
- locale resources for `en` and `ko`

### Example shape

```text
app/
  i18n/
    en.py
    ko.py
```

Or:

```text
app/
  i18n/
    en.json
    ko.json
```

The exact storage format is less important than the separation of codes from translatable text.

## Message design rules

- Keep machine-readable codes stable and short
- Keep human-readable English and Korean messages concise and operationally clear
- Avoid embedding variable data in a way that makes translation awkward
- Prefer named placeholders

Example:

- Code: `missing_required_field`
- English: `A required field is missing.`
- Korean: `필수 항목이 누락되었습니다.`

## UI expectations

- Navigation labels should be localizable
- Dashboard cards and table headings should be localizable
- Exception and validation messages visible to operators should be localizable
- Do not hard-code future-visible English strings broadly across templates

## API expectations

- Request locale may come from an explicit `locale` field, header, or application default
- Response payloads should preserve stable machine-readable codes
- Localized human-readable messages should be added as a separate field

Suggested pattern:

```json
{
  "error_code": "missing_required_field",
  "message": "A required field is missing.",
  "locale": "en"
}
```

Or in Korean:

```json
{
  "error_code": "missing_required_field",
  "message": "필수 항목이 누락되었습니다.",
  "locale": "ko"
}
```

## Testing expectations

- Every user-facing addition should consider both `en` and `ko`
- Unsupported locale fallback should be tested
- UTF-8 integrity should be checked for any changed multilingual file
- Regression testing should include at least one English path and one Korean path when locale-sensitive behavior is touched

## Minimal-stage acceptance criteria

Internationalization support for the minimal stage is acceptable only when:

- English and Korean user-facing text can be supported without structural rewrite
- Stable machine-readable codes are separate from translated messages
- UTF-8 integrity is preserved
- Locale fallback behavior is defined and testable

