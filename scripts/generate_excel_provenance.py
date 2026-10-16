#!/usr/bin/env python3
"""
Create a JSON-LD provenance file listing every Excel file in a folder.

Usage:
    python make_provenance.py [FOLDER] -o OUTPUT [-d DESCRIPTION] [--date YYYY-MM-DD]

Description and date have no defaults: if not given, the field is written
as "" and a reminder is printed so it can be filled in later.

Examples:
    python make_provenance.py ./exports -o DatahubProvenance.jsonld
    python make_provenance.py ./exports -o DatahubProvenance.jsonld -d "Manual export by Ivica Letunic sent via mail" --date 2026-10-12
"""

import argparse
import json
import sys
from datetime import date
from pathlib import Path

EXCEL_EXTENSIONS = {".xlsx", ".xlsm", ".xls", ".xlsb"}


def iso_date(value):
    """Accept only a real calendar date in YYYY-MM-DD format."""
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError:
        raise argparse.ArgumentTypeError(f"invalid date '{value}', expected YYYY-MM-DD")


def file_name(value):
    """Reject empty or whitespace-only output names."""
    if not value.strip():
        raise argparse.ArgumentTypeError("output file name must not be empty")
    return value


def main():
    parser = argparse.ArgumentParser(
        description="Build a JSON-LD provenance file from Excel file names."
    )
    parser.add_argument(
        "folder",
        nargs="?",
        default=".",
        help="Folder containing the Excel files (default: current folder)",
    )
    parser.add_argument(
        "-o",
        "--output",
        required=True,
        type=file_name,
        help="Output file name, e.g. DatahubProvenance.jsonld (required)",
    )
    parser.add_argument(
        "-d",
        "--description",
        help="Description of the export as a whole (empty if not given)",
    )
    parser.add_argument(
        "--date", type=iso_date, help="dateCreated as YYYY-MM-DD (empty if not given)"
    )
    args = parser.parse_args()

    folder = Path(args.folder)
    excel_files = sorted(
        p
        for p in folder.iterdir()
        if p.is_file()
        and p.suffix.lower() in EXCEL_EXTENSIONS
        and not p.name.startswith("~$")  # skip Excel lock files
    )

    doc = {
        "@context": {"@vocab": "https://schema.org/"},
        "@type": "DigitalDocument",
        "@id": Path(args.output).name,
        "description": args.description or "",
    }
    doc["about"] = [
        {
            "@type": "SpreadsheetDigitalDocument",
            "@id": f.name,
            "description": f"Node reflecting the Excel file '{f.name}' for provenance tracking.",
        }
        for f in excel_files
    ]
    doc["dateCreated"] = args.date or ""

    out_path = folder / args.output
    out_path.write_text(json.dumps(doc, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {out_path} with {len(excel_files)} Excel file(s).")

    missing = [
        name
        for name, val in (("description", args.description), ("dateCreated", args.date))
        if not val
    ]
    if missing:
        print(
            f"Note: {', '.join(missing)} left empty - fill in later.", file=sys.stderr
        )


if __name__ == "__main__":
    main()
