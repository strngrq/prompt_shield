# PromptShield — Masking & Unmasking Improvements

## 0. Background

Real-world usage surfaced a family of related issues around
how the user selects text in the output pane, how that selection becomes a
placeholder, and how placeholders are later restored by the de-anonymizer.

A canonical failure case: the user selects the fragment inside the
word and clicks **Mask Selection** (or **Block it**). 

When this text is later pasted into the de-anonymizer, the placeholder is not
recognised and the text comes back broken.

This single user-visible symptom actually hides **three independent problems**,
and they must be fixed separately — one does not replace another.

This document describes the logic of the fixes. No code, only behaviour.

---

## 1. Problem A — De-anonymizer fails when a placeholder is glued to a suffix

### Symptom

`INFO_12е` in the output is not matched by the de-anonymizer regex, so the
placeholder stays in the restored text instead of being replaced by the
original value.

### Root cause

The de-anonymizer identifies placeholders with a word-boundary anchor on the
right side of the token (`\b`). In Python's `re` module with Unicode
semantics, `\b` is the boundary between a word character and a non-word
character. Both a digit (`2`) and a Cyrillic letter (`е`) are word
characters, so there is **no** `\b` between them. The regex therefore fails
to find `INFO_12` inside `INFO_12е`, and the placeholder is left untouched.

For Latin neighbours (`INFO_12X`) the same `\b` correctly fails to match — we
do not want to grab a longer token. So we cannot simply drop the boundary
check; we need a boundary check that considers only characters that could
legitimately continue a placeholder token.

### Fix logic

Replace the right-side `\b` in the placeholder regex with an explicit
"lookahead that rejects characters that could belong to a placeholder
identifier". A placeholder is of the shape `<CATEGORY>_<N>` where
`CATEGORY` is ASCII uppercase letters and `N` is ASCII digits. The continuation
characters that must be rejected on the right are therefore: ASCII letters
(upper and lower), ASCII digits, and underscore.

Any other character — Cyrillic, whitespace, punctuation, end of string — is
allowed to follow the token and the match succeeds. The same logic is applied
symmetrically on the left side: the character immediately before the
placeholder must not be an ASCII letter/digit/underscore either.


### Scope of change

Only the de-anonymizer's placeholder-detection regex.

---

## 2. Problem B — Partial word selection creates ugly, half-masked tokens

### Symptom

When the user drags the mouse to select `которы` inside `которые` and clicks
**Mask Selection**, the placeholder replaces exactly those six characters and
the trailing `е` is left dangling. Result: `INFO_12е`.

Even after Problem A is fixed and the de-anonymizer can recover from this,
the intermediate anonymized text is still visually broken and, in some cases,
confuses the downstream LLM that receives it.

The same applies to **Block it** and **Allow it** actions: if the user selects
half a word and adds it to the block-list, the literal string stored in the
database is a fragment, which has no real meaning.

### Root cause

The actions in the output pane context menu operate on the exact text range
that the user selected, with no normalisation. 

### Fix logic — snap-to-word by default

Before any of the actions **Mask Selection**, **Block it**, **Allow it** act
on the selection, the selection is normalised to word boundaries:

1. Take the current selection range `[start, end)`.
2. If `start` falls **inside** a word (i.e., both the character before `start`
   and the character at `start` are word characters of the same script),
   move `start` leftward until it lands on a word boundary.
3. Symmetrically, if `end` falls inside a word, move `end` rightward until it
   lands on a word boundary.
4. If after normalisation the range is empty or whitespace-only, the action
   is cancelled silently (nothing to mask).
5. The action then operates on the normalised range. The UI briefly
   highlights the normalised range so the user understands what will happen.

Word boundary is defined using Qt's native notion of a word (which already
handles Unicode scripts correctly, including Cyrillic, and is script-aware).
Qt provides `QTextCursor.WordUnderCursor` and related movement operations
out of the box — we rely on Qt's implementation rather than rolling our own
regex-based boundary detection.

### Escape hatch for power users

There are legitimate cases where the user really wants a sub-word selection:

- Masking only the first name inside `Ivan Petrovich Sidorov` (multi-word
  selection, but precise on the outer boundaries).
- Masking part of a compound like `Müller-Schmidt` where only the first half
  should be hidden.
- Masking a substring that is genuinely not a word (e.g., a middle segment
  of an ID or a URL fragment).

For these cases, an **Alt-held** modifier (Option on macOS) during the click
or selection bypasses snap-to-word and uses the exact selection range as-is.
The UI hint on the action button updates to indicate "exact range" while Alt
is held.

### Why this is universal

It improves the UX for English
("I wanted to mask `Microsoft` but my selection started one character early"),
German compound nouns, French with its hyphenated words, and every other
language. It is a general-purpose precision aid.

### Scope of change

Only the output-pane selection handling in the UI layer. The core anonymizer,
database schema, and list-matching logic are untouched. The block-list and
allow-list receive cleaner values, but that is a passive benefit — no
migration of existing entries is needed.

---

## 3. Problem C — Block-list does not catch inflected forms of Russian words

### Symptom

The user adds `Майкрософт` to the block-list. The next input contains
`Майкрософта` or `Майкрософтом` (genitive / instrumental). The block-list
does not match these forms, because matching is literal. The user either
learns to add every form manually (bad UX) or gives up and relies on
Presidio's NER (which may or may not catch brand names reliably).

### Two candidate solutions

There are two fundamentally different ways to solve this. This section
describes both, then explains the chosen direction and why.

### Candidate C-1 — Smart default for `prefix_match` + morphology-assisted preview

The block-list already supports a per-entry `prefix_match` flag. When set,
the matching engine appends `\w*` to the pattern, so `майкрософт` with
`prefix_match` set catches `майкрософта`, `майкрософтом`, `майкрософтский`,
and any other word that *starts with* those letters. This works extremely
well for Russian, Ukrainian, German, Finnish, Turkish and every other language
where grammatical inflection is expressed as suffixes.

The problem with the current state is purely **discoverability**: the flag is
off by default, and most users never think to turn it on. They add
`Майкрософт`, get surprised when `Майкрософта` leaks through, and blame the
tool.

The proposed improvements are pure UX, zero changes to the matching engine:

1. **Smart default when adding from a text selection.** If the user triggers
   *Block it* from the output-pane context menu, `prefix_match` is set to
   `True` by default in the resulting database entry. The mental model is:
   "the user pointed at a word in real text, so they mean all forms of this
   word". The user can still untick the flag explicitly if they want a
   literal match — but they almost never do.

2. **Lemmatize on save, not on match.** When the user adds an entry from a
   selection in the output pane and the selected text is a single Russian
   word (contains Cyrillic letters and pymorphy3 can parse it), the entry is
   stored as the **lemma** of that word rather than the surface form.

   Example: the user drags to select most of the word `майкрософта` in the
   text. Snap-to-word from Problem B expands the selection to the full word
   `майкрософта`. pymorphy3 then returns the lemma `майкрософт`, and that is
   what goes into the database. Combined with `prefix_match=True`, the
   resulting rule catches every inflected form of the word: `Майкрософт`,
   `Майкрософта`, `Майкрософту`, `Майкрософтом`, `Майкрософтский`. Without
   this step, storing the surface form `майкрософта` plus prefix-match would
   only catch forms that happen to start with `майкрософта` — i.e., the
   genitive and its own extensions — and would miss the nominative, dative,
   instrumental, and everything else. Snap-to-word alone would actually make
   the situation worse; lemmatisation restores the intended behaviour.

   This is **not** the runtime morphological matching rejected in Candidate
   C-2. Lemmatisation happens exactly once, at entry-creation time. The
   matching engine still runs the simple prefix regex against the stored
   value. There is no per-match runtime cost, no change to the anonymization
   pipeline, no change to the database schema, and no dependency on
   pymorphy3 at matching time. pymorphy3 is used only as a one-shot
   normaliser at save time.

   The confirmation dialog makes the transformation explicit and reversible:
   - The dialog shows the original selected text and the resulting stored
     value side by side, e.g. `entered: майкрософта → saved as: майкрософт`.
   - A **"save as typed"** toggle skips lemmatisation and stores the surface
     form verbatim. This exists for cases where pymorphy3 mis-parses a
     proper noun or brand, or where the user genuinely wants a literal
     match. Default is **lemmatised**.
   - **Ambiguous lemmas.** If pymorphy3 returns more than one plausible
     parse for the word (e.g., `стали` → `стать` / `сталь`), the dialog
     offers an explicit choice between all candidate lemmas plus the
     "save as typed" option, instead of silently picking one. For brand
     names and surnames this is rare, but when it happens the user should
     decide, not the tool.
   - **Multi-word entries.** If the entry contains more than one word
     (e.g., `Майкрософт Россия`), lemmatisation is skipped entirely and the
     entry is stored exactly as it appears after snap-to-word. Multi-word
     matching is a separate topic, deliberately out of scope in this
     document (see §5).
   - **Non-Russian text.** If the selected text contains no Cyrillic letters
     (e.g., `Microsoft`, `SuperBrand GmbH`), lemmatisation is skipped and
     the entry is stored as-is. Non-Russian languages rely on the existing
     `prefix_match` mechanism, which already covers suffix-based inflection
     for German, Finnish, Turkish, and similar suffix-heavy languages.

3. **Live preview of caught forms — powered by pymorphy3.** As the user
   types an entry or toggles the checkbox, a small preview area shows
   "This will also catch: Майкрософта, Майкрософтом, Майкрософтский, …".
   The forms are generated by pymorphy3 (already in the bundle because of
   the Russian lemmatizer), using its ability to enumerate the paradigm of
   a word. pymorphy3 is used here **only for user feedback**, not for
   matching. The actual matching remains the cheap prefix regex. This keeps
   matching fast, deterministic, and language-agnostic, while giving Russian
   users a clear sense of what their rule will do. When the stored value
   has been lemmatised (point 2 above), the preview operates on the lemma,
   so the user sees the full expected coverage.

4. **Visual confirmation in the output pane.** When the anonymization engine
   runs against text, every form matched by a `prefix_match` rule is
   highlighted in the output exactly like any other masked entity. The
   tooltip on hover shows which rule caught it ("blocked by rule:
   Майкрософт*"). This gives the user fast feedback that the rule is working.

### Scope of change

- **UI: Block List tab** — redesign the Add-entry dialog to show the friendly
  checkbox, the lemmatisation summary (`entered → saved as`), the
  "save as typed" toggle, the ambiguous-lemma chooser when applicable, and
  the live preview area. Same for Allow List tab, symmetrically.
- **UI: output pane context menu** — when *Block it* or *Allow it* is
  triggered from a selection, pass `prefix_match=True` as the default to the
  underlying add-entry call and route the text through the lemmatisation
  step before opening the confirmation dialog.
- **New lightweight helper** around pymorphy3 with two responsibilities,
  both UI-only:
  1. **Lemmatise a single Russian word** at entry-save time. Returns the
     lemma, a list of alternative lemmas when the parse is ambiguous, or an
     empty result for non-Russian / multi-word / unparseable input (in which
     case the caller stores the text as-is).
  2. **Enumerate representative inflected forms** of a given word or lemma
     for the live preview.
  Both responsibilities gracefully degrade to "no suggestion" when pymorphy3
  cannot handle the input. Neither participates in the matching pipeline.
- **Zero changes** to the matching engine, the database schema, or the
  anonymization pipeline. Lemmatisation is a one-shot transformation at
  entry-creation time; the stored value is still a plain string, and
  matching is still a plain prefix regex.

