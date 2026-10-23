# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.
import io
import logging
from datetime import datetime
from typing import Sequence
from zoneinfo import ZoneInfo

import pandas as pd
from fpdf import FPDF
from fpdf.enums import XPos, YPos
from fpdf.fonts import FontFace
from PIL import Image

logger = logging.getLogger(__name__)

# datetime.now() is naive server-local time -- in a container that's
# whatever the OS clock is set to (normally UTC/GMT), regardless of the
# CELERY_CONFIG timezone (that setting only governs Celery beat/worker
# scheduling, not this request-time code). Convert explicitly so the PDF
# always shows IST no matter what the host clock is.
_IST = ZoneInfo("Asia/Kolkata")

# A4 landscape usable width in mm (297 page width - 2*10 margin).
_PAGE_WIDTH_MM = 277.0
_MIN_COL_WIDTH_MM = 18.0

_ATTRIBUTION_TEXT = (
    "Website Content Managed by Municipal Corporation of Delhi ,Web "
    "Information Manager Designed, Developed and Hosted by National "
    "Informatics Center( NIC ), Ministry of Electronics & IT (MeitY)"
)


class _ReportPDF(FPDF):
    """FPDF with a two-line footer on every page: the mandatory
    attribution line (kept on one line, shrinking its font until it fits
    rather than wrapping), then the page number."""

    def footer(self) -> None:
        self.set_y(-18)

        # Shrink the font just enough that the whole attribution string
        # fits on a single line at the page's usable width -- a fixed
        # font size would either wrap (user explicitly doesn't want that)
        # or get clipped once the exact string length changes.
        font_size = 7.0
        self.set_font("Helvetica", "", font_size)
        while (
            self.get_string_width(_ATTRIBUTION_TEXT) > _PAGE_WIDTH_MM
            and font_size > 4.0
        ):
            font_size -= 0.5
            self.set_font("Helvetica", "", font_size)
        self.cell(0, 5, _ATTRIBUTION_TEXT, align="C")

        self.set_y(-12)
        self.set_font("Helvetica", "I", 8)
        self.cell(0, 8, f"Page {self.page_no()} of {{nb}}", align="C")


def build_pdf_from_screenshots(screenshots: Sequence[bytes]) -> bytes:
    """
    Combine one or more screenshot images (e.g. dashboard/chart PNGs) into
    a single PDF, one page per image, each page sized to match that
    image's own dimensions/aspect ratio.
    """
    pdf = FPDF(unit="pt")
    pdf.set_auto_page_break(auto=False)
    for screenshot in screenshots:
        width, height = Image.open(io.BytesIO(screenshot)).size
        pdf.add_page(format=(width, height))
        pdf.image(io.BytesIO(screenshot), x=0, y=0, w=width, h=height)
    return bytes(pdf.output())


def _build_header(
    pdf: FPDF,
    chart_name: str,
    dashboard_name: str | None,
    filters: list[str] | None,
) -> None:
    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 10, chart_name, new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    pdf.set_font("Helvetica", "", 10)
    if dashboard_name:
        pdf.cell(
            0, 6, f"Dashboard: {dashboard_name}", new_x=XPos.LMARGIN, new_y=YPos.NEXT
        )
    pdf.cell(
        0,
        6,
        f"Generated: {datetime.now(_IST).strftime('%Y-%m-%d %H:%M')} IST",
        new_x=XPos.LMARGIN,
        new_y=YPos.NEXT,
    )
    # Every applied filter (time range, adhoc, dashboard native filters) on
    # its own line, via multi_cell so a long one wraps instead of being
    # silently clipped (plain cell() doesn't wrap). Without this, a
    # downloaded PDF has no record of what data it actually shows once
    # separated from the dashboard.
    if filters:
        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(0, 6, "Filters applied:", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_font("Helvetica", "", 9)
        for flt in filters:
            # "-" not "•" -- the core Helvetica font is latin-1 only, and a
            # bullet character crashes multi_cell() with
            # FPDFUnicodeEncodingException on every export that has filters.
            pdf.multi_cell(0, 5, f"  - {flt}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(4)


def _render_table(
    pdf: FPDF, df: pd.DataFrame, font_size: int, max_cell_len: int
) -> None:
    pdf.set_font("Helvetica", "", font_size)

    def _cell_text(value: object) -> str:
        text = str(value)
        return text if len(text) <= max_cell_len else f"{text[:max_cell_len]}..."

    num_cols = max(len(df.columns), 1)
    # Give every column a share of the page proportional to its own content
    # length (so short columns like "Status" don't take the same width as
    # "Applicant Address"), within a sane min/max per column.
    sample = pd.concat([df.head(50), df.columns.to_frame().T]) if len(df) else df
    raw_widths = [
        max((len(str(v)) for v in sample[col]), default=len(str(col)))
        for col in df.columns
    ]
    total_raw = sum(raw_widths) or num_cols
    col_widths = [
        min(max(_PAGE_WIDTH_MM * w / total_raw, _MIN_COL_WIDTH_MM), _PAGE_WIDTH_MM / 2)
        for w in raw_widths
    ]
    # Normalize so columns always sum to exactly the usable page width.
    scale = _PAGE_WIDTH_MM / sum(col_widths)
    col_widths = [w * scale for w in col_widths]

    header = [_cell_text(col) for col in df.columns]
    rows = [[_cell_text(cell) for cell in row] for row in df.values.tolist()]
    header_style = FontFace(emphasis="B")
    with pdf.table(text_align="LEFT", col_widths=col_widths) as table:
        table_row = table.row()
        for cell in header:
            table_row.cell(cell, style=header_style)
        for row in rows:
            table_row = table.row()
            for cell in row:
                table_row.cell(cell)


def df_to_pdf(
    df: pd.DataFrame,
    chart_name: str = "chart",
    dashboard_name: str | None = None,
    filters: list[str] | None = None,
) -> bytes:
    """
    Render a DataFrame as a text-based (not screenshot) landscape PDF: a
    header with the chart name, dashboard name, every applied filter, and
    today's date, followed by the data as a table, with "Page X of Y" on
    every page. Column widths and font size scale down as column count
    grows, so a wide table (many columns) still fits readably instead of
    wrapping every cell onto its own page.
    """
    num_cols = max(len(df.columns), 1)
    # More columns -> smaller font, so each column keeps enough width to
    # avoid heavy wrapping (which is what previously produced ~1-2 rows
    # per page even for small datasets).
    if num_cols <= 8:
        font_size = 9
    elif num_cols <= 14:
        font_size = 8
    elif num_cols <= 20:
        font_size = 7
    else:
        font_size = 6

    # Cap each cell at roughly 3 wrapped lines' worth of text for the
    # chosen font size, so one long address/remark can't blow a row's
    # height past a full page -- that's what previously crashed the
    # export (fpdf2 can't paginate a single oversized row) and surfaced
    # as the 500 on large-text exports.
    max_cell_len = max(20, int((_PAGE_WIDTH_MM / num_cols) * 3))

    def _new_pdf() -> _ReportPDF:
        pdf = _ReportPDF(orientation="L", unit="mm", format="A4")
        pdf.alias_nb_pages()  # resolves "{nb}" in footer() to the final page count
        pdf.set_auto_page_break(auto=True, margin=22)  # room for 2-line footer
        pdf.add_page()
        _build_header(pdf, chart_name, dashboard_name, filters)
        return pdf

    pdf = _new_pdf()
    try:
        _render_table(pdf, df, font_size, max_cell_len)
    except Exception:
        # Pathological row (unusually long single value even after the
        # cap above) -- retry once with a much smaller font and a harder
        # truncation instead of 500ing the whole export.
        logger.warning(
            "df_to_pdf: table render failed at font_size=%s, retrying smaller",
            font_size,
            exc_info=True,
        )
        pdf = _new_pdf()
        _render_table(pdf, df, font_size=5, max_cell_len=25)

    return bytes(pdf.output())
