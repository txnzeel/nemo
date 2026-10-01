# Learning guide — Performance and security claims

## What you built and why
A reproducible local latency benchmark, bounded web response reader, redirect rejection
and a narrowly scoped dependency security update. A marketing tool must report failure
clearly instead of exhausting memory or displaying partial evidence as a successful result.

## Example, formula and requirements
Ten sorted durations give nearest-rank p95 at ceil(0.95 × 10) = 10: the maximum.
The median is the middle value (or mean of the two middle values). You need a named
dataset, runtime, warm-up rule, sample count and timing scope to interpret either.
A sub-millisecond explanation benchmark does not include model/network latency: it
measures deterministic rendering only.

## Implementation and alternatives
The benchmark calls existing canonical services. It records wall-clock durations with
a monotonic timer and includes response size and case revision. The proxy counts streamed
bytes rather than trusting Content-Length. Redirects fail before following a new target.
A lockfile update patches urllib3; separate Airflow constraints get an explicit overlay.
Caching or a distributed cache could reduce latency but requires correct source/method
invalidation; no cache was added without that requirement.

## Business and statistical limits
Reliability protects decision evidence; it does not improve the causal strength of that
evidence. Ten local samples cannot establish a production p95 or availability guarantee.
A clean known-vulnerability scan cannot prove the absence of security flaws.

## Failure modes
Unbounded/incorrectly encoded responses, misleading percentile claims, stale caches,
dependency drift, and incomplete audit scope. State exact limits and preserve failure
signals. Never treat an unchanged old publication as proof of a successful new run.

## Five interview questions and strong answers
1. Why use a monotonic timer? Wall-clock adjustments should not alter elapsed durations.
2. What does this p95 prove? Only a descriptive order statistic for this small local sample.
3. Why check streamed size? A server can omit or misstate its declared length.
4. Why isolate Airflow dependencies? Its operational stack should not rewrite the frozen
   analytical runtime; each environment still needs security maintenance.
5. Is the product production-secure now? No. Specific controls and regression tests pass;
   deployment identity, isolation, operational controls and external review remain gates.

## Interview explanation
“I measured before optimizing and published the measurement scope. I fixed a known
dependency issue and tested transport bounds with oversized streams and a real redirect.
I distinguish those verified controls from broad security or scale claims.”
