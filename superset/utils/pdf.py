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

import pandas as pd
from fpdf import FPDF
from fpdf.enums import XPos, YPos
from fpdf.fonts import FontFace
from PIL import Image

logger = logging.getLogger(__name__)

# A4 landscape usable width in mm (297 page width - 2*10 margin).
_PAGE_WIDTH_MM = 277.0
_MIN_COL_WIDTH_MM = 18.0


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
    pdf: FPDF, chart_name: str, dashboard_name: str | None, filters_text: str | None
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
        f"Generated: {datetime.now().strftime('%Y-%m-%d')}",
        new_x=XPos.LMARGIN,
        new_y=YPos.NEXT,
    )
    # Applied filters (date range / adhoc / dashboard filters) -- without
    # this, a downloaded PDF has no record of what data it actually shows.
    if filters_text:
        pdf.cell(
            0, 6, f"Filters: {filters_text}", new_x=XPos.LMARGIN, new_y=YPos.NEXT
        )
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
    filters_text: str | None = None,
) -> bytes:
    """
    Render a DataFrame as a text-based (not screenshot) landscape PDF: a
    header with the chart name, dashboard name, applied filters, and
    today's date, followed by the data as a table. Column widths and font
    size scale down as column count grows, so a wide table (many columns)
    still fits readably instead of wrapping every cell onto its own page.
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

    pdf = FPDF(orientation="L", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    _build_header(pdf, chart_name, dashboard_name, filters_text)

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
        pdf = FPDF(orientation="L", unit="mm", format="A4")
        pdf.set_auto_page_break(auto=True, margin=15)
        pdf.add_page()
        _build_header(pdf, chart_name, dashboard_name, filters_text)
        _render_table(pdf, df, font_size=5, max_cell_len=25)

    return bytes(pdf.output())
