# MVP Known Limitations

## Purpose

This document captures the operating limitations that are accepted at MVP
close-out.

These limitations should be visible to internal operators before first use.

## Estimation

- estimation remains intentionally narrow
- synthetic missing-interval repair supports single-slot cases only
- bulk estimation does not exist
- approval and preview workflow do not exist

Operator implication:

- unsupported estimation cases should stay in guided manual handling or backlog
  review rather than ad hoc workaround logic

## Manual edit

- manual edit remains substitution-oriented
- bulk manual edit does not exist
- approval workflow does not exist
- compare-and-preview workspace does not exist

Operator implication:

- manual edit should be used for bounded, supported corrections rather than
  high-volume operational cleanup

## VEE and event policy

- multiplier handling remains guardrail-first rather than fully source-aware
- low-value policy remains intentionally narrow
- zero-value event-aware policy is not implemented
- duration-aware event windows are not implemented
- event-aware estimation and manual-edit policy remains intentionally narrow

Operator implication:

- some business-policy refinements still require operator judgment instead of
  full policy automation

## Auth and administration

- no user-management UI
- no password reset or account recovery flow
- no token or PAT baseline for non-browser clients
- authorization remains the first-slice `admin` versus `operator` split

Operator implication:

- account lifecycle remains admin- and CLI-assisted
- browser-session use is the expected MVP operating model

## Runtime and export

- worker or runtime registry is still string-based
- item-level actor lineage is intentionally deferred in some runtime and export
  areas
- billing export remains an internal staging flow rather than full downstream
  delivery integration

Operator implication:

- export should be treated as internal handoff staging, not as a fully
  reconciled outbound delivery system

## Out of scope for MVP close-out

- TOU determinants
- demand charge
- advanced tariff engine
- invoice rendering
- CIS integration
- MFA
- full account-management UI

## Escalation guidance

Escalate after close-out when:

- a limitation blocks normal internal use more than once
- the same operator workaround repeats across multiple service points or periods
- actor or audit visibility is insufficient for internal accountability
- a deferred policy gap becomes a recurring operational decision bottleneck
