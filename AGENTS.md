# AGENTS.md

`CLAUDE.md` and `GEMINI.md` are symlinks to this file.

# tv-renamer

Rename and organize ripped TV media files into Jellyfin-standard naming.
This is an interactive tool — Claude Code is the operator, not the end user.

## How it works

Key CLI subcommands, driven by Claude Code in conversation:

1. `uv run tv-renamer scan <dir>` — inventory a directory of media files,
   report what's there (show folders, loose movies, episode counts, naming
   patterns).

2. `uv run tv-renamer search <query>` — search TMDB for a TV show or movie,
   print candidates with IDs, years, and overviews.

3. `uv run tv-renamer episodes <tmdb-id> [--season N]` — list episodes for
   a matched show, so the operator can verify the match.

4. `uv run tv-renamer rename <dir> --id <tmdb-id> [--season N] [--dry-run]
   [--log changes.log]` — rename episodes to Jellyfin format, creating
   season folders as needed. Matches files to episodes by the episode number
   extracted from the filename. Also writes a `tvshow.nfo` with the TMDB ID.

5. `uv run tv-renamer copy <dir> --dest <path> [--dry-run]` — rsync
   organized files to the NAS with verification.

## Output format

Rename produces Jellyfin-standard structure with embedded TMDB ID:

```
Show Name (Year) [tmdbid-N]/
├── tvshow.nfo              # TMDB ID for guaranteed Jellyfin matching
├── Season 1/
│   ├── Show Name - S01E01 - Episode Title.ext
│   └── Show Name - S01E02 - Episode Title.ext
└── Season 2/
    └── ...
```

The `[tmdbid-N]` in the folder name and the `tvshow.nfo` file together
ensure Jellyfin matches the correct show without guessing. Jellyfin
auto-generates artwork, per-episode NFOs, and other metadata after import.

## Workflow

Processing the portable drive is done show by show across sessions:

1. `scan` the source directory to see what's there.
2. Per show: `search` to find the TMDB match, `episodes` to verify,
   `rename --dry-run` to preview, then `rename` to apply.
3. Before copying, check for duplicates on the NAS. Use `ffprobe` to
   compare resolution, bitrate, and audio quality when both versions exist.
4. `copy` the organized show to the NAS destination.
5. Repeat until done.

## Architecture

```
src/tv_renamer/
├── __init__.py      # Version
├── cli.py           # Argparse entry point (all subcommands)
├── tmdb.py          # TMDB API client (rate-limited, session-based)
├── scanner.py       # Directory inventory and file classification
├── matcher.py       # Episode number extraction from filenames
├── renamer.py       # Rename orchestration: match → rename → mkdir → nfo
└── copier.py        # rsync wrapper with verification
```

- `tmdb.py` searches and fetches TV shows and movies from TMDB. Uses a
  `TMDBClient` class with `requests.Session` for connection reuse,
  `User-Agent` header, and 0.25s rate limiting between requests.
- `scanner.py` walks a directory tree and classifies entries as shows vs.
  movies, reports episode counts and naming patterns.
- `matcher.py` extracts episode numbers from filenames using multiple
  patterns: `S01E01`, `[S01.E01]`, `1x01`, bare leading numbers (`01`),
  and trailing numbers after CJK characters (`死神粤语01`).
- `renamer.py` builds target paths from TMDB metadata and computed matches,
  renames files, creates season directories, writes `tvshow.nfo`.
- `copier.py` wraps rsync for verified transfer to the NAS.

## Safety

- `scan`, `search`, and `episodes` are read-only.
- `rename --dry-run` is read-only. Always run it first.
- `rename` (without `--dry-run`) moves files on disk. Review the dry-run
  output before running.
- `copy --dry-run` previews the rsync without transferring.

## Environment setup

TMDB API key is stored in `.env` (gitignored), loaded via `python-dotenv`:

```
TMDB_API_KEY=your-key-here
```

## Archetype

Python package (see the project-standards skill, `references/python-package.md`).

## Tooling

| Verb | Does |
|---|---|
| `just lint` | ruff check + format check (read-only) |
| `just format` | ruff format + fix |
| `just type-check` | mypy strict (src only) |
| `just test` | pytest with coverage |
| `just check` | full gate: lint + type-check + test |
| `just hooks-install` | install the pre-commit hook once per clone |

## Known exceptions

- **mypy scoped to src/ only.** mypy 2.3 regression prevents test overrides
  from suppressing `no-untyped-def` in strict mode.
