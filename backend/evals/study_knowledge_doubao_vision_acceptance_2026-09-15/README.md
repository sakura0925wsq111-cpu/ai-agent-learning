# Doubao Vision Knowledge Extraction Acceptance 2026 09 15

> Historical `doubao-vision-v1` result. The later `doubao-vision-v2` pipeline replaces semantic labels with `statement / list / steps`; see the post-test section in the 79-page regression report.

## Verdict

CONDITIONAL NO-GO for default automatic release.

The PDF and PPTX page-image transport now works end to end with the configured Doubao model. JSON reliability and deterministic filtering are sufficient for an opt-in experiment. Semantic fidelity is not yet sufficient for default automatic release because one high-confidence terminology substitution changed the source meaning.

The application default remains `knowledge-v1`. `doubao-vision-v1` must be selected explicitly.

## Configuration

- Model: `doubao-seed-2-1-turbo-260628`
- Pipeline: `doubao-vision-v1`
- Transport: page images
- Model interface: Chat Completions JSON mode
- Thinking: disabled
- Batch size: one page or slide
- Render: JPEG at 144 DPI, quality 80
- Confidence threshold: 0.85
- Runtime semantic review: disabled
- Local source blocks persisted: false
- API key: not recorded

## Sources

| Source | SHA-256 | Pages or slides |
| --- | --- | ---: |
| `企业战略管理分章重点【21页】(1).pdf` | `DCA3544FA8D5E5D163D1E7E53073E5AD3905F795ADF05B7F5B9BCF8928E7E6F0` | 21 |
| `9.3模糊综合评价法(1).pptx` | `C5A345C65AC800A092342DAB09549CF4332196717D293999AA724A8D4275C621` | 9 |

## Transport and format results

- The legacy Files API path uploaded PDF files but remained in `processing`; referencing the file returned `403 OperationDenied.InvalidState`.
- Responses image input returned HTTP 200, but the first full prompt timed out when deep thinking remained enabled.
- Disabling deep thinking reduced the single-page PDF run to about 20 seconds.
- Two-page Responses output produced non-JSON text. The final route therefore uses Chat Completions JSON mode with one page per request.
- LibreOffice 26.8.0 converted the nine-slide PPTX to a nine-page PDF. The Windows launcher returned before the output PDF appeared, so the implementation now waits for a stable, readable PDF before continuing.
- Visual inspection confirmed that the definition, procedure, image-based television exercise, and refrigerator tables remained visible after conversion.

## PPTX result

- Model candidates: 14
- Accepted by the run-time filter before the final course-credit rule: 7
- Rejected by model risk, completeness, or confidence rules: 7
- Rejected afterward by the deterministic course-credit rule: 1
- Accepted under the final rule set: 6
- Exercise or example risks rejected: 4
- The six retained items cover the definition, implementation steps, weighting methods, evaluation-basis requirements, result-expression requirements, and the warning about too many factors.
- The two exercise sections and their matrix, table, or image dependencies did not enter the accepted set.

## PDF result

- Pages completed: 21 of 21
- Model calls: 21
- Candidates: 265
- Accepted: 240
- Filtered: 25
- Accepted items with no exercise markers: 240 of 240
- Normalized content found as one continuous source-page substring: 116 of 240
- Accepted items with at least 99 percent source-character coverage: 129 of 240
- Accepted items with at least 95 percent source-character coverage: 184 of 240
- Accepted items with at least 90 percent source-character coverage: 218 of 240
- Observed end-to-end duration: approximately six minutes on the acceptance machine.

The character coverage metric is diagnostic only. It does not prove semantic correctness.

## Manual semantic sample

The manual sample contained one deliberately difficult, low-character-coverage accepted item from each page that produced output, plus the known terminology-sensitive item on page 1. This produced 21 reviewed items.

- Meaning preserved: 20
- Meaning changed: 1
- Observed sample accuracy: 95.2 percent

The failure was:

- Source: `经营战略的特点（1）全局性（2）长远性（3）竞合性（4）纲领性（5）相对稳定性`
- Accepted output: `经营战略的特点：（1）全局性（2）长远性（3）竞争性（4）纲领性（5）相对稳定性`
- Model confidence: 0.98
- Severity: meaning changed because `竞合性` includes cooperation as well as competition.

The sample was risk-focused rather than random, so 95.2 percent must not be presented as population accuracy.

## Code gates added during acceptance

- Reject source page or slide numbers outside the current image batch.
- Reject unbalanced brackets and parentheses.
- Reject course credits, presenter lines, and thanks pages.
- Validate candidates independently so one malformed candidate is filtered instead of failing the entire document.
- Attach the failing source page range to batch-level model errors.
- Limit documents to 40 pages and enforce the configured model-call budget.
- Preserve `knowledge-v1` as the default pipeline.

## Verification

- Full backend suite: 178 passed, 1 pre-existing Pydantic deprecation warning, 4 subtests passed.
- `docker compose config --quiet`: passed.
- Python compile check for the changed Study services and smoke runner: passed.
- `git diff --check`: passed apart from Windows line-ending notices.

## Remaining gate

Before making `doubao-vision-v1` the default, run a new blinded holdout with at least 50 accepted items and require zero meaning-changing substitutions in protected terms, numbers, negations, conditions, and list members. The current two files are development regression sources and are not a future holdout.
