"""
Lesson Agent — generates MLAI lessons from curriculum specs using Claude Agent SDK.

Usage:
    # Generate a single lesson
    uv run python main.py test_curriculum/module_01/lesson_01_01.md

    # Generate a single lesson with custom output dir
    uv run python main.py test_curriculum/module_01/lesson_01_01.md --output output/

    # Generate all lessons from curriculum.json
    uv run python main.py --all test_curriculum/curriculum.json

    # Generate all lessons from a specific module
    uv run python main.py --module module_01 test_curriculum/curriculum.json
"""

import asyncio
import argparse
import sys
from pathlib import Path

from config import DEFAULT_MODEL, DEFAULT_MAX_TURNS, PROJECT_ROOT
from agent import generate_lesson, generate_all_lessons


def main():
    parser = argparse.ArgumentParser(
        description="Generate MLAI lessons from curriculum specs using Claude Agent SDK.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Single lesson
  uv run python main.py ../test_curriculum/module_01/lesson_01_01.md

  # All lessons from curriculum
  uv run python main.py --all ../test_curriculum/curriculum.json

  # All lessons from a specific module
  uv run python main.py --all --module module_01 ../test_curriculum/curriculum.json
        """,
    )
    parser.add_argument(
        "input",
        help="Path to lesson spec (.md) or curriculum (.json) when using --all",
    )
    parser.add_argument(
        "--output", "-o",
        default="output",
        help="Output directory for generated .mlai files (default: output/)",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Generate all lessons from a curriculum.json file",
    )
    parser.add_argument(
        "--module",
        default=None,
        help="Filter to a specific module (e.g., module_01) when using --all",
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help=f"Claude model to use (default: {DEFAULT_MODEL})",
    )
    parser.add_argument(
        "--max-turns",
        type=int,
        default=DEFAULT_MAX_TURNS,
        help=f"Max agent turns per phase (default: {DEFAULT_MAX_TURNS})",
    )

    args = parser.parse_args()

    # Ensure output directory exists (resolve relative to PROJECT_ROOT)
    output_dir = (PROJECT_ROOT / args.output).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.all:
        # Batch mode: generate from curriculum.json
        curriculum_input = (PROJECT_ROOT / args.input).resolve() if not Path(args.input).is_absolute() else Path(args.input)
        results = asyncio.run(
            generate_all_lessons(
                curriculum_path=str(curriculum_input),
                output_dir=str(output_dir),
                module_filter=args.module,
                model=args.model,
                max_turns=args.max_turns,
            )
        )
        print(f"\n{'=' * 60}")
        print("BATCH RESULTS")
        print(f"{'=' * 60}")
        print(f"✅ Success: {len(results['success'])} lessons")
        print(f"❌ Failed:  {len(results['failed'])} lessons")
        print(f"⚠️  Skipped: {len(results['skipped'])} lessons")
        if results["failed"]:
            print(f"\nFailed lessons: {', '.join(results['failed'])}")
        if results["skipped"]:
            print(f"Skipped lessons: {', '.join(results['skipped'])}")
    else:
        # Single lesson mode — resolve relative to PROJECT_ROOT
        input_path = Path(args.input)
        if not input_path.is_absolute():
            input_path = (PROJECT_ROOT / input_path).resolve()
        if not input_path.exists():
            print(f"Error: {input_path} not found")
            sys.exit(1)

        # Detect curriculum.json relative to the lesson spec
        curriculum_path = input_path.parent.parent / "curriculum.json"
        if not curriculum_path.exists():
            curriculum_path = input_path.parent / "curriculum.json"
        if not curriculum_path.exists():
            print(f"Warning: curriculum.json not found near {input_path}, proceeding without course context")
            curriculum_path = None

        ok = asyncio.run(
            generate_lesson(
                lesson_spec_path=str(input_path),
                curriculum_path=str(curriculum_path) if curriculum_path else "",
                output_dir=str(output_dir),
                model=args.model,
                max_turns=args.max_turns,
            )
        )
        sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()