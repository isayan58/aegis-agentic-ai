# Routing prototype — Day 3

```mermaid
flowchart TD
    S["Start"] --> V["Validate input"]
    V -->|Valid| C["Check clarity"]
    V -->|Invalid| E["End"]
    C -->|Questions needed| E
    C -->|Complete| P["Deterministic planner"]
    P -->|"Send: one per subject/factor"| W["Parallel stub workers"]
    W --> J["Collect and validate"]
    J --> E
```

## Execution boundaries

- Invalid requests finish with `failed`.
- Incomplete requests finish with `needs_clarification`.
- Complete requests dispatch independent evidence tasks.
- Parallel updates merge through the shared state reducers.
- The collector validates references and checks task completion.
- The successful prototype path finishes with `degraded` because
  evidence is synthetic and analysis tasks have not executed.
- No model calls, web requests or final reports are produced.

For three subjects and two factors, the graph runs six stub workers.
The six analysis tasks remain planned but unexecuted.