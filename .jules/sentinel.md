
## 2024-05-18 - Prevent timing attacks in auth header check
**Vulnerability:** String comparison (`!=`) was used for validating an internal service secret header. This is susceptible to timing attacks, as the comparison halts on the first mismatch, potentially revealing characters of the secret based on response time differences.
**Learning:** This is a subtle but standard vulnerability. Python provides a standard module `secrets` for this exact scenario.
**Prevention:** Use `secrets.compare_digest()` for all security-sensitive string comparisons (like secrets, tokens, passwords) to ensure constant-time checking and prevent timing attacks.

## 2025-02-26 - Timing Attack in API Deps internal secret check
**Vulnerability:** The internal API service secret (`X-Internal-Secret`) was being checked against the expected secret (`INTERNAL_SERVICE_SECRET`) using a basic string equality comparison (`!=`).
**Learning:** Basic string comparison operators (`==`, `!=`) terminate early upon encountering the first differing character. An attacker could potentially measure the response time of requests with different secrets to infer the expected secret character by character.
**Prevention:** Always use constant-time comparison functions like `secrets.compare_digest` when comparing sensitive data like passwords, API keys, or tokens.
