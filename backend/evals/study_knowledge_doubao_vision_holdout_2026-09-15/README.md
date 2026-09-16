# Doubao Vision Holdout Test 2026 09 15

## Verdict

NO-GO for full-document use under the current limits.

The 79-page source exceeds the current 40-page safety limit, so the complete run correctly stopped with `source_page_limit_exceeded` before any model calls. A frozen representative test on pages 1 through 10 completed successfully and showed good source fidelity, but weak type classification and incomplete recall.

## Source

- File: `88b73e57ebe0ab3bad41ec6845cd01d2.pdf`
- SHA-256: `EC265DFE91B147237074C409C349C9F7AA278AF8884A5CDA155663DE20F560D3`
- Size: 12,718,373 bytes
- Pages: 79
- Page size: 960 by 540 points
- Producer context: WPS presentation export
- Encrypted: no
- Text layer: mixed; several pages are image-only

## Frozen pipeline

- Pipeline: `doubao-vision-v1`
- Model: `doubao-seed-2-1-turbo-260628`
- One page per Chat JSON-mode request
- Thinking disabled
- JPEG render at 144 DPI, quality 80
- Confidence threshold: 0.85
- No second-model semantic review
- No source-block persistence
- No prompt or filter changes were made before the first holdout run

## Visual inspection

Representative pages 1, 2, 3, 4, 5, 6, 17, 28, 42, 61, and 79 were rendered and inspected. The source is a New China history slide deck with cover pages, historical narration, photographs, film screenshots, section dividers, and image-only pages.

## Full-document result

- Result: rejected before inference
- Error: `source_page_limit_exceeded`
- Reason: 79 pages exceeds the configured 40-page limit and would also require more than the configured model-call budget at one page per call
- Model cost incurred by this attempt: none

## Pages 1 through 10 result

- Model calls: 10
- Candidates: 23
- Accepted: 11
- Filtered: 12
- Accepted source pages: 3, 4, and 5
- Accepted items from cover page 1: 0
- Accepted items from preface page 2: 0
- Accepted items from image-only pages 6 through 10: 0
- Accepted items with visually traceable source content: 11 of 11
- Accepted items preserving the source meaning: 11 of 11 in manual review
- Clearly wrong type labels: at least 4 of 11

Filtering reasons included image dependency, unclear source, incomplete context, incomplete content, low confidence, and substantial rewrite.

## Positive findings

- The model did not invent historical events from the image-only pages in the tested range.
- All 11 accepted statements were visible on pages 3 through 5.
- The accepted statements did not change names, dates, quantities, or historical meaning in the reviewed subset.
- Cover and preface material did not enter the accepted set.

## Failures

The narrow type vocabulary does not fit narrative history material. Examples include:

- `中国是一个具有悠久历史的世界文明古国。` was labeled `characteristic_list` even though it is not a list.
- `为了救亡图存，无数仁人志士奋起寻求救国救民、振兴中华的道路。` was labeled `principle` even though it is a historical statement.
- `长江三峡的曲折动荡...` was labeled `characteristic_list` even though it is narrative prose.
- The statement about the Opium War opening a major social and cultural transformation was labeled `principle`.

The extractor also omitted an important statement on page 3 describing how Western invasion and Qing corruption left modern China poor, weak, and in crisis after 1840. Therefore source fidelity among returned items does not prove adequate knowledge coverage.

## Interpretation

This sample supports using the page-image route for faithful transcription, but it does not support the current `definition / list / principle / effect` taxonomy as a general-purpose knowledge-point schema. The result is usable only as a narrow experiment, not as a complete extraction of this 79-page courseware.

After this review the file becomes a development regression source and must not be reused as a fresh holdout.

## Post-test structural taxonomy retest

After the holdout verdict was frozen, the user approved replacing discipline-specific semantic labels with three structural labels: `statement`, `list`, and `steps`. This is a new `doubao-vision-v2` pipeline and is not part of the original holdout score above.

A real rerun on pages 1 through 5 produced 18 candidates and accepted all 18. All returned items used `statement` or `list` appropriately. The previously omitted page-3 statement about the effects of Western invasion and Qing corruption after 1840 was recovered. No cover-page item was returned.

One remaining issue is semantic duplication: page 4 returned the three revolutions as individual statements and also as one summary list. Exact-text deduplication does not merge these semantically overlapping items.
