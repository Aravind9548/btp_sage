"""Generate a PowerPoint slide deck for the BTP-7 Saga presentation.

Usage:
    python make_pptx.py
    Writes slides/btp7_saga_presentation.pptx
"""
from __future__ import annotations

import os
from pathlib import Path

from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.enum.shapes import MSO_SHAPE

SLIDES_DIR = Path("slides")
RESULTS_DIR = Path("results")
OUT = SLIDES_DIR / "btp7_saga_presentation.pptx"

BLUE = RGBColor(0x25, 0x63, 0xEB)
DARK = RGBColor(0x1A, 0x1A, 0x2E)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
MUTED = RGBColor(0x64, 0x74, 0x8B)
GREEN = RGBColor(0x05, 0x96, 0x69)
RED = RGBColor(0xDC, 0x26, 0x26)
BG = RGBColor(0xF8, 0xFA, 0xFC)


def add_bg(slide, color=BG):
    bg = slide.background
    fill = bg.fill
    fill.solid()
    fill.fore_color.rgb = color


def title_box(slide, text, top=Inches(0.4), left=Inches(0.5), width=Inches(9), size=Pt(28)):
    txBox = slide.shapes.add_textbox(left, top, width, Inches(0.6))
    tf = txBox.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.text = text
    p.font.size = size
    p.font.bold = True
    p.font.color.rgb = DARK
    return txBox


def body_text(slide, text, top=Inches(1.2), left=Inches(0.5), width=Inches(9), height=Inches(5), size=Pt(16)):
    txBox = slide.shapes.add_textbox(left, top, width, height)
    tf = txBox.text_frame
    tf.word_wrap = True
    for i, line in enumerate(text.split("\n")):
        if i == 0:
            p = tf.paragraphs[0]
        else:
            p = tf.add_paragraph()
        p.text = line
        p.font.size = size
        p.font.color.rgb = DARK
        p.space_after = Pt(6)
    return txBox


def add_image(slide, path, left=Inches(0.5), top=Inches(1.5), max_width=Inches(9), max_height=Inches(5)):
    if not path.exists():
        body_text(slide, f"[Image not found: {path}]", top=top)
        return
    from PIL import Image
    try:
        with Image.open(path) as img:
            w, h = img.size
    except Exception:
        slide.shapes.add_picture(str(path), left, top, max_width)
        return

    aspect = w / h
    target_w = max_width
    target_h = int(target_w / aspect)
    if target_h > max_height:
        target_h = max_height
        target_w = int(target_h * aspect)

    slide.shapes.add_picture(str(path), left, top, target_w, target_h)


def table_slide(slide, title, headers, rows, top=Inches(1.5)):
    title_box(slide, title)
    cols = len(headers)
    tbl_shape = slide.shapes.add_table(len(rows) + 1, cols, Inches(0.5), top, Inches(9), Inches(0.4 * (len(rows) + 1)))
    tbl = tbl_shape.table

    for j, h in enumerate(headers):
        cell = tbl.cell(0, j)
        cell.text = h
        for p in cell.text_frame.paragraphs:
            p.font.size = Pt(13)
            p.font.bold = True
            p.font.color.rgb = WHITE
        cell.fill.solid()
        cell.fill.fore_color.rgb = BLUE

    for i, row in enumerate(rows):
        for j, val in enumerate(row):
            cell = tbl.cell(i + 1, j)
            cell.text = str(val)
            for p in cell.text_frame.paragraphs:
                p.font.size = Pt(12)
                p.font.color.rgb = DARK


def build():
    prs = Presentation()
    prs.slide_width = Inches(10)
    prs.slide_height = Inches(7.5)
    blank = prs.slide_layouts[6]

    # --- Slide 1: Title ---
    s = prs.slides.add_slide(blank)
    add_bg(s, BLUE)
    title_box(s, "Saga Compensation Coordination\nin Microservices", top=Inches(2), size=Pt(36))
    for p in s.shapes[0].text_frame.paragraphs:
        p.font.color.rgb = WHITE
        p.alignment = PP_ALIGN.CENTER
    body_text(s, "B.Tech Project — 7th Semester\n\nComparing Orchestration, Choreography, and\nOn-Demand Election with Graph-Aware Scheduling",
              top=Inches(4), size=Pt(18))
    for p in s.shapes[1].text_frame.paragraphs:
        p.font.color.rgb = WHITE
        p.alignment = PP_ALIGN.CENTER

    # --- Slide 2: Problem Statement ---
    s = prs.slides.add_slide(blank)
    add_bg(s)
    title_box(s, "Problem Statement")
    body_text(s,
        "When a distributed saga fails, how should services coordinate compensation?\n\n"
        "Requirements:\n"
        "  1. Correctness — respect compensation dependency ordering\n"
        "  2. Performance — minimize total compensation time\n"
        "  3. Fault tolerance — handle orchestrator crashes\n"
        "  4. No permanent coordinator — avoid single point of failure\n\n"
        "Constraint: Payment compensation must finish before Notification starts\n"
        "(e.g., refund must complete before sending cancellation email)")

    # --- Slide 3: Three Approaches ---
    s = prs.slides.add_slide(blank)
    add_bg(s)
    title_box(s, "Three Coordination Strategies")
    table_slide(s, "Three Coordination Strategies",
        ["Strategy", "Mechanism", "Correct?", "Speed"],
        [
            ["Path A: Orchestration", "Central coordinator, sequential reverse", "Yes (100%)", "Slow — grows linearly"],
            ["Path B: Choreography", "All services react independently", "No (0%)", "Fast — parallel"],
            ["Path D: Election + Graph", "On-demand leader + DAG scheduler", "Yes (100%)", "Fast — parallel + correct"],
        ])

    # --- Slide 4: Path D Design ---
    s = prs.slides.add_slide(blank)
    add_bg(s)
    title_box(s, "Path D: How It Works")
    body_text(s,
        "1. Normal operation: pure choreography (no coordinator overhead)\n\n"
        "2. On failure detection: all services race to acquire a lease\n"
        "   • DynamoDB conditional write: attribute_not_exists(saga_id)\n"
        "   • Exactly one winner becomes temporary orchestrator\n\n"
        "3. Winner reads the compensation dependency graph (DAG)\n"
        "   • Independent steps run in parallel (Order + Payment)\n"
        "   • Dependent steps wait (Notification waits for Payment)\n\n"
        "4. Crash recovery: lease TTL expires → another service re-elects\n"
        "   • SagaStore tracks what's already compensated\n"
        "   • mark_compensated() returns False on duplicates → idempotent")

    # --- Slide 5: fig1 - Makespan vs Width ---
    s = prs.slides.add_slide(blank)
    add_bg(s)
    title_box(s, "Results: Makespan vs. DAG Width")
    add_image(s, SLIDES_DIR / "fig1_makespan_vs_width.png", top=Inches(1.3), max_height=Inches(5.5))

    # --- Slide 6: fig2 - Correctness ---
    s = prs.slides.add_slide(blank)
    add_bg(s)
    title_box(s, "Results: Correctness Rate")
    add_image(s, SLIDES_DIR / "fig2_correctness.png", top=Inches(1.3), max_height=Inches(5.5))

    # --- Slide 7: fig3 - Ablation ---
    s = prs.slides.add_slide(blank)
    add_bg(s)
    title_box(s, "Ablation: Scheduler vs. Election")
    add_image(s, SLIDES_DIR / "fig3_ablation.png", top=Inches(1.3), max_height=Inches(5.5))
    body_text(s, "Same election mechanism, different dispatch: LIFO grows linearly like Path A.\nThe graph-aware scheduler is what makes Path D fast, not the election.",
              top=Inches(6.5), size=Pt(12))

    # --- Slide 8: fig4 - Premium ---
    s = prs.slides.add_slide(blank)
    add_bg(s)
    title_box(s, "The Bounded Premium")
    add_image(s, SLIDES_DIR / "fig4_premium.png", top=Inches(1.3), max_height=Inches(5.5))

    # --- Slide 9: Summary Table ---
    s = prs.slides.add_slide(blank)
    add_bg(s)
    table_slide(s, "Summary of Results",
        ["Path", "Mean Makespan", "Correctness", "Overhead vs B"],
        [
            ["A: Orchestration", "1954.6 ms", "100%", "2.43x"],
            ["B: Choreography", "805.9 ms", "0%", "1.00x"],
            ["D: Election + Graph", "913.0 ms", "100%", "1.13x"],
            ["D-LIFO (ablation)", "grows with width", "100%", "~2x at width 8"],
        ])

    # --- Slide 10: Known-Answer Validation ---
    s = prs.slides.add_slide(blank)
    add_bg(s)
    table_slide(s, "Known-Answer Validation (Width=1, n=50)",
        ["Path", "Expected (ms)", "Measured (ms)", "Deviation"],
        [
            ["A: Orchestration", "1250", "1252.5", "0.2%"],
            ["B: Choreography", "800", "819.3", "2.4%"],
            ["D: Election + Graph", "900", "930.7", "3.4%"],
        ])
    body_text(s, "Deviations < 4% confirm the benchmark measures what it claims to measure.",
              top=Inches(4.5), size=Pt(14))

    # --- Slide 11: Cloud Validation ---
    s = prs.slides.add_slide(blank)
    add_bg(s)
    title_box(s, "Cloud Validation (LocalStack)")
    body_text(s,
        "Same coordination logic, cloud-backed infrastructure:\n\n"
        "• LeaseStore → DynamoDB conditional puts\n"
        "• SagaStore → DynamoDB String Sets (ADD operation)\n"
        "• EventBus → SNS topics + SQS queues\n"
        "• EventLog → DynamoDB composite key (saga_id + timestamp)\n\n"
        "Drop-in replacement pattern: zero changes to saga_bench/\n"
        "All path functions accept infrastructure via **kwargs\n\n"
        "Results on LocalStack:\n"
        "  ✓ Path D: correct (election + graph-aware dispatch works)\n"
        "  ✓ Crash recovery: lease TTL expiry + re-election works\n"
        "  ✓ Path A: correct (sequential compensation)\n"
        "  ✗ Path B: incorrect (ordering violation, as expected)\n\n"
        "No AWS credits needed — runs on Docker Desktop + LocalStack 3.8.1")

    # --- Slide 12: Related Work ---
    s = prs.slides.add_slide(blank)
    add_bg(s)
    title_box(s, "Related Work")
    table_slide(s, "Related Work",
        ["Work", "Approach", "Gap Path D Fills"],
        [
            ["Garcia-Molina & Salem (1987)", "Sagas in single DB", "No distributed coordination"],
            ["Rudrabhatla (2018)", "Orch vs. Choreo (binary)", "False dichotomy — D is hybrid"],
            ["Xue et al. (2021)", "Runtime consensus, no benchmarks", "We add election + DAG + crash recovery"],
            ["Aydın & Çebi (2022)", "Consistency with NoSQL", "No quantitative latency benchmark"],
        ])

    # --- Slide 13: Conclusion ---
    s = prs.slides.add_slide(blank)
    add_bg(s, BLUE)
    title_box(s, "Conclusion", size=Pt(36))
    for p in s.shapes[0].text_frame.paragraphs:
        p.font.color.rgb = WHITE
        p.alignment = PP_ALIGN.CENTER
    body_text(s,
        "Path D: On-demand election + graph-aware compensation scheduling\n\n"
        "• 100% correctness (same as orchestration)\n"
        "• ~13% premium over choreography (bounded, flat with DAG width)\n"
        "• Crash-tolerant via lease TTL + idempotent re-election\n"
        "• Validated on cloud infrastructure (DynamoDB + SNS/SQS)\n\n"
        "Key insight: the scheduler, not the election, is what matters\n"
        "(proven by LIFO ablation — same election, 194% slower at width 8)\n\n"
        "1,500+ runs · 4 sweeps · deterministic fault injection · cloud-validated",
        top=Inches(2.5), size=Pt(18))
    for p in s.shapes[1].text_frame.paragraphs:
        p.font.color.rgb = WHITE
        p.alignment = PP_ALIGN.CENTER

    prs.save(str(OUT))
    print(f"Saved {OUT} ({os.path.getsize(OUT) / 1024:.0f} KB)")


if __name__ == "__main__":
    build()
