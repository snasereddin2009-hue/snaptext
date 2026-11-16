"""Measure OCR accuracy with and without preprocessing.

Reads a folder of images, each paired with a ``.txt`` file of the same name
holding its ground-truth text, and prints Markdown tables for the README.
The part of a file name before the first underscore is its category.

Usage:
    python scripts/benchmark.py [samples] [--lang eng]
"""

from __future__ import annotations

import argparse
import sys
import time
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from statistics import fmean

from PIL import Image

from snaptext import ocr
from snaptext.metrics import character_accuracy, word_accuracy

_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".bmp"}


@dataclass(frozen=True, slots=True)
class Sample:
    path: Path
    expected: str

    @property
    def category(self) -> str:
        return self.path.stem.split("_")[0]


@dataclass(frozen=True, slots=True)
class Score:
    """Result of recognising one sample in one mode."""

    character: float
    word: float
    seconds: float


def load_samples(folder: Path) -> list[Sample]:
    """Return every image in ``folder`` that has a ground-truth text file."""
    samples = []
    for path in sorted(folder.iterdir()):
        truth = path.with_suffix(".txt")
        if path.suffix.lower() in _IMAGE_SUFFIXES and truth.is_file():
            samples.append(Sample(path, truth.read_text(encoding="utf-8")))
    return samples


def score(sample: Sample, language: str, *, preprocess: bool) -> Score:
    with Image.open(sample.path) as image:
        image.load()
        start = time.perf_counter()
        actual = ocr.recognise(image, language, preprocess=preprocess)
        seconds = time.perf_counter() - start
    return Score(
        character=character_accuracy(sample.expected, actual),
        word=word_accuracy(sample.expected, actual),
        seconds=seconds,
    )


def percent(values: list[float]) -> str:
    return f"{fmean(values):.1%}"


def summary_table(raw: list[Score], processed: list[Score]) -> str:
    rows = [
        "| Mode | Character accuracy | Word accuracy | Avg. time per image |",
        "| --- | --- | --- | --- |",
    ]
    for label, scores in (("Raw screenshot", raw), ("With preprocessing", processed)):
        rows.append(
            f"| {label} "
            f"| {percent([s.character for s in scores])} "
            f"| {percent([s.word for s in scores])} "
            f"| {fmean(s.seconds for s in scores) * 1000:.0f} ms |"
        )
    return "\n".join(rows)


def category_table(samples: list[Sample], raw: list[Score], processed: list[Score]) -> str:
    grouped: dict[str, list[tuple[Score, Score]]] = defaultdict(list)
    for sample, before, after in zip(samples, raw, processed, strict=True):
        grouped[sample.category].append((before, after))

    rows = [
        "| Category | Images | Raw | With preprocessing |",
        "| --- | --- | --- | --- |",
    ]
    for category, pairs in sorted(grouped.items()):
        rows.append(
            f"| {category} | {len(pairs)} "
            f"| {percent([before.character for before, _ in pairs])} "
            f"| {percent([after.character for _, after in pairs])} |"
        )
    return "\n".join(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "folder", type=Path, nargs="?", default=Path("samples"), help="folder of test images"
    )
    parser.add_argument("--lang", default="eng", help="Tesseract language code (default: eng)")
    args = parser.parse_args()

    if not args.folder.is_dir():
        print(f"error: {args.folder} is not a folder", file=sys.stderr)
        return 1
    samples = load_samples(args.folder)
    if not samples:
        print(f"error: no image/.txt pairs found in {args.folder}", file=sys.stderr)
        return 1

    try:
        version = ocr.tesseract_version()
        raw = [score(sample, args.lang, preprocess=False) for sample in samples]
        processed = [score(sample, args.lang, preprocess=True) for sample in samples]
    except ocr.OcrError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(f"{len(samples)} images, language '{args.lang}', Tesseract {version}\n")
    print(summary_table(raw, processed))
    print("\nCharacter accuracy by category:\n")
    print(category_table(samples, raw, processed))
    return 0


if __name__ == "__main__":
    sys.exit(main())
