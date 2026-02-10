
## Generating and Validating MLAI Files

### CLI Tool

The parser includes a CLI tool for validation and documentation generation. It can be run from any directory using absolute paths.

**Validate files:**

```bash
node /Users/elvish/Documents/CODING/vibely-v2/vibely-v2-parser/dist/cli.js /path/to/your-file.mlai
```

**Multiple files:**

```bash
node /Users/elvish/Documents/CODING/vibely-v2/vibely-v2-parser/dist/cli.js file1.mlai file2.mlai
```

**Options:**

| Flag | Description |
|------|-------------|
| `--help`, `-h` | Show usage help |
| `--json` | Output validation results as JSON |
| `--quiet`, `-q` | Only output errors (no summary) |
| `--docs` | Generate full component reference documentation (Markdown) |
| `--prompt` | Generate concise LLM-oriented MLAI format guide |

### Generate Component Documentation

The documentation is **dynamic** — it reads from the component registry at runtime. When components are added or modified, the output updates automatically.

**Full reference** (all components with schemas, examples, anti-examples, attribute tables):

```bash
node /Users/elvish/Documents/CODING/vibely-v2/vibely-v2-parser/dist/cli.js --docs
```

Save to file:

```bash
node /Users/elvish/Documents/CODING/vibely-v2/vibely-v2-parser/dist/cli.js --docs > mlai-reference.md
```

**LLM prompt** (concise format guide suitable for feeding to an AI to generate .mlai files):

```bash
node /Users/elvish/Documents/CODING/vibely-v2/vibely-v2-parser/dist/cli.js --prompt
```

Copy to clipboard (macOS):

```bash
node /Users/elvish/Documents/CODING/vibely-v2/vibely-v2-parser/dist/cli.js --prompt | pbcopy
```

### How Documentation Stays Dynamic

Each component's factory function exposes a `docs()` method returning `ComponentDocs`:

```typescript
interface ComponentDocs {
  name: string;
  description: string;
  schema?: ComponentSchema;        // attributes, children, text rules
  examples?: ComponentExample[];    // valid usage examples
  antiExamples?: ComponentExample[]; // common mistakes with explanations
}
```

The registry's `generateDocs()` and `generatePrompt()` methods iterate over all registered components, call their `docs()` methods, and assemble the output. No hardcoded component lists — adding a component to the registry automatically includes it in generated documentation.

### Validation Errors

The validator catches:

- **Broken XML** — malformed tags, unclosed elements
- **Missing required elements** — e.g., `<Meta>` missing `<Version>`
- **Structural errors** — e.g., `<Meta>` not being the first child of `<Lesson>`
- **Unknown elements** — with "did you mean?" suggestions for typos (e.g., `<SingleSlect>` → `SingleSelect`)
- **Schema violations** — missing required attributes, wrong attribute types, disallowed children
- **Component-specific rules** — e.g., `SingleSelect` must have exactly one correct option

### Programmatic Usage

```typescript
import { parse, createFullRegistry } from '@vibely/malai-parser';

const content = fs.readFileSync('lesson.mlai', 'utf-8');
const registry = createFullRegistry();
const result = parse(content, registry);

if (!result.success) {
  result.messages
    .filter(m => m.severity === 'error')
    .forEach(e => console.error(`Line ${e.location?.line}: ${e.code} - ${e.message}`));
}
```

### Rebuilding After Changes

If parser source files change, rebuild before using the CLI:

```bash
cd /Users/elvish/Documents/CODING/vibely-v2/vibely-v2-parser && npm run build
```