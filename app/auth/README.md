# app/auth/

Authentication utilities.

## Capabilities

- BCrypt password hashing with SHA-256 pre-hash fallback for >72-byte inputs.
- Password verification with long-password compatibility path.
- JWT creation and verification (`sub` + `exp` checks).
- API key generation helper.
- Password strength validator (length + upper + lower + digit).
