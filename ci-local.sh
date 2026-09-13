#!/usr/bin/env bash
# ci-local.sh — run what ci.yml runs, in the same order, and say exactly where it breaks.
#
#   bash ci-local.sh            run against the working tree (fast loop)
#   bash ci-local.sh --clean    clone HEAD into a temp dir with a fresh venv first
#                               (this is the one that actually reproduces CI)
#
# Works in Git Bash on Windows and in any Linux/macOS shell.

set -u
CLEAN=0
[ "${1:-}" = "--clean" ] && CLEAN=1

red()  { printf '\033[31m%s\033[0m\n' "$*"; }
grn()  { printf '\033[32m%s\033[0m\n' "$*"; }
bold() { printf '\033[1m%s\033[0m\n' "$*"; }

# ── 0. is make even here? On Windows it often is not. ────────────────────────
if ! command -v make >/dev/null 2>&1; then
  red "make is not installed in this shell."
  echo "  Windows options:  winget install GnuWin32.Make   |   choco install make   |   use WSL"
  echo "  Git Bash does not ship make. Without it you cannot run this pipeline locally."
  exit 127
fi

# ── 1. optional clean-room clone: no editable install, no .env, no stale target/ ──
if [ "$CLEAN" = "1" ]; then
  ROOT="$(git rev-parse --show-toplevel)" || { red "not inside a git repo"; exit 1; }
  TMP="$(mktemp -d)"
  bold "cloning HEAD into $TMP (clean room — none of your local state)"
  git clone --quiet "$ROOT" "$TMP/repo" || { red "clone failed"; exit 1; }
  cd "$TMP/repo" || exit 1
  python -m venv .venv || { red "venv failed"; exit 1; }
  # Git Bash on Windows uses Scripts/, everything else uses bin/
  if [ -f .venv/Scripts/activate ]; then . .venv/Scripts/activate; else . .venv/bin/activate; fi
  grn "python: $(python --version 2>&1)  at  $(command -v python)"
else
  cd "$(git rev-parse --show-toplevel)" || exit 1
  bold "running against your working tree (use --clean to reproduce CI faithfully)"
fi

# ── 2. the steps ci.yml runs, in order ───────────────────────────────────────
run () {                       # run "<label>" "<command>"
  echo
  bold "=== $1 ==="
  echo "\$ $2"
  # shellcheck disable=SC2086
  eval "$2"
  local code=$?
  if [ $code -ne 0 ]; then
    echo
    red "FAILED at: $1"
    red "  command : $2"
    red "  exit    : $code"
    if [ $code -eq 2 ]; then
      echo "  exit 2 is make's code for EVERY failure — it means nothing on its own."
      echo "  Scroll up for the line starting 'make: ***' — it names the target and the"
      echo "  real inner exit code, e.g.  make: *** [Makefile:12: load] Error 1"
    fi
    exit $code
  fi
  grn "ok — $1"
}

run "Install dependencies"                  "pip install -r requirements.txt"

if [ -f pyproject.toml ] || [ -f setup.py ]; then
  run "Install the package itself"          "pip install -e ."
else
  echo; echo "(no pyproject.toml / setup.py — skipping editable install)"
fi

echo
bold "=== Preflight: do the targets exist? ==="
make -n samples generate load build check test >/dev/null 2>&1 \
  && grn "all six targets resolve" \
  || { red "at least one target does not resolve — running the dry run to show which:"; \
       make -n samples generate load build check test; }

run "Generate models from templates"        "make samples generate"
run "Load raw data"                         "make load"
run "Build warehouse (dbt models + tests)"  "make build"
run "Enforce the versioned model contract"  "make check"
run "Unit tests"                            "make test"

echo
grn "================================================"
grn " all steps passed — this is what CI will do too"
grn "================================================"
[ "$CLEAN" = "1" ] && echo "clean-room copy left at: $PWD"
exit 0
