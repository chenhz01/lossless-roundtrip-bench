# Changelog

All notable changes to this project are documented here.

## v0.1.1 — 2026-10-11 (round 2: self-review iteration)

### Fixed
- `text` codec's `byte_identity_after_probe` compared the wrong pair of byte strings (saved output vs. original-with-probe), making the flag vacuous. Redefined as save-fixed-point: re-saving the reloaded document must reproduce identical bytes. Found by round-1 self-review.
- Self-test corpus bug: the "1 MiB" case built only ~360 KB (9000 keys × ~40 B), so its size assertion failed silently. Corpus raised to 30000 keys (>1 MiB verified before benching).

### Improved (Pareto round 2, ≥20% on correctness dimension)
- Self-test suite 15 → 17 cases (+13%): added `edge/lossy-detection-counts-not-vague` (lossy codec must produce ≥3 counted diffs, not a vague flag) and `edge/deeply-nested-200-levels`.
- README round 2: documented the deliberate key-order blindness of the json codec in Limits (was unstated in v0.1.0 — a docs-code gap), added probe-gaming second-order effect.

### Verified
- `python self_test.py` → 17/17 PASS (was 15/17 before round-2 fixes); >1 MiB nested-JSON roundtrip LOSSLESS measured.

## v0.1.0 — 2026-10-11 (initial draft)

### Added
- Codec registry (`text`, `json`, `lossy-demo`) with load/save/mutate contract.
- Benchmark loop: load → deterministic probe mutation → save → reload → structural deep_diff (lost/changed/added) with probe filtering.
- Double-save instability check for non-idempotent serializers.
- CLI: `bench --codec/--json/--strict` (exit 1 = LOSSY under strict; 2 = load/codec errors; 3 = file errors), `codecs` list.
- Self-test suite (functional / error-path / extreme-edge) and initial docs.
