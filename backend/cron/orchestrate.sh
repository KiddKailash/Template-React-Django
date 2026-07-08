#!/usr/bin/env bash
# =============================================================================
# Cron Orchestrator (template)
# =============================================================================
#
# MODES (extend with the commands your project needs):
#   daily         — runs every day
#   nightly       — runs most nights
#   weekly        — Sunday batch
#
# USAGE
#   ./cron/orchestrate.sh daily
#   ./cron/orchestrate.sh nightly [--dry-run]
#   ./cron/orchestrate.sh weekly
#
# CRONTAB (install with: crontab backend/cron/crontab.txt)
# =============================================================================

set -euo pipefail

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(dirname "$SCRIPT_DIR")"
LOG_DIR="$SCRIPT_DIR/logs"
LOG_FILE="$LOG_DIR/orchestrate-$(date +%Y-%m-%d).log"

# Detect uv (docker container vs local dev machine)
if [[ -f "/bin/uv" ]]; then
    UV="/bin/uv"
elif command -v uv >/dev/null 2>&1; then
    UV=$(command -v uv)
else
    echo "uv not found on PATH" >&2
    exit 1
fi

MANAGE="$UV run python manage.py"

# ---------------------------------------------------------------------------
# Args
# ---------------------------------------------------------------------------
MODE="${1:-}"
DRY_RUN=""
if [[ "${2:-}" == "--dry-run" ]]; then
    DRY_RUN="--dry-run"
fi

if [[ -z "$MODE" ]]; then
    echo "Usage: $0 {daily|nightly|weekly} [--dry-run]" >&2
    exit 1
fi

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
mkdir -p "$LOG_DIR"

log() {
    local msg="[$(date '+%Y-%m-%d %H:%M:%S')] $*"
    echo "$msg" | tee -a "$LOG_FILE"
}

log_sep() {
    log "──────────────────────────────────────────────────────"
}

# ---------------------------------------------------------------------------
# Command runner — logs outcome, tracks failures
# ---------------------------------------------------------------------------
FAILURES=0

run_cmd() {
    local name="$1"
    shift
    log "▶ $name"
    local start
    start=$(date +%s)

    # shellcheck disable=SC2086
    if (cd "$BACKEND_DIR" && $MANAGE "$@") >> "$LOG_FILE" 2>&1; then
        local elapsed=$(( $(date +%s) - start ))
        log "✓ $name completed in ${elapsed}s"
    else
        local exit_code=$?
        local elapsed=$(( $(date +%s) - start ))
        log "✗ $name FAILED (exit $exit_code) after ${elapsed}s"
        FAILURES=$(( FAILURES + 1 ))
        # Non-fatal: continue so remaining commands still run
    fi
}

# ---------------------------------------------------------------------------
# Mode dispatch — add project-specific management commands here.
# ---------------------------------------------------------------------------
log_sep
log "START mode=$MODE${DRY_RUN:+ DRY_RUN}"
log_sep

case "$MODE" in

    daily)
        # Example placeholder — replace with your daily commands.
        log "No daily commands configured. Add them to cron/orchestrate.sh."
        ;;

    nightly)
        # Example placeholder — replace with your nightly commands.
        log "No nightly commands configured. Add them to cron/orchestrate.sh."
        ;;

    weekly)
        # Example placeholder — replace with your weekly commands.
        log "No weekly commands configured. Add them to cron/orchestrate.sh."
        ;;

    *)
        log "ERROR: unknown mode '$MODE'. Valid modes: daily, nightly, weekly"
        exit 1
        ;;

esac

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
log_sep
if [[ $FAILURES -eq 0 ]]; then
    log "DONE mode=$MODE — all commands succeeded"
else
    log "DONE mode=$MODE — $FAILURES command(s) FAILED (see above)"
    exit 1
fi
