# pomocli

A single-file curses Pomodoro timer. Everything lives in `pomocli.py`;
there are no packages, no dependencies beyond the standard library, and no
build step. Run it with `python3 pomocli.py`.

## Hard rules

### Never put session links or AI byline footers in git or GitHub

This covers commit messages, tags, PR titles and bodies, issue bodies, and
review comments. Specifically forbidden:

- Any `claude.ai/code/session_…` link, in any form
- `Claude-Session:` trailers
- `Generated with Claude Code` footers

`Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>` is fine and should
stay — the objection is to session links and byline footers, not to
attribution.

These links resolve for nobody but the repo owner, they cannot be revoked
once published, and a public repo keeps them forever. Before pushing a
branch or opening a PR, grep the message text and strip any hit.

## Constraints

- **Python 3.9 is the floor.** The README promises it. This rules out
  `X | None` annotations and `zip(strict=)`; `list[str]` is fine. Ruff's
  `UP045` suggestions would break it — do not apply them blindly.
- **Standard library only.** No third-party imports, ever.
- **The log format is a compatibility surface.** Lines are
  `{timestamp} - {state}: {task}` with states `START`, `END`, `ABORT`, and
  `COMPLETE EARLY`. People grep this file. Changing the format is a breaking
  change; write through `format_log_line()` and read through
  `parse_log_line()` rather than hand-rolling either.
- **Task descriptions may contain `": "`.** Parse against the known state
  list, not the first separator found.

## Release process

- The version lives in exactly one place: `__version__` in `pomocli.py`.
  Nothing in the README or packaging duplicates it.
- Semver: bug fixes are patch, new features are minor.
- The version bump is its own commit, included in the feature PR.
- **The user merges the PR and applies the tag on `main`, after merging.**
  Never `gh pr merge`, and never push a version tag. A tag on an unmerged
  branch dangles if the PR is squash- or rebase-merged.

## Testing

The user runs and visually checks the curses TUI themselves. Commit locally
and hand off rather than pushing unprompted. Logic that is not the TUI —
log parsing, session grouping, file rewriting — should be exercised
headlessly before handing off.
