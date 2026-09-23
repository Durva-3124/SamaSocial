# Evaluation Report

Date: 2026-09-22 06:18 UTC
Model: `openai/gpt-oss-120b`
Cases: 35

## Metrics by Case Type

| Type | N | keyword_match | citation_correct | retrieval_hit | decline_rate |
|---|---|---|---|---|---|
| in_scope | 15 | 100% | 80% | 100% | N/A |
| cross_source | 5 | 100% | 80% | 100% | N/A |
| out_of_scope | 5 | 100% | N/A | 100% | 80% |
| follow_up | 5 | 80% | 60% | 100% | N/A |
| false_premise | 3 | 33% | 33% | 33% | 0% |
| injection | 2 | 100% | N/A | 100% | 100% |

## Latency

- Median TTFT: 1868 ms
- p95 TTFT: 10285 ms
- Median total: 1904 ms

## Failing Cases

### c27 (follow_up)
**Q:** What HTTP methods does REST use?
**A:** ...
**Retrieved locators:** []
