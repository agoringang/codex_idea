from __future__ import annotations

import argparse

from app.core.schemas import IngestRequest
from app.services.ingest import ingest_csv


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", required=True)
    parser.add_argument("--output-name", default="runners")
    parser.add_argument("--race-id-column", default="race_id")
    parser.add_argument("--horse-column", default="horse_name")
    args = parser.parse_args()

    res = ingest_csv(
        IngestRequest(
            csv_path=args.csv,
            output_name=args.output_name,
            race_id_column=args.race_id_column,
            horse_column=args.horse_column,
        )
    )
    print(res.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
