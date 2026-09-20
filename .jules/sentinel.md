
## 2024-05-18 - Prevent timing attacks in auth header check
**Vulnerability:** String comparison (`!=`) was used for validating an internal service secret header. This is susceptible to timing attacks, as the comparison halts on the first mismatch, potentially revealing characters of the secret based on response time differences.
**Learning:** This is a subtle but standard vulnerability. Python provides a standard module `secrets` for this exact scenario.
**Prevention:** Use `secrets.compare_digest()` for all security-sensitive string comparisons (like secrets, tokens, passwords) to ensure constant-time checking and prevent timing attacks.

## 2025-02-26 - Timing Attack in API Deps internal secret check
**Vulnerability:** The internal API service secret (`X-Internal-Secret`) was being checked against the expected secret (`INTERNAL_SERVICE_SECRET`) using a basic string equality comparison (`!=`).
**Learning:** Basic string comparison operators (`==`, `!=`) terminate early upon encountering the first differing character. An attacker could potentially measure the response time of requests with different secrets to infer the expected secret character by character.
**Prevention:** Always use constant-time comparison functions like `secrets.compare_digest` when comparing sensitive data like passwords, API keys, or tokens.

## 2025-02-26 - Prevent stack trace leakage in MCP tool calls
**Vulnerability:** The generic exception handler in `dynamic_call_tool` was directly interpolating the raw exception message into the user-facing text response, potentially exposing internal server state or stack trace information to external clients.
**Learning:** Returning raw exception details in HTTP/MCP responses is a known security anti-pattern (CWE-209: Generation of Error Message Containing Sensitive Information). It gives attackers insights into the internal architecture, libraries used, or system state.
**Prevention:** Catch generic exceptions gracefully, log the detailed error internally using `logger.exception()`, and return a standardized, opaque error message (like "Internal Server Error") to the client.
