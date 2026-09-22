# Evaluation Report

Date: 2026-09-21 18:52 UTC
Model: `openai/gpt-oss-120b`
Cases: 35

## Metrics by Case Type

| Type | N | keyword_match | citation_correct | retrieval_hit | decline_rate |
|---|---|---|---|---|---|
| in_scope | 15 | 80% | 100% | 100% | N/A |
| cross_source | 5 | 80% | 100% | 0% | N/A |
| out_of_scope | 5 | 100% | 100% | 100% | 100% |
| follow_up | 5 | 100% | 100% | 100% | N/A |
| adversarial | 5 | 80% | 100% | 60% | 40% |

## Latency

- Median TTFT: 1820 ms
- p95 TTFT: 2432 ms
- Median total: 2019 ms

## Failing Cases

### c04 (in_scope)
**Q:** What is RuBisCO's role in carbon fixation?
**A:** RuBisCO is the enzyme that catalyzes the incorporation of CO₂ into organic molecules—i.e., it drives the carbon‑fixation step of photosynthesis【S1】....
**Retrieved locators:** []

### c06 (in_scope)
**Q:** What does REST stand for and who defined it?
**A:** REST stands for **Representational State Transfer**, and it was defined by **Roy Fielding** in his 2000 doctoral dissertation【S1】....
**Retrieved locators:** []

### c12 (in_scope)
**Q:** What is K-fold cross-validation?
**A:** K‑fold cross‑validation is a technique that divides the available data into K separate subsets (folds). The model is trained K times, each time using K – 1 folds for training and the remaining fold for testing, so that every data point is used for validation exactly once【S1】....
**Retrieved locators:** []

### c20 (cross_source)
**Q:** What are Python dictionaries and how are REST resources identified?
**A:** Python dictionaries are data structures that store **key‑value pairs** and are implemented internally as **hash tables**【S1】.  

In REST, **resources** are identified by **URIs** (Uniform Resource Identifiers); each resource’s representation can be returned in formats such as JSON or XML【S2】....
**Retrieved locators:** []
