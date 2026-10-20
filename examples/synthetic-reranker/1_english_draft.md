# Hard Negatives Hurt Small Rerankers Until You Remove False Negatives

## Abstract
Rerankers in RAG services must be small to meet latency budgets. A common belief holds that more hard negatives make better rerankers, but this was only shown for 7B+ models. We fine-tune the same 0.5B Korean reranker with 0%, 25%, 50% and 75% hard negatives (3 seeds each) and evaluate on two public Korean retrieval benchmarks (KoMS, KoNQ) and a 1,200-query held-out set from service logs. MRR@10 rises up to 25% (KoMS 0.612 to 0.648) and falls beyond 50% (0.603 at 75%). Human review of 300 hard negatives finds 31% are actually correct. Removing them restores 75% to 0.651. Latency is unchanged at 11 ms. For small rerankers, remove false negatives first; 25% is a practical default.

## 1 Introduction
A RAG service retrieves candidates and then reranks them. The reranker runs on every query, so it must be small. Hard negatives are negatives that look relevant. Prior work reports that more of them help large rerankers [3, 4]. Does this hold for small ones? And if not, why? We answer both questions with a controlled study. Our findings:
- More hard negatives help only up to 25%; beyond that, accuracy drops below the no-hard-negative baseline (Sec. 4.1).
- The drop comes from false negatives: 31% of reviewed hard negatives are correct answers, and removing them recovers accuracy (Sec. 4.2).
- Latency does not depend on the ratio.
The practical rule is simple: clean first, then add hard negatives.

## 4 Results
### 4.1 Effect of the hard-negative ratio
Table 1 shows the results. Going from 0% to 25% raises MRR@10 on both benchmarks (KoMS +0.036, KoNQ +0.027), far above the seed standard deviation (at most 0.004). Beyond 50% the trend reverses. At 75%, KoMS falls to 0.603, below the 0% model. The held-out set shows the same shape; 25% is best (0.702). Latency stays at 11 ms per query in all conditions, as expected, since model size does not change.

### 4.2 False negatives
Why does 75% hurt? We reviewed 300 mined hard negatives by hand. 31% were in fact correct answers. Training then pushes the model away from relevant passages. Removing these false negatives and retraining at 75% gives 0.651 on KoMS, on par with 25%. So the ratio itself is not the problem; label noise is. This matches the concern raised in [5].

## 5 Conclusion
More hard negatives are not always better for small rerankers. Past 25%, false negatives dominate and accuracy falls. Cleaning them restores performance at no latency cost. Limitations: one model, one language, one miner, and only 300 reviewed negatives.
