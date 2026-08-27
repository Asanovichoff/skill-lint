---
name: clean-skill
description: Converts CSV exports into a normalized ledger format with consistent column names and ISO dates. Use when the user has raw CSV exports from a bank or accounting tool and wants them merged or cleaned.
license: MIT
---

# clean-skill

## Instructions

1. Read the CSV headers before parsing.
2. Normalize the date column to ISO 8601.
3. Write the result to `ledger.csv` beside the input.

## Examples

Merge three exports into one ledger.
