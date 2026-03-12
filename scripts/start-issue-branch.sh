#!/usr/bin/env bash

set -euo pipefail

if [ "$#" -ne 3 ]; then
  echo "Usage: $0 <issue-number> <type> <short-slug>" >&2
  echo "Example: $0 8 feature fastapi-migration" >&2
  exit 1
fi

issue_number="$1"
branch_type="$2"
short_slug="$3"
branch_name="codex/${branch_type}/${issue_number}-${short_slug}"

git checkout main
git pull --ff-only
git checkout -b "${branch_name}"

echo "Created branch ${branch_name}"
