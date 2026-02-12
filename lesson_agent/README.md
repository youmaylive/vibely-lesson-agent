# Lesson Agent

Generates MLAI lesson files from curriculum specifications using Claude Agent SDK.

## Setup

```bash
cd lesson_agent
uv sync
```

Set your API key:

```bash
export ANTHROPIC_API_KEY=your-api-key
```

## Usage

### Generate all lessons from a curriculum

```bash
uv run python main.py --all <path-to-curriculum.json> --output <output-dir>
```

**Example:**

```bash
uv run python main.py --all test_curriculum/curriculum.json --output output
```

This will:
1. Read every lesson spec referenced in `curriculum.json`
2. Generate `.mlai` files for each lesson
3. Validate each file against the MLAI parser
4. Auto-fix validation errors (up to 500 attempts per lesson)
5. Write an enriched `curriculum.json` to the output directory with `mlai_path` fields pointing to each generated `.mlai` file

### Filter to a specific module

```bash
uv run python main.py --all test_curriculum/curriculum.json --output output --module module_01
```

### Options

| Flag | Default | Description |
|------|---------|-------------|
| `--output`, `-o` | `output` | Output directory for generated `.mlai` files |
| `--module` | (all) | Filter to a specific module (e.g., `module_01`) |
| `--model` | `claude-opus-4-5` | Claude model to use |
| `--max-turns` | `30` | Max agent turns per phase |

### Output structure

```
output/
├── curriculum.json          # Enriched with mlai_path fields
├── module_01/
│   ├── lesson_01_01.mlai
│   ├── lesson_01_02.mlai
│   └── ...
├── module_02/
│   ├── lesson_02_01.mlai
│   └── ...
└── ...
```

The output `curriculum.json` adds an `mlai_path` field to each successfully generated lesson:

```json
{
  "lesson_id": "lesson_01_01",
  "mlai_path": "module_01/lesson_01_01.mlai",
  ...
}