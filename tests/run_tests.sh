#!/usr/bin/env bash
# Asserts that each fixture produces exactly the findings it is designed to produce.
set -u
cd "$(dirname "$0")/.."
LINT="python3 scripts/lint_skills.py"
pass=0; fail=0

codes() { $LINT "tests/fixtures/$1" --target "${2:-both}" --json | python3 -c \
  'import json,sys; print(" ".join(sorted({f["code"] for f in json.load(sys.stdin)["findings"]})))'; }

expect() { # name  target  expected-codes
  local got; got="$(codes "$1" "$2")"
  if [ "$got" = "$3" ]; then
    printf 'ok    %-20s %s\n' "$1" "$got"; pass=$((pass+1))
  else
    printf 'FAIL  %-20s expected [%s] got [%s]\n' "$1" "$3" "$got"; fail=$((fail+1))
  fi
}

expect clean-skill         both        ""
expect broken-frontmatter  both        "E002"
expect portability-break   both        "E004"
expect portability-break   claude-code "I001"
expect bad-name            both        "E008 E009 W004 W006"
expect weak-description    both        "W004 W005 W006 W013 W014 W015 W016"
expect deep-refs           both        "W017"

# exit codes
$LINT tests/fixtures/clean-skill --strict >/dev/null 2>&1
[ $? -eq 0 ] && { echo "ok    exit-code clean = 0"; pass=$((pass+1)); } || { echo "FAIL  exit-code clean"; fail=$((fail+1)); }
$LINT tests/fixtures/portability-break >/dev/null 2>&1
[ $? -eq 1 ] && { echo "ok    exit-code errors = 1"; pass=$((pass+1)); } || { echo "FAIL  exit-code errors"; fail=$((fail+1)); }
$LINT tests/fixtures/does-not-exist >/dev/null 2>&1
[ $? -eq 2 ] && { echo "ok    exit-code bad-path = 2"; pass=$((pass+1)); } || { echo "FAIL  exit-code bad-path"; fail=$((fail+1)); }

# the skill must lint itself clean
$LINT . --target spec --strict >/dev/null 2>&1
[ $? -eq 0 ] && { echo "ok    self-lint clean"; pass=$((pass+1)); } || { echo "FAIL  self-lint"; fail=$((fail+1)); }

echo
echo "$pass passed, $fail failed"
[ "$fail" -eq 0 ]
