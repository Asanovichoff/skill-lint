---
name: portability-break
description: Deploys the service to staging and tails the logs. Use when the user asks to deploy or ship to staging.
argument-hint: "[environment]"
disable-model-invocation: true
model: claude-sonnet-5
allowed-tools: Bash(git *)
---

# portability-break

## Instructions

Run the deploy script, then tail logs for 60 seconds.
