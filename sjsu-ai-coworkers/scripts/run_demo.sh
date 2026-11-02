#!/usr/bin/env bash
# Regenerate every file in samples/ from scratch (offline, deterministic).
set -euo pipefail
cd "$(dirname "$0")/.."
DB=samples/demo_memory.sqlite
rm -f "$DB" samples/*.md samples/*.txt
CLI="python -m coworkers.cli --db $DB"
SNAP=data/fixtures/articles_snapshot_2026-11-01.json

echo "== Agent 1: day 1 brief"
$CLI brief --snapshot $SNAP --date 2026-11-01 --out samples > /dev/null
echo "== Student feedback on day 1"
$CLI read  "https://www.anthropic.com/engineering/redesigning-source-control"
$CLI rate  "https://www.anthropic.com/engineering/redesigning-source-control" 5
$CLI read  "https://aws.amazon.com/blogs/machine-learning/build-reliable-ai-agents-with-amazon-bedrock-agentcore-evaluations"
$CLI rate  "https://aws.amazon.com/blogs/machine-learning/build-reliable-ai-agents-with-amazon-bedrock-agentcore-evaluations" 5
$CLI rate  "https://www.langchain.com/blog/langchain-langgraph-1dot0" 3

echo "== Agent 2: coaching session 1 (week 1)"
$CLI coach --answers data/fixtures/session1_answers.json --date 2026-11-01 --session-id week1 \
     --out samples --transcript samples/coaching_session_week1_transcript.md > samples/coaching_session_week1_console.txt
echo "== Agent 1: day 2 brief (no repeats; adapted to ratings + coaching gaps)"
$CLI brief --snapshot $SNAP --date 2026-11-02 --out samples > /dev/null
echo "== Agent 2: coaching session 2 (one week later)"
$CLI coach --answers data/fixtures/session2_answers.json --date 2026-11-08 --session-id week2 \
     --out samples --transcript samples/coaching_session_week2_transcript.md > samples/coaching_session_week2_console.txt
$CLI progress > samples/progress.txt
$CLI opportunities > samples/opportunities.txt
echo "done: $(ls samples | wc -l) files in samples/"
