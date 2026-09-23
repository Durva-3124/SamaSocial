# Planner Evaluation Report

Date: 2026-09-22 17:02 UTC
Model: `openai/gpt-oss-120b`

## Results

| Scenario | schema_valid | diff_violations | modules | refine_isolated | edit_persistence | ttf_ms | total_ms |
|---|---|---|---|---|---|---|---|
| School Python | ✓ | 0 | 6 | ✓ | ✓ | 9264 | 9264 |
| College Data Structures | ✗ | 0 | 0 | ✗ | ✗ | 0 | 0 |
| Adult Digital Marketing | ✓ | 0 | 4 | ✓ | ✗ | 5766 | 5766 |
| ML Intro for Engineers | ✗ | 0 | 0 | ✗ | ✗ | 0 | 0 |
| Spoken English | ✓ | 0 | 5 | ✓ | ✓ | 6613 | 6613 |

## Summary

- schema_valid: 60% (3/5)
- difficulty violations total: 0
- refine_isolated: 3/5
- edit_persistence: 2/5

### College Data Structures issues
- ERROR: generate_plan failed: LLM rate limit hit. Retry after 28s.

### ML Intro for Engineers issues
- ERROR: generate_plan failed: LLM rate limit hit. Retry after 25s.