# Movie Support Plan

Add support for renaming and organizing movie files into Jellyfin-standard
naming, alongside the existing TV episode workflow.

## Target output format

Jellyfin-standard movie structure with embedded TMDB ID:

```
Movie Name (Year) [tmdbid-N]/
├── movie.nfo
└── Movie Name (Year) [tmdbid-N].ext
```

The `[tmdbid-N]` in the folder name and the `movie.nfo` file together ensure
Jellyfin matches the correct movie without guessing.

## Current state

- `tmdb.py` has `search_movie()` but no `get_movie()` for fetching details.
- `scanner.py` classifies top-level files as `LooseFile` — already surfaces
  movies, but doesn't call them that.
- `matcher.py` is entirely episode-oriented — not relevant for movies.
- `renamer.py` builds episode paths with season folders — no movie path logic.
- `planner.py` generates YAML plans for episode assignment — no movie variant.
- `copier.py` is media-type-agnostic — works as-is for movies.
- `cli.py` has `search --type movie` but no movie detail or rename commands.

---

## Phase 1 — TMDB movie metadata (`tmdb.py`)

Add the ability to fetch movie details by TMDB ID, parallel to `get_show()`.

### 1.1 Add `MovieInfo` dataclass

**Files:** `src/tv_renamer/tmdb.py`

Add `MovieInfo` with fields: `tmdb_id`, `name`, `release_date`, `overview`,
`runtime`. Add a `year` property matching the `ShowInfo.year` pattern.

**Acceptance:**
- [x] `MovieInfo` is a frozen dataclass with all five fields.
- [x] `.year` returns the first four characters of `release_date`, or `"????"`
      when `release_date` is empty.

### 1.2 Add `TMDBClient.get_movie()`

**Files:** `src/tv_renamer/tmdb.py`

Call the `/movie/{id}` endpoint. Map the JSON response to `MovieInfo`.

**Acceptance:**
- [x] `client.get_movie(550)` returns a `MovieInfo` with correct fields.
- [x] Rate limiting applies to movie requests the same as TV requests.

### 1.3 Tests for movie metadata

**Files:** `tests/test_tmdb.py`

Mock the `/movie/{id}` endpoint. Verify `MovieInfo` fields parse correctly.
Test missing `release_date` returns `"????"` for year.

**Acceptance:**
- [x] Test class `TestGetMovie` with at least two test methods.
- [x] All existing TMDB tests still pass.

---

## Phase 2 — Movie rename paths (`renamer.py`)

Build Jellyfin-standard destination paths for movies and write movie NFOs.

### 2.1 Add `movie_dir_name()`

**Files:** `src/tv_renamer/renamer.py`

`movie_dir_name(name, year, tmdb_id) -> str`. Returns
`"Name (Year) [tmdbid-N]"`, reusing `_safe_name()` for sanitization. This is
identical to `show_dir_name()` — decide whether to share or keep separate.
Keeping them separate is safer if TV and movie Jellyfin conventions ever
diverge.

**Acceptance:**
- [x] `movie_dir_name("Fight Club", "1999", 550)` returns
      `"Fight Club (1999) [tmdbid-550]"`.
- [x] Characters unsafe for filenames are sanitized.

### 2.2 Add `build_movie_path()`

**Files:** `src/tv_renamer/renamer.py`

`build_movie_path(out_root, name, year, tmdb_id, extension) -> Path`. Returns
`out_root / dir_name / "Name (Year) [tmdbid-N].ext"`. No season subfolder.

**Acceptance:**
- [x] Returns `root/Fight Club (1999) [tmdbid-550]/Fight Club (1999) [tmdbid-550].mkv`.
- [x] Extension is preserved from the source file.
- [x] Long movie names are truncated to fit 255 UTF-8 bytes.

### 2.3 Add movie NFO support

**Files:** `src/tv_renamer/renamer.py`

Add `_MOVIE_NFO_TEMPLATE` with `<movie>` root element containing `<title>` and
`<tmdbid>`. Add `write_movie_nfo(movie_dir, name, tmdb_id) -> Path`. Write as
`movie.nfo` (not `tvshow.nfo`).

**Acceptance:**
- [x] NFO file is named `movie.nfo`.
- [x] XML-escape is applied to the title.
- [x] Output parses as valid XML with correct elements.

### 2.4 Add `plan_movie_rename()`

**Files:** `src/tv_renamer/renamer.py`

`plan_movie_rename(file, name, year, tmdb_id, output) -> RenameOp`.
Single-file rename planning for one movie. Validates the source file exists
and has a media extension.

**Acceptance:**
- [x] Returns a `RenameOp` with correct source and dest.
- [x] Raises if the source file does not exist.

### 2.5 Tests for movie rename paths

**Files:** `tests/test_renamer.py`

Test `movie_dir_name` sanitization, `build_movie_path` output structure,
`write_movie_nfo` XML content, and `plan_movie_rename` source/dest pair.

**Acceptance:**
- [x] All new functions have test coverage.
- [x] All existing renamer tests still pass.
- [x] `just check` passes.

---

## Phase 3 — CLI movie commands (`cli.py`)

Add subcommands for the movie workflow: fetch details, rename files.

### 3.1 Add `movie` subcommand

**Files:** `src/tv_renamer/cli.py`

Takes a TMDB movie ID. Calls `get_movie()`, prints name, year, runtime, and
overview.

**Acceptance:**
- [x] `tv-renamer movie 550` prints movie details.
- [x] Requires `TMDBClient` (sets `needs_client=True`).

### 3.2 Add `movie-rename` subcommand

**Files:** `src/tv_renamer/cli.py`

Takes a file path and `--id` (TMDB movie ID). Supports `--dry-run`,
`--output`, and `--log`. Calls `get_movie()` for metadata, builds rename op
via `plan_movie_rename()`, executes or previews. Writes `movie.nfo` on real
runs.

**Acceptance:**
- [x] `movie-rename file.mkv --id 550 --dry-run` previews the rename.
- [x] `movie-rename file.mkv --id 550` moves the file and writes `movie.nfo`.
- [x] `--output` overrides the destination root directory.
- [x] `--log` writes the move and NFO path to the log file.
- [x] Log format matches the existing `source -> dest` / `wrote path` format.

### 3.3 Verify undo works for movie renames

**Files:** `tests/test_renamer.py`

The existing `undo` subcommand parses `source -> dest` and `wrote path` log
lines generically. Verify it reverses movie renames without code changes.
Add a test if the log format is compatible (it should be).

**Acceptance:**
- [x] `rename` then `undo` on a movie log restores the original file.
- [x] `movie.nfo` is removed by undo.
- [x] Emptied movie directory is pruned.

### 3.4 CLI tests

**Files:** `tests/test_cli.py`

Test `movie` subcommand output, `movie-rename --dry-run` preview, and actual
rename execution.

**Acceptance:**
- [x] Tests cover both `movie` and `movie-rename` subcommands.
- [x] `just check` passes.

---

## Phase 4 — Batch movie planning (`planner.py`)

Support a YAML plan for renaming multiple movie files at once, each mapped
to its own TMDB ID.

### 4.1 Add `MoviePlanEntry` dataclass

**Files:** `src/tv_renamer/planner.py`

Fields: `file`, `tmdb_id` (nullable), `name` (nullable), `year` (nullable).
A null `tmdb_id` means the file is skipped during execution.

**Acceptance:**
- [x] Dataclass is defined with all fields.
- [x] Nullable fields default to `None`.

### 4.2 Add `MoviePlanData` dataclass

**Files:** `src/tv_renamer/planner.py`

Fields: `directory`, `files: list[MoviePlanEntry]`, `output` (nullable).

**Acceptance:**
- [x] Dataclass is defined with all fields.

### 4.3 Add `generate_movie_plan()`

**Files:** `src/tv_renamer/planner.py`

`generate_movie_plan(directory) -> MoviePlanData`. Lists all media files in
the directory with null TMDB IDs, ready for the operator to fill in.

**Acceptance:**
- [x] All media files in the directory appear as entries.
- [x] Non-media files are excluded.
- [x] All TMDB fields are null in the generated plan.

### 4.4 Add `write_movie_plan()` and `read_movie_plan()`

**Files:** `src/tv_renamer/planner.py`

YAML serialization matching the TV plan style. Include comments guiding the
operator to fill in TMDB IDs.

**Acceptance:**
- [x] Round-trip write then read produces identical `MoviePlanData`.
- [x] Generated YAML includes instructional comments.
- [x] Missing required keys in the YAML raise `ValueError`.

### 4.5 Add `movie_plan_to_renames()`

**Files:** `src/tv_renamer/planner.py`

`movie_plan_to_renames(plan, client) -> RenamePlan`. For each entry with a
non-null `tmdb_id`: if `name`/`year` are provided, use them directly;
otherwise fetch from TMDB via `client.get_movie()`. Build rename ops.
Detect collisions.

**Acceptance:**
- [x] Entries with null `tmdb_id` are skipped and reported as unmatched.
- [x] Entries with `name`/`year` filled in do not call TMDB.
- [x] Two entries resolving to the same destination are reported as collisions.

### 4.6 Add `movie-plan` CLI subcommand

**Files:** `src/tv_renamer/cli.py`

`movie-plan <directory> [-o plan.yaml]`. Generates the YAML plan file from a
directory of movie files.

**Acceptance:**
- [x] `movie-plan ./movies -o plan.yaml` writes a valid YAML plan.
- [x] Without `-o`, prints to stdout.

### 4.7 Extend `movie-rename` to accept `--plan`

**Files:** `src/tv_renamer/cli.py`

`movie-rename --plan plan.yaml [--dry-run] [--output DIR] [--log FILE]`.
Alternative to single-file mode. Executes the batch plan.

**Acceptance:**
- [x] `--plan` and single-file `--id` modes are mutually exclusive.
- [x] Batch mode renames all entries with TMDB IDs and writes per-movie NFOs.
- [x] `--dry-run` previews all renames.

### 4.8 Tests for batch movie planning

**Files:** `tests/test_planner.py`

Round-trip plan write/read, plan-to-renames with mock TMDB, collision
detection, CLI integration.

**Acceptance:**
- [x] All new functions have test coverage.
- [x] `just check` passes.

---

## Phase 5 — Scanner movie awareness (`scanner.py`)

Improve `scan` output to distinguish likely movies from misplaced episodes.

### 5.1 Classify top-level files as movies vs. episodes

**Files:** `src/tv_renamer/scanner.py`

Use `extract_episode()` from `matcher.py` on each loose file. Files that
match an episode pattern stay as loose files (likely misplaced episodes).
Files that don't match any episode pattern are classified as probable movies.

**Acceptance:**
- [ ] `Some.Movie.2020.mkv` (no episode pattern) classified as movie.
- [ ] `S01E01 - Pilot.mkv` (episode pattern) classified as loose episode.
- [ ] Classification is a new field or separate list on `ScanResult`.

### 5.2 Update scan CLI output

**Files:** `src/tv_renamer/cli.py`

Print a "Movies" section listing probable movie files separately from
episode-looking loose files.

**Acceptance:**
- [ ] `scan` output has separate "Movies" and "Loose files" sections.
- [ ] Section is suppressed when empty (no "Movies (0):" noise).

### 5.3 Tests for movie classification

**Files:** `tests/test_scanner.py`

Verify classification of movie files vs. episode-like files at the top level.

**Acceptance:**
- [ ] Tests cover both categories.
- [ ] `just check` passes.

---

## Phase 6 — Documentation and cleanup

### 6.1 Update `CLAUDE.md`

**Files:** `CLAUDE.md`

Update architecture table to list any new modules. Update workflow section
to cover movie commands. Add movie output format example.

**Acceptance:**
- [ ] Architecture table includes all source modules.
- [ ] Movie workflow is documented parallel to the TV workflow.

### 6.2 Update CLI description

**Files:** `src/tv_renamer/cli.py`

Change program description from "TV media files" to "TV and movie media
files". Update help strings as needed.

**Acceptance:**
- [ ] `tv-renamer --help` mentions movies.

### 6.3 Final gate

**Acceptance:**
- [ ] `just check` passes (lint + type-check + test).
- [ ] All checkboxes in this plan are checked.

---

## Non-goals

- **Automatic movie identification.** The tool does not guess which TMDB movie
  a file is. The operator searches, verifies, and assigns the ID.
- **Movie collections/series.** No special handling for franchise grouping.
  Each movie is independent.
- **Subtitle or extras renaming.** Only the primary media file is renamed.
- **Package rename.** The package stays `tv-renamer`.

## Dependencies

No new dependencies. All TMDB movie endpoints use the same API key and rate
limiting already in `TMDBClient`.

## Risk

- The existing `undo` command parses log lines generically (`source -> dest`
  and `wrote path`). If movie renames use the same log format, undo works
  for free. Verify in Phase 3.3.
- `_safe_name()` and `_truncate_filename()` are shared with TV — movie names
  go through the same sanitization. No new edge cases expected.
- `show_dir_name()` and `movie_dir_name()` produce the same format. Could
  share one function, but keeping them separate avoids coupling if Jellyfin
  conventions diverge.
