# UI-0B — Static Application Shell

## Status

Non-production, repository-owned static prototype.

This directory implements the UI-0B shell defined by `docs/ui-0a-visual-foundation-application-shell-contract.md` without creating runtime authority.

## Scope

UI-0B contains only:

- semantic HTML for the Teacher Review workspace regions;
- dependency-free CSS for the visual system and responsive layout;
- static keyboard-accessible mobile disclosure controls for Issues and Structured Edit;
- disabled presentation controls for future edit and transport areas;
- explicit disconnected/locked states;
- a restrictive Content Security Policy that blocks scripts, network connections, forms, frames, and objects.

Required shell regions:

- Issues;
- Score View;
- Structured Edit;
- Source Evidence;
- Review Transport;
- Validation / Revision Status.

## Responsive behavior

Score View remains the primary region. At narrow widths, Issues and Structured Edit are collapsed by default behind keyboard-accessible checkbox/label disclosure controls. Source Evidence remains visible in the stacked flow. This is presentation-only behavior and does not require JavaScript or runtime state.

## Isolation guarantees

UI-0B does **not**:

- connect to the OMR Gateway, Teacher Review API, engines, storage, or any external service;
- load MusicXML, Canonical Score, source PDF/image artifacts, or review evidence;
- create jobs, revisions, approvals, or publication state;
- implement upload;
- execute JavaScript;
- implement rendering, editing, playback, cursor behavior, authentication, or RBAC;
- add a package manager, framework, dependency, build step, deployment target, or server;
- modify `compose.yaml`, service code, schemas, workflows, or production configuration.

The official logo asset is not packaged here. UI-0B uses a lightweight textual/visual brand placeholder derived from the approved visual direction only. Logo asset packaging remains a separate reviewed package.

## Viewing

Open `index.html` directly in a browser. No local server or installation is required.

## Verification

`tests/test_ui_0b_static_shell.py` checks the static isolation contract with Python standard-library parsing. It verifies required regions, disabled controls, restrictive CSP directives, the absence of scripts, forms, frames, remote URLs and CSS URL loads, and the narrow-screen disclosure contract.

UI-0B must remain replaceable and must not become a parallel production application architecture.
