## Task 1: Rate-limit the login endpoint
Goal: reject more than 5 failed logins per account per 15 minutes with HTTP 429.
Scope:
- src/auth/rate_limit.ts
- src/auth/login.ts
- tests/auth/rate_limit.test.ts
Done:
- `pnpm test tests/auth/rate_limit.test.ts` passes
- 6th failed login within 15 minutes returns 429 with a Retry-After header
Failing test first: tests/auth/rate_limit.test.ts :: blocks the sixth failed attempt

## Task 2: Show the lockout message on the login form
Goal: when the API returns 429, the form shows "Too many attempts. Try again in N minutes."
Scope:
- src/ui/LoginForm.tsx
- tests/ui/LoginForm.test.tsx
Done:
- `pnpm test tests/ui/LoginForm.test.tsx` passes
- design pass with ui-ux-pro-max and impeccable recorded in the report
Failing test first: tests/ui/LoginForm.test.tsx :: shows lockout message on 429
