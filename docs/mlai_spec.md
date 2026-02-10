# MLAI: Markup Language for Agentic Interfaces

## The Problem

Large language models are remarkably good at generating declarative, structured content. Given clear constraints and examples, they produce well-formed output reliably. This makes them excellent candidates for generating educational content—lessons, explanations, assessments.

But there's a fundamental tension.

JSX and similar templating languages embed arbitrary computation. A component can execute any JavaScript. This power comes at a cost: you cannot verify what a JSX document will do without running it. Rice's theorem tells us that any non-trivial semantic property of a program is undecidable. If an agent can write JSX, it can write anything—including code that leaks answers, breaks rendering, or behaves unpredictably.

We need a language where:

- Agents can generate rich, interactive educational content
- Every document is fully verifiable before execution
- Sensitive data (answer keys, grading rubrics) cannot leak to clients
- The component vocabulary is extensible by humans, not agents
- Generation is reliable enough for autonomous pipelines

The goal is **verification by construction**: if a document parses and validates, it will render correctly and securely. No runtime surprises.

---

## Design Principles

### Data, Not Programs

MLAI documents are declarative data structures. There are no expressions, no conditionals evaluated at parse time, no loops, no function calls. The document describes *what* exists, never *how* it behaves.

Behavior lives in the interpreter and renderer—human-authored code that the agent cannot influence.

### XML Syntax

The syntax is pure XML. Not XML-inspired, not a custom format—actual XML.

This gives us:
- Mature parsers in every language
- Unambiguous grammar
- Standard tooling (validators, formatters, editors)
- No syntax design decisions to make

Boolean attributes use explicit values (`correct="true"`) for standard XML compliance.

### Closed Vocabulary

At any moment, the set of valid element tags is finite and known. Agents select from this vocabulary. They cannot introduce new tags, invent attributes, or compose behaviors beyond what the schema permits.

New components are added by humans writing component definitions. The agent's documentation regenerates automatically. The agent learns new components through updated documentation, not through invention.

### Components Are Just Components

There are no privileged categories. A `Section` and a `SingleSelect` are both components. Some components have answer keys to extract. Some track metrics. Some do neither. The component definition declares what each component has. The interpreter handles extraction uniformly.

### Self-Documenting

Every component definition includes documentation: description, attribute explanations, examples, anti-examples. The system generates agent instructions automatically from these definitions. When components change, documentation regenerates. There is no drift between implementation and documentation.

---

## Component Architecture

### Flat Component Definitions

Each component is a self-contained `MlaiComponentDefinition` that directly exposes its backend operations and frontend:

```typescript
interface MlaiComponentDefinition<TSubmission = unknown, TAnswerKey = unknown> {
  readonly name: string;

  // Backend — flat, no factory indirection
  validate?: (node: ElementNode) => ValidationMessage[];
  render: (node: ElementNode, ctx: RenderContext) => RenderResult;
  extractAnswer?: (node: ElementNode) => TAnswerKey;
  grade?: (submission: TSubmission, answerKey: TAnswerKey, ctx: GradeContext) => GradeResult;

  // Frontend
  frontend: ComponentType<MlaiComponentProps>;

  // Documentation
  docs?: ComponentDocs;
}
```

- **Content components** (`Section`, `Body`, `FlashCard`) have `render` + `frontend` only.
- **Assessable components** (`SingleSelect`, `SortQuiz`) also have `extractAnswer` + `grade`.
- No factory indirection. No `handleSubmission` parallel path. Each definition directly exposes what it can do.

**Why flat, not factories?**

The original design used factory functions (`function SingleSelect(node): AssessableComponent`). This added indirection without benefit—the factory was called once per node, returning an object whose methods closed over the node. The flat interface achieves the same thing more directly: the definition's methods receive the node as a parameter. Simpler to test, simpler to type, simpler to understand.

### Composition Over Inheritance

Components share behavior through **utility functions**, not base classes:

```typescript
import { extractText, getChild, getChildren } from '../shared/extract-text';
import { binaryGrade, setDifferenceGrade, kendallTauGrade } from '../shared/grading-utils';

const SingleSelectDefinition: MlaiComponentDefinition<number> = {
  name: 'SingleSelect',
  render: (node, ctx) => { /* uses shared utilities by choice */ },
  extractAnswer: (node) => { /* ... */ },
  grade: (submission, answerKey, ctx) => binaryGrade(submission, answerKey),
  frontend: SingleSelectFrontend,
};
```

Utilities are **opt-in imports**, not inherited methods. A component chooses which utilities to use. Nothing is forced by a parent class.

### Type Guards

A type guard distinguishes assessable from content-only components:

```typescript
function isAssessableDefinition(
  definition: MlaiComponentDefinition
): definition is MlaiComponentDefinition & {
  extractAnswer: NonNullable<MlaiComponentDefinition['extractAnswer']>;
  grade: NonNullable<MlaiComponentDefinition['grade']>;
} {
  return typeof definition.extractAnswer === 'function' && typeof definition.grade === 'function';
}
```

No inheritance hierarchy. The presence of `extractAnswer` and `grade` is what makes a component assessable.

### Two-Layer Frontend

UI code and MLAI adaptation are separate concerns:

**Layer 1 (`ui/`):** Pure React components. They accept typed props and render. No knowledge of MLAI, XML, nodes, or grading. Testable in isolation with just props. Theming, animation, and accessibility patterns are cohesive.

**Layer 2 (tag folders):** Each tag's `MlaiComponentDefinition`. The `frontend.tsx` imports the UI component and maps MLAI node data to its props:

```typescript
// Layer 2: single-select/frontend.tsx — thin adapter
import { MCQGrid, type MCQGridProps } from '../ui';
import type { MlaiComponentProps } from '../types';

export function SingleSelectFrontend({ node, onSubmit, submissionState }: MlaiComponentProps) {
  const props: MCQGridProps = {
    question: getPromptText(node),
    options: getOptionTexts(node),
    onSelect: (index) => onSubmit?.(index),
    state: submissionState,
  };
  return <MCQGrid {...props} />;
}
```

If `MCQGridProps` changes, TypeScript catches the breakage in the adapter immediately.

**Exception:** Simple content wrappers (Section, Body, H1-H3) render semantic HTML directly — no `ui/` intermediary. A `ui/Heading.tsx` wrapping `<h1>` would be over-engineering.

### Scoped Component Registration

Registries support hierarchical scoping for course-level and lesson-level component extension:

```typescript
import { componentRegistry } from '@vibely/mlai-components';
import { InfoBoxDefinition } from '@vibely/mlai-components/examples';

// Create a scoped registry for a course/lesson (inherits all 13 built-ins)
const lessonRegistry = componentRegistry.createScope();
lessonRegistry.register(InfoBoxDefinition);

// The scoped registry has 14 components; the global still has 13
```

**Design properties:**

- **Parent chain inheritance**: Scoped registries inherit all components from their parent chain.
- **Conflict detection**: Registering a component with a name that exists in the parent chain throws an error.
- **Sibling isolation**: Two scoped registries from the same parent are isolated — they can each register the same custom component name independently.
- **Additive-only**: Lessons can add custom components but cannot override or remove built-ins. If a lesson needs a different `Code` component, it registers it under a different name (e.g., `CodePlayground`).

---

## Document Format

```xml
<Lesson>

<Meta>
  <Id>python-101</Id>
  <Title>Introduction to Python</Title>
  <Version>1</Version>
  <Tags>
    <Tag>python</Tag>
    <Tag>beginner</Tag>
  </Tags>
</Meta>

<Section>
  <H1>What is Python?</H1>
  <Body>
    Python is a high-level programming language known for
    readable syntax and versatility.
  </Body>
</Section>

<Section>
  <H2>Variables</H2>
  <Body>
    Variables store values in memory. In Python, you create
    them with simple assignment.
  </Body>
  <Code lang="python">
name = "Alice"
age = 30
  </Code>
</Section>

<FlashCard id="fc1">
  <Front>What is a variable?</Front>
  <Back>A named reference to a value stored in memory.</Back>
</FlashCard>

<SingleSelect id="q1">
  <Prompt>What is a variable?</Prompt>
  <Options>
    <Option correct="true">A named reference to a value in memory</Option>
    <Option>A type of loop</Option>
    <Option>A function definition</Option>
    <Option>An error message</Option>
  </Options>
</SingleSelect>

<MultiSelect id="q2">
  <Prompt>Which are valid Python data types?</Prompt>
  <Options>
    <Option correct="true">str</Option>
    <Option correct="true">int</Option>
    <Option>char</Option>
    <Option correct="true">bool</Option>
  </Options>
</MultiSelect>

<SortQuiz id="q3">
  <Prompt>Order from fastest to slowest execution:</Prompt>
  <SortedItems>
    <Item>Assembly</Item>
    <Item>C</Item>
    <Item>Java</Item>
    <Item>Python</Item>
  </SortedItems>
</SortQuiz>

<MatchPairs id="q4">
  <Prompt>Match values to their types:</Prompt>
  <Pairs>
    <Pair>
      <Left>"hello"</Left>
      <Right>str</Right>
    </Pair>
    <Pair>
      <Left>42</Left>
      <Right>int</Right>
    </Pair>
    <Pair>
      <Left>3.14</Left>
      <Right>float</Right>
    </Pair>
  </Pairs>
  <RightDistractors>
    <Distractor>char</Distractor>
    <Distractor>double</Distractor>
  </RightDistractors>
</MatchPairs>

<FillBlanks id="q5">
  <Prompt>
    Text values are called <Blank>strings</Blank>.
    They are defined using <Blank>quotes</Blank>.
  </Prompt>
  <Distractors>
    <Distractor>integers</Distractor>
    <Distractor>parentheses</Distractor>
  </Distractors>
</FillBlanks>

<Subjective id="q6">
  <Prompt>
    Why is choosing good variable names important?
  </Prompt>
  <Rubric>
    <Criterion points="3" required="true">
      <Requirement>Explains readability or maintainability</Requirement>
      <Indicators>readable, understand, maintain, clear</Indicators>
    </Criterion>
    <Criterion points="2">
      <Requirement>Provides a concrete example</Requirement>
      <Indicators>example, such as, compare</Indicators>
    </Criterion>
  </Rubric>
  <Constraints minWords="20" maxWords="150" />
</Subjective>

</Lesson>
```

The entire document is pure XML. The `<Meta>` block contains document-level metadata as child elements. The rest of the document contains content and interactive elements.

---

## Interactive Elements

### Single-Select (SingleSelect)

One correct answer. User selects exactly one option. Binary grading.

### Multi-Select (MultiSelect)

Multiple correct answers. User may select any number of options. Partial credit based on hits minus false positives.

### Ordering (SortQuiz)

Items are written in correct order. The interpreter knows the correct sequence from document order. Scoring uses Kendall tau (pairwise agreement) for partial credit.

### Matching (MatchPairs)

Pairs define correct matches. Distractors are unmatched right-side options that increase difficulty. The interpreter extracts the mapping from the `Pair` elements.

### Fill in the Blanks (FillBlanks)

Blank content is the correct answer. Distractors mix with correct answers as draggable options. The interpreter extracts answers from `Blank` element contents.

### Subjective

Free-text response graded by AI against a rubric. The rubric specifies criteria, point values, and indicator terms. The entire rubric is server-only—clients never see grading criteria.

### FlashCard

Two-sided card with front (question/term) and back (answer/definition). Non-assessable — no grading. CSS 3D flip animation, keyboard accessible.

---

## Shuffling and Answer Isolation

### Non-Deterministic Shuffling

Options and items shuffle on every render. Not deterministically—truly randomly each time. This prevents:

- Users memorizing positions across attempts
- Users fumbling through options using system memory
- Pattern exploitation ("the answer is usually B")

When a user answers incorrectly and retries, options appear in a new order. They cannot use elimination-by-memory.

### Shuffle Tracking

Every shuffle is recorded:

```
{
  lessonId: "python-101",
  elementId: "q1",
  userId: "user-123",
  attemptId: "attempt-456",
  timestamp: "2025-01-28T10:30:00Z",
  shuffleOrder: [2, 0, 3, 1],  // indices into original option order
  selectedIndex: 1,            // what user picked in shuffled order
  originalIndex: 0,            // maps back to original
  correct: true
}
```

This enables analysis of:

- Position bias (do users favor certain positions?)
- First-option bias (do users pick the first plausible answer?)
- Pattern detection (does shuffling affect success rates?)

The user sees shuffled indices. The system stores the mapping. Analysis happens on original indices.

### Answer Isolation

Correct answers exist only in the interpreter's memory. The `render()` method returns a view with:

- No `correct` attributes on options
- No answer content in blanks
- No rubrics for subjective questions
- No pair mappings exposed
- No correct ordering revealed

The client receives what it needs to display the question. Nothing more.

---

## Architecture

### Interpreter + React Renderer

```
.mlai files
     │
     ▼
┌─────────────┐
│ Interpreter │
│   (Server)  │
│             │
│ • Parse     │
│ • Validate  │
│ • Hold in memory
│ • Render (shuffle, strip answers)
│ • Grade
│ • Track sessions
└─────────────┘
     │
     │  JSON over HTTP
     ▼
┌─────────────┐
│ React SPA   │
│  (Client)   │
│             │
│ • Fetch rendered tree
│ • Display components
│ • Capture interactions
│ • Submit answers
│ • Track viewport/time
└─────────────┘
```

The server holds lessons in memory as class instances. Each request calls methods on these objects. The client is purely presentational—it renders what the server sends and forwards user actions back.

### Server Responsibilities

- Parse and validate .mlai files at startup
- Hold Lesson instances in memory
- Render lessons (shuffle options, strip answers)
- Grade submissions against answer keys
- Track sessions and attempts
- Record shuffle orders for analysis
- Serve AI grading for subjective questions

### Client Responsibilities

- Fetch rendered lesson structure
- Map element tags to React components
- Handle user interaction (selections, ordering, typing)
- Submit answers to server
- Display feedback from grading
- Track time-on-page, viewport visibility
- Send metrics to server

The client never knows what's correct. It displays, collects input, and shows results.

---

## Package Structure

```
vibely-v2/                        # Docs, lessons, component definitions
├── mlai-specification.md         # This file — design philosophy and architecture
├── malai-format-spec.md          # Formal XML format specification
├── mlai-http-layer.md            # HTTP API reference
├── lessons/                      # Sample .mlai lesson files
├── scripts/                      # Utility scripts
└── mlai-components/              # Unified component definitions
    └── src/
        ├── ui/                   # Layer 1: Pure React components
        │   ├── MCQGrid.tsx
        │   ├── SortableList.tsx
        │   ├── MatchPairsBoard.tsx
        │   ├── FillBlanksPanel.tsx
        │   ├── TextResponseInput.tsx
        │   ├── FlipCard.tsx
        │   ├── CodeBlock.tsx
        │   ├── shared/           # MathText, TypewriterText, particles, etc.
        │   └── index.ts
        ├── single-select/        # Layer 2: Tag definitions
        │   ├── backend.ts        # render, validate
        │   ├── grading.ts        # extractAnswer, grade
        │   ├── frontend.tsx      # Maps MlaiComponentProps → MCQGrid props
        │   └── index.ts          # MlaiComponentDefinition export
        ├── multi-select/
        ├── sort-quiz/
        ├── match-pairs/
        ├── fill-blanks/
        ├── subjective/
        ├── code/
        ├── flash-card/
        ├── content/              # Section, Body, H1-H3 (simple wrappers)
        ├── shared/               # extractText, grading-utils
        ├── examples/             # Example custom components (InfoBox)
        ├── registry.ts           # Scoped registry with parent chain
        ├── types/index.ts        # MlaiComponentDefinition interface
        └── index.ts              # Barrel exports, auto-registers 13 built-ins

# Sibling repos (linked via file: protocol)
vibely-v2-parser/                 # XML parser, validation, rendering, grading
mlai-service/                     # Business logic: lesson, session, grading services
mlai-api/                         # HTTP transport: Hono routes, Zod validation
mlai-client/                      # React: hooks, scoped registry, TreeRenderer
mlai-demo/                        # Demo application
```

### Package Roles

| Package | What It Does | Tests |
|---------|-------------|-------|
| `vibely-v2-parser` | XML parser, component factories, validation, rendering, grading | 354 |
| `mlai-service` | Lesson loading, session management, shuffle tracking, grading orchestration | 112 |
| `mlai-api` | HTTP layer (Hono + Zod), REST endpoints | 25 |
| `mlai-components` | 13 component definitions with co-located backend + frontend | 133 |
| `mlai-client` | React hooks, scoped registry, TreeRenderer | 22 |
| `mlai-demo` | Renders all components | — |

**Total: 646+ tests, all passing.**

### Built-in Components (13)

| Component | Type | Grading | UI Layer |
|-----------|------|---------|----------|
| SingleSelect | Assessable | Binary | MCQGrid |
| MultiSelect | Assessable | Set-difference | MCQGrid (multi) |
| SortQuiz | Assessable | Kendall tau | SortableList |
| MatchPairs | Assessable | Fraction-match | MatchPairsBoard |
| FillBlanks | Assessable | Fraction-match | FillBlanksPanel |
| Subjective | Assessable | AI rubric (placeholder) | TextResponseInput |
| Code | Content | — | CodeBlock |
| FlashCard | Interactive | — | FlipCard |
| Section | Content | — | Direct HTML |
| Body | Content | — | Direct HTML |
| H1 | Content | — | Direct HTML |
| H2 | Content | — | Direct HTML |
| H3 | Content | — | Direct HTML |

---

## Session and Progress Tracking

### Session State

```
Session {
  lessonId
  userId
  startedAt
  lastActiveAt

  elements: Map<elementId, ElementSession>
}

ElementSession {
  elementId
  firstSeenAt
  attempts: Attempt[]
  bestScore
  completed
}

Attempt {
  attemptId
  timestamp
  shuffleOrder
  answer (in shuffled indices)
  answerMapped (in original indices)
  result
  timeSpent
}
```

### Why Server-Side State

Sessions live on the server. The client is stateless regarding progress.

This means:
- Resume works across devices
- Progress cannot be manipulated client-side
- Shuffle history is authoritative
- Analytics have complete data

For demo: in-memory storage. For production: database.

---

## Grading

### Objective Questions

Grading is mechanical comparison:

**SingleSelect**: Selected index matches correct index. Binary.

**MultiSelect**: Score = (hits - false positives) / total correct. Clamped to 0.

**SortQuiz**: Kendall tau coefficient. Measures pairwise agreement between submitted order and correct order. Ranges from -1 (perfectly reversed) to 1 (perfect).

**MatchPairs**: Fraction of pairs correctly matched.

**FillBlanks**: Fraction of blanks correctly filled. Case-insensitive, trimmed.

### Subjective Questions

AI grades against the rubric:

1. Extract rubric from server-side lesson data
2. Build prompt with rubric criteria and indicators
3. Send student response + rubric to AI
4. Parse structured response (score per criterion, feedback)
5. Return aggregate score and feedback

The rubric never reaches the client. Students see only: prompt, constraints (min/max words), and eventually their score and feedback.

**Current status:** Subjective grading returns `score: 0` as a placeholder. Real AI grading is planned as separate feature work.

---

## Validation

### Compile-Time (Type System)

The `render()` method returns `RenderResult`, which excludes answer-related fields. TypeScript enforces that `render()` cannot return what it cannot access.

### Runtime (Unit Tests)

```
test: SingleSelect.render() excludes correct attribute
test: MultiSelect.render() excludes correct attribute
test: SortQuiz.render() excludes position information
test: MatchPairs.render() excludes pair mappings
test: FillBlanks.render() excludes blank answers
test: Subjective.render() excludes rubric entirely
```

If these tests pass, answers cannot leak through rendering.

### Schema Validation

Every document validates against the component registry before loading:

- All tags exist in registry
- All attributes are declared and type-correct
- All children are allowed by parent
- All constraints satisfied

Invalid documents fail at startup. No runtime validation errors.

---

## Security Properties

**Answer isolation**: Answers exist only in interpreter memory. `render()` physically cannot return them (type system). Client receives stripped view.

**No agent execution**: Documents are data. All behavior is in human-authored interpreter and renderer code. Agents cannot inject logic.

**Shuffle unpredictability**: Random on each render. Users cannot predict or exploit order. Complete shuffle history recorded for analysis.

**Validation completeness**: If a document loads, it will render. All structural errors caught at startup.

---

## Alternatives Considered

### Compiled JSON Bundles

**Approach**: Compile .mlai to separate client.json and server.json files. Client bundle has answers stripped. Server bundle has answer keys. Physical file separation.

**Why not**:
- Serialization complexity
- Two representations to keep in sync
- Grading logic lives where? Separate from data?
- Verification becomes "grep the files" rather than type safety
- Adds a build step that slows iteration

In-memory classes are simpler. `render()` and `grade()` are just methods. One representation. Type system enforces what's accessible.

### Astro Integration

**Approach**: Use Astro's content collections. MLAI loader produces content entries. Astro handles routing, rendering, builds.

**Why not**:
- Astro is static-first; SSR is bolted on
- Content collections are designed for markdown/MDX
- No built-in session concept
- Fighting the framework for dynamic features
- Verification depends on trusting Astro's pipeline

We'd end up building a separate backend anyway for sessions, grading, and progress. At that point, Astro is just a rendering layer adding complexity.

### Next.js

**Approach**: Use Next.js with server components. API routes for grading. App router for lessons.

**Why not**:
- Overkill for this use case
- App router adds conceptual overhead
- Server components complicate the mental model
- Vendor lock-in to Vercel patterns
- We don't need SSR/SSG complexity

Plain React SPA + API is simpler and gives us full control.

### Deterministic Shuffling

**Approach**: Shuffle based on hash(lessonId + elementId + userId). Same user sees same order. Reproducible.

**Why not**:
- Users can exploit memory across attempts
- Incorrect answer → retry → same order → eliminate by memory
- Undermines assessment validity

Random shuffle on every render is essential. Record the shuffle for analysis, but never reproduce it for the user.

### YAML/JSON Configuration for Components

**Approach**: Define components in YAML or JSON config files rather than code.

**Why not**:
- Can't express extraction logic declaratively
- Custom validation requires escaping to code anyway
- Type safety is weaker
- IDE support is worse
- Config languages always grow until they're bad programming languages

Components as code. The definition *is* the implementation.

---

## Remaining Work

| Item | Description | Priority |
|------|-------------|----------|
| Lesson renderer | A working app that renders .mlai files in a browser | Next |
| Subjective grading | Integrate LLM for rubric-based grading (currently `score: 0` placeholder) | Medium-high |
| Accordion component | Collapsible content sections | Low (add when needed) |
| Tabs component | Tabbed content panels | Low (add when needed) |
| InfoBox two-layer refactor | Move InfoBox frontend to `ui/` layer for pattern consistency | Low |
| Service render migration | Have service call `definition.render()` directly instead of parser factory | Deferred |
| Parser dependency reduction | Extract shared types to reduce coupling | Deferred |

---

## Key Decisions

- **`file:` protocol** for local package dependencies (no monorepo tooling)
- **Build to `dist/`** before cross-package imports (TypeScript `rootDir` constraint)
- **Jest `moduleNameMapper`** for test-time resolution of local packages
- **Grading functions use `ElementNode` directly** — no parser dependency, just the AST node type
- **`vibely-lesson-components` absorbed, not wrapped** — UI ported into `ui/`, old verification layer stripped
- **`motion/react`** for SortableList drag-and-drop (Reorder component)
- **`useMlaiContext` directly** in adapters instead of `useQuizBase` shim — simpler, no indirection
- **Scoped registries are additive-only** — courses/lessons extend the platform, never fragment it
