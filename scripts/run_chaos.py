from __future__ import annotations

import argparse
import random
from pathlib import Path

from reliability_lab.cache import SharedRedisCache
from reliability_lab.chaos import load_queries, run_simulation
from reliability_lab.config import load_config


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="configs/default.yaml")
    parser.add_argument("--out", default="reports/metrics.json")
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args()
    random.seed(args.seed)
    config = load_config(args.config)
    if config.cache.enabled and config.cache.backend == "redis":
        redis_cache = SharedRedisCache(
            config.cache.redis_url,
            config.cache.ttl_seconds,
            config.cache.similarity_threshold,
        )
        redis_cache.flush()
        redis_cache.close()
    metrics = run_simulation(config, load_queries())
    metrics.write_json(args.out)
    csv_path = Path(args.out).with_suffix(".csv")
    metrics.write_csv(csv_path)
    print(f"wrote {args.out} and {csv_path}")


if __name__ == "__main__":
    main()
