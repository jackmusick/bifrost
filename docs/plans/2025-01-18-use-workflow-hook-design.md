# useWorkflow Hook Design

## Overview

Replace the current broken `useWorkflow` hook in the code-based app builder with one that properly handles async workflow execution. The current implementation returns execution metadata (`{ execution_id, status: "Pending", result: null }`) instead of waiting for actual results.

The new hook composes existing infrastructure:
- `executeWorkflow()` API call
- `useExecutionStream` WebSocket subscription
- `useExecutionStreamStore` for reactive state

## API

```typescript
const workflow = useWorkflow('workflow-id')

// Start execution
workflow.execute({ limit: 10 })

// Reactive state (updates via WebSocket)
workflow.executionId   // string | null
workflow.status        // "Pending" | "Running" | "Success" | "Failed" | null
workflow.loading       // true while Pending/Running
workflow.completed     // true when Success
workflow.failed        // true when Failed
workflow.result        // workflow output (null until completed)
workflow.error         // error message if failed
workflow.logs          // streaming logs array
```

## Behavior

1. **`execute(params)`** - POSTs to execute API, stores `executionId`, triggers WebSocket subscription
2. **Calling `execute()` again** - Replaces current execution (new ID, subscription switches, state resets)
3. **Unmount** - Cleans up WebSocket subscription
4. **`result`** - Unwrapped workflow output (not execution metadata)

## Usage Examples

### Load on mount

```typescript
const workflow = useWorkflow('list-customers')

useEffect(() => {
  workflow.execute({ limit: 10 })
}, [])

if (workflow.loading) return <Spinner />
if (workflow.failed) return <Error message={workflow.error} />

return <CustomerList data={workflow.result} />
```

### Button trigger

```typescript
const workflow = useWorkflow('create-customer')

<Button
  onClick={() => workflow.execute({ name: 'Acme' })}
  disabled={workflow.loading}
>
  {workflow.loading ? <Spinner /> : 'Create'}
</Button>
```

### With streaming logs

```typescript
const workflow = useWorkflow('long-running-task')

useEffect(() => {
  workflow.execute({ taskId: 123 })
}, [])

{workflow.loading && (
  <div>
    <p>Processing...</p>
    <LogViewer logs={workflow.logs} />
  </div>
)}
```

## Implementation Notes

### Internal composition

```typescript
function useWorkflow(workflowId: string) {
  const [executionId, setExecutionId] = useState<string | null>(null)
  const [result, setResult] = useState<unknown>(null)

  // Subscribe to WebSocket updates
  useExecutionStream({
    executionId: executionId || '',
    enabled: !!executionId,
    onComplete: () => fetchResult()
  })

  // Get reactive state from store
  const streamState = useExecutionStreamStore((state) =>
    executionId ? state.streams[executionId] : undefined
  )

  const execute = async (params?: Record<string, unknown>) => {
    // Reset state
    setResult(null)

    // POST to API
    const response = await executeWorkflowAPI(workflowId, params)
    setExecutionId(response.execution_id)
  }

  const fetchResult = async () => {
    // Fetch completed execution to get result
    const execution = await getExecution(executionId)
    setResult(execution.result)
  }

  return {
    execute,
    executionId,
    status: streamState?.status ?? null,
    loading: streamState?.status === 'Pending' || streamState?.status === 'Running',
    completed: streamState?.status === 'Success',
    failed: streamState?.status === 'Failed',
    result,
    error: streamState?.error ?? null,
    logs: streamState?.streamingLogs ?? [],
  }
}
```

### Key decisions

- **`result` is unwrapped** - Contains actual workflow output, not execution metadata
- **Replaces on re-execute** - Calling `execute()` again starts fresh, no queuing
- **Uses existing infrastructure** - No new WebSocket or streaming code needed
- **Cleans up on unmount** - Handled by `useExecutionStream` internally

## Files to modify

- `client/src/lib/app-code-platform/useWorkflow.ts` - Replace implementation
- `client/src/lib/app-code-platform/scope.ts` - May need to update exports
