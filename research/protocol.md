# Pilot Protocol: Cross-Family Trace Generalization (v5)

Status: draft v5 — incorporates four rounds of adversarial review (v1 → v2: feature leakage, train/test independence, operation-type leakage, value semantics, open-set, baseline reproduction; v2 → v3: pseudoreplication, near/far-OOD, task-specific interfaces, nested-operation attribution, oracle-size disclosure, original-vs-adapted baseline; v3 → v4: hierarchy/terminology contradiction between §4.1 and §4.3, hierarchical risk weighting, B1 length-control inconsistency, taxonomy-audit procedure, array-anonymization leak via first-seen order, semantic-root ambiguity, Task UR probe gaps, OOD-rationale and rejection-method specification, bootstrap caution at small N, paired-design requirement for the interaction term, pipeline-metadata denylist, primary/secondary endpoint split for falsifiability; v4 → v5: residual hierarchical-split wording in §4.2/§4.3, internal contradiction between the §6.1 near/far-OOD class lists and the §6.1.1 rationale, an under-specified taxonomy-audit pass threshold and a selection-bias risk in excluding observationally-equivalent implementations, an undefined `Δ_F`/non-inferiority criterion in §8, a micro-pilot that cannot exercise its own split/risk code paths, undefined per-baseline input channels, an unoperationalized length-matching procedure, an unguarded composition mismatch in the risk-cell comparison, and an underspecified "plain prefix array" candidate). Not cleared for full corpus collection. Cleared only for a **micro-pilot** (§10) once the §11 checklist is signed off — and the micro-pilot itself validates pipeline mechanics only, not the cross-family hypothesis (see §2.1, §10).

Locking order (each section depends on the ones before it):
1. Feature contract & event semantics
2. Task/API manifest & label hierarchy (incl. four-tier hierarchy, §2.1)
3. Probe grid
4. Statistical unit & split manifest
5. Normalization registry
6. Open-set manifest
7. Baseline reproduction specification
8. Falsifiability criterion / pilot questions
9. Micro-pilot scope

Scope: oracle-assisted setting (array identity + operation boundaries given by instrumentation).

---

## 1. Feature Contract & Event Semantics

Grounded in `prototype/cpp/trace.hpp` JSONL event types as currently implemented.

### 1.1 Events currently emitted

| Event | Fields | Source | Notes |
|---|---|---|---|
| `array` | `array`, `size`, `structure`, `index_base` | Oracle (registration) | `structure`/`index_base` are declared, not inferred |
| `op_begin` | `op_id`, `parent_op_id`, `kind`, `array`, `n`, `file`, `line` | Oracle (`kind` from function-name matching) | `parent_op_id` exposes call nesting |
| `op_end` | `op_id` | Oracle | |
| `op_param` | `op_id`, `key`, `value` | Oracle (explicit `param()` calls) | |
| `access` | `op_id`, `mode`, `array`, `index`, `value`, `file`, `line` | Observed | Core signal |
| `watch` | `name`, `value`, `file`, `line` | Observed | Not used in pilot v1 |
| `error` | `array`, `message` | Observed | |
| `line`/`condition` | `line`, `kind`, `value` | Observed | Not used in pilot v1 |

### 1.2 Feature contract (binding for every model variant)

| Field | Core model | Oracle/probe-context ablation | Other use |
|---|---:|---:|---:|
| normalized index | Yes | — | — |
| read/write mode | Yes | — | — |
| `value` | No in pilot v1 | Yes, once instrumentation gives before/after (§1.3) | — |
| `array.structure` | **No, never** | **No, never** | Ground-truth label only |
| raw `array` name | No | No | Filtered to target array, then dropped entirely (§1.4) |
| `op_id` | No | No | Segmentation only |
| `parent_op_id` | No | Yes (`+oracle_context`) | Nesting audit (§1.5) |
| `kind` | No | Yes (`+oracle_context`) | Separate oracle-context experiment |
| `op_param` | No | Yes (`+probe_context`) | Separate probe-context experiment, probe-memorization risk |
| `n_logical` | Not direct | Used for normalization, disclosed (§5.1) | Oracle-size vs no-size setting |
| `n_allocated` | No | Yes (`+allocation_ratio`) | Separate ablation |
| `file`, `line` | **No, never** | **No, never** | Debug/audit logs only |

Any result using an oracle/probe-context ablation column is reported as a separate, explicitly labeled experiment — never silently merged into the default `B0`–`B4`/relational-representation numbers.

### 1.2.1 Pipeline metadata denylist

Beyond the fields above, the following are pipeline/run metadata, not access-pattern signal. They are kept in the manifest/audit log for split construction and debugging, but **never** enter the feature matrix: `probe_id`, `run_id`, random seed, source-implementation ID, representation-family ID, source file path, compiler flags, build hash, timestamp, and event sequence number (where it resets in a way specific to a given source template, it can otherwise leak template identity). See §1.6 for the toolchain lock that keeps build configuration from becoming an extra uncontrolled confound.

### 1.2.2 Per-model input channels (resolves §7 ambiguity)

§1.2's allowlist fixes what may *ever* enter a feature matrix; it does not by itself say which of those allowed fields each named baseline/model variant actually uses. Without this, `B0-original` could silently inherit `B1`'s size normalization, collapsing the baseline ladder. Four index-derived channels are distinguished:

| Channel | Definition |
|---|---|
| `raw_index` | `i_t` exactly as emitted by `access.index`, no transform |
| `offset_index` | `i_t^(1) = i_t − b` (§5, offset only) |
| `size_normalized_index` | `i_t^(2) = i_t^(1) / n_logical` (§5, offset then size) |
| `mode` | `access.mode` (read/write), unchanged |

| Model | Permitted channels |
|---|---|
| `B0-original` | `raw_index`, `mode` only — matches the original paper's address-trace setting as closely as the index-based setting allows; no offset/size normalization, since the original used raw memory addresses |
| `B0-adapted` | `offset_index`, `mode` — offset is the documented adaptation (§7) from address-space to index-space; no size normalization |
| `B0-modern` | same channels as `B0-adapted`, different classifier only |
| `B1-oracle-size` | `size_normalized_index`, `mode` |
| `B1-no-size` | `offset_index`, `mode` (no size step, §5.1) |
| Relational representation (`φ`) | whatever channel(s) the experiment under §8/§9 declares in advance, drawn only from this table or an explicitly-named oracle/probe-context ablation (§1.2) |

Any reported result must state which row of this table it used. A result is not attributed to "the baseline" without naming the `B0-*` variant and confirming its channel matches this table.

### 1.3 Value semantics — unresolved, excluded from pilot v1

Pre/post-write semantics of `access.value` are undocumented, and reconstructing a delta by pairing consecutive accesses is unreliable (unknown pre/post convention, interleaved reads, repeated writes, multi-access operator overloads, unpaired writes). **Decision:** value-based features (RQ3) are excluded from pilot v1; only `index` + `mode` form the core observation. RQ3 becomes its own sub-study once `trace.hpp` logs `value_before`/`value_after` explicitly.

### 1.4 Array identity handling — drop, don't anonymize-by-order

First-seen-order anonymization (mapping distinct `array` values to `array_0, array_1, ...` in order of first appearance) was found to leak implementation identity itself: e.g., if implementation A always accesses `tree` before `lazy` while implementation B accesses `lazy` first, the `array_0`/`array_1` labels still encode each implementation's access order, not just array identity.

**Fix for the core task (Task UQ/UR, §2.2, both single-array):** since array identity is oracle-provided only to filter/segment events, the trace is filtered down to the one oracle-identified target array and the array field is then **dropped from the feature vector entirely** — no anonymized ID is carried forward, because there is exactly one array per sample in the core task.

**Multi-array structures** (lazy Segment Tree, dual-BIT Fenwick) are out of scope for the core task. If/when studied, they require a representation that is invariant to array-ID permutation, not an anonymization scheme that orders arrays by first access — that is a separate, explicitly scoped follow-on setting, not part of pilot v1.

### 1.5 Nested-operation access attribution — semantic root, not absolute outermost

Recursive implementations create nested `op_id`s sharing the same underlying accesses conceptually. "Outermost ancestor in the `parent_op_id` chain" is ambiguous — it could resolve to a benchmark/test-harness wrapper or batch driver enclosing many unrelated operations, which would silently merge an entire run into one sample.

> Each `access` event belongs to exactly one analysis unit — the **semantic root**: the nearest ancestor in its `parent_op_id` chain that the instrumenter/task manifest marks as one of the task's fixed operation-surface calls (§2.2: `build`, `point_update`, `prefix_query`, `range_query`), not the absolute outermost ancestor. Nested (child) `op_id`s below the semantic root are retained only for audit (e.g., confirming recursive vs. iterative call shape) and never spawn additional training samples by attributing the same access to more than one unit.

### 1.6 Toolchain lock

For the pilot, compiler, compiler version, optimization level, instrumentation flags, and platform are fixed identically across every source implementation — unless a future, separately-scoped experiment explicitly studies compiler/toolchain shift. This prevents a build-configuration difference from acting as an unintended extra confound alongside implementation/representation differences.

---

## 2. Task / API Manifest & Label Hierarchy

### 2.1 Four-tier hierarchy and label axes (resolves the v3 §4.1/§4.3 contradiction)

```
structure class
└── representation family   (indexing base, recursive/iterative, layout, ...)
    └── source implementation   (one concrete codebase / author)
        └── trace   (one probe run)
```

- **Structure class** (Fenwick / SegTree / decoy / unknown) — the prediction target.
- **Representation family** — a manually-tagged sub-group within a structure class sharing the same `representation_tags` (assigned by the taxonomy audit, §4.5.1), e.g. "Fenwick, 1-indexed, recursive."
- **Source implementation** — one concrete codebase realizing one representation family, ideally from an independent author/source.
- **Operation type** (build / point_update / prefix_query / range_query) — a probe-grid dimension, never a proxy for structure class.

v3 had an internal contradiction: §4.1 forbade any source implementation from appearing in both train and test, while §4.3 defined the "seen family" test cell as a held-out trace from "a family that had other traces in training" — those can only both be true if a representation family contains **multiple independent source implementations**:

```
Fenwick
├── 1-indexed canonical
│   ├── implementation A   (train)
│   └── implementation B   (test — "seen representation family")
└── 0-indexed
    ├── implementation C   (test — entire family held out, "unseen representation family")
    └── implementation D   (test — entire family held out, "unseen representation family")
```

So in §4.3, **"seen family"** means: the representation family appears in training via a sibling implementation, but the specific test implementation is independent and held out. **"Unseen family"** means: every implementation in that representation family is held out.

**Consequence:** populating the `(seen family, *)` cells requires ≥2 independent source implementations per representation family. With only one implementation per representation family — the case for the micro-pilot, §10 — there is no independent sibling to test against, so `(seen family, *)` cannot be populated correctly. The micro-pilot can therefore validate pipeline mechanics only; it cannot produce a usable `P_IID`, `P_F`, `P_Q`, or `P_FQ`, and no GO/PIVOT decision may be drawn from micro-pilot numbers.

### 2.2 Task-specific common interfaces (replaces a single universal API)

Forcing every candidate structure into one universal API is itself artificial (e.g., not all structures support range queries equally naturally). Instead, define **tasks**, each with its own fixed operation surface and its own candidate set:

**Task UQ** (update + prefix query):
```
build(n), point_update(i, delta), prefix_query(i)
```
Candidates: Fenwick variants, Segment Tree (configured for prefix query), and the **non-tree array-based prefix-sum family** (the decoy class, §6.1). "Plain prefix-sum array" (v4's label) is not a single implementation — at least these distinct variants exist, each with a different access trace and therefore each requiring its own `representation_tags`/family entry in the registry (§4.5.2), not a single shared decoy label:
- **PA-recompute:** `point_update` writes the raw array only (`O(1)`); `prefix_query` walks `[0, i]` summing raw values every call (`O(n)`).
- **PA-eager:** `point_update` rewrites the stored prefix array from `i` to `n` (`O(n)`); `prefix_query` is a single read (`O(1)`).
- **PA-rebuild:** `point_update` writes the raw array; the prefix array is fully rebuilt from scratch on the next `prefix_query` call if dirty, then cached until the next write.

These three are run as three separate decoy representation families through the same taxonomy audit (§4.5.1) as the tree-structured candidates, not folded into one "decoy" implementation.

**Task UR** (update + range query):
```
build(n), point_update(i, delta), range_query(l, r)
```
Candidates: Fenwick variants (range sum computed as the difference of two prefix queries — point-update + range-query does **not** require a dual-BIT array; dual-BIT is needed only for range-update + range/prefix-query, which is out of scope here), Segment Tree, sqrt decomposition, plain array.

Each task is run as its own experiment with its own family subset, its own probe grid (§3), and its own reported results. Operation semantics are identical across all families *within* a task, which is what prevents operation-type-as-label-leakage (the problem the v2 "common interface" section was trying to solve, now scoped correctly per task instead of forcing one global interface).

---

## 3. Probe Grid

Defined per task (§2.2); all families in a task share the same grid `Q_task`.

| Dimension | Levels |
|---|---|
| `n_logical` | Power-of-two: 8, 16, 64, 256, 1024. Non-power-of-two: 10, 50, 777, 1000 |
| Position | start, middle, end, random (fixed seed per probe id) |
| Operation type | restricted to the task's fixed surface (§2.2) |
| Sequence pattern | single op, interleaved, burst |
| Update:query ratio | 1:0, 1:1, 1:4, 0:1 |

### 3.0 Task UR additional dimensions

`Position = start/middle/end/random` (the table above) is sufficient for Task UQ's point operations but underspecifies range queries. For Task UR, the probe grid additionally varies:

| Dimension | Levels |
|---|---|
| Left endpoint | start, middle, end, random |
| Right endpoint / interval length | full-range, short-range (fixed small width), boundary-crossing (spans a structural boundary, e.g. a power-of-two block) |
| Range category | full-range, singleton (`l == r`), short-range, boundary-crossing |
| Query overlap pattern | non-overlapping sequential ranges, overlapping/nested ranges |

### 3.1 Logical vs. allocated size

`n_logical` is the oracle-provided problem size (used for size normalization, §5.1, and as the probe-grid parameter). `n_allocated` (true array length, varies by structure: Fenwick `n+1`, Segment Tree `2n`/`4n`) is excluded from default features — see `+allocation_ratio` ablation in §1.2.

### 3.2 Probe-shift regimes

Reported **separately**, not collapsed:

1. **Random-combination holdout** — stratified random split over full probe tuples (interpolation).
2. **Dimension holdout** — entire levels of one dimension withheld (e.g., all `n ∈ {777,1000}`, or all `range_query`, or all `random`-position).
3. **Compositional holdout** — individual levels seen, specific combinations withheld.

---

## 4. Statistical Unit & Split Manifest

### 4.1 Statistical unit (pseudoreplication fix)

A single implementation can generate thousands of traces from the probe grid; those traces are **not independent observations**. The statistical unit is the **implementation (family)**, not the individual trace. Concretely:

- No trace from the same source implementation appears in both train and test.
- Metrics are aggregated through the full §2.1 hierarchy with equal weight at each level — structure class, then representation family, then source implementation, then trace — so that a structure class or representation family with more implementations (or an implementation with more probe traces) does not dominate the reported risk. See §4.6 for the formula.

- Uncertainty is computed via grouped bootstrap, resampling at the **representation-family or source-implementation level** (per the §2.1 hierarchy), then traces within each resampled unit — not a flat per-trace confidence interval, which would understate uncertainty by treating thousands of correlated traces as independent. With only 2–5 implementations per class, this bootstrap interval will itself be unstable — see the caveat at the end of §4.4.

### 4.2 Three-way split — hierarchical, not flat family-level

**Train** (fits classifier + train-only normalization parameters) / **Validation** (model selection, open-set threshold calibration, never used for reported `R_ab`) / **Test** (only place `R_ab` is computed).

The split is **hierarchical**, following §2.1, not a single flat cut at the family level:

- For a representation family with ≥2 independent source implementations, the split is made at the **source-implementation** level *within* the family: one or more sibling implementations go to train, one or more independent siblings go to test. The family itself appears on both sides; no individual implementation does. This is what produces the `(seen family, *)` cells in §4.3.
- For a representation family with only 1 source implementation (no independent sibling), the entire family — its one implementation, all its traces — is assigned to exactly one of train/validation/test. This is what produces the `(unseen family, *)` cells in §4.3.

So "split at the family level" (v4 wording) was imprecise: it is only correct for the single-implementation case. The general rule is split-by-implementation, with the implementation-to-split assignment constrained by family membership (§4.1's invariant — no implementation in more than one split — always holds; family membership across splits is allowed and is in fact required for `(seen family, *)`).

### 4.3 2×2 evaluation cells

All cells computed on **test** data only. **"Seen representation family"** means the representation family is represented in training by one or more source implementations, while the test trace comes from a *different, independently held-out source implementation in the same family* (§4.2) — never a trace from the same implementation seen in training, and never literally "the same implementation, a different trace." **"Unseen representation family"** means every source implementation in that family is held out from training entirely.

| Cell | Family | Probe | Purpose |
|---|---|---|---|
| `(seen, seen)` | seen family, independent held-out sibling implementation | `Q_seen` test partition | `P_IID` |
| `(unseen, seen)` | unseen family, all implementations held out | `Q_seen` test partition | `P_F` |
| `(seen, unseen)` | seen family, independent held-out sibling implementation | `Q_held` (per regime, §3.2) | `P_Q` |
| `(unseen, unseen)` | unseen family, all implementations held out | `Q_held` (per regime, §3.2) | `P_FQ` |

`P_Q`/`P_FQ` reported per probe-shift regime.

### 4.4 Repetition for uncertainty

k grouped family-holdout splits, k ≥ 5 when family count allows. With only 2 families per structure (pilot-scale), this is explicitly an exploratory repeat count, not a population-level CI — see §4.5 scale caveat.

**Bootstrap caution at small N:** with 2–5 independent implementations per class, the bootstrap interval is itself unstable — thousands of generated (deterministic) traces from the same handful of implementations do not add independent statistical evidence, since repeated traces from the same implementation under the same probe are not new information about cross-implementation generalization. At pilot/micro-pilot scale: report descriptive results only (point estimates, qualitative spread across the available implementations), and do not report a population-level confidence interval or a significance test. At larger corpus scale, the inference target must be stated explicitly before bootstrapping: if the probe grid `Q` is treated as fixed, resample only at the family/implementation level; if the goal is to generalize over the probe-generating distribution itself, resample probe blocks as well, rather than treating individual traces as exchangeable units.

### 4.5 Family registry & scale caveat

#### 4.5.1 Taxonomy audit procedure (determines `taxonomy_status` below — not optional, run once before any split is finalized)

1. Assign `representation_tags` manually, from implementation knowledge, **before** running anything.
2. Run the fixed task probe grid `Q_task` (§3) on every candidate source implementation.
3. Check exact trace equivalence between implementations under `Q_task` (same index/mode sequence given the same probe).
4. Re-check equivalence after applying the normalization registry (§5) — distinguishes a normalization-coordinate difference from a genuine structural difference.
5. Check stability of any observed difference across `n_logical`, operation type, and probe pattern.
6. Clustering (e.g., on normalized index sequences) is used only to flag disagreement with the manual tags from step 1 — it never defines the labels used for training or evaluation.
7. `taxonomy_status = pass` only if the implementation is **both** representation-distinct (its step-1 tag differs from sibling implementations it is meant to be distinguished from) **and** observationally distinct under the stability bar fixed here — not merely "distinct under at least one probe/normalization condition" (v4's bar, too weak: a single corner-case mismatch would pass). The observational-distinctness bar requires the trace difference from step 3 to persist after normalization (step 4) **and** to be observed at ≥2 distinct `n_logical` values **and** on at least the task's primary operation (`point_update` for Task UQ) **and** across ≥2 of the probe-grid's sequence-pattern levels (§3) — not just a single probe tuple.

   **On failure — merge, don't silently drop:** an implementation that fails this bar is **not** excluded from the corpus. Excluding it would bias the family registry toward representation families that happen to be easy to tell apart, which is itself a finding worth hiding only by accident. Instead: implementations whose traces are observationally indistinguishable under `Q_task` are merged into a single **observational family** (a `family_id` distinct from, and cross-referenced against, their manually-assigned `representation_tags`), the merge is recorded in the family registry (§4.5.2, new `observational_family_id` field) and reported as a limitation of the trace-level operational definition for that pair — but the implementations remain in the corpus and are still eligible for the `(unseen family, *)` cells under their observational family, just not for representation-tag-level distinctions the protocol cannot actually measure.

#### 4.5.2 Family registry table

| Field | Description |
|---|---|
| `family_id` | stable identifier (representation family, §2.1, from manually-assigned `representation_tags`) |
| `observational_family_id` | identifier after the §4.5.1 step-7 merge; equals `family_id` unless two or more manually-tagged families were merged for being observationally indistinguishable under `Q_task` |
| `structure` | ground truth, never a feature |
| `provenance` | author/source per implementation |
| `representation_tags` | from taxonomy audit step 1 |
| `taxonomy_status` | pass/fail from taxonomy audit step 7 (fail ⇒ merged into an observational family, not excluded) |
| `n_implementations` | independent source implementations in this representation family (≥2 required for `(seen family, *)` cells, §2.1) |
| `n_traces` | per family |
| `generator_definition` | for open-set unknown classes only (§6.1): the precise access generator, so distinctness between validation- and test-unknown classes is auditable, not just a name |

Pilot v1 may proceed with as few as 2 independent-provenance implementations per known structure, reported strictly as exploratory/feasibility. Publication scale targets ≥5 independent-provenance families per known structure with a clone-detection/manual-audit pass.

### 4.6 Risk-based metrics

Risk is averaged through the full §2.1 hierarchy, not just per-implementation, so that a structure class or representation family with more implementations does not dominate:

```
R = (1/|C|) * Σ_{c in C}  (1/|G_c|) * Σ_{g in G_c}  (1/|I_g|) * Σ_{i in I_g}  (1/|T_i|) * Σ_{t in T_i} loss(t)
```

where `C` = structure classes, `G_c` = representation families within class `c`, `I_g` = source implementations within family `g`, `T_i` = traces of implementation `i`. Each `R_ab` cell (§4.3) is this same nested average, computed on test data only, conditioned on `family_shift=a, probe_shift=b`.

```
I = R_11 - R_10 - R_01 + R_00
```

**Paired-design requirement:** `I` is only interpretable as a family-shift/probe-shift interaction if the four cells are otherwise comparable — same structure-class composition, same hierarchy weighting, comparable probe difficulty between `Q_seen` and `Q_held`, same loss function, same test protocol. If `Q_seen` and `Q_held` differ substantially in difficulty (not just in seen/unseen status), `I` partly reflects probe-difficulty mismatch rather than a true interaction. Absent a verified paired/blocked design, `I` is reported as a **descriptive interaction contrast**, not a clean causal interaction estimate.

**Composition guard:** the nested average in `R` silently changes meaning if `C` (or `G_c`, `I_g`) differs between two cells being compared — e.g. if one structure class has no representation family eligible for `(unseen family, *)` at all (only 1 implementation exists, no held-out family possible), that class must either be dropped from **both** cells being compared, or the cells are not compared. Concretely: before computing any `Δ` (§8) or `I` (above) between two cells, verify the set of `(c, g)` pairs contributing to each cell's average is identical, or restrict both cells to their intersection and state the restriction explicitly. A cell is never silently computed over a different class/family composition than the cell it is compared against — that would make the comparison partly an artifact of which classes happened to have enough implementations, not of model behavior.

---

## 5. Normalization Registry

Ordered composition (avoids double-subtracting offset):

```
i_t^(1) = i_t - b                # offset, b = array.index_base (oracle)
i_t^(2) = i_t^(1) / n_logical    # size, n_logical (oracle, probe-grid param)
```

| Name | Formula | Scope | Parameter source | Permission |
|---|---|---|---|---|
| Offset | `i_t^(1) = i_t - b` | per-implementation | `array.index_base` | Oracle-permitted |
| Size | `i_t^(2) = i_t^(1) / n_logical` | per-implementation | `n_logical` | Oracle-permitted |
| Trace-length control | §5.2 | per-operation | `L` from train split only | Learned-from-train-only |
| Operation-mix stratification | reweight inversely to op-type frequency | per-family | train split only | Learned-from-train-only |

`B1` = `B0` + offset→size (fixed order) + length-control (**setting 2: matched/stratified**, §5.2) + mix-stratification.

**Why setting 2, not setting 3:** §5.2 establishes that padding+mask (setting 3) does not actually remove trace length from the feature space — the model can still infer length from the mask or padding-token position. Using setting 3 inside `B1` would make `B1` not actually a "fully controlled" baseline for length. Setting 3 remains available purely as a sequence-model batching convenience, never as the length-control claim inside `B1`.

### 5.1 Oracle-size vs. no-size disclosure

Because `n_logical` is itself oracle metadata, every headline result using size normalization is reported alongside a **`B1-no-size`** variant (`B1` with the size-normalization step removed, offset retained) against the default **`B1-oracle-size`** (as defined above). If a representation's cross-family gain depends on size normalization, the claim is scoped explicitly to the oracle-size setting and not generalized beyond it.

### 5.2 Trace-length control — three settings, reported separately

1. **Unmodified length** — sequence model handles variable length natively.
2. **Matched/stratified by length** — samples matched/stratified across compared groups without altering sequences. Operationalized as follows (v4 left this unspecified):
   - **Bins:** length bins are fixed from the **train split's** trace-length distribution only (quantile bins, e.g. deciles of train-split trace length), never from validation/test — consistent with §5.3.
   - **Matching unit:** matching is performed *within* each `(structure class, operation type)` stratum — not globally — so that, e.g., a Fenwick `point_update` trace is only matched against other `point_update` traces, not against a SegTree `range_query` trace of similar length. This prevents trace length from acting as a proxy for operation type.
   - **Procedure:** within each `(class, operation type)` stratum, take the per-bin minimum count across the groups being compared (e.g., across representation families in that stratum) and subsample every group down to that count per bin, using a fixed seed. No upsampling/duplication.
   - **Unmatched groups:** a stratum where one group has zero traces in a bin that another group occupies drops that bin for *all* groups in the comparison (not just the deficient one), so the compared sets remain length-matched.
   - **Reporting:** every result using setting 2 reports the **retention rate** — `(samples after matching) / (samples before matching)` — broken down by structure class and representation family, alongside the matched result. A retention rate that differs sharply across classes/families is flagged as a possible selection-bias signal (e.g., if matching disproportionately discards one family's longer, possibly harder, traces) rather than silently absorbed into the headline number.
3. **Padded/truncated with mask** — fixed `L` from training-split length distribution; padding token, mask, and truncation policy documented in advance.

**Caveat:** a length mask prevents shape mismatches in batching but does **not** remove trace length from the feature space — the model can still infer length from the mask itself or from padding-token position. If trace length must be genuinely controlled (not just batchable), use setting 2 (matched/stratified sampling, operationalized above) or treat length explicitly as a covariate in a separate analysis, not setting 3 alone.

### 5.3 Forbidden parameter sources

Test-split labels; any statistic computed over the test split; any threshold chosen after viewing test-set performance.

### 5.4 Ablation design

Independent: `B0`, `B0+offset`, `B0+offset→size`, `B0+length-control` (each of 3 settings, §5.2), `B0+mix-stratification`.
Cumulative: `B1-oracle-size` (defined above), `B1-no-size` (§5.1).

---

## 6. Open-Set Manifest

### 6.1 Known / unknown classes, split by OOD difficulty

Class lists below are a *consequence* of applying the §6.1.1 criteria, decided first — if the two ever disagree, §6.1.1's criteria win and this list is corrected, never the reverse.

```
Known (train/validation):
- Fenwick (>=2 independent-provenance families)
- Segment Tree (>=2 independent-provenance families)
- Prefix array (decoy, §2.2)

Validation-only unknown (used for threshold calibration; never seen at test):
- Near-OOD: heap
- Far-OOD: matrix traversal

Test-only unknown (used only for final open-set evaluation; never used to calibrate):
- Near-OOD: sparse table, blocked/hierarchical array, DSU
- Far-OOD: pure random-index access over a fixed-size array (uniform random index each step, no auxiliary structure)
```

Validation-unknown and test-unknown must be **disjoint at the generator level**, not just at the label level: "random/unstructured access" (validation) and "randomized array" (test) in v4 were two names that could denote the same underlying generator, which would silently leak calibration information into the test-unknown set. Fixed here: validation far-OOD uses **matrix traversal** (a fixed deterministic access generator unrelated to randomness); test far-OOD uses **uniform-random index access** (an explicitly stochastic generator). The two are structurally distinct families, not just distinctly named, and this distinctness is documented in the family registry (§4.5.2) alongside each unknown class's generator definition.

Near-OOD (structurally close to known classes) and far-OOD (obviously different) results are reported **separately** — strong far-OOD rejection alone is not reported as evidence of meaningful open-set capability.

### 6.1.1 Near/far-OOD classification rationale (fixed in advance, never adjusted after seeing results)

A candidate unknown structure is **near-OOD** if it shares most of the following with a known class, and **far-OOD** otherwise: same encoding medium (array-backed), comparable local index-transition regularity (e.g., arithmetic or near-arithmetic index relations between consecutive accesses), a hierarchical/recursive access relation, and state-changing (write) operations analogous to `point_update`.

Applying the criteria (v4 misapplied this for two classes — DSU and matrix traversal — corrected in §6.1's lists above):
- **Sparse table** (arithmetic block jumps, hierarchical, but read-only — no state-changing operation): near-OOD.
- **DSU** (parent-chasing over an array, hierarchical via path compression, state-changing via `union`): near-OOD, not far-OOD as v4 had it.
- **Blocked/hierarchical array** (sqrt-decomposition-style blocking): near-OOD.
- **Heap** (array-backed, arithmetic `2i`/`2i+1` index relation, hierarchical, state-changing via sift-up/down): near-OOD.
- **Matrix traversal** (array-backed, but index relation is row/column-stride arithmetic with no hierarchical/recursive relation, and typically read-only, not a `point_update`-analogous write): far-OOD, not near-OOD as v4 had it.
- **Uniform-random index access**: far-OOD by construction (no local index-transition regularity).

This classification is part of the manifest (§6.1) and is locked before any model is evaluated against it — it is not revisited based on observed rejection performance.

### 6.1.2 Rejection method

The pilot specifies, in advance, exactly one primary rejection method to evaluate (e.g., maximum softmax/class probability, energy score, distance-to-prototype, or a one-class model) — alternatives may be reported as secondary comparisons but the primary method is fixed before results are seen. Calibrating the rejection threshold using validation-unknown examples (§6.1) is a form of **outlier exposure** and is named as such in any write-up; it is explicitly distinguished from a stricter open-set setting with *no* unknown-class exposure at all during calibration (threshold chosen from known-class confidence statistics only), which is reported as a secondary, harder variant.

### 6.2 Metrics

AUROC (known vs. unknown, reported separately for near/far-OOD), AUPR, FPR@95%TPR, OSCR, macro-F1 with explicit `unknown` class, calibration error if using a confidence threshold. `d_between − d_within` is a representation-quality diagnostic only, not the primary open-set metric.

---

## 7. Baseline Reproduction Specification (Itai–Slavkin)

Three explicitly separate variants, each its own short spec doc (`baseline_b0_spec.md`) before implementation:

- **B0-original** — reproduces the paper as closely as the original (memory-address-trace) setting allows; gaps where the index-based trace setting cannot match are documented as "not reproducible," not silently adapted.
- **B0-adapted** — same conceptual features (address/index normalization, transition graph, short subsequences ≤3, SVM/C4.5/Naive Bayes), explicitly adjusted for index-based (not memory-address-based) traces, with each adaptation documented.
- **B0-modern** — same feature set as B0-adapted, fed into a modern classifier, documented as a deliberate upgrade, not a reproduction.

Reported results state which variant(s) are used; "the baseline" without a variant label is not an acceptable reporting form.

---

## 8. Falsifiability Criterion

Pre-registered as a **primary endpoint** plus a set of **secondary endpoints**, so that failing one secondary stress test does not by itself invalidate an otherwise-real effect — secondary endpoints bound the scope/robustness of the claim, while GO/PIVOT is decided primarily on the primary endpoint.

**Primary endpoint:** cross-family risk on `(unseen representation family, Q_seen)` after `B1-oracle-size` (§5), evaluated strictly on held-out test data (§4.3) at the source-implementation/representation-family statistical unit (§4.1, §2.1), hierarchy-weighted (§4.6), reported only when the `(seen, seen)`/`(unseen, seen)` cell pair has matched composition (§4.6 composition guard).

v4 left "measurable `Δ_F` gap" undefined. Locked here, on the hierarchical risk `R` from §4.6, model `φ` (the new relational representation) compared against baseline `β = B1-oracle-size`, both restricted to the same test composition:

```
G_β = R^β_{unseen,Q_seen} − R^β_{seen,Q_seen}      # baseline's own family-generalization gap
G_φ = R^φ_{unseen,Q_seen} − R^φ_{seen,Q_seen}      # representation's family-generalization gap
Δ_gap  = G_β − G_φ                                  # how much smaller the gap got
Δ_risk = R^β_{unseen,Q_seen} − R^φ_{unseen,Q_seen}  # direct improvement on the unseen-family cell itself
```

`Δ_gap` alone is not a sufficient criterion: a representation can shrink the gap purely by making `(seen, Q_seen)` worse (raising `R^φ_{seen,Q_seen}`), which is not a generalization improvement. The primary endpoint therefore requires **both**:

1. `Δ_risk > 0` — `φ` measurably reduces unseen-family risk relative to `β`, not just relative to its own seen-family risk.
2. **Non-inferiority on seen-family risk** — `R^φ_{seen,Q_seen} − R^β_{seen,Q_seen} ≤ δ` for a margin `δ` fixed in advance, so `φ` is not "generalizing" by degrading uniformly. At pilot/micro-pilot scale (§4.4 bootstrap caution), `δ` and statistical significance for `Δ_risk` are not yet meaningful with 2–5 implementations per class; both are reported as descriptive point estimates only. At publication scale (≥5 independent implementations per representation family), `δ` is pre-registered before test-set results are seen, and `Δ_risk > 0` is required to hold with a population-level interval (§4.4) that excludes 0, not just a positive point estimate.

**Secondary endpoints** (each reported separately, each scoping the claim rather than vetoing it outright):
- Dimension-holdout and compositional-holdout probe-shift regimes (§3.2)
- Held-out probes generally (`P_Q`, `P_FQ`)
- `B1-no-size` (does the gain survive without oracle size metadata, §5.1)
- Near-OOD and far-OOD open-set rejection (§6), reported separately
- Unseen source provenance generally

Results are reported as a controlled decomposition of family-shift, probe-shift, and their interaction (§4.6, descriptive interaction contrast unless the paired-design conditions hold) — not a causal claim, since implementation provenance, compiler/toolchain (locked per §1.6), and coding-template confounders are not independently randomized.

---

## 9. Pilot Questions (final, locked)

1. Which source variants produce genuinely different traces under the fixed task-specific probe grid (taxonomy audit, family registry §4.5)?
2. Is that difference stable across `n_logical`, operation type, and probe pattern?
3. How much does `B0` (with explicit variant label, §7) degrade on `(unseen family, Q_seen)` vs. `(seen family, Q_seen)`, family-weighted, test-only?
4. How much of that degradation survives `B1`?
5. Does a relational representation reduce the residual gap on `(unseen, Q_seen)`, under both oracle-size and no-size settings (§5.1)?
6. Does that improvement persist across all three probe-shift regimes on `(seen, Q_held)`/`(unseen, Q_held)`?
7. Does the representation maintain near- and far-OOD discrimination (§6) separately, not just aggregate open-set accuracy?

---

## 10. Micro-Pilot Scope (run before any large-corpus collection)

Purpose: validate the *pipeline itself* (schema extraction, allowlist/denylist enforcement, split correctness, normalization composition order, taxonomy audit, open-set calibration code) end-to-end on a small, cheap setup before investing in a larger corpus.

- 2–3 structure classes total (e.g., 1 Fenwick representation family, 1 Segment Tree representation family, 1 decoy), **1 source implementation each** — explicitly acceptable for mechanics-only validation, but per §2.1, this means `(seen family, *)` cells cannot be populated (no independent sibling implementation exists), so **no `P_IID`, `P_F`, `P_Q`, `P_FQ`, or GO/PIVOT decision is drawn from the micro-pilot**.
- Single task only (Task UQ), toolchain locked per §1.6.
- Small probe grid (reduced `n_logical` levels, 1 probe-shift regime — random-combination holdout only).
- Goal is confirming every checklist item in §11 works mechanically: `structure` truly never reaches the feature matrix; the array field is dropped, not leaked via anonymization order (§1.4); the semantic-root attribution rule (§1.5) behaves correctly on a recursive example; pipeline metadata (§1.2.1) never appears in features; the offset→size composition (§5) produces hand-checkable numbers; the taxonomy audit (§4.5.1) procedure runs end to end, including the merge-on-fail path (not just the pass path); the open-set calibration code keeps validation-unknown and test-unknown disjoint (§6.1).
- Only after the micro-pilot passes its own mechanical checks does corpus scaling (≥2, then ≥5 independent implementations per representation family, §4.5.2) begin — at which point the 2×2 matrix and falsifiability criterion (§8) become applicable.

### 10.1 Synthetic hierarchical-split fixture (separate from the C++ micro-pilot corpus)

With 1 implementation per structure class, the real micro-pilot corpus structurally cannot exercise the `(seen family, *)` split/risk code paths (§2.1) — there is no independent sibling implementation to hold out. Testing that code against real traces only happens once a ≥2-implementation family exists, which is too late to catch a split/weighting bug cheaply. So before (or alongside) the real micro-pilot, a **synthetic manifest fixture** — hand-constructed labels and dummy per-trace losses, no real C++ traces involved — exercises the evaluation machinery in isolation:

```
Class A
├── Family A1 (2 implementations: A1-x, A1-y)
└── Family A2 (2 implementations: A2-x, A2-y)
Class B
├── Family B1 (2 implementations: B1-x, B1-y)
└── Family B2 (1 implementation: B2-x)            # forces an unseen-family-only class
```

This fixture unit-tests, against hand-computed expected values:
- The hierarchical split (§4.2): `A1-x`/`A2-x`/`B1-x` train, `A1-y`/`A2-y`/`B1-y` held out as seen-family test (independent siblings), `B2-x` held out entirely as unseen-family test.
- All four `R_ab` cells (§4.3) compute the correct nested average (§4.6) on a synthetic loss assignment where the expected number is known by hand.
- The §4.6 composition guard: deliberately construct a cell pair with mismatched `(c, g)` composition and assert the code refuses to compare them (or restricts to the stated intersection) rather than silently averaging over different classes.
- No implementation ID ever appears on both sides of any split (§4.1 invariant), asserted programmatically.

The real micro-pilot corpus (1 implementation/class) and this synthetic fixture are complementary, not substitutes: the corpus tests the parser/instrumentation/feature-extraction path on real traces; the fixture tests the split/weighting/comparison path that the corpus is too small to exercise.

---

## 11. Status: checklist before micro-pilot

**Six blocking points from the v3→v4 review (must close before any code is written):**

- [x] Fix 1. §2.1 four-tier hierarchy (structure class → representation family → source implementation → trace) adopted consistently; §4.1/§4.3 terminology reconciled
- [x] Fix 2. §5 `B1` redefined to use length-control setting 2 (matched/stratified), not setting 3 (padding+mask)
- [x] Fix 3. §4.5.1 taxonomy audit procedure specified (not just a `taxonomy_status` field)
- [x] Fix 4. §1.5 semantic-root definition specified (nearest task-manifest-marked ancestor, not absolute outermost)
- [x] Fix 5. §1.2.1 pipeline-metadata denylist specified (probe_id, run_id, seed, implementation/family ID, source path, compiler flags, build hash, timestamp, sequence number)
- [x] Fix 6. §2.2 Task UQ and §1.6 toolchain locked for the micro-pilot

**Nine points from the v4→v5 review (must close before any code is written):**

- [x] Fix 7. §4.2/§4.3 split is hierarchical (by source implementation within family), not a flat family-level cut; "seen family" wording corrected to "independent sibling implementation," not "disjoint traces from the same implementation"
- [x] Fix 8. §6.1/§6.1.1 near/far-OOD contradiction resolved (DSU → near-OOD, matrix traversal → far-OOD); validation-unknown vs. test-unknown far-OOD generators made structurally distinct (matrix traversal vs. uniform-random access), not just distinctly named
- [x] Fix 9. §4.5.1 step 7 taxonomy-audit pass bar tightened (stability across ≥2 `n_logical`, primary operation, ≥2 sequence patterns, post-normalization) and failure path changed from exclusion to merge-into-observational-family, avoiding selection bias toward easily-distinguished families
- [x] Fix 10. §8 `Δ_risk`/`Δ_gap` defined precisely on the §4.6 hierarchical risk; primary endpoint requires both `Δ_risk > 0` and a non-inferiority bound on seen-family risk, not a gap reduction alone
- [x] Fix 11. §10.1 synthetic hierarchical-split fixture added — exercises `(seen family, *)` split/risk/composition-guard code paths that the 1-implementation-per-class micro-pilot corpus structurally cannot reach
- [x] Fix 12. §1.2.2 per-model input-channel table added, so `B0-original`/`B0-adapted`/`B0-modern`/`B1-oracle-size`/`B1-no-size` each have an explicit, distinct, auditable feature set instead of an implicit shared one
- [x] Fix 13. §5.2 length-control setting 2 (matched/stratified) operationalized: train-only quantile bins, within-stratum matching by `(class, operation type)`, fixed-seed subsampling to per-bin minimum, mandatory retention-rate reporting
- [x] Fix 14. §4.6 composition guard added: `Δ`/`I` comparisons across cells require identical `(class, family)` composition or an explicitly stated restriction to the intersection
- [x] Fix 15. §2.2 "plain prefix-sum array" replaced with three explicitly distinct decoy representation families (PA-recompute, PA-eager, PA-rebuild), each independently taxonomy-audited

**Remaining mechanical checklist:**

- [ ] §1.2 allowlist/denylist enforced in code (not yet written) and unit-tested on a synthetic trace (assert `structure` never appears in extracted feature vectors)
- [ ] §1.2.2 per-model input-channel table enforced in code (each `B0-*`/`B1-*` variant restricted to its declared channels only)
- [ ] §1.4 array field confirmed dropped (not anonymized-by-order) for the single-array core task
- [ ] §1.5 semantic-root attribution rule implemented and verified on a recursive example
- [ ] §2.2 confirmed every micro-pilot implementation supports Task UQ's full operation surface; all three PA-* decoy variants implemented separately
- [ ] §3.1 `n_logical` vs `n_allocated` distinguishable in collected metadata
- [ ] §4.1/§4.2 hierarchical split implemented at the source-implementation level (not flat family-level); assert-checked that no implementation appears in both train and test
- [ ] §4.5.1 taxonomy audit implemented end to end, including the merge-on-fail path producing `observational_family_id`
- [ ] §4.6 hierarchical risk formula implemented (not flat per-trace average); composition guard implemented and unit-tested (rejects/restricts mismatched-composition comparisons)
- [ ] §5 normalization composition order implemented exactly as specified; hand-verified on one example
- [ ] §5.1 `B1-no-size` variant implemented alongside `B1-oracle-size`
- [ ] §5.2 length-matching procedure implemented exactly as specified (train-only bins, within-stratum matching, retention-rate reporting)
- [ ] §6.1.1 near/far-OOD rationale and corrected class lists fixed before any model is run; validation-unknown and test-unknown confirmed disjoint at the generator level, not just by label
- [ ] §6.1.2 primary rejection method chosen in advance and documented
- [ ] §7 `baseline_b0_spec.md` written, each line labeled original/adapted/modernized/not-reproducible, cross-referenced against the §1.2.2 channel table
- [ ] §8 `Δ_risk`/`Δ_gap`/non-inferiority computation implemented on the hierarchical risk; descriptive-only at micro-pilot scale (§4.4)
- [ ] §10 micro-pilot run and mechanically verified; explicitly not used to draw any GO/PIVOT conclusion (§2.1)
- [ ] §10.1 synthetic hierarchical-split fixture implemented and passing, independent of real C++ trace collection
