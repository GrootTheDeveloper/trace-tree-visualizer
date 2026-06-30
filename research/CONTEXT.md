# Session Handoff — Micro-Pilot Implementation

**Ngày tạo:** 2026-07-01. Đọc file này trước khi làm bất cứ điều gì.

---

## 1. Nghiên cứu này là gì (đọc kỹ trước)

**Không phải** hệ thống end-to-end phục hồi cấu trúc dữ liệu (cái đó là hướng thesis cũ, file `implementation_plan.md` — hiện tại không dùng).

**Đây là:** nghiên cứu **phân loại** — trong oracle-assisted setting, liệu một representation học máy có thể nhận ra *họ cấu trúc dữ liệu* (Fenwick Tree, Segment Tree, decoy) từ access trace của mảng, bao gồm cả nhận dạng mở (từ chối cấu trúc chưa thấy)?

**Oracle-assisted setting:** array identity (tên mảng nào là target) và operation boundaries (mỗi `build`/`point_update`/`prefix_query` bắt đầu/kết thúc ở đâu) được cho sẵn bởi instrumentation `trace.hpp`. Không cần tự phát hiện — đây là điều kiện tiên quyết phải nêu rõ trong mọi claim.

**Ba câu hỏi nghiên cứu (locked):**
- RQ1: Itai–Slavkin features (2007) generalize thế nào sang unseen trace families?
- RQ2: Relational vocabulary không hard-code cấu trúc cụ thể có cải thiện cross-family generalization không?
- RQ3: Các thành phần read/write mode, value transitions, operation context đóng góp gì cho open-set recognition?

**Novelty claim:** là empirical hypothesis, KHÔNG phải đã được chứng minh. Được quyết định bởi kết quả experiment.

---

## 2. Bốn tầng hierarchy (phải thuộc trước khi viết dòng code nào)

```
structure class         (Fenwick / SegTree / decoy / unknown)
└── representation family   (vd: "Fenwick, 1-indexed, recursive")
    └── source implementation   (một codebase cụ thể / tác giả độc lập)
        └── trace   (một lần chạy probe)
```

**Đây không phải abstraction tùy ý.** Nó quyết định:
- Đơn vị thống kê = **source implementation**, không phải trace
- Split: không có source implementation nào trong cả train lẫn test
- 2×2 matrix: `(seen family, *)` cần ≥2 implementation độc lập / representation family
- Risk formula: lồng bốn cấp, trọng số đều ở mỗi cấp

**Micro-pilot chỉ có 1 implementation / structure class** — do đó không thể tính `P_IID`, `P_F`, `P_Q`, `P_FQ`, không có kết luận GO/PIVOT.

---

## 3. Source of truth duy nhất

**`prototype/research/protocol.md` (v5)** — tất cả các quyết định thiết kế đều ở đây. Đọc trước khi code.

File này có 11 section theo thứ tự locking:
1. Feature Contract & Event Semantics
2. Task/API Manifest & Label Hierarchy (four-tier hierarchy)
3. Probe Grid
4. Statistical Unit & Split Manifest
5. Normalization Registry
6. Open-Set Manifest
7. Baseline Reproduction Specification
8. Falsifiability Criterion
9. Pilot Questions
10. Micro-Pilot Scope (+ §10.1 Synthetic fixture)
11. Status checklist — đọc mục này để biết chính xác cần làm gì

---

## 4. Những gì cần làm tiếp (task hiện tại)

Protocol đã được review 4 vòng adversarial (v1→v5), tất cả lỗi methodology đã sửa. Verdict cuối: **cleared cho mechanical micro-pilot only**.

### 4a. Synthetic hierarchical-split fixture (§10.1) — ưu tiên TRƯỚC khi thu trace thật

**Lý do:** micro-pilot corpus (1 implementation/class) không thể exercise đường code `(seen family, *)` split/risk/composition-guard. Fixture này test evaluation machinery độc lập với C++ traces.

**Fixture structure (hand-constructed):**
```
Class A
├── Family A1 (2 implementations: A1-x, A1-y)
└── Family A2 (2 implementations: A2-x, A2-y)
Class B
├── Family B1 (2 implementations: B1-x, B1-y)
└── Family B2 (1 implementation: B2-x)  # class với chỉ unseen-family
```

**Phải kiểm tra:**
- Hierarchical split đúng: A1-x/A2-x/B1-x train → A1-y/A2-y/B1-y test (seen family), B2-x test (unseen family)
- 4 cells R_00/R_01/R_10/R_11 tính đúng nested average theo §4.6
- Composition guard: từ chối so sánh cells có `(class, family)` composition khác nhau
- Không có implementation ID nào xuất hiện ở cả hai split

### 4b. Micro-pilot C++ corpus (sau khi fixture pass)

- 3 structure classes: 1 Fenwick family, 1 Segment Tree family, 3 decoy families (PA-recompute, PA-eager, PA-rebuild)
- 1 source implementation mỗi family
- Task UQ duy nhất: `build`, `point_update`, `prefix_query`
- Toolchain locked: g++ -std=c++17 -O2, Windows 11

**Micro-pilot CÒN PHẢI kiểm tra (§11 remaining checklist):**
- `structure` field KHÔNG ĐƯỢC xuất hiện trong feature vector (assert trước khi training)
- Array field bị DROP, không phải anonymize-by-order
- Semantic root attribution đúng trên recursive example
- Pipeline metadata (probe_id, run_id, seed, etc.) KHÔNG vào feature matrix
- Offset→size normalization composition đúng thứ tự, hand-verify một example
- Taxonomy audit 7-bước chạy end-to-end, kể cả merge-on-fail path
- Open-set calibration: validation-unknown và test-unknown disjoint ở generator level

---

## 5. Những gì đã được khóa (không cần hỏi lại)

### Feature allowlist (§1.2)
Core model input: **chỉ** `normalized_index` (offset→size) + `read/write mode`.

Không được dùng: `structure` (ground truth label), raw `array` name, `op_id`, `file`, `line`, `probe_id`, `run_id`, seed, source path, compiler flags, build hash, timestamp.

### Input channels per baseline (§1.2.2)
| Model | Channels được phép |
|---|---|
| B0-original | raw_index + mode |
| B0-adapted / B0-modern | offset_index + mode |
| B1-oracle-size | size_normalized_index + mode |
| B1-no-size | offset_index + mode |

Không baseline nào được "mượn" normalization của baseline khác.

### Normalization (§5) — ordered, không đổi thứ tự
```
i^(1) = i - b           # b = array.index_base (oracle)
i^(2) = i^(1) / n       # n = n_logical (oracle, probe-grid param)
```

### Split (§4.2) — hierarchical, không phải flat
- `(seen family, *)`: split ở cấp source implementation *trong* family
- `(unseen family, *)`: cả family bị hold out
- Không implementation nào ở cả hai split

### Near/far-OOD (§6.1.1 → §6.1)
| Class | Loại |
|---|---|
| Heap | Near-OOD (validation) |
| Matrix traversal | Far-OOD (validation) |
| Sparse table, blocked array, DSU | Near-OOD (test) |
| Uniform-random index access | Far-OOD (test) |

DSU là **near-OOD** (không phải far-OOD như v4 nhầm). Matrix traversal là **far-OOD** (không phải near-OOD).

### Falsifiability (§8)
Primary endpoint cần CẢ HAI:
1. `Δ_risk = R^β_unseen - R^φ_unseen > 0` (model mới cải thiện unseen-family risk trực tiếp)
2. `R^φ_seen - R^β_seen ≤ δ` (không trade-off bằng cách phá seen-family)

`Δ_gap = G_β - G_φ` (gap giảm) là điều kiện cần nhưng chưa đủ.

Ở micro-pilot scale: chỉ báo cáo descriptive, không CI, không significance test.

---

## 6. Những gì KHÔNG được làm (lịch sử lỗi cần tránh)

| Hành động | Lý do bị reject |
|---|---|
| Dùng clustering để định nghĩa ground-truth labels | Circular: feature dùng để cluster = feature được evaluate |
| Anonymize array name theo first-seen order | Leak implementation identity (implementation A và B truy cập array theo thứ tự khác nhau) |
| Dùng `P_IID` từ micro-pilot như kết quả nghiên cứu | Không có independent sibling implementation → không thể tính P_IID nghiêm túc |
| So sánh Δ giữa hai cells có composition khác nhau | Nếu classes khác nhau ở hai cells, Δ phản ánh composition chứ không phải model behavior |
| Length control bằng padding+mask (setting 3) trong B1 | Mask không remove length signal — model vẫn thấy length từ mask position |
| Báo cáo "the baseline" không ghi variant | B0-original/B0-adapted/B0-modern có input channels khác nhau |
| Coi DSU là far-OOD | DSU có hierarchical structure, state-changing via union → near-OOD |
| Claim "first system to identify data structures" | Itai–Slavkin 2007 đã có, bao gồm cả array structures |
| "Dual-BIT required for point-update + range-query" | Sai: dual-BIT chỉ cần cho range-update + range-query |

---

## 7. File locations

```
f:\Self\thesis\proposal\
├── prototype\
│   ├── cpp\
│   │   └── trace.hpp           ← event schema source (JSONL: array/op_begin/op_end/op_param/access/watch/error)
│   ├── research\
│   │   ├── protocol.md         ← SOURCE OF TRUTH, v5, đọc trước khi làm gì
│   │   └── CONTEXT.md          ← file này
│   └── examples\
│       ├── seg_iterative.cpp   ← example implementation (có thể dùng cho micro-pilot)
│       └── seg_lazy.cpp        ← example implementation
├── implementation_plan.md      ← HƯỚNG CŨ, không dùng cho research này
└── chapters\                   ← thesis chapters (thesis proposal cũ, scope khác)
```

**Chưa có:**
- Script thu trace (trace collection code) — chưa được viết
- Feature extraction code — chưa được viết
- Split/risk evaluation code — chưa được viết
- `baseline_b0_spec.md` — chưa được viết
- Bất kỳ dòng code nào cho ML pipeline — chưa được viết

---

## 8. Thứ tự làm việc được khuyến nghị

```
Bước 1: Đọc protocol.md §11 "Remaining mechanical checklist" — đây là danh sách task đầy đủ nhất.

Bước 2: Implement synthetic fixture (§10.1) — Python, không cần C++.
  File: prototype/research/eval/test_split_fixture.py (hoặc tests/)
  Input: hand-written manifest YAML/JSON với labels và dummy losses
  Output: assert pass/fail trên hierarchical split, risk formula, composition guard

Bước 3: Implement feature extraction pipeline
  - Event parser (grounded in trace.hpp schema)
  - Allowlist/denylist enforcement (§1.2, §1.2.1)
  - Array field DROP (§1.4)
  - Semantic root attribution (§1.5)
  - Offset→size normalization composition (§5)
  Unit test: assert `structure` never in features (§11 checklist item 1)

Bước 4: Taxonomy audit (§4.5.1) — 7 bước, chạy trên implementations thật
  Cần có ít nhất 1 Fenwick + 1 SegTree + 3 PA-* implementations

Bước 5: Collect traces từ micro-pilot corpus (Task UQ, toolchain locked)
  Probe grid nhỏ: n ∈ {8, 64, 256}, reduced positions/patterns

Bước 6: Chạy micro-pilot end-to-end, verify §11 checklist mechanically
  KHÔNG diễn giải accuracy/risk như evidence cho cross-family hypothesis

Bước 7: Viết baseline_b0_spec.md (§7) — trước khi implement B0

Bước 8: Scale lên ≥2 independent implementations / representation family
  → Lúc đó mới có thể tính P_IID, P_F, P_Q, P_FQ và xem kết quả thật
```

---

## 9. Checklist kế thừa từ protocol.md §11

Copy từ protocol.md v5 để tiện theo dõi:

- [ ] §1.2 allowlist/denylist enforced in code, unit-tested
- [ ] §1.2.2 per-model input-channel table enforced per baseline variant
- [ ] §1.4 array field dropped (not anonymized-by-order)
- [ ] §1.5 semantic-root attribution verified on recursive example
- [ ] §2.2 all three PA-* decoy variants implemented separately
- [ ] §3.1 n_logical vs n_allocated distinguishable in metadata
- [ ] §4.1/§4.2 hierarchical split at source-implementation level, assert-checked
- [ ] §4.5.1 taxonomy audit end-to-end, including merge-on-fail path
- [ ] §4.6 hierarchical risk formula, composition guard implemented+unit-tested
- [ ] §5 normalization composition order, hand-verified on one example
- [ ] §5.1 B1-no-size variant implemented alongside B1-oracle-size
- [ ] §5.2 length-matching procedure (train-only bins, within-stratum, retention reporting)
- [ ] §6.1.1 near/far-OOD class lists fixed before any model run; disjoint at generator level
- [ ] §6.1.2 primary rejection method chosen and documented in advance
- [ ] §7 baseline_b0_spec.md written (original/adapted/modernized/not-reproducible labels)
- [ ] §8 Δ_risk/Δ_gap/non-inferiority computation implemented; descriptive-only at micro-pilot scale
- [ ] §10 micro-pilot run and mechanically verified; no GO/PIVOT conclusion drawn
- [ ] §10.1 synthetic hierarchical-split fixture implemented and passing

---

## 10. Key citations (đừng quên)

- **Itai & Slavkin 2007** (AAIP@ECML/PKDD): baseline B0, bao gồm array structures + ML. Claim "first to identify data structures" sẽ bị reject vì paper này.
- **Gold 1967, Rice's theorem**: impossibility results — không thể claim là novel contribution riêng.

---

*Tạo tự động từ protocol.md v5 và lịch sử session 2026-07-01.*
*Nếu có conflict giữa file này và protocol.md: protocol.md thắng.*
