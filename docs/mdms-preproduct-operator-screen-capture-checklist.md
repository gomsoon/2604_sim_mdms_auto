# MDMS Preproduct Operator Screen Capture Checklist

## Purpose

This checklist defines the screenshots that should be captured before creating a
screen-centered operator `pptx`.

It should be used together with:

- [mdms-preproduct-operator-manual.md](/home/tprover/2604_sim_mdms_auto/docs/mdms-preproduct-operator-manual.md)
- [mdms-preproduct-operator-slide-outline.md](/home/tprover/2604_sim_mdms_auto/docs/mdms-preproduct-operator-slide-outline.md)

## Capture rules

Use these rules consistently:

- prefer Korean UI labels for the first presentation baseline
- use one stable desktop viewport size across all captures
- mask passwords, secret references, and sensitive environment values
- use stable demo or bounded internal-use data
- keep account names consistent across screenshots
- capture the most representative state, not every possible variant

## Recommended screen set

### 1. Login screen

- purpose
  - show the operator entry point
- preferred state
  - clean login form
- notes
  - do not expose real credentials

### 2. Dashboard normal state

- purpose
  - show the first daily opening screen
- preferred state
  - summary cards, open alerts, and recent events visible together

### 3. Dashboard attention-needed state

- purpose
  - show what an operator should notice first when action is needed
- preferred state
  - one or more open alerts, stale or failed indicator, recent event trail

### 4. HES detail

- purpose
  - show the HES-first operating surface
- preferred state
  - linked adapters, recent batches, recent events, actor visibility

### 5. Adapter detail

- purpose
  - show runtime state and operator controls
- preferred state
  - `Enable`, `Pause`, `Run Once`, recent runs, last error, watermark summary

### 6. Master data page

- purpose
  - show minimum master context and actor visibility
- preferred state
  - at least one populated row with `생성 주체` or `마지막 수정 주체`

### 7. Raw read or raw event visibility

- purpose
  - show source ingest visibility
- preferred state
  - recent batch, identifiers, and timestamps visible

### 8. Canonical measurements

- purpose
  - show normalized progression after ingest
- preferred state
  - representative canonical row with lineage columns or filters visible

### 9. Final measurements

- purpose
  - show authoritative result visibility
- preferred state
  - current final row or final lineage context visible

### 10. VEE exception queue

- purpose
  - show triage starting point
- preferred state
  - blocking and non-blocking cues, filters, spotlight wording

### 11. VEE exception detail

- purpose
  - show blocked reason, next-step guidance, and related lineage
- preferred state
  - correction actions visible, action or result guidance visible

### 12. Estimation audit detail

- purpose
  - show correction accountability
- preferred state
  - actor, memo, result code, blocked reason or result summary visible

### 13. Manual edit audit detail

- purpose
  - show manual correction accountability
- preferred state
  - actor, memo, result code, value change, lineage visible

### 14. Replay request list

- purpose
  - show queue-style request monitoring
- preferred state
  - status, progress, requester, spotlight helper visible

### 15. Replay request detail

- purpose
  - show request scope, progress, current item, and failed items
- preferred state
  - one representative request with visible progress and item sections

### 16. Billing export request list

- purpose
  - show export lifecycle overview
- preferred state
  - status hint, progress, actor, and spotlight helper visible

### 17. Billing export request detail

- purpose
  - show export request deep inspection
- preferred state
  - summary, progress, current item, failed items, and action context visible

### 18. Operational event detail

- purpose
  - show accountability and action snapshot
- preferred state
  - action snapshot plus raw JSON details section visible

## Optional supporting captures

- HES list
- adapter list
- usage transaction detail
- bill determinant detail
- bill charge detail
- empty-state examples for selected high-traffic views

## Packaging recommendation

When the first `pptx` is assembled:

- prefer one screenshot per slide for the main workflow slides
- use two smaller screenshots only when the comparison itself is the teaching
  point
- add a short caption explaining what the operator should check first in that
  screen
