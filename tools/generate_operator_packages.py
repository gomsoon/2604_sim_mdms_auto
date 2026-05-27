#!/usr/bin/env python3
"""
Generate DOCX and PPTX operator-manual package files from the Markdown sources.

The generated PPTX is a training draft with text-first slide content and
screen-capture placeholders. It is intended to be refined later with actual UI
captures.
"""

from __future__ import annotations

import argparse
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
import re
from xml.sax.saxutils import escape


ROOT = Path(__file__).resolve().parents[1]
DOCS_DIR = ROOT / "docs"
GENERATED_DIR = DOCS_DIR / "generated"
SCREEN_DIR = GENERATED_DIR / "screens"

MANUAL_MD = DOCS_DIR / "mdms-preproduct-operator-manual.md"
SLIDE_MD = DOCS_DIR / "mdms-preproduct-operator-slide-outline.md"
OUTPUT_HTML = GENERATED_DIR / "mdms-preproduct-operator-manual.html"
OUTPUT_DOCX = GENERATED_DIR / "mdms-preproduct-operator-manual.docx"
OUTPUT_PPTX = GENERATED_DIR / "mdms-preproduct-operator-training-draft.pptx"
OUTPUT_PPTX_V2 = GENERATED_DIR / "mdms-preproduct-operator-training-v2.pptx"


@dataclass
class SlideScreen:
    filename: str
    caption: str


SLIDE_SCREEN_MAP: dict[int, list[SlideScreen]] = {
    1: [SlideScreen("02-dashboard-normal.png", "운영 시작 기준 화면")],
    2: [SlideScreen("02-dashboard-normal.png", "시스템 전반 요약")],
    3: [SlideScreen("01-login.png", "운영자 로그인 진입점")],
    4: [SlideScreen("15-replay-request-detail.png", "진행 중 요청 확인 예시")],
    5: [SlideScreen("03-dashboard-attention.png", "우선 확인 대상이 있는 대시보드")],
    6: [
        SlideScreen("04-hes-detail.png", "HES 상세"),
        SlideScreen("05-adapter-detail.png", "어댑터 상세"),
    ],
    7: [SlideScreen("06-master-data.png", "기본 마스터 데이터와 actor visibility")],
    8: [
        SlideScreen("07-raw-reads.png", "원시 검침 가시성"),
        SlideScreen("09-final-measurements.png", "최종 계측 가시성"),
    ],
    9: [
        SlideScreen("10-vee-exception-queue.png", "VEE 예외 큐"),
        SlideScreen("11-vee-exception-detail.png", "VEE 예외 상세"),
    ],
    10: [
        SlideScreen("12-estimation-audit-detail.png", "추정 감사 상세"),
        SlideScreen("13-manual-edit-audit-detail.png", "수동 보정 감사 상세"),
    ],
    11: [
        SlideScreen("15-replay-request-detail.png", "재평가 요청 상세"),
        SlideScreen("17-billing-export-request-detail.png", "청구 내보내기 요청 상세"),
    ],
    12: [
        SlideScreen("18-operational-event-detail.png", "운영 이벤트 조치 스냅샷"),
        SlideScreen("06-master-data.png", "관리 row actor visibility"),
    ],
    13: [
        SlideScreen("03-dashboard-attention.png", "주의 필요 대시보드"),
        SlideScreen("05-adapter-detail.png", "런타임 점검 예시"),
    ],
    14: [SlideScreen("02-dashboard-normal.png", "일일 마감 기준 화면")],
}


def clean_inline(text: str) -> str:
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1 (\2)", text)
    text = text.replace("`", "")
    text = text.replace("**", "")
    text = re.sub(r"(?<!\*)\*(?!\*)(.*?)\*(?!\*)", r"\1", text)
    return text.strip()


@dataclass
class ManualBlock:
    kind: str
    text: str = ""
    level: int = 0
    indent: int = 0


def parse_manual_blocks(path: Path) -> list[ManualBlock]:
    lines = path.read_text(encoding="utf-8").splitlines()
    blocks: list[ManualBlock] = []
    paragraph: list[str] = []
    in_code = False
    code_lines: list[str] = []

    def flush_paragraph() -> None:
        nonlocal paragraph
        if paragraph:
            blocks.append(ManualBlock(kind="paragraph", text=clean_inline(" ".join(paragraph))))
            paragraph = []

    def flush_code() -> None:
        nonlocal code_lines
        if code_lines:
            for line in code_lines:
                blocks.append(ManualBlock(kind="code", text=line))
            code_lines = []

    for raw in lines:
        line = raw.rstrip("\n")
        if line.strip().startswith("```"):
            flush_paragraph()
            if in_code:
                flush_code()
                in_code = False
            else:
                in_code = True
            continue

        if in_code:
            code_lines.append(line)
            continue

        if not line.strip():
            flush_paragraph()
            blocks.append(ManualBlock(kind="blank"))
            continue

        heading = re.match(r"^(#{1,6})\s+(.*)$", line)
        if heading:
            flush_paragraph()
            blocks.append(
                ManualBlock(
                    kind="heading",
                    text=clean_inline(heading.group(2)),
                    level=len(heading.group(1)),
                )
            )
            continue

        bullet = re.match(r"^(\s*)-\s+(.*)$", line)
        if bullet:
            flush_paragraph()
            blocks.append(
                ManualBlock(
                    kind="bullet",
                    text=clean_inline(bullet.group(2)),
                    indent=len(bullet.group(1)) // 2,
                )
            )
            continue

        number = re.match(r"^(\s*)(\d+)\.\s+(.*)$", line)
        if number:
            flush_paragraph()
            blocks.append(
                ManualBlock(
                    kind="number",
                    text=f"{number.group(2)}. {clean_inline(number.group(3))}",
                    indent=len(number.group(1)) // 2,
                )
            )
            continue

        paragraph.append(line.strip())

    flush_paragraph()
    flush_code()
    return blocks


@dataclass
class Slide:
    title: str
    body_lines: list[str] = field(default_factory=list)
    visual_lines: list[str] = field(default_factory=list)


def parse_slide_outline(path: Path) -> list[Slide]:
    lines = path.read_text(encoding="utf-8").splitlines()
    slides: list[Slide] = []
    current: Slide | None = None
    mode = "body"

    for raw in lines:
        line = raw.rstrip("\n")
        slide_heading = re.match(r"^##\s+(Slide\s+\d+\.\s+.*)$", line)
        if slide_heading:
            current = Slide(title=clean_inline(slide_heading.group(1)))
            slides.append(current)
            mode = "body"
            continue

        if current is None:
            continue

        if line.startswith("- "):
            text = clean_inline(line[2:])
            if text.lower() == "suggested visual":
                mode = "visual"
            else:
                mode = "body"
                current.body_lines.append(f"• {text}")
            continue

        if line.startswith("  - "):
            text = clean_inline(line[4:])
            if mode == "visual":
                current.visual_lines.append(f"• {text}")
            else:
                current.body_lines.append(f"  - {text}")
            continue

        if line.strip():
            current.body_lines.append(clean_inline(line.strip()))

    return slides


def xml_text(text: str) -> str:
    if text.startswith(" ") or text.endswith(" "):
        return f'<w:t xml:space="preserve">{escape(text)}</w:t>'
    return f"<w:t>{escape(text)}</w:t>"


def docx_run(text: str, *, bold: bool = False, size: int = 22, mono: bool = False) -> str:
    font_xml = (
        '<w:rFonts w:ascii="Consolas" w:hAnsi="Consolas" w:eastAsia="Consolas"/>'
        if mono
        else ""
    )
    bold_xml = "<w:b/>" if bold else ""
    return (
        "<w:r>"
        f"<w:rPr>{font_xml}{bold_xml}<w:sz w:val=\"{size}\"/><w:szCs w:val=\"{size}\"/></w:rPr>"
        f"{xml_text(text)}"
        "</w:r>"
    )


def docx_paragraph(text: str, *, bold: bool = False, size: int = 22, mono: bool = False) -> str:
    return f"<w:p>{docx_run(text, bold=bold, size=size, mono=mono)}</w:p>"


def build_docx_document(blocks: list[ManualBlock]) -> str:
    body_parts: list[str] = []
    title_used = False

    for block in blocks:
        if block.kind == "blank":
            body_parts.append("<w:p/>")
            continue

        if block.kind == "heading":
            if block.level == 1 and not title_used:
                body_parts.append(docx_paragraph(block.text, bold=True, size=36))
                title_used = True
            elif block.level == 2:
                body_parts.append(docx_paragraph(block.text, bold=True, size=28))
            elif block.level == 3:
                body_parts.append(docx_paragraph(block.text, bold=True, size=24))
            else:
                body_parts.append(docx_paragraph(block.text, bold=True, size=22))
            continue

        if block.kind == "paragraph":
            body_parts.append(docx_paragraph(block.text, size=22))
            continue

        if block.kind == "bullet":
            prefix = "  " * block.indent + "• "
            body_parts.append(docx_paragraph(prefix + block.text, size=22))
            continue

        if block.kind == "number":
            prefix = "  " * block.indent
            body_parts.append(docx_paragraph(prefix + block.text, size=22))
            continue

        if block.kind == "code":
            body_parts.append(docx_paragraph(block.text, size=20, mono=True))
            continue

    sect_pr = (
        "<w:sectPr>"
        '<w:pgSz w:w="12240" w:h="15840"/>'
        '<w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440" '
        'w:header="720" w:footer="720" w:gutter="0"/>'
        "</w:sectPr>"
    )
    body_xml = "".join(body_parts) + sect_pr
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body>{body_xml}</w:body>"
        "</w:document>"
    )


def build_docx_package(blocks: list[ManualBlock], out_path: Path) -> None:
    created = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    document_xml = build_docx_document(blocks)
    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/word/document.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
        '<Override PartName="/docProps/core.xml" '
        'ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>'
        '<Override PartName="/docProps/app.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>'
        "</Types>"
    )
    rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
        'Target="word/document.xml"/>'
        '<Relationship Id="rId2" '
        'Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" '
        'Target="docProps/core.xml"/>'
        '<Relationship Id="rId3" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" '
        'Target="docProps/app.xml"/>'
        "</Relationships>"
    )
    core = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<cp:coreProperties '
        'xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
        'xmlns:dc="http://purl.org/dc/elements/1.1/" '
        'xmlns:dcterms="http://purl.org/dc/terms/" '
        'xmlns:dcmitype="http://purl.org/dc/dcmitype/" '
        'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
        "<dc:title>MDMS Preproduct Operator Manual</dc:title>"
        "<dc:creator>OpenAI Codex</dc:creator>"
        "<cp:lastModifiedBy>OpenAI Codex</cp:lastModifiedBy>"
        f'<dcterms:created xsi:type="dcterms:W3CDTF">{created}</dcterms:created>'
        f'<dcterms:modified xsi:type="dcterms:W3CDTF">{created}</dcterms:modified>'
        "</cp:coreProperties>"
    )
    app = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" '
        'xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">'
        "<Application>OpenAI Codex</Application>"
        "</Properties>"
    )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", content_types)
        zf.writestr("_rels/.rels", rels)
        zf.writestr("word/document.xml", document_xml)
        zf.writestr("docProps/core.xml", core)
        zf.writestr("docProps/app.xml", app)


def build_html_manual(blocks: list[ManualBlock], out_path: Path) -> None:
    parts: list[str] = [
        "<!DOCTYPE html>",
        '<html lang="ko">',
        "<head>",
        '<meta charset="utf-8"/>',
        "<title>MDMS Preproduct Operator Manual</title>",
        "<style>",
        "body{font-family:'Noto Sans CJK KR','Malgun Gothic',sans-serif;max-width:980px;margin:40px auto;padding:0 24px;line-height:1.6;color:#111827;}",
        "h1,h2,h3,h4{color:#0f172a;}",
        "pre{background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:12px;overflow:auto;}",
        "code{font-family:'Liberation Mono','Consolas',monospace;}",
        "ul,ol{margin:0 0 14px 24px;}",
        "p{margin:0 0 14px 0;}",
        "</style>",
        "</head>",
        "<body>",
    ]

    list_mode: str | None = None

    def close_list() -> None:
        nonlocal list_mode
        if list_mode == "ul":
            parts.append("</ul>")
        elif list_mode == "ol":
            parts.append("</ol>")
        list_mode = None

    for block in blocks:
        if block.kind == "blank":
            close_list()
            continue

        if block.kind == "heading":
            close_list()
            level = max(1, min(block.level, 4))
            parts.append(f"<h{level}>{escape(block.text)}</h{level}>")
            continue

        if block.kind == "paragraph":
            close_list()
            parts.append(f"<p>{escape(block.text)}</p>")
            continue

        if block.kind == "code":
            close_list()
            parts.append(f"<pre><code>{escape(block.text)}</code></pre>")
            continue

        if block.kind == "bullet":
            if list_mode != "ul":
                close_list()
                parts.append("<ul>")
                list_mode = "ul"
            parts.append(f"<li>{escape(block.text)}</li>")
            continue

        if block.kind == "number":
            if list_mode != "ol":
                close_list()
                parts.append("<ol>")
                list_mode = "ol"
            numbered_text = re.sub(r'^\d+\.\s+', "", block.text)
            parts.append(f"<li>{escape(numbered_text)}</li>")
            continue

    close_list()
    parts.extend(["</body>", "</html>"])
    out_path.write_text("\n".join(parts), encoding="utf-8")


def pptx_text_runs(text: str, *, size: int = 2000, bold: bool = False) -> str:
    lines = text.splitlines() or [text]
    paragraphs: list[str] = []
    for line in lines:
        if not line:
            paragraphs.append('<a:p><a:endParaRPr lang="ko-KR"/></a:p>')
            continue
        bold_xml = ' b="1"' if bold else ""
        paragraphs.append(
            "<a:p>"
            f'<a:r><a:rPr lang="ko-KR" sz="{size}"{bold_xml}/><a:t>{escape(line)}</a:t></a:r>'
            '<a:endParaRPr lang="ko-KR"/>'
            "</a:p>"
        )
    return "".join(paragraphs)


def pptx_shape(
    shape_id: int,
    name: str,
    x: int,
    y: int,
    cx: int,
    cy: int,
    text: str,
    *,
    font_size: int = 1800,
    bold: bool = False,
    fill: str | None = None,
    line: str | None = None,
) -> str:
    fill_xml = f'<a:solidFill><a:srgbClr val="{fill}"/></a:solidFill>' if fill else "<a:noFill/>"
    line_xml = (
        f'<a:ln w="12700"><a:solidFill><a:srgbClr val="{line}"/></a:solidFill></a:ln>'
        if line
        else "<a:ln><a:noFill/></a:ln>"
    )
    return (
        "<p:sp>"
        "<p:nvSpPr>"
        f'<p:cNvPr id="{shape_id}" name="{escape(name)}"/>'
        '<p:cNvSpPr txBox="1"/>'
        "<p:nvPr/>"
        "</p:nvSpPr>"
        "<p:spPr>"
        f'<a:xfrm><a:off x="{x}" y="{y}"/><a:ext cx="{cx}" cy="{cy}"/></a:xfrm>'
        '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom>'
        f"{fill_xml}{line_xml}"
        "</p:spPr>"
        "<p:txBody>"
        '<a:bodyPr wrap="square"/>'
        "<a:lstStyle/>"
        f"{pptx_text_runs(text, size=font_size, bold=bold)}"
        "</p:txBody>"
        "</p:sp>"
    )


def _read_png_dimensions(path: Path) -> tuple[int, int]:
    raw = path.read_bytes()
    if raw[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError(f"Unsupported image format for PPTX embedding: {path}")
    width = int.from_bytes(raw[16:20], "big")
    height = int.from_bytes(raw[20:24], "big")
    return width, height


def _fit_image_into_box(
    *,
    width_px: int,
    height_px: int,
    box_x: int,
    box_y: int,
    box_cx: int,
    box_cy: int,
) -> tuple[int, int, int, int]:
    scale = min(box_cx / width_px, box_cy / height_px)
    scaled_cx = max(1, int(width_px * scale))
    scaled_cy = max(1, int(height_px * scale))
    scaled_x = box_x + max(0, (box_cx - scaled_cx) // 2)
    scaled_y = box_y + max(0, (box_cy - scaled_cy) // 2)
    return scaled_x, scaled_y, scaled_cx, scaled_cy


def pptx_picture(
    shape_id: int,
    name: str,
    x: int,
    y: int,
    cx: int,
    cy: int,
    rel_id: str,
) -> str:
    return (
        "<p:pic>"
        "<p:nvPicPr>"
        f'<p:cNvPr id="{shape_id}" name="{escape(name)}"/>'
        '<p:cNvPicPr><a:picLocks noChangeAspect="1"/></p:cNvPicPr>'
        "<p:nvPr/>"
        "</p:nvPicPr>"
        "<p:blipFill>"
        f'<a:blip r:embed="{rel_id}"/>'
        "<a:stretch><a:fillRect/></a:stretch>"
        "</p:blipFill>"
        "<p:spPr>"
        f'<a:xfrm><a:off x="{x}" y="{y}"/><a:ext cx="{cx}" cy="{cy}"/></a:xfrm>'
        '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom>'
        "</p:spPr>"
        "</p:pic>"
    )


def _build_visual_elements(visuals: list[dict[str, object]], *, start_shape_id: int) -> tuple[list[str], int]:
    if not visuals:
        return [], start_shape_id

    visual_x = 4343400
    visual_y = 1600200
    visual_cx = 7391400
    visual_cy = 4572000
    gap = 228600
    caption_cy = 342900
    elements: list[str] = []
    shape_id = start_shape_id

    if len(visuals) == 1:
        visual = visuals[0]
        image_box_y = visual_y + caption_cy + 114300
        image_box_cy = visual_cy - caption_cy - 114300
        elements.append(
            pptx_shape(
                shape_id,
                f"Caption {shape_id}",
                visual_x,
                visual_y,
                visual_cx,
                caption_cy,
                str(visual["caption"]),
                font_size=1500,
                bold=True,
            )
        )
        shape_id += 1
        x, y, cx, cy = _fit_image_into_box(
            width_px=int(visual["width_px"]),
            height_px=int(visual["height_px"]),
            box_x=visual_x,
            box_y=image_box_y,
            box_cx=visual_cx,
            box_cy=image_box_cy,
        )
        elements.append(pptx_picture(shape_id, str(visual["filename"]), x, y, cx, cy, str(visual["rel_id"])))
        shape_id += 1
        return elements, shape_id

    group_cy = (visual_cy - gap) // 2
    image_box_cy = group_cy - caption_cy - 114300
    for index, visual in enumerate(visuals[:2]):
        group_y = visual_y + index * (group_cy + gap)
        elements.append(
            pptx_shape(
                shape_id,
                f"Caption {shape_id}",
                visual_x,
                group_y,
                visual_cx,
                caption_cy,
                str(visual["caption"]),
                font_size=1400,
                bold=True,
            )
        )
        shape_id += 1
        x, y, cx, cy = _fit_image_into_box(
            width_px=int(visual["width_px"]),
            height_px=int(visual["height_px"]),
            box_x=visual_x,
            box_y=group_y + caption_cy + 114300,
            box_cx=visual_cx,
            box_cy=image_box_cy,
        )
        elements.append(pptx_picture(shape_id, str(visual["filename"]), x, y, cx, cy, str(visual["rel_id"])))
        shape_id += 1
    return elements, shape_id


def build_slide_xml(slide: Slide, *, visuals: list[dict[str, object]] | None = None) -> str:
    body = "\n".join(slide.body_lines) if slide.body_lines else "• 본문 요약을 여기에 추가"
    visual = "\n".join(slide.visual_lines) if slide.visual_lines else "• representative UI screen capture goes here"
    visuals = visuals or []
    shapes = [
        pptx_shape(2, "Title", 457200, 274320, 10363200, 1143000, slide.title, font_size=2600, bold=True),
        pptx_shape(3, "Body", 457200, 1600200, 3429000, 4572000, body, font_size=1700),
    ]
    if visuals:
        visual_elements, _ = _build_visual_elements(visuals, start_shape_id=4)
        shapes.extend(visual_elements)
    else:
        shapes.append(
            pptx_shape(
                4,
                "Visual Placeholder",
                4343400,
                1600200,
                7391400,
                4572000,
                "Screen Capture Placeholder\n\n" + visual,
                font_size=1600,
                fill="F8FAFC",
                line="CBD5E1",
            )
        )
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<p:sld xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
        'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">'
        "<p:cSld>"
        "<p:spTree>"
        "<p:nvGrpSpPr>"
        '<p:cNvPr id="1" name=""/>'
        "<p:cNvGrpSpPr/>"
        "<p:nvPr/>"
        "</p:nvGrpSpPr>"
        "<p:grpSpPr>"
        '<a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/><a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm>'
        "</p:grpSpPr>"
        + "".join(shapes) +
        "</p:spTree>"
        "</p:cSld>"
        '<p:clrMapOvr><a:overrideClrMapping '
        'bg1="lt1" tx1="dk1" bg2="lt2" tx2="dk2" accent1="accent1" accent2="accent2" '
        'accent3="accent3" accent4="accent4" accent5="accent5" accent6="accent6" '
        'hlink="hlink" folHlink="folHlink"/></p:clrMapOvr>'
        "</p:sld>"
    )


def build_slide_rels_xml(visuals: list[dict[str, object]]) -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        + "".join(
            f'<Relationship Id="{visual["rel_id"]}" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" '
            f'Target="../media/{visual["media_name"]}"/>'
            for visual in visuals
        )
        + "</Relationships>"
    )


def _resolve_slide_visuals(slide_index: int) -> list[dict[str, object]]:
    visuals: list[dict[str, object]] = []
    for item_index, screen in enumerate(SLIDE_SCREEN_MAP.get(slide_index, []), start=1):
        path = SCREEN_DIR / screen.filename
        if not path.exists():
            continue
        width_px, height_px = _read_png_dimensions(path)
        visuals.append(
            {
                "filename": screen.filename,
                "caption": screen.caption,
                "path": path,
                "width_px": width_px,
                "height_px": height_px,
                "rel_id": f"rId{item_index}",
            }
        )
    return visuals


def build_pptx_package(
    slides: list[Slide],
    out_path: Path,
    *,
    use_screens: bool = False,
) -> None:
    created = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    content_overrides = [
        '<Override PartName="/ppt/presentation.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml"/>',
        '<Override PartName="/docProps/core.xml" '
        'ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>',
        '<Override PartName="/docProps/app.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>',
    ]
    for idx in range(1, len(slides) + 1):
        content_overrides.append(
            f'<Override PartName="/ppt/slides/slide{idx}.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.presentationml.slide+xml"/>'
        )

    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Default Extension="png" ContentType="image/png"/>'
        + "".join(content_overrides) +
        "</Types>"
    )
    root_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
        'Target="ppt/presentation.xml"/>'
        '<Relationship Id="rId2" '
        'Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" '
        'Target="docProps/core.xml"/>'
        '<Relationship Id="rId3" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" '
        'Target="docProps/app.xml"/>'
        "</Relationships>"
    )

    slide_ids = []
    slide_rels = []
    for idx in range(1, len(slides) + 1):
        slide_ids.append(f'<p:sldId id="{255 + idx}" r:id="rId{idx}"/>')
        slide_rels.append(
            f'<Relationship Id="rId{idx}" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide" '
            f'Target="slides/slide{idx}.xml"/>'
        )

    presentation_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<p:presentation xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
        'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">'
        f"<p:sldIdLst>{''.join(slide_ids)}</p:sldIdLst>"
        '<p:sldSz cx="12192000" cy="6858000"/>'
        '<p:notesSz cx="6858000" cy="9144000"/>'
        "</p:presentation>"
    )
    presentation_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        + "".join(slide_rels) +
        "</Relationships>"
    )
    core = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<cp:coreProperties '
        'xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
        'xmlns:dc="http://purl.org/dc/elements/1.1/" '
        'xmlns:dcterms="http://purl.org/dc/terms/" '
        'xmlns:dcmitype="http://purl.org/dc/dcmitype/" '
        'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
        "<dc:title>MDMS Preproduct Operator Training Draft</dc:title>"
        "<dc:creator>OpenAI Codex</dc:creator>"
        "<cp:lastModifiedBy>OpenAI Codex</cp:lastModifiedBy>"
        f'<dcterms:created xsi:type="dcterms:W3CDTF">{created}</dcterms:created>'
        f'<dcterms:modified xsi:type="dcterms:W3CDTF">{created}</dcterms:modified>'
        "</cp:coreProperties>"
    )
    app = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" '
        'xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">'
        "<Application>OpenAI Codex</Application>"
        "<PresentationFormat>On-screen Show (16:9)</PresentationFormat>"
        f"<Slides>{len(slides)}</Slides>"
        "<Notes>0</Notes>"
        "<HiddenSlides>0</HiddenSlides>"
        "<MMClips>0</MMClips>"
        "</Properties>"
    )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    media_parts: dict[str, bytes] = {}
    with zipfile.ZipFile(out_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", content_types)
        zf.writestr("_rels/.rels", root_rels)
        zf.writestr("ppt/presentation.xml", presentation_xml)
        zf.writestr("ppt/_rels/presentation.xml.rels", presentation_rels)
        zf.writestr("docProps/core.xml", core)
        zf.writestr("docProps/app.xml", app)
        for idx, slide in enumerate(slides, start=1):
            visuals = _resolve_slide_visuals(idx) if use_screens else []
            for media_index, visual in enumerate(visuals, start=1):
                media_name = f"slide{idx}_image{media_index}.png"
                visual["media_name"] = media_name
                media_parts[media_name] = Path(visual["path"]).read_bytes()
            zf.writestr(f"ppt/slides/slide{idx}.xml", build_slide_xml(slide, visuals=visuals))
            if visuals:
                zf.writestr(f"ppt/slides/_rels/slide{idx}.xml.rels", build_slide_rels_xml(visuals))
        for media_name, payload in media_parts.items():
            zf.writestr(f"ppt/media/{media_name}", payload)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.parse_args()

    if not MANUAL_MD.exists():
        raise SystemExit(f"Missing manual source: {MANUAL_MD}")
    if not SLIDE_MD.exists():
        raise SystemExit(f"Missing slide source: {SLIDE_MD}")

    GENERATED_DIR.mkdir(parents=True, exist_ok=True)
    manual_blocks = parse_manual_blocks(MANUAL_MD)
    slide_blocks = parse_slide_outline(SLIDE_MD)
    build_html_manual(manual_blocks, OUTPUT_HTML)
    build_docx_package(manual_blocks, OUTPUT_DOCX)
    build_pptx_package(slide_blocks, OUTPUT_PPTX, use_screens=False)
    build_pptx_package(slide_blocks, OUTPUT_PPTX_V2, use_screens=True)

    print(f"Wrote {OUTPUT_HTML}")
    print(f"Wrote {OUTPUT_DOCX}")
    print(f"Wrote {OUTPUT_PPTX}")
    print(f"Wrote {OUTPUT_PPTX_V2}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
