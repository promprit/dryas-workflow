# TDD reference

Read the section the pointer in `SKILL.md` names; nothing here is needed on every turn.

## Red and green examples

**Red, good:** clear name, tests real behavior, one thing.

```typescript
test('retries failed operations 3 times', async () => {
  let attempts = 0;
  const operation = () => {
    attempts++;
    if (attempts < 3) throw new Error('fail');
    return 'success';
  };
  const result = await retryOperation(operation);
  expect(result).toBe('success');
  expect(attempts).toBe(3);
});
```

**Red, bad:** vague name, tests the mock, not the code.

```typescript
test('retry works', async () => {
  const mock = jest.fn()
    .mockRejectedValueOnce(new Error())
    .mockRejectedValueOnce(new Error())
    .mockResolvedValueOnce('success');
  await retryOperation(mock);
  expect(mock).toHaveBeenCalledTimes(3);
});
```

**Green, good:** just enough to pass.

```typescript
async function retryOperation<T>(fn: () => Promise<T>): Promise<T> {
  for (let i = 0; i < 3; i++) {
    try {
      return await fn();
    } catch (e) {
      if (i === 2) throw e;
    }
  }
  throw new Error('unreachable');
}
```

**Green, bad:** over-engineered (options for `maxRetries`, `backoff`, `onRetry` that no test asked for: YAGNI).

## Rationalizations

| Excuse | Reality |
|---|---|
| "Too simple to test" | Simple code breaks. The test takes 30 seconds. |
| "I'll test after" | Tests written after pass immediately, which proves nothing. They may test the wrong thing, test the implementation instead of the behavior, or miss the edge case you forgot. You never watched it fail, so you never proved it can catch the bug. Test-first forces that failure. |
| "Tests after achieve the same goals (spirit not ritual)" | Tests-after answer "what does this do?"; tests-first answer "what should this do?" Tests written after are biased by the code you already wrote: you verify the cases you remembered, not the ones you would have discovered. Coverage without proof the tests work. |
| "Already manually tested" | Manual testing is ad hoc: no record of what you covered, no way to re-run it when the code changes, easy to forget cases under pressure. "Worked when I tried it" is not comprehensive. Automated tests run the same way every time. |
| "Deleting X hours is wasteful" | Sunk cost fallacy: that time is spent either way. The real choice: rewrite with TDD (high confidence) or keep it and bolt tests on after (low confidence, likely bugs). Keeping code you cannot trust is the waste. |
| "Keep as reference, write tests first" | You will adapt it. That is testing after. Delete means delete. |
| "Need to explore first" | Fine. Throw the exploration away, start with TDD. |
| "Test hard = design unclear" | Listen to the test. Hard to test = hard to use. |
| "TDD will slow me down" | TDD IS the pragmatic path: it catches bugs before commit, prevents regressions, lets you refactor without fear. "Pragmatic" shortcuts mean debugging in production: slower, not faster. |
| "Manual test faster" | Manual testing does not prove edge cases. You will re-test every change. |
| "Existing code has no tests" | You are improving it. Add tests for the existing code. |

## Example: bug fix

**Bug:** an empty email is accepted.

**Red**
```typescript
test('rejects empty email', async () => {
  const result = await submitForm({ email: '' });
  expect(result.error).toBe('Email required');
});
```

**Verify red**
```
$ npm test
FAIL: expected 'Email required', got undefined
```

**Green**
```typescript
function submitForm(data: FormData) {
  if (!data.email?.trim()) {
    return { error: 'Email required' };
  }
  // ...
}
```

**Verify green**
```
$ npm test
PASS
```

**Refactor:** extract validation for several fields if needed.

## When stuck

| Problem | Solution |
|---|---|
| Do not know how to test | Write the wished-for API. Write the assertion first. Ask your human partner. |
| Test too complicated | Design too complicated. Simplify the interface. |
| Must mock everything | Code too coupled. Use dependency injection. |
| Test setup huge | Extract helpers. Still complex? Simplify the design. |
