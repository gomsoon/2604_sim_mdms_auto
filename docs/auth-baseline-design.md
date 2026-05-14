# Auth Baseline Design

## Purpose

This document defines the first human-user authentication and authorization
baseline required before the current operator-facing MVP can be treated as
close-out ready.

The project already has broad internal operator workflows, correction actions,
and billing-lite staging actions. What is still missing is a minimal
user-account, login, and role boundary that can make those actions attributable
and controllable.

This baseline is intentionally small.

It aims to make the current MVP safe enough for internal use, not to introduce
a full enterprise identity platform.

## Why this is now required

The current repository already supports:

- operator-visible exception handling
- operator-triggered estimation
- operator-triggered manual edit
- async replay requests
- billing export cancel and recovery actions
- master-data and adapter administration actions

Without user identity and role boundaries, these actions remain attributable
only to free-form strings such as `operator_ui`, `api`, or `web_tester`.

That is no longer sufficient for MVP close-out.

The near-term goal is therefore:

1. require login for human-facing surfaces
2. distinguish at least `admin` from `operator`
3. record login and logout history
4. record actual user identity on sensitive business mutations
5. roll actor identity into existing persistence one functional unit at a time

## Baseline scope

### Included in the first auth slice

- `user_account` persistence
- `admin` and `operator` roles only
- `login_id + password` web login
- session-cookie authentication for human-facing web and API surfaces
- append-only login and logout history
- route protection for operator and admin surfaces
- sensitive-action authorization for at least:
  - VEE actions
  - estimation
  - synthetic missing-interval estimation
  - manual edit
  - replay request actions
  - billing export recovery and cancellation
  - master-data and adapter administration
- staged persistence updates so sensitive actions can store user-account
  lineage explicitly

### Explicitly out of scope for the first auth slice

- MFA
- password reset
- lockout or throttling policy beyond minimal defensive handling
- SSO or OIDC
- API tokens for machine users
- user self-service screens
- full RBAC matrix
- per-field permissioning
- external audit sink integration

## Roles

### `operator`

The first `operator` role is meant for human users who:

- review ingest and exception state
- acknowledge or resolve VEE exceptions
- trigger estimation and manual edit
- request or inspect replay
- inspect billing-lite outputs

### `admin`

The first `admin` role is meant for human users who:

- maintain master data
- control adapters and HES runtime configuration
- manage billing context and tariff assignment
- perform billing export recovery or cancellation
- manage user bootstrap and environment-level operations

### Why only two roles first

The existing workflow documents describe more nuanced operator personas such as
data operations operator, master-data operator, and technical support operator.

For the first slice, these should all map to `operator`.

The goal is to create a hard boundary between:

- business correction and monitoring work
- system configuration and external handoff work

without designing a large permission taxonomy too early.

## Persistence baseline

### `user_account`

Recommended minimum fields:

- `id`
- `login_id`
- `password_hash`
- `display_name`
- `role_code`
- `is_active`
- `last_login_at`
- `password_changed_at`
- `details`
- `created_at`
- `updated_at`

Recommended first constraints:

- unique `login_id`
- `role_code in ('admin', 'operator')`
- `is_active` default `true`

### `auth_session_audit`

Recommended minimum fields:

- `id`
- `user_account_id` nullable for failed login attempts before a user is
  resolved
- `login_id_attempted`
- `auth_event_type`
- `session_identifier`
- `auth_channel`
- `ip_address`
- `user_agent`
- `result_code`
- `details`
- `occurred_at`
- `created_at`

Recommended first event types:

- `login_succeeded`
- `login_failed`
- `logout`
- `session_expired`

Recommended first channel values:

- `web_session`
- later `api_session` or `api_token`

## Login and logout history

### Existing mechanism review

The repository already has `operational_event` as a broad operator-facing event
timeline.

That mechanism is useful for visibility, but it is not the right authoritative
store for security-sensitive login and logout history because:

- auth history should remain append-only and queryable by account
- failed login attempts may exist before the user is resolved
- session identifiers and user agents are more specific than normal operational
  events

### Recommended direction

Use **two layers**:

1. `auth_session_audit` as the authoritative append-only login/logout history
2. optional `operational_event` mirroring for operator-visible auth timeline
   entries

This keeps security-grade traceability separate from general operations
visibility while still reusing the existing event timeline where it helps.

### First-slice rule

The first implementation should require `auth_session_audit`.

Mirroring into `operational_event` can happen in the same slice if it remains
small, but it is not required for the first persistence baseline.

## Broader user activity audit

### Why login history alone is not enough

Once human-user authentication exists, the repository should be able to answer
questions like:

- which account viewed a sensitive exception or export request
- which account created, changed, or cancelled an operational object
- which account triggered estimation, manual edit, replay, or recovery
- which account used a master-data administration screen

This is broader than login and logout history.

It is also broader than the current business-specific audit tables, because
those tables usually record only selected mutation events and do not cover all
read or navigation activity.

### Existing audit mechanisms and how to use them

The repository already has several useful audit or traceability layers:

- `estimation_audit`
- `manual_edit_audit`
- `vee_exception` action fields
- replay request persistence
- billing export request persistence
- `operational_event`

These should be **reused and expanded**, not replaced.

Recommended role split:

1. `auth_session_audit`
   - authoritative for login, logout, failed login, and session lifecycle
2. domain-specific audit tables
   - authoritative for business mutations inside their bounded context
3. new generic `user_action_audit`
   - authoritative for cross-cutting user activity across read, create, update,
     delete, and execute actions
4. optional `operational_event` mirroring
   - timeline visibility only for selected important actions

### Recommended new table: `user_action_audit`

Recommended minimum fields:

- `id`
- `user_account_id`
- `auth_session_audit_id` nullable
- `action_type`
- `resource_type`
- `resource_id`
- `request_method`
- `request_path`
- `status_code`
- `outcome_code`
- `ip_address`
- `user_agent`
- `details`
- `occurred_at`
- `created_at`

Recommended first action types:

- `read`
- `create`
- `update`
- `delete`
- `execute`
- `login`
- `logout`

Recommended first resource-type examples:

- `vee_exception`
- `estimation_audit`
- `manual_edit_audit`
- `vee_replay_request`
- `billing_export_request`
- `service_point`
- `device`
- `adapter_instance`
- `hes_system`
- `dashboard`

### Audit coverage expectation

The medium-term expectation should be:

- every login-protected web or API feature is attributable to one
  `user_account`
- every sensitive mutation remains traceable both through:
  - generic `user_action_audit`
  - and its domain-specific audit or persistent mutation record
- important reads are attributable through `user_action_audit` even where no
  business mutation happened

This means the system can audit all major existing feature usage by account
without forcing every persistence table to become a general-purpose audit log.

## Session and route model

### Authentication mode

The first human-user authentication mode should be Flask session cookies.

This is preferred over introducing token auth immediately because:

- the current product is strongly operator-UI oriented
- most new protected surfaces are browser-driven
- it keeps the first close-out slice small

### Route policy

Anonymous access should remain allowed only for:

- `/login`
- `/logout`
- health
- receive-adapter machine endpoints that already use shared-secret
  authentication

All other human-facing web routes should require login.

Human-facing API routes should also require login in the first slice, while
machine endpoints continue to use their existing shared-secret flow.

## Sensitive action audit

The current repository already records many sensitive actions through free-form
actor strings.

Examples include:

- `VeeException.acknowledged_by`
- `EstimationAudit` actor snapshots through `estimated_by`
- `ManualEditAudit.edited_by`
- `VeeReplayRequest.requested_by`
- `BillingExportRequest.requested_by`
- cancellation and recovery actor details stored in JSON `details`

The auth baseline should not try to replace every actor field in one migration.

Instead, user-account lineage should be introduced one feature unit at a time.

At the same time, broad user activity logging should start from the first auth
slice through `user_action_audit`, so that read and navigation behavior is not
left completely untracked while domain-specific actor FKs are still being added
incrementally.

## Phased actor identity propagation

### Principle

Do not change most persistence tables in one large sweep.

Instead:

1. introduce `user_account`
2. make login mandatory
3. propagate user-account identity through one large functional unit at a time
4. keep legacy string actor columns temporarily while new `*_user_account_id`
   columns are introduced

This allows audit continuity without destabilizing the whole repository.

### Regression rule

Every actor-identity propagation phase must update regression coverage in the
same slice.

That means when one functional unit gains explicit `user_account` lineage:

1. the affected persistence fields must be added or updated
2. the corresponding service layer must start writing real user identity
3. the web and API action tests must verify the authenticated actor is stored
4. the visibility or detail tests must verify the new lineage is readable

This rule is important because actor identity will be introduced gradually
across many already-implemented features.

Without slice-by-slice regression updates, the repository would accumulate a
mixed and fragile audit model that is difficult to trust.

### Phase A. Auth core

Tables:

- `user_account`
- `auth_session_audit`
- `user_action_audit`

Behavior:

- login
- logout
- session expiry logging
- `g.current_user`
- navbar identity
- baseline activity logging for authenticated routes

### Phase B. VEE and correction

Tables and fields to introduce first:

- `vee_exception`
  - `acknowledged_by_user_account_id`
  - `resolved_by_user_account_id`
- `estimation_audit`
  - `estimated_by_user_account_id`
- `manual_edit_audit`
  - `edited_by_user_account_id`
- `vee_replay_request`
  - `requested_by_user_account_id`
  - `cancelled_by_user_account_id`

Reason:

These are the most sensitive and most operator-driven business mutations in the
 current MVP loop.

Required regression update scope:

- VEE action web and API tests
- estimation service and visibility tests
- manual edit service and visibility tests
- replay request service and visibility tests where actor identity changes
- generic user-action audit tests for related read and execute flows

### Phase C. Billing export and recovery

Tables and fields:

- `billing_export_request`
  - `requested_by_user_account_id`
  - `cancelled_by_user_account_id`
  - `recovery_requested_by_user_account_id`
    or equivalent explicit lineage fields depending on final schema shape

Reason:

Export cancellation and recovery affect downstream handoff and should not rely
only on free-form strings in `details`.

Required regression update scope:

- export request creation tests
- export cancel and recovery action API tests
- export list and detail visibility tests
- payload and lineage assertions where user-account identity becomes explicit
- generic user-action audit tests for export read and recovery routes

### Phase D. Master-data and system administration

Tables and fields:

- `device`
- `service_point`
- `measuring_component`
- `installation_history`
- `hes_system`
- `adapter_instance`
- `service_point_billing_context`
- `service_point_tariff_assignment`

Recommended first pattern:

- `created_by_user_account_id`
- `updated_by_user_account_id`

Reason:

This area is broad and invasive, so it should follow the correction and export
units rather than block the initial auth close-out.

Required regression update scope:

- master-data service and web tests
- HES and adapter administration tests
- any affected dashboard or visibility tests that surface admin lineage
- generic user-action audit tests for administrative reads and mutations

### Phase E. Broader actor cleanup

Once the phased FK rollout is stable:

- reduce reliance on free-form string actor columns
- keep them only where worker or machine identity is genuinely different from a
  human user
- preserve existing text actor fields temporarily where backward compatibility
  helps

## UI baseline

### Required first screens

- `/login`
- logout action

### Required first navbar behavior

- show current display name or login id
- show role badge
- show logout action

### Authorization UX

For the first slice:

- hide clearly unauthorized action buttons where practical
- still enforce authorization server-side with `403`

This avoids implying capability while keeping the server as the real control
boundary.

## First authorization matrix

### `operator`

Allowed:

- read all current operator screens
- acknowledge and resolve VEE exceptions
- run estimation and synthetic repair
- run manual edit
- create and inspect replay requests
- inspect billing-lite outputs

Not allowed:

- master-data mutation
- adapter enable, pause, run-once
- billing export recovery and cancellation
- HES configuration mutation

### `admin`

Allowed:

- everything `operator` can do
- master-data mutation
- adapter and HES administration
- billing context and tariff assignment mutation
- billing export cancel, rerun, recreate
- user bootstrap and account administration

## Recommended implementation order

1. `user_account` and `auth_session_audit` ORM plus migration
2. password hashing and session login service
3. `/login` and `/logout`
4. route guards for web and human-facing API
5. navbar identity
6. baseline `user_action_audit` logging for authenticated routes
7. `operator` versus `admin` role guards
8. Phase B actor FK propagation for VEE and correction
9. Phase C actor FK propagation for billing export and recovery
10. CLI bootstrap user flow
11. optional auth-event mirroring into `operational_event`

## Deferred backlog for later auth maturity

- MFA
- password reset and enrollment flow
- API token baseline
- lockout and throttling policy
- richer role model beyond `admin` and `operator`
- auth-event analytics dashboard
- user management UI
- external identity provider integration
