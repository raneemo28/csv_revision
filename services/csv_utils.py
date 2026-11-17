"""CSV parsing for uploads. Raises ValueError with a message safe to show to the admin."""
import csv
import io
from typing import List, Tuple

MAX_COLUMNS = 500
csv.field_size_limit(2 ** 20)


def _clean(cell: str) -> str:
    # Browsers submit textarea line breaks as \r\n; store one style so edits compare correctly.
    return cell.replace("\r\n", "\n").replace("\r", "\n")


def parse_csv(raw: bytes) -> Tuple[List[str], List[List[str]]]:
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise ValueError(
            "The file must be UTF-8 encoded. In Excel, save it as "
            "'CSV UTF-8 (Comma delimited)' and upload it again."
        )

    first_line = text.split("\n", 1)[0]
    delimiter = max(",;\t", key=first_line.count)   # Excel in some regions uses ";"
    if first_line.count(delimiter) == 0:
        delimiter = ","

    try:
        rows = [
            r for r in csv.reader(io.StringIO(text, newline=""), delimiter=delimiter)
            if any(c.strip() for c in r)
        ]
    except csv.Error as exc:
        raise ValueError(f"The CSV could not be read: {exc}")

    if len(rows) < 2:
        raise ValueError("The CSV needs a header row and at least one record.")

    header = [_clean(c).strip() or f"Column {i + 1}" for i, c in enumerate(rows[0])]
    if len(header) > MAX_COLUMNS:
        raise ValueError(f"The CSV has {len(header)} columns; the maximum is {MAX_COLUMNS}.")

    width = len(header)
    records: List[List[str]] = []
    for line_no, row in enumerate(rows[1:], start=2):
        if len(row) > width:
            if any(c.strip() for c in row[width:]):
                raise ValueError(
                    f"Row {line_no} has {len(row)} columns but the header has {width}. "
                    "Check for an unquoted comma."
                )
            row = row[:width]
        records.append([_clean(c) for c in row] + [""] * (width - len(row)))
    return header, records
