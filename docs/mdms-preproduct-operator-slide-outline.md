# MDMS Preproduct Operator Slide Outline

## Purpose

This outline converts the operator manual into a presentation-friendly structure.

It is intended as the source outline for a future `pptx` deck.
The first deck should be image-first, using the screen captures listed in the
capture checklist.

## Slide 1. Title and scope

- title
  - `MDMS Preproduct Operator Manual`
- subtitle
  - bounded internal-use operating guide
- speaker focus
  - what this system currently supports
  - who should use `admin` versus `operator`
- suggested visual
  - cover slide only or a simple dashboard background image later

## Slide 2. System at a glance

- PostgreSQL
- Flask web UI
- adapter queue commands
- HES, adapter, VEE, replay, export, and operational-event as the main operator
  objects
- suggested visual
  - simple system block diagram or dashboard plus HES detail thumbnail

## Slide 3. Startup procedure

- verify PostgreSQL
- activate environment
- first-time bootstrap commands only when needed
- start `make run`
- run adapter queue commands in separate shells when needed
- post-start checks
- suggested visual
  - terminal command snapshot plus login or health endpoint capture

## Slide 4. Shutdown procedure

- check in-flight replay, export, and adapter work
- stop worker shells first
- stop Flask
- stop PostgreSQL only when appropriate
- restart after abnormal stop
- suggested visual
  - detail page showing processing state or a simple checklist panel

## Slide 5. Daily opening checklist

- log in
- open dashboard
- review open alerts
- review recent operational events
- identify stale adapters, failed replay, failed export, or blocking VEE
- suggested visual
  - dashboard with alert and event sections visible

## Slide 6. HES and adapter operations

- HES list and detail
- adapter list and detail
- `Enable`, `Pause`, `Run Once`
- runtime versus human actor interpretation
- suggested visual
  - HES detail and adapter detail

## Slide 7. Master data minimum

- service point
- device
- measuring component
- installation history
- why mapping fails when these are missing
- suggested visual
  - master-data page with actor visibility and empty-state guidance

## Slide 8. Raw, canonical, and final lineage

- review raw reads and raw events first
- confirm canonical progression
- confirm final authoritative state
- use lineage screens to trace one sample end to end
- suggested visual
  - canonical or final measurement detail/list capture

## Slide 9. VEE exception triage

- start from the queue
- prioritize blocking items
- use detail view for blocked reason, event context, and next action
- understand re-evaluate versus correction
- suggested visual
  - VEE exception queue and detail

## Slide 10. Estimation and manual edit

- when to use each correction path
- what to confirm after execution
- audit detail, actor lineage, memo, result code, and downstream impact
- suggested visual
  - estimation audit detail and manual-edit audit detail

## Slide 11. Replay and billing export

- replay request create, monitor, and cancel
- billing export create, inspect, rerun, recreate, or cancel
- processing state versus failed state versus quiet state
- suggested visual
  - replay request detail and billing export request detail

## Slide 12. Operational events and accountability

- operational-event timeline
- action snapshot
- created actor and updated actor on admin-managed rows
- user action audit evidence meaning
- suggested visual
  - operational-event detail plus HES or master-data actor visibility

## Slide 13. Incident quick guide

- stale adapter
- failed replay
- failed export
- blocking VEE
- missing master data
- suggested visual
  - two-column quick triage table

## Slide 14. Daily closing and limitations

- end-of-day checks
- whether to keep the local environment running
- current preproduct limitations
- escalation posture for repeated failures
- suggested visual
  - closing checklist or known-limitations summary

## Packaging notes

For the first training deck:

- prefer Korean UI captures
- use the same account names consistently across screenshots
- mask secrets, credentials, and environment-specific identifiers
- keep one wide desktop viewport across the whole deck
- reserve space for captions that explain what the operator should look at first
