---
name: new-entity
description: Author a new Entity Definition for Odum ERP Suite's metadata-driven engine (fields, permissions, workflow, hooks). Use this whenever the user asks to add, define, or model a new business object — an Invoice, Employee, Purchase Order, Student, Patient, Work Order, or any other entity — within an existing Odum App, or asks how entities/DocTypes work in this codebase. Also use it when the user is about to hand-write a CRUD endpoint, serializer, or permission check for a new model — the whole point of the metadata engine is that they shouldn't have to. Grounded in CLAUDE.md §5 and §12.
---

# Authoring a new Entity Definition

Odum ERP Suite's core differentiator (CLAUDE.md §5) is that business objects are *declared*, not hand-coded. Every entity (Invoice, Employee, Purchase Order, Student, Patient, Work Order, ...) is an Entity Definition that the metadata engine turns into a database table, a versioned REST API, generated UI, and enforced permissions/workflow. Custom Python is written **only** for real business logic in hooks — never for CRUD plumbing, serialization, or permission checks. If you find yourself about to hand-write any of those for a new entity, stop and define the entity instead.

Before authoring, check `CLAUDE.md` §5 in the repo root for the current version of this pattern — this skill mirrors it but the doc is the source of truth if they diverge.

## The Entity Definition shape

CLAUDE.md §5 gives this shape (YAML shown here; check the repo for whatever concrete file format/location the metadata engine actually expects once it exists — `core/metadata_engine/` per §18 — since none of this skill's YAML is meant to be a literal, load-bearing schema until that engine is built):

```yaml
entity: SalesInvoice
app: accounting
fields:
  - {name: customer, type: link, target: Customer, required: true}
  - {name: currency, type: link, target: Currency, default: company_currency}
  - {name: items, type: table, target: SalesInvoiceItem}
  - {name: grand_total, type: currency, computed: sum(items.amount)}
  - {name: status, type: select, options: [Draft, Submitted, Paid, Cancelled]}
permissions:
  - {role: Accountant, read: true, write: true, submit: true}
  - {role: SalesRep, read: true, write: false}
workflow:
  states: [Draft, Submitted, Paid, Cancelled]
  transitions:
    - {from: Draft, to: Submitted, action: post_to_gl}
hooks:
  before_save: [validate_customer_credit_limit]
  after_submit: [post_journal_entry, notify_customer]
```

Walk through each section when authoring a new entity:

- **`entity` / `app`** — the entity's name and which App owns it. An entity belongs to exactly one App; other Apps reference it via `link` fields or extend it (§7's extension pattern for industry Apps), never by redefining it.
- **`fields`** — each field needs at least a `name` and `type`. Common types from the doc: `link` (foreign key to another entity, needs `target`), `table` (child/line-item rows, needs `target`), `currency`, `select` (needs `options`), plus whatever scalar types the engine supports (text, number, date, etc.). A field can be `computed` (derived, like `grand_total: sum(items.amount)`) instead of stored input.
- **`permissions`** — per-role `read`/`write`/`submit` (and presumably `cancel`, per §13's mention of submit/cancel permissions) flags. This is what the engine enforces identically at both the API and UI layer (§13) — don't plan on a separate permission check anywhere else.
- **`workflow`** — `states` plus `transitions` with an optional `action` hook fired on transition. Not every entity needs a workflow section (simple master data like a Customer record may not have states) — only include it if the entity actually has a document lifecycle.
- **`hooks`** — lifecycle hooks (`before_save`, `after_submit`, and presumably others like `before_submit`, `after_save`, `on_cancel` by analogy — confirm against what the engine actually supports once built) that reference named Python functions. This is the *only* place custom logic goes for this entity.

## What gets auto-generated (so you know what not to hand-write)

From a completed Entity Definition, CLAUDE.md §5 says the engine generates:

- The PostgreSQL table and migration
- A typed, versioned REST endpoint (e.g. `/api/v1/accounting/sales-invoice`) with OpenAPI docs
- List/kanban/detail views in the SPA with correct field widgets
- Permission enforcement at both the API and UI layers
- Workflow state-machine enforcement

Do not hand-write a serializer, a CRUD view, a permission decorator, or a migration for a new entity's own table — if you're about to, that's a sign the entity definition is incomplete rather than a sign you need custom code. The only custom Python for a new entity is the hook function bodies referenced in `hooks`.

## Platform-wide field conventions to apply

These aren't part of the entity YAML shape itself but are conventions CLAUDE.md expects every relevant entity to follow — check each one before considering a new entity done:

- **Multi-company (§2, §12):** every *transactional* entity (things tied to a business transaction — invoices, orders, journal entries — as opposed to pure reference/lookup data) carries a `company_id`. Don't add this to entities that are genuinely company-agnostic (e.g., a shared Currency lookup table).
- **Multi-currency (§12):** any monetary field is modeled as `(amount, currency)`, not a bare number — and the exchange rate is timestamped/snapshotted onto the transaction at posting time so historical reports never reprice. The `grand_total` field in the example above would need this treatment if `currency` isn't already implied by the entity's own currency field.
- **Universal audit trail (§12):** every entity write is automatically versioned (who, when, before/after diff) at the ORM layer. This is not something to opt into per entity — don't add a bespoke "history" table or manual audit logging to a new entity; it's handled platform-wide.
- **AI-eligibility flags (§8.1, §8.4):** CLAUDE.md describes the *concept* — an entity declares which fields/actions are AI-eligible, and sensitive fields (salary, national ID, PHI) are flagged as excluded from AI context — but never shows a concrete key or syntax for either, even in its own canonical example. Don't invent one (e.g. don't make up an `ai_eligible: true` key as if it were real). Note the intent in a plain comment or in prose instead, and treat the actual schema key as an open gap for whoever builds the AI layer (§8) to define.
- **Geo fields (§5):** if the entity has a meaningful location, boundary, or path (a branch, a farm plot, a service area), use the dedicated `geopoint`, `geofence`/`polygon`, or `route`/`line` field types rather than plain lat/lng numbers — these are backed by PostGIS and automatically get a generated Map view (§5) that plain numeric fields wouldn't get.

## Child/line-item entities (the `table` field type)

CLAUDE.md's own canonical example uses a `table` field (`items: {type: table, target: SalesInvoiceItem}`) but never actually defines what `SalesInvoiceItem` looks like — so there's no documented spec for child/line-item entities, only the implication that they exist. When a new entity needs one, the reasonable inference (call it out as an inference, not a documented fact, when you write it) is:

- The child is its own full Entity Definition (its own `fields`, generated table, etc.), not a special case.
- It carries a back-link to its parent (e.g. a `parent` link field) so rows can be queried and rendered as the parent's embedded table.
- It typically doesn't need its own `permissions` or `workflow` section — access and lifecycle are governed by the parent entity — but don't state that as settled fact either; flag it the same way.

## Role names

CLAUDE.md's examples (`Accountant`, `SalesRep`) illustrate the *shape* of a `permissions` entry, not a fixed, platform-wide role registry — no such registry is documented. When a new entity needs a role that doesn't already appear elsewhere in the codebase, name it by analogy to existing examples and note that it's a new role being introduced, rather than assuming it already exists somewhere.

## Extension vs. new entity

If you're adding fields for an industry vertical (e.g., Legal Services adding matter-specific fields to something project-shaped), check CLAUDE.md §7 first — the intended pattern is that industry Apps **extend** an existing core entity via the metadata engine's inheritance/extension mechanism (§7) rather than defining a parallel entity that duplicates Customer, Invoice, or Employee concepts. Only define a wholly new entity when the concept genuinely doesn't exist yet in any App the new one depends on.
