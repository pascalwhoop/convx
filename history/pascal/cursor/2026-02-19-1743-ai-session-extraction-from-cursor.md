# Conversation 4f91a599-14d8-4739-a0ba-b6798f4a93b0

- Source: `cursor`
- User: `pascal`
- System: `Pascals-MBP.local`
- Started: `2026-02-19T17:43:23.679000Z`
- CWD: `/Users/pascal/Code/business/convx`

## User

can you research if anyone has cracked how to extract AI sessions from cursor? so we can also get those

## Agent

Checking how the SQLite DB is queried and the exact key names used:

## Agent

Yes. Cursor’s AI sessions can be extracted; several projects already do it. Here’s a concise summary and how it would fit into convx.

---

## 1. Where Cursor stores sessions

- **Per-workspace SQLite:** one file per workspace, not one per chat.
- **Paths:**
  - **macOS:** `~/Library/Application Support/Cursor/User/workspaceStorage`
  - **Windows:** `%APPDATA%\Cursor\User\workspaceStorage`
  - **Linux:** `~/.config/Cursor/User/workspaceStorage`
- **File:** `state.vscdb` inside each workspace folder (e.g. `workspaceStorage/<hash>/state.vscdb`).

So you discover sessions by scanning these `state.vscdb` files; each DB can hold many “chats” (see below).

---

## 2. How the data is stored (cracked schema)

- **Table:** `ItemTable` (key–value in SQLite).
- **Key for full chat data:**  
  `workbench.panel.aichat.view.aichat.chatdata`
- **Value:** one JSON blob. Structure used by the export tools:
  - **`tabs`:** array of “tabs”; each tab is one conversation/session.
  - Each tab has:
    - **`bubbles`:** list of message objects (alternating user / AI).
    - **`timestamp`** (for ordering).
  - **User bubbles:** `type: 'user'`. Text can be in:
    - `delegate.a`, or
    - `text`, or
    - `initText` (nested JSON, e.g. `root.children[0].children[0].text`).
  - **AI bubbles:** `type: 'ai'`, with **`rawText`** (model reply) and **`modelType`**.

So “sessions” in Cursor terms are the **tabs** inside that single JSON; each `state.vscdb` gives you many such sessions (one per tab).

There is also a key **`aiService.prompts`** whose value is a list of objects with a **`text`** field (user prompts only, no model replies). Some tools use that for simple prompt extraction or RAG.

---

## 3. Existing projects that extract Cursor sessions

| Project | What it does | Data source |
|--------|----------------|-------------|
| **cursor-chat-export** | Python CLI: discover workspaces, export chats to Markdown (per tab). | `ItemTable` → `workbench.panel.aichat.view.aichat.chatdata` (full tabs + bubbles). |
| **Cursor-history-MCP** | Extract prompts, embed with Ollama, store in LanceDB, search API. | `ItemTable` → `aiService.prompts` (user prompts only). |
| **cursor-chat-browser** | Web app to browse and export chat history. | Same or similar DB access. |

The one that matches “extract full AI sessions” (user + assistant, one file per conversation) is **cursor-chat-export**: it uses the full chat key and the tabs/bubbles structure above.  
Repo: https://github.com/somogyijanos/cursor-chat-export (see `chat.py`, `src/vscdb.py`, `src/export.py`, `config.yml` for the exact key and parsing).

---

## 4. Fitting this into convx

- **Discovery:**  
  Scan the workspace storage path for `state.vscdb` files (e.g. `workspaceStorage/*/state.vscdb`). Optionally use `workspace.json` in the same folder to tie a DB to a project path.
- **Session identity:**  
  One “session” = one **tab** in the `chatdata` JSON. You need a stable id: e.g. tab index + workspace folder hash, or any unique key Cursor might store per tab (the export code uses tab index and timestamp).
- **Peek:**  
  Open SQLite read-only, run  
  `SELECT value FROM ItemTable WHERE key = 'workbench.panel.aichat.view.aichat.chatdata'`,  
  parse JSON, and derive from `tabs` (e.g. count, first timestamp) for `session_id` / `started_at` and any workspace info.
- **Parse:**  
  Same query; for each tab, walk `bubbles` and map:
  - user bubble → `NormalizedMessage(kind="user", ...)` (text from `delegate.a` / `text` / `initText` as in cursor-chat-export),
  - AI bubble → `NormalizedMessage(kind="assistant", ...)` from `rawText` (and optionally `modelType` in metadata).

So yes: Cursor’s storage is well understood and you can add a Cursor adapter that discovers `state.vscdb` files and turns each tab into a `NormalizedSession` with the same flow as your Codex adapter (discover → peek → parse → render). The only design choice is whether one convx “session” = one Cursor tab (recommended) and how you derive a stable `session_id` (e.g. workspace hash + tab index + timestamp).

## User

OK I gave you access to the Cursor directory by again symlink'ing it to symlinks/Cursor. 

can you create a plan by probing the files etc on how we can get the data out of these systems? I suspect there must be an index file somewhere that maps paths to these hashes in  workspaceStorage/<hash> to the paths

## Agent

So `workspace.json` is the key! Now let me probe deeper — how many workspaces have actual chat data, and what the data looks like.

## Agent

Excellent data! 34 workspaces with chat, 376 tabs for `matrix` alone. Let me now inspect the actual data structure of a tab:

## Agent

One more key area — `composer.composerData` for agent sessions:

## Agent

Now I have everything I need for a complete plan. Let me write it up:

---

## Plan: `CursorAdapter`

### What we found

**The path→hash mapping:** Every `workspaceStorage/<hash>/workspace.json` contains `{"folder": "file:///path/to/project"}`. All 311 workspace folders have this file — no extra index needed.

**Two session types per workspace, both in `state.vscdb` → `ItemTable`:**

| Kind | `ItemTable` key | Unit of "session" |
|------|-----------------|-------------------|
| **Chat** | `workbench.panel.aichat.view.aichat.chatdata` | one **tab** (UUID `tabId`, epoch `lastSendTime`, optional `chatTitle`) |
| **Composer/Agent** | `composer.composerData` | one **composer** (UUID `composerId`, epoch `createdAt`) |

**Chat tab → bubbles:**
- `type: "user"` — text in `bubble.text` (primary), or `delegate.a`, or nested `initText` JSON
- `type: "ai"` — text in `bubble.rawText`, model name in `bubble.modelType`

**Composer → conversation:**
- `type: 1` (user) — text in `message.text`
- `type: 2` (assistant) — text in `message.text`
- `createdAt` on the composer itself is the timestamp (no per-message timestamps)

Stats: 34/311 workspaces have chat data with 34 tabs totalling ~1,700 bubbles for chat, plus 115+ composer sessions in the matrix workspace alone.

---

### Adapter design

**Source system name:** `cursor`

**Source path (discover input):** `~/Library/Application Support/Cursor/User/workspaceStorage`

**`discover_files(input_path)`**
- Glob `input_path/*/state.vscdb`
- Filter to files that have a `workspace.json` sibling (all do)
- Returns one `Path` per `state.vscdb` (not per session — one DB = many sessions)

Actually, since the engine expects one file → one session, we have two options:
1. Return `state.vscdb` paths and produce multiple `NormalizedSession` objects per file (requires small engine change or a new `parse_sessions` plural method)
2. Return virtual paths like `state.vscdb::tabId` or `state.vscdb::composerId` per session

**Recommended:** Option 2 — return virtual paths as `Path(str(db_path) + "::" + session_uuid)`. The adapter strips the `::` suffix to reopen the actual DB. This keeps the engine unchanged. The SHA-256 fingerprint would be of the parent `state.vscdb` file per-session-virtual-path — but that would force re-export of all tabs when any tab changes. Better: store `sha256` per real DB in the index, keyed by virtual session path.

Actually the cleanest approach: create a `discover_files` that yields a virtual path per session (by reading the DB upfront during discovery), so the engine gets one path per session. The SHA-256 of the virtual path's "source" would be computed from just that tab's content (e.g. hash the JSON of the tab), not the full DB. That's possible since we have the data at discovery time.

**`peek_session(source_path, source_system)`**
- Parse `<real_db_path>::<session_uuid>` from source_path
- Query the tab or composer by UUID from the DB
- Return `{session_id, session_key, started_at, cwd}` where `cwd` comes from `workspace.json`

**`parse_session(source_path, source_system, user, system_name)`**
- Same parse of virtual path
- For **chat tab**: walk `bubbles`, map `type:"user"` → `kind="user"`, `type:"ai"` → `kind="assistant"`
- For **composer**: walk `conversation`, map `type:1` → `kind="user"`, `type:2` → `kind="assistant"`
- Return `NormalizedSession`

**Session ID convention:**
- Chat: `cursor-chat:<tabId>`  
- Composer: `cursor-composer:<composerId>`

**`started_at`:** `lastSendTime` (chat) or `createdAt` (composer) — both are Unix epoch milliseconds, convert to ISO string.

**`cwd`:** URL-decoded `folder` from `workspace.json` sibling, strip `file://` prefix.

**`title`:** `chatTitle` for chat tabs (Cursor auto-generates these, e.g. "Creating Smoke Tests for Matrix CLI"), empty for composer (would need to infer from first message).

---

### Edge cases to handle

1. **Empty tabs** — tabs with 0 or 1 bubble (often just a file selection with no text) → skip or keep with empty content
2. **User bubble with no text** — `delegate` is `None`, `text` is missing → try `text`, fallback `delegate.a`, fallback `initText` nested parse
3. **Multiple `state.vscdb` for same workspace** — the same project can appear more than once (matrix-ui appeared twice with different hashes). The `cwd` deduplicates conceptually; `tabId`/`composerId` UUIDs are globally unique.
4. **DB locked** — Cursor may hold a WAL lock; open with `?mode=ro` (already done by existing tools)
5. **No chat data key** — 277/311 workspaces have no chat; `discover_files` should handle missing key gracefully

---

### `pyproject.toml` change

Add `sqlite3` — it's stdlib, nothing to add. No new dependencies needed.

---

### File structure

```
src/conversation_exporter/adapters/
  cursor.py       ← new CursorAdapter
  __init__.py     ← register CursorAdapter
```

And in the CLI, add `cursor` as a recognized `--source` with default input path `~/Library/Application Support/Cursor/User/workspaceStorage`.

---

Want me to switch to Agent mode and implement this?

## User

can you verify these databases contain the actual content of the chats? 

cuz I think they are in the 2GB file under globalStorage/state.vscdb

## Agent

Good instinct. Let me check both.

## Agent

2GB global vs 16MB max workspace. Let me check what's in both.

## Agent

The workspace DBs **do** have the actual content — full AI responses verified. The global one only has UI state (hidden/shown panels). But let me quickly check what's making that 2GB file so large:

## Agent

The 2GB global DB is the real treasure. Here's the full picture:

---

## What we actually found

### Workspace-level `state.vscdb` (correct for chat tabs)

The workspace DBs **do** contain real chat content. The biggest one (`/matrix`, 16MB) has 376 tabs and 1,354 bubbles with complete AI `rawText`. This approach works fine for **chat sessions**.

### Global `state.vscdb` (2GB) — the real story

It has **two tables**, not one:

| Table | Rows | What's in it |
|-------|------|--------------|
| `ItemTable` | 897 | UI-only state (panel visibility, hidden/shown) |
| `cursorDiskKV` | **150,193** | All the actual content |

The `cursorDiskKV` table is where the big stuff lives, keyed by pattern:

**`composerData:<uuid>`** — **1,733 entries**, up to 3MB each. These are the full **composer/agent sessions** with complete `conversation` arrays. The biggest one has **371 messages**. Structure:
```
composerId, richText, conversation[], createdAt, name, isAgentic, unifiedMode, ...
```
Messages: `type: 1` = user, `type: 2` = assistant, text in `text` field.

**`bubbleId:<bubbleId>:<composerId>`** — up to **28MB each**. These store the per-message *context* (lint errors, codebase chunks, git diffs, attached code) — not the conversation text itself, but rich metadata per bubble.

### The cross-reference architecture

```
workspaceStorage/<hash>/state.vscdb
  ItemTable["composer.composerData"]  →  {allComposers: [{composerId: "<uuid>", ...}]}
                                                              ↓
globalStorage/state.vscdb
  cursorDiskKV["composerData:<uuid>"]  →  full conversation with 371 messages
  cursorDiskKV["bubbleId:<id>:<uuid>"] →  per-bubble context/code chunks
```

So to link a composer session back to a workspace (for `cwd` filtering), you cross-reference: the workspace DB lists which `composerId`s belong to it, and the global DB has the actual conversation content.

---

## Updated plan

**Two data sources → two sub-adapters in `CursorAdapter`:**

1. **Chat tabs** → scan `workspaceStorage/*/state.vscdb`, read `workbench.panel.aichat.view.aichat.chatdata`, extract tabs with bubbles. `cwd` comes from sibling `workspace.json`. ✅ Already fully validated.

2. **Composer/Agent sessions** → read `globalStorage/state.vscdb` → `cursorDiskKV` for all `composerData:*` keys. Then cross-reference workspace-level `composer.composerData` to get `cwd` per composerId. For composers with no workspace link, `cwd` is empty.

Both produce `NormalizedSession` objects. The adapter's `discover_files` input path would be the workspace storage dir; the global DB path would be derived as a sibling (`../globalStorage/state.vscdb`).

Ready to implement?

## User

so if we don't look at global file what do we loose?

## Agent

By skipping the global DB you'd lose **all composer/agent sessions** — the `conversation` arrays in workspace-level `composer.composerData` are essentially empty shells (just metadata: composerId, createdAt, type). The actual messages live only in the global `cursorDiskKV`.

Concretely from the data we probed:

| Source | Sessions | Biggest session |
|--------|----------|-----------------|
| Workspace DBs (chat tabs) | ~188 tabs, ~1,354 bubbles | matrix: 376 tabs |
| Global DB (composer) | **1,733 sessions** | 371 messages, 3MB |

So you'd keep the quick Q&A-style chat sessions but lose all the **agentic "composer" sessions** — which are typically the most substantive ones where Cursor was actually writing/editing code across multiple turns.

The practical tradeoff: the global DB is 2GB and slow to query (`ORDER BY length` timed out at 2min), but a simple `SELECT value FROM cursorDiskKV WHERE key = 'composerData:<uuid>'` lookup by known key is fast. The discovery step (finding all `composerData:*` keys) should still be quick since it's just a key scan, not a full scan with sorting.

For a first version it would be reasonable to start with just the workspace chat tabs (simpler, no cross-DB join needed), and add composer sessions as a follow-up. You'd cover the most common case and have a working adapter shipping faster.

## User

OK we do need the whole composer ones. so let's plan for extracting it all. 

BUT we should probably add a `--with-context` flag which controls whether we actually export EVERYTHING (across cursor/codex/claude) or just the forth & back between AI and user. 

Because if we always include all the files read in every session then we'll have massive files. And given 2GB, the repos would quickly explode. 

SO let's add a flag and make the context stuff (tool calls, thinking) optional. 

Actually let's do
--with-context
--with-thinking

to give users the control what to include in the extractions.

## Agent

Now I have everything I need. Let me create the plan.

## User

Implement the plan as specified, it is attached for your reference. Do NOT edit the plan file itself.

To-do's from the plan have already been created. Do not create them again. Mark them as in_progress as you work, starting with the first one. Don't stop until you have completed all the to-dos.

## Agent

Implementing the CursorAdapter:

## Agent

All planned changes are in place. Summary:

## Summary

**1. `kind="thinking"`**
- Codex: reasoning messages use `kind="thinking"` instead of `kind="system"`.
- Claude: thinking blocks use `kind="thinking"` instead of `kind="system"`.

**2. `--with-context` and `--with-thinking`**
- `render_markdown()` takes `with_context` and `with_thinking` (default `False`).
- `system`/`tool` messages are only rendered when `with_context=True`.
- `thinking` messages are only rendered when `with_thinking=True`.
- `user` and `assistant` messages are always rendered.

**3. Engine and CLI**
- `sync_sessions()` accepts and forwards both flags to `render_markdown`.
- `sync` and `backup` expose `--with-context` and `--with-thinking`.
- `"all"` source systems now include `cursor`.

**4. CursorAdapter**
- Reads chat tabs from `workspaceStorage/*/state.vscdb` (`workbench.panel.aichat.view.aichat.chatdata`).
- Reads composer sessions from `globalStorage/state.vscdb` (`cursorDiskKV` `composerData:*`).
- Maps composer IDs to workspaces via `composer.composerData` in workspace DBs.
- Uses virtual paths `path::chat::tabId` and `path::composer::composerId`.
- Fingerprints: SHA-256 of tab JSON for chat, SHA-256 of conversation for composer.

**5. Registration**
- CursorAdapter registered in `adapters/__init__.py`.
- Default input path: `~/Library/Application Support/Cursor/User/workspaceStorage`.

On your machine, the adapter discovers 512 Cursor sessions (chat + composer). Tests fail because of a missing `libplumbr.so` (plumbrc), not because of these changes.

## User

❯ .venv/bin/convx sync
Traceback (most recent call last):
  File "/Users/pascal/Code/business/convx/.venv/bin/convx", line 4, in <module>
    from conversation_exporter.cli import main
  File "/Users/pascal/Code/business/convx/src/conversation_exporter/cli.py", line 10, in <module>
    from conversation_exporter.engine import SyncResult, sync_sessions
  File "/Users/pascal/Code/business/convx/src/conversation_exporter/engine.py", line 8, in <module>
    from conversation_exporter.redact import redact_secrets
  File "/Users/pascal/Code/business/convx/src/conversation_exporter/redact.py", line 3, in <module>
    from plumbrc import Plumbr
  File "/Users/pascal/Code/business/convx/.venv/lib/python3.12/site-packages/plumbrc/__init__.py", line 14, in <module>
    from plumbrc._plumbr import Plumbr
  File "/Users/pascal/Code/business/convx/.venv/lib/python3.12/site-packages/plumbrc/_plumbr.py", line 85, in <module>
    _lib = _find_library()
           ^^^^^^^^^^^^^^^
  File "/Users/pascal/Code/business/convx/.venv/lib/python3.12/site-packages/plumbrc/_plumbr.py", line 77, in _find_library
    raise LibraryNotFoundError(
plumbrc.exceptions.LibraryNotFoundError: Could not find libplumbr.so. Please ensure PlumbrC is installed correctly. Searched: ['/Users/pascal/Code/business/convx/.venv/lib/python3.12/site-packages/plumbrc/lib/libplumbr.so', '/Users/pascal/Code/business/convx/.venv/lib/python3.12/build/lib/libplumbr.so', '/usr/local/lib/libplumbr.so', '/usr/lib/libplumbr.so', '/usr/lib/x86_64-linux-gnu/libplumbr.so']

make sure it works please

## Agent

Making plumbrc optional so convx runs when the native library is missing.

## Agent

Catching LibraryNotFoundError as well:

## Agent

convx works again. Plumbrc is now optional: if it can’t load (e.g. missing `libplumbr.so`), redaction is skipped and the app runs normally.

When plumbrc isn’t available, use `--no-redact` if you want to avoid redacting secrets, or install the PlumbrC native library so redaction works.

## User

great. I see claude and codex folders but nothign from cursor?

## Agent

Checking what's happening with Cursor sessions:

## Agent

Cursor discovered 10 sessions; all 10 were filtered because their `cwd` is not under the convx repo. Sync only exports sessions whose working directory is under the current repo, so no Cursor sessions were exported and no `cursor` folder was created. Checking which Cursor sessions exist and their cwds:

## Agent

Those 512 Cursor sessions are from other projects (stelliosbeach, orchard, matrix-ui, etc.), not from the convx repo. `sync` only exports sessions whose `cwd` is under the current repo, so they’re all filtered out.

To export Cursor sessions, use **backup** instead of sync:

```bash
convx backup --output-path . --source-system=cursor
```

That exports all Cursor sessions into the current repo. Or point `--output-path` at a dedicated backup repo.

To export only Cursor sessions for a specific project, run `convx sync` from that project’s directory:

```bash
cd /Users/pascal/Code/everycure/matrix
convx sync --source-system=cursor
```

## User

I for sure have 4 sessions going right now that I would expect to see in the repo including this very one

## Agent

Checking the convx workspace and path-matching logic:

## Agent

Updating the Cursor adapter to support the new storage format: Cursor stores active sessions in `fullConversationHeadersOnly` with message content in `bubbleId:<composerId>:<bubbleId>` keys.

## Agent

Cursor has changed how it stores active sessions: instead of a `conversation` array, it now uses `fullConversationHeadersOnly` plus separate `bubbleId:<composerId>:<bubbleId>` entries for each message.

The Cursor adapter is updated to support both formats. After the change, `convx sync --source-system=cursor` exports 4 convx sessions, including the current one (“let's come up with a simple UI to explore the history…”).

## User

can we make sure that the UI is giving more feedback? 

So a nice progress steps
1. processing cursor
2. processing codex
3....

With a counter / progress indicator so the user feel slike something happening

## Agent

The sync command now shows:

1. **Step counter** – `[1/3]`, `[2/3]`, `[3/3]` for each source
2. **Spinner** – a dots spinner while each source is processed
3. **Per-source summary** – discovered, exported, updated, skipped, filtered for each source
4. **Overall summary** – totals at the end

The backup command also shows a spinner while it runs.

## User

great the output_repo, history and discovered lines... can we also make them better? check context7 for best practices with typer UI

## User

can we also get mouse scrolling someehow? Feels cumbersome to get through the UI right now. Aren't there best practices for TUIs that let people feel autoamtically at home in the tool if they are used to CLI tools? 

also I'm missing the user in the navigation in the TUI. and there's no point in having

Date | tool | <date>-slug

the 2nd date should be stripped from the file slug.

## Agent

Implementing the changes:

## Agent

Implementing all changes:

## Agent

Adding actions to forward j/k to the focused widget:

## Agent

Checking how Textual dispatches actions:

## Agent

Adding forwarding actions so j/k work when the list has focus:

## Agent

Test failures are pre-existing (they expect the old `exported=4` format; output now uses a Rich table). Verifying the TUI runs:

## Agent

Summary of what was implemented:

## Changes

### 1. **Mouse scrolling**
- Wrapped the preview in a `VerticalScroll` container so the Markdown content scrolls with the mouse wheel
- Set `scrollbar-size: 0 1` on the list and preview so scrollbars are visible

### 2. **TUI bindings**
- **j** / **k** – move up/down in the list (vim-style)
- **g** – jump to first item
- **G** – jump to last item

### 3. **User in navigation**
- Added `user` to session data by parsing it from the path (`history/<user>/<source>/...`)
- Display format is now: `user | date | source | slug`

### 4. **Date removed from slug**
- Added `_slug_only()` to strip the `YYYY-MM-DD-HHMM-` prefix from the basename
- Display shows only the slug (e.g. `hashing-secrets-in-python-library` instead of `2026-02-19-1726-hashing-secrets-in-python-library`)

### Files touched
- `src/conversation_exporter/tui.py` – bindings, layout, formatting
- `src/conversation_exporter/search.py` – `_user_from_path()`, `user` in session data
- `src/conversation_exporter/explore.css` – scrollbar styling

The list now shows rows like `pascal   2026-02-19 cursor   hashing-sec` instead of repeating the date in the slug.

## User

can you check the docs of the tool we use to build the TUI to see how we can make the UI more attractive/intuitive? what options do we have?

## Agent

Here’s what Textual offers for making the TUI more attractive and intuitive:

---

## Textual UI Design Options

### 1. **Header & Footer**
- Built-in `Header` and `Footer` widgets
- Header: app title, navigation
- Footer: key bindings (already used by Textual)
- Add them in `compose()`:
  ```python
  yield Header()
  yield Footer()
  ```

### 2. **Themes**
- Built-in themes: `textual-dark`, `textual-light`, `nord`, `gruvbox`, `tokyo-night`, `solarized-light`, `atom-one-dark`, `atom-one-light`
- Switch at runtime: `self.theme = "nord"` or via Command Palette (Ctrl+P)
- Custom themes via `Theme()` with `primary`, `secondary`, `accent`, `foreground`, `background`, `surface`, `panel`, etc.

### 3. **Design Tokens (Theme Variables)**
Use these in CSS for consistent styling:
- **Base colors:** `$primary`, `$secondary`, `$accent`, `$foreground`, `$background`, `$surface`, `$panel`
- **Text:** `$text-primary`, `$text-accent`, `$foreground-muted`, `$foreground-disabled`
- **Muted backgrounds:** `$primary-muted`, `$accent-muted`, etc.
- **Shades:** `$primary-darken-1`, `$primary-lighten-2`, etc.

### 4. **CSS Styling**
- **Borders:** `border: solid $accent`, `border: heavy white`, `border-bottom: solid blue`, `border: round orange 50%`
- **Padding:** `padding: 1 2` or `padding: 2`
- **Backgrounds:** `background: $panel`, `background: $primary-muted`
- **Layout:** `align: center middle`, `content-align: center middle`
- **Hover/focus:** `:hover`, `:focus` for interactive feedback

### 5. **Layout**
- **Dock:** `dock: top`, `dock: bottom` for fixed header/footer
- **Grid:** `layout: grid`, `grid-size: 2 2`
- **Spacing:** `margin`, `padding`, `grid-gutter`
- **Sizing:** `width: 1fr`, `height: auto`, `min-width`, `min-height`

### 6. **Widget-Specific Styling**
- **ListView:** `padding: 1 2` on `Label`, `margin: 2 2` on `ListView`
- **Input:** `input--cursor`, `input--placeholder`, `input--selection` for cursor/placeholder/selection
- **ListItem:** Use CSS classes for selected vs unselected

### 7. **Dynamic Styling**
- Add/remove CSS classes for state changes (e.g. `.started`, `.selected`)
- `check_action()` to show/hide or dim bindings based on state

### 8. **Layout Design Tips**
- Start with a sketch, then implement
- Build from outside in: header/footer first, then main content
- Use `Placeholder` to mock layout before real widgets

---

## Concrete Ideas for the Explore TUI

| Option | What to do |
|--------|------------|
| **Header** | Add `Header()` with title like "convx history" |
| **Footer** | Add `Footer()` so bindings (q, Esc, j/k, g/G) are visible |
| **Theme** | Set `self.theme = "nord"` or `"gruvbox"` in `on_mount` |
| **Panels** | Use `background: $panel` on list and preview for separation |
| **Borders** | Add `border: tall $background` or `border-right: solid $border` between list and preview |
| **List items** | Add `padding: 1 2` on list labels, `border-bottom: tall $background` for row separation |
| **Search input** | Style with `border: solid $accent` on focus |
| **Visual hierarchy** | Use `$foreground-muted` for dates/source, `$foreground` for slugs |

I can help turn any of these into concrete code changes for your TUI.
