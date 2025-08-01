# Core Instructions

1. **Read ************************`DESIGN.md`************************ first.**
   It is the authoritative overview of architecture, data models, directory layout, and UI conventions. Get the big picture there before touching code.

2. **What AGENTS.md is for.**
   This file is a *quick‑lookup map* that tells you where in the repo to find implementation details your agents depend on.

3. **Keep this file current.**
   When you add, move, or rename modules, update the lookup table below so the map stays accurate.

4. **Sync with ************************`DESIGN.md`************************.**
   Any change that affects the core design—architecture diagrams, data contracts, deployment assumptions—**must** be reflected in both the code *and* `DESIGN.md`. Update that doc first, then reference the change here if agent developers should know about it.

5. **Maintain the Changes History.**
   After **any meaningful update to the repository**  append a row to the *Changes History* table describing **what** changed and **why**. Keep both rows as concise as possible.

# Quick Lookup Table

| Topic                          | Look in…                                |
| ------------------------------ | --------------------------------------- |
| Streamlit page flow            | `src/label_app/ui/pages/`               |
| Task‑type renderers            | `src/label_app/ui/components/*_view.py` |
| Domain services (Git, auth, …) | `src/label_app/services/`               |
| Data models & item schemas     | `src/label_app/data/models.py`          |
| Project YAML schema            | See **§6** of `DESIGN.md`               |

---

# Changes History

| Change                                                                                      | Reason                                                                      |
| ------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------- |
| Initial creation of `AGENTS.md` with core instructions, lookup map, and history guidelines. | Provide a living reference for agent developers and ensure doc/code parity. |
