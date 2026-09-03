# T-EVAL-0003 Metrics Summary

- Retrieval status: `passed`
- Retrieval sample count: `1000`
- Retrieval failures: `0`
- Response generation status: `blocked`
- Response count: `402`
- Response failures: `598`
- RAGAS status: `blocked`
- RAGAS sample count: `0`

## Retrieval Overall

```json
{
  "dense": {
    "hit_count": 299,
    "mean_rank": 5.066889632107023,
    "median_rank": 3,
    "miss_count": 701,
    "mrr": 0.1501678137608865,
    "rank_observation_count": 299,
    "recall_at": {
      "1": 0.103,
      "10": 0.242,
      "20": 0.299,
      "30": 0.299,
      "5": 0.204
    },
    "sample_count": 1000
  },
  "rrf": {
    "hit_count": 708,
    "mean_rank": 7.124293785310734,
    "median_rank": 4.0,
    "miss_count": 292,
    "mrr": 0.28065312770767026,
    "rank_observation_count": 708,
    "recall_at": {
      "1": 0.163,
      "10": 0.557,
      "20": 0.649,
      "30": 0.689,
      "5": 0.427
    },
    "sample_count": 1000
  },
  "sparse": {
    "hit_count": 668,
    "mean_rank": 3.8622754491017965,
    "median_rank": 2.0,
    "miss_count": 332,
    "mrr": 0.39378598294550304,
    "rank_observation_count": 668,
    "recall_at": {
      "1": 0.293,
      "10": 0.602,
      "20": 0.668,
      "30": 0.668,
      "5": 0.518
    },
    "sample_count": 1000
  }
}
```

## RAGAS

```json
null
```

Automated metrics are baseline evidence only and do not establish comprehensive system accuracy.
