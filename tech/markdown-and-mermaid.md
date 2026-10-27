# Markdown and Mermaid

## What it is

**Markdown** is a way of writing formatted documents in plain text. You write `# Title` for a heading, `**bold**`, `- item` for a list, and a program (GitHub, an editor preview) turns it into a nicely formatted page. Every `.md` file in this repository is Markdown. **Mermaid** is a small language for drawing diagrams from text; GitHub and many editors draw a Mermaid block as a picture, so diagrams live in the same file as the words and can be changed with a normal text edit.

## Why this repository uses it

The documentation is part of the product: a README that proves every "Done when" line, an ARCHITECTURE document that names the pattern and draws the data flow, a changelog, a decision record, a results file written by the program, and these notes. All of it is Markdown, so it is read on GitHub and in any editor.

## Where it appears

| File | What it is |
|---|---|
| `README.md` | How to set up, run and test; the proofs of each "Done when" line; the project tree. |
| `ARCHITECTURE.md` | The pattern, the components, the schema (a Mermaid `erDiagram`) and the data flow (a Mermaid `flowchart`). |
| `CHANGELOG.md` | Keep a Changelog format, version 0.1.0. |
| `docs/adr/0001-pure-plan-parsing-behind-ports.md` | A decision record. |
| `sql/explain/results.md` | Written by the program: a table of before and after figures. |
| `tech/*.md` | These notes. |

## How it works underneath

**Markdown syntax used here.**

| You write | You get |
|---|---|
| `# Heading`, `## Subheading`, ... | headings of levels 1, 2, ... |
| a blank line | a new paragraph |
| `- item` or `1. item` | a bullet or numbered list |
| `**bold**`, `*italic*` | bold, italic |
| `` `code` `` | inline code in a fixed-width font |
| three backticks, an optional language name, lines, three backticks | a **code block** (``` ```python ```), shown as is, with colours for the named language |
| `[text](https://address)` | a link |
| `\| a \| b \|` rows with a line of `\|---\|---\|` under the first | a table; `:` in the dashes aligns a column (`---:` right) |
| `> text` | a quotation |

Markdown is plain text first: it is readable without any program. Different programs add small extensions (tables and task lists are "GitHub Flavored Markdown"). Two spaces at the end of a line can force a line break, which is why `.editorconfig` does not trim trailing spaces in `.md` files.

**Mermaid.** A code block whose language is `mermaid` holds a diagram description. The first word chooses the diagram type:

- `flowchart LR` (boxes and arrows, left to right). A node is `id["label"]`; `id[("label")]` is drawn as a database cylinder; `a --> b` is an arrow; `a -->|"text"| b` an arrow with a label; `<br/>` is a line break inside a label.
- `erDiagram` (entity-relationship: tables and their columns). `NAME { type column KEY "comment" }` lists a table's columns; `PK` marks a primary key.

The picture is drawn by the viewer; the text stays in the file.

**Documents of other kinds in this repository** are also Markdown: `CHANGELOG.md` follows the Keep a Changelog convention (a section per released version with `Added`, `Changed`, `Fixed` lists); `docs/adr/NNNN-title.md` are **architecture decision records** (a short document per real decision: context, decision, consequences); `tech/` is these notes.

## Walkthrough of this repository's use

### The two Mermaid diagrams

`ARCHITECTURE.md`, lines 42 to 60:

````markdown
```mermaid
erDiagram
    ORDERS {
        bigint id PK
        int customer_id "1-50 heavy, 51-50000 light"
        text status "pending, paid, shipped, failed"
        timestamptz created_at "all of 2026"
        numeric total
        text notes "420 bytes, inline"
    }
    ORDER_NOTES_DEMO {
        bigint id PK
        int customer_id
        text status
        timestamptz created_at
        numeric total
        text notes "5 KB, stored out of line (TOAST)"
    }
```
````

`erDiagram` starts an entity-relationship diagram. Each block (`ORDERS { ... }`) is a table; each line inside is `type column [key] ["comment"]`. `PK` marks the primary key. The quoted text after a column is shown as a note. The two tables are drawn as two separate boxes because they are unrelated.

`ARCHITECTURE.md`, lines 68 to 79:

````markdown
```mermaid
flowchart LR
    seed["Seed script<br/>1,000,000 rows"] --> orders[("orders table")]
    cli["interfaces: run_cli"] --> replay["application: ReplayLesson"]
    replay -->|"LabDatabase port"| adapter["infrastructure: lab_database"]
    adapter -->|"1. EXPLAIN before"| orders
    adapter -->|"2. migration"| idx["Indexes you add"]
    idx --> orders
    adapter -->|"3. EXPLAIN after"| orders
    adapter -->|"4. rolled-back 10,000 inserts"| orders
    replay -->|"ArtifactStore port"| notes["Notes file<br/>explain/*.txt + results.md"]
```
````

`flowchart LR` draws left to right. `seed["Seed script<br/>1,000,000 rows"]` is a node with an id (`seed`) and a label in quotes, with `<br/>` for a line break. `orders[("orders table")]` draws a cylinder, the symbol for a database. `seed --> orders` is an arrow. `replay -->|"LabDatabase port"| adapter` is a labelled arrow: the label names the port (typing note) that the replay uses to reach the adapter. The numbered labels (`"1. EXPLAIN before"`) show the order of the steps.

### The results file written by the program

`src/slow_queries/application/report.py`, lines 14 to 30:

```python
def render_results(result: LessonResult) -> str:
    """Markdown with the before-and-after table, the write cost per index set and the index sizes."""
    lines = [
        "# Results of the last `make run`",
        "",
        "Generated by `slow-queries-run`; the plans are the `.txt` files next to each `.sql` here.",
        "",
        *([result.host_load.note(), ""] if result.host_load else []),
        "| Query | Before ms | After ms | Faster | Before pages | After pages |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for label, before_name, after_name in lesson.COMPARISONS:
        improvement = Improvement(result.plans[before_name], result.plans[after_name])
        lines.append(
            f"| {label} | {improvement.before.execution_ms:.3f} | {improvement.after.execution_ms:.3f} "
            f"| {improvement.speedup:.0f}x | {improvement.before.pages} | {improvement.after.pages} |"
        )
```

`render_results` builds Markdown lines in Python: `"# Results of the last `make run`"` is a heading; `"| Query | Before ms | ... |"` is the table header and `"|---|---:|---:|..."` the separator row in which `---:` right-aligns the numbers. Each data row is an f-string with the same number of `|` separators.

### The changelog and the decision record

`CHANGELOG.md`, lines 1 to 8:

```markdown
# Changelog

All notable changes to this project are recorded here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses [Semantic Versioning](https://semver.org/).

## [0.1.0] - 2026-10-27

### Added

```
`docs/adr/0001-pure-plan-parsing-behind-ports.md`, lines 1 to 12:

```markdown
# 0001. Plan parsing is pure domain code; PostgreSQL sits behind one port

Status: accepted, 2026-10-27

## Context

The lesson is about reading plans. The numbers that matter (execution time, pages touched, whether a `Sort` node is there, which index was read) all come out of `EXPLAIN` text or JSON. The first version of this repository parsed them inside helpers that also held the database connection, so nothing about the lesson could be tested without a seeded database and a minute of waiting.

## Decision

Parsing and arithmetic live in `domain/` (`plan.py`, `write_cost.py`, `comparison.py`) and never import a database driver; `application/` replays the lesson against a `LabDatabase` port; `infrastructure/lab_database.py` is the only module that talks to PostgreSQL. An import-linter contract fails the build if `domain` or `application` import `psycopg`.

```

The changelog has a heading per version (`## [0.1.0] - 2026-10-27`) and sub-headings `### Added`. The decision record has the fixed parts `Status`, `Context`, `Decision`, `Consequences`.

## Try it yourself

1. Open `ARCHITECTURE.md` on GitHub, or in an editor with a Markdown preview, to see the two diagrams drawn.
2. Paste the flowchart block into https://mermaid.live to edit it and watch the picture change.
3. `grep -c '```mermaid' ARCHITECTURE.md` prints `2`.
4. `head -12 sql/explain/results.md` — the generated table in raw Markdown; paste it into a previewer to see the table.
5. `.venv/bin/python -c "print(open('CHANGELOG.md').read().splitlines()[0])"` prints `# Changelog`.

## Mistakes people make

- Forgetting the blank line before a list or a table, so it is shown as plain text.
- Not closing a code block (three backticks), so the rest of the page turns into code.
- Putting a literal `|` inside a table cell without escaping it.
- Making diagrams so large that nobody can read them.
- Hard-wrapping lines inconsistently, which makes diffs noisy.

**How this repository avoids them.** Every code block is closed; tables have blank lines before them; diagrams are small; `.editorconfig` keeps trailing spaces in `.md` files; generated Markdown comes from one function that is unit-tested (`test_report.py`).

## Check yourself

1. How do you write a level-2 heading? *Start a line with `## `.*
2. How do you show a command as code? *Put it in backticks for inline code, or in a fenced block with three backticks.*
3. What does a Mermaid block contain? *A diagram described as text, drawn by the viewer.*
4. What does `a -->|"text"| b` draw? *An arrow from node a to node b labelled "text".*
5. What is an ADR? *An architecture decision record: a short document giving the context, the decision and the consequences of one real choice.*

## Further reading

- CommonMark specification (the base of Markdown): https://spec.commonmark.org/ ; GitHub Flavored Markdown: https://github.github.com/gfm/
- Mermaid documentation: https://mermaid.js.org/intro/ (flowchart: https://mermaid.js.org/syntax/flowchart.html ; entity relationship: https://mermaid.js.org/syntax/entityRelationshipDiagram.html)
- Keep a Changelog 1.1.0: https://keepachangelog.com/en/1.1.0/ ; ADRs: https://adr.github.io/
