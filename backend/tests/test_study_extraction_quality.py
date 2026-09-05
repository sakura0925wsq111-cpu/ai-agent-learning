from __future__ import annotations

import pytest

from services.study_extraction_quality import apply_paragraph_gate, assess_ocr_page
from services.study_ocr import OCRBlock


PRIMARY_SIZE = (1000, 1000)
VERIFY_SIZE = (1200, 1200)


def _primary(text: str, confidence: float = 0.99, top: int = 100) -> OCRBlock:
    return OCRBlock(text, confidence, [100, top, 900, top + 80])


def _verification(text: str, confidence: float = 0.99, top: int = 120) -> OCRBlock:
    return OCRBlock(text, confidence, [120, top, 1080, top + 96])


def _assess(primary: list[OCRBlock], verification: list[OCRBlock]):
    return assess_ocr_page(
        primary,
        verification,
        primary_size=PRIMARY_SIZE,
        verification_size=VERIFY_SIZE,
        min_confidence=0.95,
    )


def test_stable_high_confidence_text_is_accepted():
    assessment = _assess(
        [_primary("土的三相组成。")],
        [_verification("土的三相组成")],
    )

    assert assessment.quality_status == "accepted"
    assert assessment.safe_text == "土的三相组成。"
    assert assessment.quality_reasons == []
    assert assessment.blocks[0]["decision"] == "accepted"
    assert assessment.blocks[0]["bbox_unit"] == "relative"


def test_low_confidence_noise_and_unbalanced_text_are_excluded():
    assessment = _assess(
        [
            _primary("土的三相组成", top=100),
            _primary("固相(颗粒", top=250),
            _primary("1.1", top=400),
            _primary("í", confidence=0.46, top=550),
            _primary("表现出土的不同工程性质", top=700),
        ],
        [
            _verification("土的三相组成", top=120),
            _verification("固相(颗粒", top=300),
            _verification("1.1", top=480),
            _verification("í", confidence=0.48, top=660),
            _verification("表现出土的不同工程性质", top=840),
        ],
    )

    assert assessment.quality_status == "partial"
    assert assessment.safe_text == "土的三相组成"
    assert "unbalanced_delimiters" in assessment.quality_reasons
    assert "noise_detected" in assessment.quality_reasons
    assert "ocr_low_confidence" in assessment.quality_reasons
    assert "context_fragment" in assessment.quality_reasons


def test_formula_dependency_rejects_the_whole_page():
    primary = [
        _primary("天然地面", top=100),
        _primary("σz=(0.2或0.1)σc", top=300),
        _primary("计算步骤一", top=500),
    ]
    verification = [
        _verification("天然地面", top=120),
        _verification("σz=(0.2或0.1)σc", top=360),
        _verification("计算步骤一", top=600),
    ]

    assessment = _assess(primary, verification)

    assert assessment.quality_status == "rejected"
    assert assessment.safe_text == ""
    assert "formula_detected" in assessment.quality_reasons
    assert "formula_context_dependency" in assessment.quality_reasons
    assert "no_safe_text" in assessment.quality_reasons
    assert all(block["decision"] == "rejected" for block in assessment.blocks)


def test_disagreement_between_ocr_passes_is_rejected():
    assessment = _assess(
        [_primary("土中颗粒的大小")],
        [_verification("土中颗粒的成分")],
    )

    assert assessment.quality_status == "rejected"
    assert assessment.safe_text == ""
    assert assessment.quality_reasons == [
        "no_safe_text", "ocr_unstable", "paragraph_member_rejected"
    ]
    assert assessment.blocks[0]["verification_text"] == "土中颗粒的成分"
    assert assessment.blocks[0]["verification_confidence"] == pytest.approx(0.99)


def _same_layout(primary):
    return assess_ocr_page(
        primary, [OCRBlock(block.text, block.confidence, block.bbox) for block in primary],
        primary_size=PRIMARY_SIZE, verification_size=PRIMARY_SIZE, min_confidence=0.95,
    )


def test_rejected_middle_line_rejects_whole_paragraph_not_other_paragraph():
    assessment = _same_layout([
        OCRBlock("荷载作用下，土体发生", 0.99, [100, 100, 800, 140]),
        OCRBlock("压缩并排出孔隙水，", 0.6, [100, 148, 800, 188]),
        OCRBlock("最终产生地基沉降。", 0.99, [100, 196, 800, 236]),
        OCRBlock("另一个独立段落。", 0.99, [100, 400, 800, 440]),
    ])
    assert assessment.safe_text == "另一个独立段落。"
    assert assessment.raw_text.startswith("荷载作用下，土体发生\n压缩并排出孔隙水，")
    first, middle, last, other = assessment.blocks
    assert first["paragraph_id"] == middle["paragraph_id"] == last["paragraph_id"]
    assert other["paragraph_id"] != first["paragraph_id"]
    assert first["line_decision"] == last["line_decision"] == "accepted"
    assert all(block["decision"] == "rejected" for block in (first, middle, last))
    assert "ocr_low_confidence" in first["paragraph_reasons"]


def test_complete_wrapped_paragraph_retains_all_lines_and_balanced_parentheses():
    assessment = _same_layout([
        OCRBlock("土由三种物质（固相、", 0.99, [100, 100, 800, 140]),
        OCRBlock("液相和气相）组成，", 0.99, [100, 148, 800, 188]),
        OCRBlock("因此称为三相体系。", 0.99, [100, 196, 800, 236]),
    ])
    assert assessment.safe_text == assessment.raw_text
    assert assessment.quality_status == "accepted"
    assert len({block["paragraph_id"] for block in assessment.blocks}) == 1


def test_side_by_side_columns_are_independent_even_with_interleaved_ocr_order():
    assessment = _same_layout([
        OCRBlock("左栏第一行", 0.99, [80, 100, 430, 140]),
        OCRBlock("右栏错误行", 0.5, [600, 100, 950, 140]),
        OCRBlock("左栏最后一行。", 0.99, [80, 148, 430, 188]),
        OCRBlock("右栏最后一行。", 0.99, [600, 148, 950, 188]),
    ])
    assert assessment.safe_text == "左栏第一行\n左栏最后一行。"
    assert assessment.blocks[1]["paragraph_id"] == assessment.blocks[3]["paragraph_id"]
    assert assessment.blocks[0]["paragraph_id"] != assessment.blocks[1]["paragraph_id"]


def test_inline_rejected_fragment_cannot_leave_a_good_prefix():
    assessment = _same_layout([
        OCRBlock("动强度说明：", 0.99, [100, 100, 500, 140]),
        OCRBlock("符号识别错误", 0.5, [508, 100, 800, 140]),
    ])
    assert assessment.safe_text == ""
    assert assessment.blocks[0]["paragraph_id"] == assessment.blocks[1]["paragraph_id"]


def test_secondary_only_middle_line_prevents_primary_from_skipping_it():
    first = OCRBlock("第一行未结束，", 0.99, [100, 100, 800, 140])
    missing = OCRBlock("主识别遗漏的关键行", 0.99, [100, 148, 800, 188])
    last = OCRBlock("第三行结束。", 0.99, [100, 196, 800, 236])
    assessment = assess_ocr_page(
        [first, last], [first, missing, last],
        primary_size=PRIMARY_SIZE, verification_size=PRIMARY_SIZE, min_confidence=0.95,
    )
    assert assessment.safe_text == ""
    assert "ocr_missing_primary" in assessment.quality_reasons
    assert len({block["paragraph_id"] for block in assessment.blocks}) == 1
    assert "主识别遗漏" not in assessment.raw_text


@pytest.mark.parametrize("boundary", ["white_space", "new_item", "sentence_end", "font_change"])
def test_paragraph_boundaries_prevent_unrelated_rejection(boundary):
    first = OCRBlock("第一段内容", 0.99, [100, 100, 800, 140])
    other = OCRBlock("错误内容", 0.4, [100, 150, 800, 190])
    if boundary == "white_space":
        other = OCRBlock(other.text, 0.4, [100, 250, 800, 290])
    elif boundary == "new_item":
        other = OCRBlock("2. 错误条目", 0.4, other.bbox)
    elif boundary == "sentence_end":
        first = OCRBlock("第一段内容。", 0.99, first.bbox)
    else:
        first = OCRBlock(first.text, 0.99, [100, 60, 800, 140])
    assessment = _same_layout([first, other])
    assert assessment.safe_text == first.text
    assert assessment.blocks[0]["paragraph_id"] != assessment.blocks[1]["paragraph_id"]


@pytest.mark.parametrize("top,bottom", [
    ("基底压力呈梯形分布时，基底附加", "压力pomax，P0min为"),
    ("破坏振", "次1gNf"),
])
def test_real_problem_fragments_are_rejected_as_complete_source_groups(top, bottom):
    # These source lines were inspected on PDF pages 160 and 400. No phrase
    # blacklist is used by production grouping, only their geometric proximity.
    assessment = _same_layout([
        OCRBlock(top, 0.999, [100, 600, 700, 640]),
        OCRBlock(bottom, 0.8, [100, 638, 500, 686]),
    ])
    assert assessment.safe_text == ""
    assert all(block["decision"] == "rejected" for block in assessment.blocks)
    assert assessment.blocks[0]["paragraph_id"] == assessment.blocks[1]["paragraph_id"]


def test_every_paragraph_has_an_atomic_final_decision():
    assessment = _same_layout([
        OCRBlock("第一行", 0.99, [100, 100, 800, 140]),
        OCRBlock("不可靠行", 0.5, [100, 148, 800, 188]),
        OCRBlock("另一独立段落。", 0.99, [100, 400, 800, 440]),
    ])
    for paragraph_id in {block["paragraph_id"] for block in assessment.blocks}:
        group = [block for block in assessment.blocks if block["paragraph_id"] == paragraph_id]
        assert len({block["decision"] for block in group}) == 1


def test_page_400_source_geometry_groups_inline_formula_and_wrapped_axis_label():
    # Frozen bounding boxes from the retained 20-page evaluation, page 400.
    source = [
        ("10.1土的动强度与砂土的振动液化", [0.041471, 0.015115, 0.420693, 0.053204], True),
        ("do的一半)", [0.7469, 0.088875, 0.863189, 0.14208], False),
        ("d（即动应力幅", [0.580162, 0.091294, 0.742625, 0.14208], False),
        ("动强度曲线：试件45°面上的动剪应力", [0.177854, 0.093712, 0.566481, 0.136034], True),
        ("do/2 ₃与破坏振次Nf间的曲线", [0.309106, 0.135429, 0.624198, 0.192866], False),
        ("或动应力比", [0.179991, 0.143289, 0.301838, 0.182588], True),
        ("破坏振", [0.741342, 0.677146, 0.815733, 0.71705], True),
        ("次1gNf", [0.739205, 0.711608, 0.826849, 0.766626], False),
    ]
    records = [{
        "text": text, "bbox": box, "kind": "text",
        "decision": "accepted" if accepted else "rejected",
        "reasons": [] if accepted else ["ocr_low_confidence"],
    } for text, box, accepted in source]
    safe_text = apply_paragraph_gate(records, image_size=(2339, 1654))
    assert safe_text == source[0][0]
    assert len({block["paragraph_id"] for block in records[1:6]}) == 1
    assert records[6]["paragraph_id"] == records[7]["paragraph_id"]
    assert records[6]["paragraph_id"] != records[1]["paragraph_id"]
