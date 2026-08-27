from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from reliability_lab.config import LabConfig, load_config


def load_metrics(path: str) -> dict[str, Any] | None:
    metrics_path = Path(path)
    if not metrics_path.exists():
        return None
    return json.loads(metrics_path.read_text())


def metric_value(value: object) -> str:
    return "not observed" if value is None else str(value)


def config_rows(config: LabConfig) -> list[str]:
    rows = ["| Setting | Value | Rationale |", "|---|---:|---|"]
    for provider in config.providers:
        rows.extend(
            [
                f"| providers.{provider.name}.fail_rate | {provider.fail_rate} | Injected failure rate for chaos testing. |",
                f"| providers.{provider.name}.base_latency_ms | {provider.base_latency_ms} | Baseline provider latency before jitter. |",
                f"| providers.{provider.name}.cost_per_1k_tokens | {provider.cost_per_1k_tokens} | Cost estimate for this provider. |",
            ]
        )
    rows.extend(
        [
            f"| circuit_breaker.failure_threshold | {config.circuit_breaker.failure_threshold} | Opens after repeated failures. |",
            f"| circuit_breaker.reset_timeout_seconds | {config.circuit_breaker.reset_timeout_seconds} | Cooldown before a half-open probe. |",
            f"| circuit_breaker.success_threshold | {config.circuit_breaker.success_threshold} | Successful probes required to close. |",
            f"| cache.enabled | {config.cache.enabled} | Enables cache-first routing. |",
            f"| cache.backend | {config.cache.backend} | Selects memory or shared Redis state. |",
            f"| cache.ttl_seconds | {config.cache.ttl_seconds} | Bounds response freshness. |",
            f"| cache.similarity_threshold | {config.cache.similarity_threshold} | Avoids borderline semantic hits; dated queries also require matching 4-digit numbers. |",
            f"| cache.redis_url | {config.cache.redis_url} | Shared-cache endpoint for Redis. |",
            f"| load_test.requests | {config.load_test.requests} | Requests per named scenario. |",
        ]
    )
    for scenario in config.scenarios:
        overrides = scenario.provider_overrides or {"none": "default rates"}
        rows.append(
            f"| scenarios.{scenario.name}.provider_overrides | {overrides} | {scenario.description} |"
        )
    return rows


def comparison_rows(with_cache: dict[str, Any], without_cache: dict[str, Any] | None) -> list[str]:
    if without_cache is None:
        return ["No no-cache comparison metrics file was found."]

    rows = [
        "| Metric | Without cache | With cache | Delta (with - without) |",
        "|---|---:|---:|---:|",
    ]
    keys = ("latency_p50_ms", "latency_p95_ms", "estimated_cost", "cache_hit_rate", "circuit_open_count")
    for key in keys:
        before = float(without_cache[key])
        after = float(with_cache[key])
        rows.append(f"| {key} | {before:.4f} | {after:.4f} | {after - before:+.4f} |")
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--metrics", default="reports/metrics.json")
    parser.add_argument("--out", default="reports/final_report.md")
    parser.add_argument("--config", default="configs/default.yaml")
    parser.add_argument("--comparison", default="reports/metrics_no_cache.json")
    parser.add_argument("--redis-metrics", default="reports/metrics.json")
    parser.add_argument("--redis-evidence", default="reports/redis_keys.txt")
    args = parser.parse_args()

    metrics = load_metrics(args.metrics)
    if metrics is None:
        raise FileNotFoundError(f"Metrics file not found: {args.metrics}")
    comparison = load_metrics(args.comparison)
    redis_metrics = load_metrics(args.redis_metrics)
    config = load_config(args.config)
    scenarios = metrics.get("scenarios", {})
    evidence_path = Path(args.redis_evidence)
    redis_evidence = evidence_path.read_text().strip() if evidence_path.exists() else "No Redis CLI output captured."

    lines = [
        "# Day 25 Reliability Final Report",
        "",
        "Họ và Tên: Quách Xuân Trường  ",
        "MSSV: 2A202601371",
        "",
        "## 1. Architecture summary",
        "",
        "~~~text",
        "User -> ReliabilityGateway -> Cache -> Circuit breaker -> Provider chain -> Static fallback",
        "~~~",
        "",
        "The gateway returns cache hits before calling providers. Cache misses pass through a per-provider circuit breaker; provider errors and open circuits continue to the next provider before a static degraded response is returned.",
        "",
        "## 2. Configuration",
        "",
        *config_rows(config),
        "",
        "## 3. SLO definitions",
        "",
        "| SLI | SLO target | Actual value | Met? |",
        "|---|---|---:|---|",
        f"| Availability | >= 99% | {float(metrics['availability']) * 100:.2f}% | {'Yes' if float(metrics['availability']) >= 0.99 else 'No'} |",
        f"| Latency P95 | < 2500 ms | {metric_value(metrics.get('latency_p95_ms'))} ms | {'Yes' if float(metrics['latency_p95_ms']) < 2500 else 'No'} |",
        f"| Fallback success rate | >= 95% | {float(metrics['fallback_success_rate']) * 100:.2f}% | {'Yes' if float(metrics['fallback_success_rate']) >= 0.95 else 'No'} |",
        f"| Cache hit rate | >= 10% | {float(metrics['cache_hit_rate']) * 100:.2f}% | {'Yes' if float(metrics['cache_hit_rate']) >= 0.10 else 'No'} |",
        f"| Recovery time | < 5000 ms | {metric_value(metrics.get('recovery_time_ms'))} | {'Yes' if isinstance(metrics.get('recovery_time_ms'), (int, float)) and float(metrics['recovery_time_ms']) < 5000 else 'Not measured'} |",
        "",
        "## 4. Metrics",
        "",
        "| Metric | Value |",
        "|---|---:|",
    ]
    for key, value in metrics.items():
        if key != "scenarios":
            lines.append(f"| {key} | {value} |")

    lines += [
        "",
        "## 5. Cache comparison",
        "",
        *comparison_rows(metrics, comparison),
        "",
        "## 6. Redis shared cache",
        "",
        "Redis stores cache entries by deterministic query hash with TTL, allowing independent gateway instances to share cached responses. The integration suite verifies exact retrieval, expiry, cross-instance state, privacy bypass, and false-hit handling.",
        "",
        "### Redis CLI output",
        "",
        "~~~text",
        redis_evidence,
        "~~~",
        "",
        "### Redis-backed chaos metrics",
        "",
    ]
    if redis_metrics is None:
        lines.append("Redis chaos metrics were not generated.")
    else:
        lines.extend(
            [
                "| Metric | Value |",
                "|---|---:|",
                f"| availability | {redis_metrics['availability']} |",
                f"| latency_p50_ms | {redis_metrics['latency_p50_ms']} |",
                f"| latency_p95_ms | {redis_metrics['latency_p95_ms']} |",
                f"| cache_hit_rate | {redis_metrics['cache_hit_rate']} |",
            ]
        )

    lines += [
        "",
        "## 7. Chaos scenarios",
        "",
        "| Scenario | Expected behavior | Observed status | Pass/Fail |",
        "|---|---|---|---|",
    ]
    for scenario in config.scenarios:
        status = str(scenarios.get(scenario.name, "not run")) if isinstance(scenarios, dict) else "not run"
        lines.append(f"| {scenario.name} | {scenario.description} | {status} | {status} |")

    lines += [
        "",
        "## 8. Failure analysis",
        "",
        "Availability and fallback-success SLOs can miss their targets during injected provider failures. The current half-open state does not restrict concurrent probes, and circuit-breaker state is local to each process. Production should share circuit state, limit half-open probes, and define scenario-specific SLO gates.",
        "",
        "## 9. Next steps",
        "",
        "1. Share circuit-breaker state across replicas.",
        "2. Add per-provider half-open probe concurrency limits.",
        "3. Track response-quality and cache false-hit rates as SLOs.",
    ]
    output = Path(args.out)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines))
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
