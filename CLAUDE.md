# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project status

This repository currently contains no code — only hackathon brief and reference materials. There is no build, lint, or test tooling yet. When code is added, update this file with real commands and architecture notes (don't invent them now).

## Repository layout

- `doc/Factored AI & Data Hackathon 2026.md` — the competition problem statement. Read this first; it defines scope and constraints for any implementation work in this repo.
- `doc/LATAM_Bank_Complete_Data_Dictionary.pdf` — schema/field reference for the supplied banking dataset.
- `doc/LATAM_Bank_Dataset_Summary.pdf` — summary/profile of the supplied dataset.
- `doc/Datathon_2026_Kickoff.pdf` — kickoff/event slides.
- `spec/` — currently empty; intended location for design specs as the solution takes shape.

## Challenge context (from the problem statement)

The task is to build an AI-first banking customer-service prototype for a chosen workflow (e.g. account/payment inquiries, card-service support, dispute intake, or credit eligibility support), using only the organizer-supplied data.

Key constraints future work in this repo must respect:

- **Scope**: pick one coherent workflow; depth and engineering judgment matter more than breadth. Must demonstrate a normal resolution path, an ambiguous/unsupported request, and a case requiring human handoff. Must show Spanish and Portuguese interactions.
- **Controlled automation**: policy/permission enforcement must live outside model-generated prose (deterministic guardrails, not just prompting). The model must never invent eligibility rules or approve credit; credit eligibility must go through a separate, clearly-labeled rules/policy component.
- **Data boundaries**: only organizer-approved data; no real customer records, credentials, or restricted data. Identity must be established via a trusted test session/identity service, never by ID/customer number alone.
- **Evaluation**: any proposed system needs a baseline comparison on a held-out set, with explicit reporting of safe automated resolution rate, containment, escalation quality, unsafe outcomes, and latency/cost — including failure cases (bad data, expired sessions, prompt injection, tool failures, multilingual ambiguity).
- **No live money movement or lending decisions** are required or authorized.

Consult the full text in `doc/Factored AI & Data Hackathon 2026.md` before making architectural decisions — it contains detailed requirements this summary omits.
