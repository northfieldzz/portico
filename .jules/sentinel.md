## 2024-05-18 - Prevent timing attacks in auth header check
**Vulnerability:** String comparison (`!=`) was used for validating an internal service secret header. This is susceptible to timing attacks, as the comparison halts on the first mismatch, potentially revealing characters of the secret based on response time differences.
**Learning:** This is a subtle but standard vulnerability. Python provides a standard module `secrets` for this exact scenario.
**Prevention:** Use `secrets.compare_digest()` for all security-sensitive string comparisons (like secrets, tokens, passwords) to ensure constant-time checking and prevent timing attacks.
