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
from datetime import datetime
from typing import Sequence

import pandas as pd
from fpdf import FPDF
from fpdf.enums import XPos, YPos
from fpdf.fonts import FontFace
from PIL import Image


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


def df_to_pdf(
    df: pd.DataFrame,
    chart_name: str = "chart",
    dashboard_name: str | None = None,
) -> bytes:
    """
    Render a DataFrame as a text-based (not screenshot) landscape PDF: a
    header with the chart name, dashboard name, and today's date, followed
    by the data as a table. Paginates automatically for large result sets.
    """
    pdf = FPDF(orientation="L", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 10, chart_name, new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    pdf.set_font("Helvetica", "", 10)
    if dashboard_name:
        pdf.cell(
            0,
            6,
            f"Dashboard: {dashboard_name}",
            new_x=XPos.LMARGIN,
            new_y=YPos.NEXT,
        )
    pdf.cell(
        0,
        6,
        f"Generated: {datetime.now().strftime('%Y-%m-%d')}",
        new_x=XPos.LMARGIN,
        new_y=YPos.NEXT,
    )
    pdf.ln(4)

    pdf.set_font("Helvetica", "", 8)

    # Truncate oversized cell values (e.g. raw dict/JSON dumps) -- a cell
    # long enough to wrap past a full page height makes fpdf2's table
    # renderer raise rather than paginate.
    max_cell_len = 200

    def _cell_text(value: object) -> str:
        text = str(value)
        return text if len(text) <= max_cell_len else f"{text[:max_cell_len]}..."

    header = [_cell_text(col) for col in df.columns]
    rows = [[_cell_text(cell) for cell in row] for row in df.values.tolist()]
    header_style = FontFace(emphasis="B")
    with pdf.table(text_align="LEFT") as table:
        table_row = table.row()
        for cell in header:
            table_row.cell(cell, style=header_style)
        for row in rows:
            table_row = table.row()
            for cell in row:
                table_row.cell(cell)

    return bytes(pdf.output())
