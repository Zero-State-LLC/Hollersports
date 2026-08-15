#!/usr/bin/env bash
#
# Security scan — run this locally, exactly as CI runs it.
#
#   ./scripts/security-scan.sh                 # scan, fail on findings
#   REPORT_ONLY=1 ./scripts/security-scan.sh   # scan, always exit 0
#
# CodeQL is licensed for open source only, so these private repos use
# permissively-licensed scanners instead. Nothing here uploads source code:
# gitleaks and bandit are entirely local, osv-scanner sends package names and
# versions, semgrep downloads rules and runs with metrics disabled.
#
# Tools are cached outside the repo, so the working tree stays clean.

set -euo pipefail

GITLEAKS_VERSION="${GITLEAKS_VERSION:-8.30.1}"
OSV_VERSION="${OSV_VERSION:-2.5.0}"
REPORT_ONLY="${REPORT_ONLY:-0}"

ROOT="$(git rev-parse --show-toplevel)"
TOOLDIR="${RUNNER_TEMP:-${TMPDIR:-/tmp}}/zsl-security-tools"
BIN="$TOOLDIR/bin"
VENV="$TOOLDIR/venv"
mkdir -p "$BIN"

failed=()
note() { printf '\n\033[1m== %s\033[0m\n' "$1"; }
record() { failed+=("$1"); printf '\033[31mFAIL: %s\033[0m\n' "$1"; }

case "$(uname -s)" in Darwin) OS=darwin ;; *) OS=linux ;; esac
case "$(uname -m)" in arm64|aarch64) ARCH=arm64 ;; *) ARCH=amd64 ;; esac

# ---------------------------------------------------------------- install ---
if [ ! -x "$BIN/gitleaks" ]; then
  note "installing gitleaks $GITLEAKS_VERSION"
  GL_ARCH="$ARCH"; [ "$ARCH" = amd64 ] && GL_ARCH=x64
  curl -fsSL -o "$TOOLDIR/gl.tar.gz" \
    "https://github.com/gitleaks/gitleaks/releases/download/v${GITLEAKS_VERSION}/gitleaks_${GITLEAKS_VERSION}_${OS}_${GL_ARCH}.tar.gz"
  tar xzf "$TOOLDIR/gl.tar.gz" -C "$BIN" gitleaks
fi

if [ ! -x "$BIN/osv-scanner" ]; then
  note "installing osv-scanner $OSV_VERSION"
  curl -fsSL -o "$BIN/osv-scanner" \
    "https://github.com/google/osv-scanner/releases/download/v${OSV_VERSION}/osv-scanner_${OS}_${ARCH}"
  chmod +x "$BIN/osv-scanner"
fi

has_python=0
if find "$ROOT" -name '*.py' -not -path '*/.git/*' -print -quit 2>/dev/null | grep -q .; then
  has_python=1
fi

if [ ! -x "$VENV/bin/semgrep" ]; then
  note "installing semgrep + bandit"
  python3 -m venv "$VENV"
  "$VENV/bin/pip" install --quiet --upgrade pip
  # Deliberately unpinned: stale rules are worse than non-reproducible ones
  # for a security scanner.
  "$VENV/bin/pip" install --quiet semgrep bandit
fi

EXCLUDES=(--exclude=.git --exclude=build --exclude=DerivedData
          --exclude=node_modules --exclude=.venv --exclude=Pods)

# ------------------------------------------------------------------ scans ---
note "secrets (gitleaks, full history)"
GL_CONF=()
[ -f "$ROOT/.gitleaks.toml" ] && GL_CONF=(--config "$ROOT/.gitleaks.toml")
"$BIN/gitleaks" detect --source "$ROOT" "${GL_CONF[@]}" \
  --redact --no-banner || record "gitleaks: secrets detected"

BANDIT_EXCLUDE="$ROOT/.git,$ROOT/build,$ROOT/DerivedData,$ROOT/.venv,$ROOT/node_modules"

if [ "$has_python" = 1 ]; then
  # Note on flags: -l/-ll/-lll is severity LOW/MEDIUM/HIGH and above, and
  # -i/-ii/-iii is the same for confidence. So -ll -ii means MEDIUM and above,
  # NOT high -- which is why this gate first failed on repos whose worst
  # finding was medium.
  note "python SAST (bandit) — informational, medium severity and above"
  "$VENV/bin/bandit" -r "$ROOT" -ll -ii -q --exclude "$BANDIT_EXCLUDE" || true

  note "python SAST (bandit) — gate, high severity AND high confidence"
  "$VENV/bin/bandit" -r "$ROOT" -lll -iii -q --exclude "$BANDIT_EXCLUDE" \
    || record "bandit: high-severity, high-confidence python findings"
else
  note "python SAST (bandit) — no python sources, skipped"
fi

note "multi-language SAST (semgrep)"
"$VENV/bin/semgrep" scan --config=p/security-audit \
  --metrics=off --error --severity=ERROR --quiet \
  "${EXCLUDES[@]}" "$ROOT" || record "semgrep: ERROR-severity findings"

note "dependencies (osv-scanner) — advisory only"
# Never blocking: a fresh CVE in a transitive dependency should not stop an
# unrelated PR. Review these, do not gate on them.
"$BIN/osv-scanner" scan source --recursive "$ROOT" || true

# ----------------------------------------------------------------- result ---
echo
if [ ${#failed[@]} -eq 0 ]; then
  printf '\033[32mAll blocking checks passed.\033[0m\n'
  exit 0
fi
printf '\033[31m%d blocking check(s) failed:\033[0m\n' "${#failed[@]}"
printf '  - %s\n' "${failed[@]}"
[ "$REPORT_ONLY" = "1" ] && { echo "REPORT_ONLY=1 — exiting 0 anyway."; exit 0; }
exit 1
