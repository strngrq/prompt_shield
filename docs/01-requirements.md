# PromptShield — Requirements 
## 1. Overview

PromptShield is a desktop application for anonymizing personal data and company names before sending text to cloud-based LLMs. It replaces sensitive entities with labeled placeholders (e.g., `PERSON_1`, `COMPANY_3`, `ADDRESS_17`) and maintains a persistent mapping database so that anonymized responses can be de-anonymized later.

## 2. Technology Stack

| Layer | Technology |
|---|---|
| UI framework | **PySide6** (Qt 6 for Python, LGPL) |
| NER / Anonymization | Microsoft Presidio (Analyzer + Anonymizer) |
| NLP backend | spaCy (language-specific models) |
| Persistence | SQLite (single local database file) |
| Language | Python 3.10+ |
| Packaging | PyInstaller or similar (future) |

## 3. Core Workflow

1. User pastes or types source text into the **input pane**.
2. User clicks **"Proceed"**.
3. The application runs Presidio analysis, respecting the current entity-category selection, sensitivity threshold, language setting, allow-list, and block-list.
4. Every detected entity is replaced with a labeled placeholder in the format `<CATEGORY>_<N>` (e.g., `PERSON_5`, `ADDRESS_12`). The counter `N` is global and monotonically increasing per category across all sessions.
5. The anonymized text appears in the **output pane**.
6. User can copy the output to the clipboard (`Ctrl-C` / `Cmd-C`).

## 4. Interactive Masking / Unmasking in the Output Pane

### 4.1 Output Pane Implementation (QTextEdit)

The output pane is a read-only `QTextEdit` using `QTextCharFormat` to style placeholder tokens differently from plain text (e.g., bold, colored background). Each placeholder span carries the mapping ID in `QTextCharFormat.setProperty()` or via `QTextCursor` user data, enabling identification on click.

### 4.2 Selecting Text

- User can **click on a single placeholder token** (detected via `cursorForPosition()` + char format inspection) or **select an arbitrary text fragment** in the output pane.

### 4.3 Actions on Selected Text

A small **context toolbar** appears near the selection (or use a right-click context menu) with these actions:

| Button | Behavior |
|---|---|
| **Mask / Unmask** (toggle) | If the selection is currently in clear text — replace it with a new placeholder (`INFO_<N>` or the appropriate category). If it is already a placeholder — reveal the original text **in this prompt only** (does not affect the database lists). |
| **Block it** | Add the original text behind the selection to the **block-list**. From now on this text will always be masked in every prompt. |
| **Allow it** | Add the original text behind the selection to the **allow-list**. From now on this text will never be masked. |

### 4.4 Tooltip on Hover

Implemented via `QTextEdit.mouseMoveEvent()` + `cursorForPosition()`. When the cursor is over a placeholder-formatted span, a `QToolTip.showText()` call displays the original value near the cursor. Mouse tracking must be enabled on the widget (`setMouseTracking(True)`).

## 5. De-anonymization Tab

A dedicated **"Unmask"** tab provides the reverse workflow:

1. User pastes anonymized text (e.g., an LLM response containing `PERSON_5`, `ADDRESS_12`).
2. User clicks **"Proceed"**.
3. The application looks up every `<CATEGORY>_<N>` token in the hash/mapping database and replaces it with the original value.
4. The restored text appears in the output pane and can be copied to the clipboard.

## 6. Database Schema (SQLite)

### 6.1 Tables

#### `mappings`

Stores every substitution ever made.

| Column | Type | Description |
|---|---|---|
| `id` | INTEGER PK | Auto-increment |
| `original_text` | TEXT | The real sensitive value |
| `hash` | TEXT UNIQUE | Deterministic hash of `original_text` (e.g., SHA-256) |
| `placeholder` | TEXT UNIQUE | The placeholder label, e.g. `PERSON_5` |
| `category` | TEXT | Entity category (`PERSON`, `ADDRESS`, `COMPANY`, etc.) |
| `created_at` | TIMESTAMP | When the mapping was first created |

#### `counters`

Tracks the next available index per category.

| Column | Type | Description |
|---|---|---|
| `category` | TEXT PK | Entity category name |
| `next_index` | INTEGER | Next number to assign |

#### `block_list`

| Column | Type | Description |
|---|---|---|
| `id` | INTEGER PK | Auto-increment |
| `text` | TEXT UNIQUE | Text that must always be masked |
| `prefix_match` | BOOLEAN | If true, match any word starting with `text` |
| `case_sensitive` | BOOLEAN | If true, match exact case only |
| `added_at` | TIMESTAMP | When the entry was added |

#### `allow_list`

| Column | Type | Description |
|---|---|---|
| `id` | INTEGER PK | Auto-increment |
| `text` | TEXT UNIQUE | Text that must never be masked |
| `prefix_match` | BOOLEAN | If true, match any word starting with `text` |
| `case_sensitive` | BOOLEAN | If true, match exact case only |
| `added_at` | TIMESTAMP | When the entry was added |

### 6.2 Lookup Logic

Before masking, the application:

1. Checks the **allow-list** — if the entity text matches, skip masking.
2. Checks the **block-list** — if it matches, always mask (even if Presidio did not flag it).
3. Checks the **mappings** table by hash — if the same text was masked before, reuse the same placeholder.
4. Otherwise, allocate a new placeholder using the `counters` table.

## 7. Block-list and Allow-list Management

A dedicated **"Lists"** tab (or two sub-tabs: **Block List** / **Allow List**) provides:

- A scrollable table showing all entries with columns: **Text**, **Prefix match**, **Case sensitive**, **Date added**.
- An **"Add"** form: text input field + two checkboxes (see below) + "Add" button.
- A **"Delete"** button to remove selected entries.
- Search / filter functionality for large lists.

### 7.1 Entry Matching Options

Each entry in the block-list or allow-list has two boolean flags:

| Flag | Default | Behavior |
|---|---|---|
| **Prefix match** | Off | When enabled, the entry matches any word that **starts with** the given text. E.g., `майкрософт` will match `майкрософта`, `майкрософтом`, `майкрософту`, `Майкрософт` (if case-insensitive). Each matched word form gets its own separate hash and placeholder in the mappings table. |
| **Case sensitive** | Off | When enabled, matching is exact-case only. When disabled (default), matching is case-insensitive: `Microsoft` matches `microsoft`, `MICROSOFT`, `Microsoft`, etc. |

### 7.2 Matching Priority

During anonymization, list matching is applied before Presidio analysis:

1. Check **allow-list** (prefix + case rules) — if matched, the text is protected from masking.
2. Scan the full input text against **block-list** entries (prefix + case rules) — any match is force-masked, even if Presidio would not detect it.
3. Run Presidio on the remaining (non-allowed) text.

## 8. Category and Sensitivity Settings

A **Settings** panel (sidebar, tab, or modal) allows the user to configure:

### 8.1 Entity Categories

Checkboxes to enable/disable each Presidio-supported entity type:

- `PERSON`
- `EMAIL_ADDRESS`
- `PHONE_NUMBER`
- `LOCATION` / `ADDRESS`
- `ORGANIZATION` / `COMPANY`
- `CREDIT_CARD`
- `IBAN_CODE`
- `IP_ADDRESS`
- `URL`
- `DATE_TIME`
- (other Presidio built-in types)

The user can also define **custom categories** if needed.

### 8.2 Sensitivity / Confidence Threshold

A slider or numeric input (0.0 – 1.0) controlling the minimum Presidio confidence score required for an entity to be masked. Lower values = more aggressive masking.

### 8.3 Language Selection and Model Management

- A list of available languages with download/status indicators (see Section 14.2 for full model management flow).
- Each language shows its status: **Installed** / **Not installed** / **Downloading...** with a progress bar.
- **"Download"** button to fetch the spaCy model for a language (runs in a background thread).
- **"Remove"** button to delete an installed model and free disk space.
- Choice between `lg` (large, higher accuracy) and `sm` (small, faster) model variants.
- The user can select which installed languages are **active** for analysis (checkboxes). Multiple languages can be active simultaneously.
- The list of available languages is configurable and can be extended by the user.

## 9. Clipboard Integration

- The output pane text must be copyable via standard OS shortcuts (`Ctrl-C` / `Cmd-C`).
- Optionally, a **"Copy to Clipboard"** button for explicit one-click copying of the full output.

## 10. Data Flow Diagram

```
                         ┌────────────┐
                         │  Input Pane │
                         └─────┬──────┘
                               │ raw text
                               ▼
                      ┌─────────────────┐
                      │  Allow-list     │──► skip if matched
                      │  Block-list     │──► force mask if matched
                      │  Presidio + spaCy│──► detect entities
                      └─────┬───────────┘
                            │
                      ┌─────▼───────┐
                      │  SQLite DB  │ lookup hash / create mapping
                      └─────┬───────┘
                            │ anonymized text
                            ▼
                      ┌────────────┐
                      │ Output Pane │ ← interactive mask/unmask
                      └────────────┘
```

## 11. Non-functional Requirements

| Requirement | Target |
|---|---|
| Startup time | < 3 seconds (after first model load) |
| Anonymization latency | < 2 seconds for texts up to 5 000 words |
| Offline operation | Fully offline; no network calls required |
| OS support | macOS (primary), Windows, Linux |
| Database location | `~/.promptshield/promptshield.db` (configurable) |
| Config location | `~/.promptshield/config.json` |

## 12. UI Framework — PySide6

### Why PySide6

- **LGPL license** — free for commercial use without source disclosure (unlike PyQt6 GPL).
- **`QTextEdit` / `QTextDocument`** — native rich-text support with per-character formatting, cursor positioning, inline click detection, and tooltips. This directly covers the core interactive masking/unmasking requirements.
- **`QTabWidget`** — built-in tabbed interface for Anonymize / De-anonymize / Lists / Settings tabs.
- **`QTableView` + `QSqlTableModel`** — direct SQLite-backed table views for block/allow list management with minimal glue code.
- **`QToolTip`** — native tooltip API for hover-over-placeholder feature.
- **Signals & Slots** — clean event-driven architecture for button clicks, text selection changes, and context menus.
- **Cross-platform** — native look on macOS, Windows, Linux.
- **Mature ecosystem** — extensive documentation, large community, well-tested with PyInstaller for packaging.

### Key Qt Components Mapping

| Requirement | Qt Component |
|---|---|
| Tabbed layout | `QTabWidget` |
| Text input pane | `QPlainTextEdit` (plain text, no formatting needed) |
| Text output pane (interactive) | `QTextEdit` (read-only, rich text with `QTextCharFormat` for token styling) |
| Placeholder tooltip on hover | `QTextEdit.mouseMoveEvent()` + `QToolTip.showText()` |
| Token click detection | `QTextEdit.cursorForPosition()` + char format property lookup |
| Context actions (Mask/Unmask, Block, Allow) | `QMenu` (right-click context menu) or floating `QToolBar` |
| Block/Allow list tables | `QTableView` + `QSqlTableModel` or `QStandardItemModel` |
| Settings checkboxes | `QCheckBox` in a `QScrollArea` |
| Sensitivity slider | `QSlider` + `QDoubleSpinBox` |
| Language list | `QListWidget` with add/remove buttons |
| Copy to clipboard | `QApplication.clipboard().setText()` |
| Application styling | Qt Style Sheets (QSS) for consistent modern look |

## 13. Application Tabs Summary

| Tab | Purpose |
|---|---|
| **Anonymize** | Main tab. Input text → Proceed → anonymized output with interactive mask/unmask. |
| **De-anonymize** | Reverse tab. Paste LLM response → Proceed → restored text. |
| **Block List** | View, add, delete entries that are always masked. |
| **Allow List** | View, add, delete entries that are never masked. |
| **Settings** | Entity categories, sensitivity, language selection. |

## 14. Packaging and Distribution

### 14.1 PyInstaller Strategy

The application is packaged as a standalone executable using PyInstaller with a custom `.spec` file.

**What goes into the bundle:**

| Component | Included | Approx. Size |
|---|---|---|
| Python runtime | Yes | ~15 MB |
| PySide6 (trimmed) | Yes | ~80–120 MB |
| Presidio (analyzer + anonymizer) | Yes | ~5 MB |
| spaCy core library | Yes | ~10 MB |
| spaCy language models | **No** — downloaded on demand | 0 MB |
| SQLite | Yes (Python stdlib) | ~1 MB |

**Excluded PySide6 modules** (via `--exclude-module` to reduce bundle size):
`QtWebEngine`, `Qt3D`, `QtBluetooth`, `QtMultimedia`, `QtSensors`, `QtSerialPort`, `QtRemoteObjects`, `QtNfc`.


### 14.2 spaCy Model Management

Language models are **not bundled** with the application. They are downloaded on demand and stored locally.

**Storage location:** `~/.promptshield/models/`

**Model download flow:**

1. On first launch (or when no models are installed), the app shows a welcome dialog prompting the user to select languages and download the corresponding models.
2. In the **Settings → Languages** panel, the user sees a list of available languages with status:
   - **Installed** (green) — model is present and ready.
   - **Not installed** (gray) — model available for download.
   - **Downloading...** (progress bar) — download in progress.
3. User clicks **"Download"** next to a language. The app downloads the spaCy model in a background `QThread`, showing a progress bar. The UI remains responsive during download.
4. User clicks **"Remove"** next to an installed language to delete the model files and free disk space.
5. Models are loaded at runtime via `spacy.load("/path/to/model")` from the local storage directory.

**Available language models (initial set):**

| Language | spaCy Model | Size (approx.) |
|---|---|---|
| English | `en_core_web_lg` | ~560 MB |
| English (small) | `en_core_web_sm` | ~12 MB |
| Russian | `ru_core_news_lg` | ~490 MB |
| Russian (small) | `ru_core_news_sm` | ~15 MB |
| German | `de_core_news_lg` | ~540 MB |
| French | `fr_core_news_lg` | ~540 MB |
| Spanish | `es_core_news_lg` | ~540 MB |
| Chinese | `zh_core_web_lg` | ~570 MB |

The user can choose between `lg` (large, higher accuracy) and `sm` (small, faster download and lower memory usage) variants where available. The list of available languages is defined in a configuration file and can be extended.

### 14.3 Offline Considerations

- After initial model download, the application is **fully offline**.
- Model downloads require internet access. If the network is unavailable, the app shows a clear error message and allows the user to retry later.
- Users can manually place model files into `~/.promptshield/models/` for air-gapped environments.

### 14.4 Platform-specific Packaging

| Platform | Format | Notes |
|---|---|---|
| macOS | `.dmg` containing `.app` bundle | Code signing recommended for Gatekeeper |
| Windows | `.exe` installer (NSIS or Inno Setup) | Optional: `.msi` for enterprise deployment |


