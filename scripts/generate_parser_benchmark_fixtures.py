"""Generate domain-neutral parser fixtures under the ignored data directory.

The fixtures exercise native narrative, multi-column, table, and image-only
layouts. They are evaluation inputs; no expected value is imported by runtime
code.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


def _escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _native_pdf(pages: list[list[str]], output: Path) -> None:
    objects: list[bytes] = []
    page_object_ids = [4 + index * 2 for index in range(len(pages))]
    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    kids = " ".join(f"{number} 0 R" for number in page_object_ids)
    objects.append(f"<< /Type /Pages /Kids [{kids}] /Count {len(pages)} >>".encode())
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    for index, commands in enumerate(pages):
        page_id = page_object_ids[index]
        content_id = page_id + 1
        page = (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            f"/Resources << /Font << /F1 3 0 R >> >> /Contents {content_id} 0 R >>"
        ).encode()
        content = "\n".join(commands).encode("latin-1", errors="replace")
        stream = f"<< /Length {len(content)} >>\nstream\n".encode() + content + b"\nendstream"
        objects.extend((page, stream))
    payload = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for object_id, body in enumerate(objects, start=1):
        offsets.append(len(payload))
        payload.extend(f"{object_id} 0 obj\n".encode())
        payload.extend(body)
        payload.extend(b"\nendobj\n")
    xref = len(payload)
    payload.extend(f"xref\n0 {len(objects) + 1}\n".encode())
    payload.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        payload.extend(f"{offset:010d} 00000 n \n".encode())
    payload.extend(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    )
    output.write_bytes(payload)


def _text(x: int, y: int, value: str, size: int = 10) -> str:
    return f"BT /F1 {size} Tf {x} {y} Td ({_escape(value)}) Tj ET"


def _narrative_pages() -> list[list[str]]:
    pages = []
    for page in range(1, 19):
        lines = [
            _text(54, 742, f"Orchard Signal Systems — operating brief {page}", 16),
            _text(54, 708, "This independent validation document describes a sensor software business."),
            _text(54, 688, f"Annual recurring monitoring revenue reached ${18 + page} million in FY{25 + page % 2}."),
            _text(54, 668, f"Net device retention was {106 + page % 7} percent for the same reporting period."),
            _text(54, 648, f"The company appointed Regional Operations Lead {page} effective July {page}, 2026."),
        ]
        pages.append(lines)
    return pages


def _multicolumn_pages() -> list[list[str]]:
    pages = []
    for page in range(1, 13):
        pages.append(
            [
                _text(54, 744, f"Northwind Materials research circular {page}", 15),
                _text(54, 708, "MARKET REVIEW", 11),
                _text(54, 686, f"Composite demand expanded {5 + page / 10:.1f} percent year over year."),
                _text(54, 666, "Customers adopted lower-emission binder formulations."),
                _text(54, 646, f"Backlog ended the quarter at ${70 + page} million."),
                _text(318, 708, "OPERATIONS", 11),
                _text(318, 686, f"Nameplate capacity reached {240 + page * 5} thousand tonnes."),
                _text(318, 666, f"Plant utilization averaged {71 + page % 9} percent."),
                _text(318, 646, "A second kiln remained in scheduled maintenance."),
            ]
        )
    return pages


def _table_pages() -> list[list[str]]:
    pages = []
    for page in range(1, 9):
        commands = [
            _text(54, 744, f"Cobalt Harbor Manufacturing — site metrics {page}", 15),
            _text(62, 704, "Site"),
            _text(192, 704, "Capacity (units)"),
            _text(332, 704, "Utilization"),
            _text(442, 704, "Defect rate"),
        ]
        for row in range(6):
            y = 680 - row * 34
            commands.extend(
                [
                    _text(62, y, f"Facility {page}-{row + 1}"),
                    _text(192, y, str(10000 + page * 700 + row * 125)),
                    _text(332, y, f"{68 + (page + row) % 20}%"),
                    _text(442, y, f"{1 + (page + row) % 5 / 10:.1f}%"),
                ]
            )
        for y in range(654, 723, 34):
            commands.append(f"54 {y} m 558 {y} l S")
        for x in (54, 184, 324, 434, 558):
            commands.append(f"{x} 518 m {x} 722 l S")
        pages.append(commands)
    return pages


def _scanned_pdf(output: Path) -> None:
    font = ImageFont.load_default(size=22)
    pages = []
    for page in range(1, 4):
        image = Image.new("RGB", (1275, 1650), "white")
        draw = ImageDraw.Draw(image)
        draw.text((110, 110), f"Blue Mesa Clinical Logistics — scan {page}", fill="black", font=font)
        draw.text((110, 190), f"Temperature excursions fell to {3 + page} events in Q{page} 2026.", fill="black", font=font)
        draw.text((110, 250), f"Validated cold-storage capacity was {800 + page * 75} pallet positions.", fill="black", font=font)
        draw.text((110, 310), "This page intentionally has no native PDF text layer.", fill="black", font=font)
        pages.append(image)
    pages[0].save(output, "PDF", save_all=True, append_images=pages[1:], resolution=150)


def generate(output_dir: Path) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    outputs = [
        output_dir / "unseen-narrative.pdf",
        output_dir / "unseen-multicolumn.pdf",
        output_dir / "unseen-table-heavy.pdf",
        output_dir / "unseen-scanned.pdf",
    ]
    _native_pdf(_narrative_pages(), outputs[0])
    _native_pdf(_multicolumn_pages(), outputs[1])
    _native_pdf(_table_pages(), outputs[2])
    _scanned_pdf(outputs[3])
    return outputs


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("data/parser_benchmark"))
    args = parser.parse_args()
    for path in generate(args.output_dir):
        print(path)


if __name__ == "__main__":
    main()
