"""
Correlate memory_sampler.py output with per-test timestamps from JUnit XML
(backend) or Playwright JSON reporter (frontend). Produces two rankings:

  1. Top tests by RSS growth during the test window (likely allocators).
  2. Top tests by peak RSS reached (stress indicators, may be transient).

Skip tests that are too short (<min_duration) since single-point samples
are noisy. We also emit a raw per-test table in CSV so you can sanity-
check individual runs.

Usage:
  python scripts/memory_sampler_correlate.py \
    --trace /tmp/bifrost/memory-trace.csv \
    --junit /tmp/bifrost/test-results.xml \
    [--min-duration 0.5] [--top 20]
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Sample:
    ts: float
    rss_kb: int
    inactive_anon: int
    anon_mapping_bytes: int


@dataclass
class Test:
    name: str
    classname: str
    start: float  # unix seconds
    end: float
    status: str  # passed/failed/skipped

    @property
    def duration(self) -> float:
        return self.end - self.start


def _load_samples(path: Path) -> list[Sample]:
    samples: list[Sample] = []
    with path.open() as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                ts = float(row["ts_unix"])
                rss = int(row["rss_kb"])
                inactive = int(row["inactive_anon_bytes"])
                amap = int(row["anon_mapping_bytes"])
            except (ValueError, KeyError):
                continue
            if rss <= 0:
                continue
            samples.append(Sample(ts=ts, rss_kb=rss, inactive_anon=inactive,
                                   anon_mapping_bytes=amap))
    samples.sort(key=lambda s: s.ts)
    return samples


def _load_junit(path: Path) -> list[Test]:
    """Parse JUnit XML and return a list of tests with start/end unix times.

    JUnit XML's `timestamp` attribute on <testsuite> is an ISO 8601 datetime,
    and each <testcase> has a `time` attribute (duration in seconds). We
    accumulate the duration across testcases to derive per-test start times.
    """
    tree = ET.parse(path)
    root = tree.getroot()
    # Sometimes root is <testsuites>, sometimes <testsuite>. Normalize.
    if root.tag == "testsuites":
        suites = root.findall("testsuite")
    else:
        suites = [root]

    tests: list[Test] = []
    for suite in suites:
        suite_ts = suite.get("timestamp")
        if not suite_ts:
            continue
        try:
            # Handle both `2026-04-21T18:00:00` and `...+00:00`
            t0 = dt.datetime.fromisoformat(suite_ts)
        except ValueError:
            continue
        if t0.tzinfo is None:
            t0 = t0.replace(tzinfo=dt.timezone.utc)
        cursor = t0.timestamp()

        for case in suite.findall("testcase"):
            name = case.get("name") or "<unnamed>"
            classname = case.get("classname") or ""
            try:
                dur = float(case.get("time") or 0)
            except ValueError:
                dur = 0
            status = "passed"
            if case.find("failure") is not None:
                status = "failed"
            elif case.find("error") is not None:
                status = "error"
            elif case.find("skipped") is not None:
                status = "skipped"
            tests.append(Test(
                name=name, classname=classname,
                start=cursor, end=cursor + dur, status=status,
            ))
            cursor += dur
    return tests


def _samples_in_window(samples: list[Sample], start: float, end: float) -> list[Sample]:
    # Binary-search-ish: samples are sorted. Small-range linear scan is fine
    # too given tests are few-minutes at most.
    lo = None
    hi = None
    for i, s in enumerate(samples):
        if lo is None and s.ts >= start:
            lo = i
        if s.ts <= end:
            hi = i
    if lo is None or hi is None or lo > hi:
        return []
    return samples[lo:hi + 1]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--trace", required=True, type=Path)
    ap.add_argument("--junit", required=True, type=Path)
    ap.add_argument("--min-duration", type=float, default=0.5,
                    help="Skip tests shorter than this (default 0.5s)")
    ap.add_argument("--top", type=int, default=20,
                    help="Report top N tests per ranking (default 20)")
    ap.add_argument("--out-csv", type=Path,
                    help="Optional: write per-test enriched CSV here")
    args = ap.parse_args()

    samples = _load_samples(args.trace)
    tests = _load_junit(args.junit)
    if not samples:
        sys.exit(f"No samples parsed from {args.trace}")
    if not tests:
        sys.exit(f"No tests parsed from {args.junit}")

    print(f"Loaded {len(samples)} samples "
          f"({dt.datetime.fromtimestamp(samples[0].ts).isoformat(timespec='seconds')} → "
          f"{dt.datetime.fromtimestamp(samples[-1].ts).isoformat(timespec='seconds')})",
          file=sys.stderr)
    print(f"Loaded {len(tests)} tests", file=sys.stderr)

    rows = []
    for t in tests:
        if t.duration < args.min_duration:
            continue
        window = _samples_in_window(samples, t.start, t.end)
        if len(window) < 2:
            continue
        rss_start = window[0].rss_kb
        rss_end = window[-1].rss_kb
        rss_peak = max(s.rss_kb for s in window)
        rows.append({
            "test": f"{t.classname}::{t.name}" if t.classname else t.name,
            "status": t.status,
            "duration_s": round(t.duration, 2),
            "rss_start_mb": round(rss_start / 1024, 1),
            "rss_end_mb": round(rss_end / 1024, 1),
            "rss_delta_mb": round((rss_end - rss_start) / 1024, 1),
            "rss_peak_mb": round(rss_peak / 1024, 1),
            "peak_above_start_mb": round((rss_peak - rss_start) / 1024, 1),
            "samples": len(window),
        })

    if not rows:
        sys.exit("No tests overlap with memory samples — did the sampler "
                 "run during the test?")

    if args.out_csv:
        args.out_csv.parent.mkdir(parents=True, exist_ok=True)
        with args.out_csv.open("w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)
        print(f"Wrote per-test CSV: {args.out_csv}", file=sys.stderr)

    def _print_ranked(title: str, key: str) -> None:
        print()
        print(f"=== {title} ===")
        print(f"{'Δ MB':>8} {'peak MB':>9} {'dur s':>7} {'status':>7}  test")
        for r in sorted(rows, key=lambda r: -r[key])[:args.top]:
            print(f"{r['rss_delta_mb']:>8} {r['rss_peak_mb']:>9} "
                  f"{r['duration_s']:>7} {r['status']:>7}  {r['test'][:110]}")

    _print_ranked("Top tests by RSS growth (retained after test)", "rss_delta_mb")
    _print_ranked("Top tests by peak RSS during test", "rss_peak_mb")

    print()
    print("=== Session totals ===")
    print(f"First sample RSS: {samples[0].rss_kb / 1024:.1f} MB")
    print(f"Last sample RSS:  {samples[-1].rss_kb / 1024:.1f} MB")
    print(f"Peak RSS:         {max(s.rss_kb for s in samples) / 1024:.1f} MB")
    print(f"Net growth:       {(samples[-1].rss_kb - samples[0].rss_kb) / 1024:+.1f} MB")

    return 0


if __name__ == "__main__":
    sys.exit(main())
