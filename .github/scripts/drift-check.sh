#!/usr/bin/env bash
# Quick documentation drift check for the BA agent.
# Outputs a systemMessage if drift indicators are found.
set -euo pipefail

cd "$(dirname "$0")/../.."

issues=()

# 1. Count NotImplementedError stubs vs what plan.md claims as done
stubs=$(grep -r 'NotImplementedError' src/ --include='*.py' -l 2>/dev/null | wc -l | tr -d ' ')
if [[ "$stubs" -gt 0 ]]; then
  issues+=("$stubs file(s) still have NotImplementedError stubs")
fi

# 2. Check if plan.md exists
if [[ ! -f docs/plan.md ]]; then
  issues+=("docs/plan.md is missing")
fi

# 3. Check tasks with stale in-progress status (> basic heuristic)
if [[ -d docs/tasks ]]; then
  in_progress=$(grep -rl 'Статус.*in-progress' docs/tasks/ 2>/dev/null | wc -l | tr -d ' ')
  if [[ "$in_progress" -gt 3 ]]; then
    issues+=("$in_progress tasks stuck in-progress — review needed")
  fi
fi

# Output
if [[ ${#issues[@]} -gt 0 ]]; then
  msg="⚠️ Documentation drift detected:\\n"
  for issue in "${issues[@]}"; do
    msg+="- $issue\\n"
  done
  msg+="\\nRun a drift check to get details."
  # JSON output for hook systemMessage
  printf '{"systemMessage": "%s"}' "$msg"
fi
