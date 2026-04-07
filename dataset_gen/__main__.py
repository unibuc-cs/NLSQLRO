"""Module entrypoint: enables `python -m dataset_gen`."""

from dataset_gen.cli import main


if __name__ == "__main__":
    raise SystemExit(main())
