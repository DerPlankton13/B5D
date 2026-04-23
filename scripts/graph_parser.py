import argparse
from pathlib import Path

from rdflib import Graph


def main():
    parser = argparse.ArgumentParser(
        description="Merge JSON-LD files into a single Jelly graph file."
    )
    parser.add_argument(
        "path",
        type=Path,
        help="Directory to search recursively for .jsonld files.",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path("graph.jelly"),
        help="Output file path (default: graph.jelly).",
    )
    args = parser.parse_args()

    if not args.path.is_dir():
        parser.error(f"Path does not exist or is not a directory: {args.path}")

    g = Graph()

    count = 0
    for file in args.path.glob("**/*.jsonld"):
        print(f"  Parsing {file.name}...")
        g.parse(file, format="json-ld")
        count += 1

    print(f"✓ {count} file(s) loaded — {len(g)} triples total")

    g.serialize(destination=str(args.output), format="jelly")
    print(f"✓ Serialized to {args.output}")


if __name__ == "__main__":
    main()
