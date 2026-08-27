# Day 25 Reliability Final Report

Họ và Tên: Quách Xuân Trường  
MSSV: 2A202601371

## 1. Architecture summary

~~~text
User -> ReliabilityGateway -> Cache -> Circuit breaker -> Provider chain -> Static fallback
~~~

The gateway returns cache hits before calling providers. Cache misses pass through a per-provider circuit breaker; provider errors and open circuits continue to the next provider before a static degraded response is returned.

## 2. Configuration

| Setting | Value | Rationale |
|---|---:|---|
| providers.primary.fail_rate | 0.25 | Injected failure rate for chaos testing. |
| providers.primary.base_latency_ms | 180 | Baseline provider latency before jitter. |
| providers.primary.cost_per_1k_tokens | 0.01 | Cost estimate for this provider. |
| providers.backup.fail_rate | 0.05 | Injected failure rate for chaos testing. |
| providers.backup.base_latency_ms | 260 | Baseline provider latency before jitter. |
| providers.backup.cost_per_1k_tokens | 0.006 | Cost estimate for this provider. |
| circuit_breaker.failure_threshold | 3 | Opens after repeated failures. |
| circuit_breaker.reset_timeout_seconds | 2.0 | Cooldown before a half-open probe. |
| circuit_breaker.success_threshold | 1 | Successful probes required to close. |
| cache.enabled | True | Enables cache-first routing. |
| cache.backend | redis | Selects memory or shared Redis state. |
| cache.ttl_seconds | 300 | Bounds response freshness. |
| cache.similarity_threshold | 0.92 | Avoids borderline semantic hits; dated queries also require matching 4-digit numbers. |
| cache.redis_url | redis://localhost:6379/0 | Shared-cache endpoint for Redis. |
| load_test.requests | 100 | Requests per named scenario. |
| scenarios.primary_timeout_100.provider_overrides | {'primary': 1.0} | Primary provider fails 100% — all traffic should fallback |
| scenarios.primary_flaky_50.provider_overrides | {'primary': 0.5} | Primary provider fails 50% — circuit should oscillate |
| scenarios.all_healthy.provider_overrides | {'primary': 0.0, 'backup': 0.0} | Baseline — both providers healthy |

## 3. SLO definitions

| SLI | SLO target | Actual value | Met? |
|---|---|---:|---|
| Availability | >= 99% | 99.00% | Yes |
| Latency P95 | < 2500 ms | 312.27 ms | Yes |
| Fallback success rate | >= 95% | 94.55% | No |
| Cache hit rate | >= 10% | 70.00% | Yes |
| Recovery time | < 5000 ms | 2347.4459648132324 | Yes |

## 4. Metrics

| Metric | Value |
|---|---:|
| total_requests | 300 |
| availability | 0.99 |
| error_rate | 0.01 |
| latency_p50_ms | 269.16 |
| latency_p95_ms | 312.27 |
| latency_p99_ms | 318.04 |
| fallback_success_rate | 0.9455 |
| cache_hit_rate | 0.7 |
| circuit_open_count | 8 |
| recovery_time_ms | 2347.4459648132324 |
| estimated_cost | 0.034048 |
| estimated_cost_saved | 0.21 |

## 5. Cache comparison

| Metric | Without cache | With cache | Delta (with - without) |
|---|---:|---:|---:|
| latency_p50_ms | 270.2100 | 269.1600 | -1.0500 |
| latency_p95_ms | 316.1200 | 312.2700 | -3.8500 |
| estimated_cost | 0.1250 | 0.0340 | -0.0909 |
| cache_hit_rate | 0.0000 | 0.7000 | +0.7000 |
| circuit_open_count | 24.0000 | 8.0000 | -16.0000 |

## 6. Redis shared cache

Redis stores cache entries by deterministic query hash with TTL, allowing independent gateway instances to share cached responses. The integration suite verifies exact retrieval, expiry, cross-instance state, privacy bypass, and false-hit handling.

### Redis CLI output

~~~text
# Command: docker compose exec redis redis-cli KEYS "rl:cache:*"
rl:cache:dacb2b833659
rl:cache:0bc3b1acf73d
rl:cache:844ef0143a5c
rl:cache:d354658dc020
rl:cache:9e413fd814eb
rl:cache:734852f3cf4a
rl:cache:da61fb49b4f6
rl:cache:fff10da1c72c
rl:cache:98332d0d1c9c
rl:cache:095946136fea
rl:cache:b2a52f7dc795
rl:cache:3dab98c0e49e
~~~

### Redis-backed chaos metrics

| Metric | Value |
|---|---:|
| availability | 0.99 |
| latency_p50_ms | 269.16 |
| latency_p95_ms | 312.27 |
| cache_hit_rate | 0.7 |

## 7. Chaos scenarios

| Scenario | Expected behavior | Observed status | Pass/Fail |
|---|---|---|---|
| primary_timeout_100 | Primary provider fails 100% — all traffic should fallback | pass | pass |
| primary_flaky_50 | Primary provider fails 50% — circuit should oscillate | pass | pass |
| all_healthy | Baseline — both providers healthy | pass | pass |

## 8. Failure analysis

Availability and fallback-success SLOs can miss their targets during injected provider failures. The current half-open state does not restrict concurrent probes, and circuit-breaker state is local to each process. Production should share circuit state, limit half-open probes, and define scenario-specific SLO gates.

## 9. Next steps

1. Share circuit-breaker state across replicas.
2. Add per-provider half-open probe concurrency limits.
3. Track response-quality and cache false-hit rates as SLOs.
