"""Security test strategy."""


from testicli.models import TestType


class SecurityStrategy:
    test_type = TestType.SECURITY

    def build_planning_context(self, source_files_content: str) -> str:
        return (
            "Focus on security vulnerabilities. Look for:\n"
            "- Input validation and sanitization\n"
            "- Authentication and authorization checks\n"
            "- SQL queries or command execution\n"
            "- File path handling\n"
            "- Sensitive data handling\n"
            "- Cryptographic operations\n"
        )

    def planning_prompt_additions(self) -> str:
        return (
            "Generate security tests that verify the application handles "
            "malicious or unexpected input safely. Focus on OWASP Top 10 categories "
            "relevant to the codebase. Test for injection, path traversal, "
            "authentication bypass, and data exposure."
        )

    def writing_prompt_additions(self) -> str:
        return (
            "Write a security test. Guidelines:\n"
            "- Test with malicious inputs (SQL injection, XSS payloads, path traversal)\n"
            "- Verify input validation rejects dangerous values\n"
            "- Check that sensitive data is not leaked in errors\n"
            "- Test authorization boundaries\n"
            "- Ensure cryptographic functions use secure defaults\n"
        )
