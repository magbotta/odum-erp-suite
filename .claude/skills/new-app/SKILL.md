---
name: new-app
description: Scaffold a new Odum ERP Suite App (a core module like Accounting/CRM, or an installable industry module like Manufacturing/POS/Microfinance). Use this whenever the user asks to add, create, or scaffold a new App, module, or vertical for the Odum ERP Suite platform — including phrases like "add a new core module", "scaffold the Manufacturing app", "start the Warehouse App", or "set up a new industry app for X". Also use it when the user is unsure whether new functionality belongs in an existing App or needs its own — this skill explains the App boundary rules that make that call. Grounded in CLAUDE.md §2, §5, and §18.
---

# Scaffolding a new App

In Odum ERP Suite, every unit of functionality — core module or industry vertical — is packaged as an **App** (CLAUDE.md §2, "Everything is an App"). This skill walks through what a new App needs and, more importantly, the boundary rule that keeps 10+ Apps from turning into a shared ball of mud as more of them get built by different contributors.

Before scaffolding, read the relevant sections of `CLAUDE.md` at the repo root if it's not already in context — §2 (Architecture Principles), §5 (Metadata-Driven Extensibility Framework), and §18 (Suggested Repository Structure) are the ones this skill is built from. If CLAUDE.md has evolved since this skill was written, trust the file over this skill.

## The one rule that matters most

**An App's code must never import another App's models directly, and must never run raw SQL against another App's tables.** All cross-App interaction goes through the internal event bus or a declared public service interface (CLAUDE.md §2, principle 3).

This isn't a style preference — CLAUDE.md describes it as mechanically enforced in CI via import-linter-style contracts that fail the build on a direct cross-App model import, plus a migration-time check that blocks a migration from touching a table outside the App that owns it. When scaffolding a new App, set this up as a real constraint from the first commit, not something to retrofit later:

- If the new App needs data from another App (e.g., Manufacturing needs Warehouse stock levels), call that App's public service interface, not its ORM models.
- If the new App needs to react to something happening in another App (e.g., Payroll reacting to an Attendance record being finalized), subscribe to that event on the internal event bus rather than polling or joining across App tables.
- Declare the dependency explicitly (see below) rather than importing quietly — a Manufacturing App that needs Warehouse and Accounting says so up front, the same way a Python package declares its dependencies.

If you're not sure whether the functionality you're adding belongs in an existing App or needs a new one, the test from CLAUDE.md §7's industry-module table is: does it **extend** an existing App's core entities (Customer, Invoice, Employee, etc.) without needing new calculation/compliance logic those Apps don't already have? If yes, it's very likely a feature *within* an existing App. If it needs genuinely new shared capability — CLAUDE.md's own examples are Microfinance needing a loan-amortization engine (§7.1) and Legal Services needing a trust-accounting ledger type (§7.3) — it's a new App, possibly one that itself needs a small new core capability alongside it.

## What a new App needs

Per CLAUDE.md §5 ("Apps are the unit of packaging") and the repo layout in §18, a new App is a directory under `apps/<app_name>/` containing:

1. **Entity definitions** — one or more Entity Definition files (see the companion `new-entity` skill for the authoring workflow and YAML shape from §5). These are what the metadata engine turns into tables, APIs, and UI.
2. **Hook implementations** — the actual Python business logic referenced by each entity's `hooks` section (`before_save`, `after_submit`, etc.) — this is where custom code belongs, not in hand-written CRUD or serialization.
3. **Optional custom UI screens** — only for the cases CLAUDE.md §5 calls out as genuinely needing bespoke UX (the POS terminal, Gantt charts, financial statement layouts are its own examples) rather than the generated form/list/kanban/report views. Per §5, these ship as an independently versioned frontend bundle loaded by the SPA shell at runtime, not compiled into the core frontend build — so a new App's custom screen (if any) should be structured to be added/updated without a full frontend rebuild.
4. **Database seed data** — reference/lookup data the App needs to be usable out of the box (e.g., a default chart of accounts, standard tax categories).
5. **Its own test suite** — scoped to the App, exercising its entities, hooks, and any public service interface it exposes to other Apps.
6. **A declared dependency list** — which other Apps this one builds on (e.g., "Manufacturing depends on Warehouse and Accounting", CLAUDE.md §5). This is what a self-hoster's install process uses to pull in only what's needed — an education nonprofit installs Core + Nonprofit + SIS and skips Manufacturing, Telecom, Microfinance, Legal Services, and Insurance entirely (§5).

If this is a **core** App (one of Accounting, Asset Management, CRM, HRM, Payroll, Project Management, Purchasing, Sales, Warehouse, Website, Expense & Travel — CLAUDE.md §6), it ships enabled by default. If it's an **industry** App (Manufacturing, POS, Education/SIS, Healthcare/HIS, Agriculture, Nonprofit, Telecom, Government, Microfinance, Legal Services, Insurance — §7), it's installable/optional and should extend core Apps' entities rather than duplicating concepts like Customer, Invoice, or Employee (§7's explicit warning against "13 different definitions of a Contact").

## Directory shape

Following §18's suggested repo structure, a new App lives alongside its siblings under `apps/`:

```
apps/
├── <existing apps...>
└── <new_app_name>/
```

Check `CLAUDE.md` §18 for the current full list of App directories (both shipped core Apps and already-planned industry Apps) before naming a new one, so it lines up with the existing naming convention (snake_case, matches the App's role — e.g. `education_sis`, `healthcare_his`).

## Before you start writing code

Since the metadata engine, event bus, and CI boundary-enforcement tooling described in §2/§5/§18 may not exist yet this early in the project (check `core/metadata_engine/`, `core/platform_api/` for what's actually implemented), don't invent scaffolding commands or tooling that CLAUDE.md doesn't describe. If no `odum` CLI or app-generator script exists yet, treat this skill as the manual checklist above rather than assuming a one-command scaffold — and if you end up hand-building the same App skeleton more than once, that's a signal a real scaffolding script is worth writing (and should probably live in `core/` per §18, or in `scripts/`, with this skill updated to call it).

CLAUDE.md states the *rule* for cross-App interaction (public service interface or event bus, §2) without ever specifying the concrete mechanism — no base class, decorator, or registration pattern is documented anywhere, and there's no documented file format for declaring an App's dependency list either (Entity Definitions have a documented YAML shape; App-level dependency declarations don't). Don't invent one to fill the gap. Until the metadata engine defines these:

- Expose a public interface as a plain Python module (e.g. `apps/<app>/services/`) with plain functions other Apps can import and call — simple, obvious, and easy to later formalize once a real pattern exists, rather than a speculative registration/decorator scheme nobody asked for.
- Declare an App's dependencies in its own `README.md` rather than a fake manifest file.
- If the App needs to react to another App's events (e.g., "notify Manufacturing when stock drops"), note it as an open gap rather than guessing at a subscription API — CLAUDE.md doesn't specify one yet.

Flag all of these as placeholders (a short note in the App's README is enough) so they're easy to find and replace once the real mechanisms are built, rather than letting them quietly calcify into the de facto pattern.

## Vertical-specific capability check

If the new App is one of the industry verticals CLAUDE.md flags as needing genuinely new platform capability beyond simple extension (currently: Manufacturing, Telecom, Microfinance, Legal Services, Insurance, Education, Healthcare, Government, Nonprofit — §7), read that App's dedicated subsection (§7.1 Microfinance, §7.2 POS device integration, §7.3 Legal Services are the ones fully written out as of this writing) before scaffolding, since it may require a new shared core capability (like a loan-amortization engine or a dedicated ledger type) rather than being pure entity definitions + hooks.
