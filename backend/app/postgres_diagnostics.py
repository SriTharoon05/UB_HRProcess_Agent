"""Fixed PostgreSQL failure messages; driver text never leaves this module."""


def postgres_failure(exc: Exception) -> tuple[str, str, bool]:
    code = getattr(exc, "sqlstate", None)
    states = {
        "28P01": ("invalid_password", "PostgreSQL rejected the database password. Check DATABASE_URL and URL-encode special characters in the password.", False),
        "28000": ("authentication_failed", "PostgreSQL authentication failed. Copy the complete Session pooler connection string from Supabase Connect, including its username and database password.", False),
        "42501": ("permission_denied", "The database user lacks permission to create or update the talentmatch schema. Use an authorized database role.", False),
        "3D000": ("database_not_found", "The database in DATABASE_URL was not found. Use the database name shown in Supabase Connect.", False),
        "57014": ("statement_timeout", "PostgreSQL cancelled the query or reached its statement timeout. Check database load and retry.", True),
        "55P03": ("lock_timeout", "PostgreSQL could not acquire a database lock. Stop duplicate migration processes and retry.", True),
        "53300": ("connection_limit", "The database or pooler connection limit was reached. Stop duplicate API and worker instances, then retry.", True),
        "53400": ("connection_limit", "The database or pooler resource limit was reached. Check Supabase capacity before retrying.", True),
        "57P03": ("database_unavailable", "The database is starting, paused, or temporarily unavailable. Check its Supabase project status and retry.", True),
    }
    if code in states:
        return states[code]
    # Inspect messages only to choose a fixed category. Never return any part of
    # the original text: it may contain credentials, identifiers, or SQL values.
    message = str(exc).lower()
    patterns = (
        (("tenant or user not found",), "tenant_not_found", "Supabase did not recognize the pooler username or project. Copy the exact Session pooler connection string from Supabase Connect.", False),
        (("no password supplied",), "authentication_failed", "DATABASE_URL has no database password. Use the complete connection string from Supabase Connect.", False),
        (("password authentication failed", "wrong password", "invalid password", "server login failed"), "invalid_password", states["28P01"][1], False),
        (("authentication failed",), "authentication_failed", states["28000"][1], False),
        (("maxclientsinsessionmode", "max clients reached", "too many clients", "remaining connection slots"), "connection_limit", states["53300"][1], True),
        (("circuit breaker open", "database system is starting up", "database system is shutting down"), "database_unavailable", states["57P03"][1], True),
        (("certificate verify failed", "sslrootcert", "root certificate", "self-signed", "certificate has expired", "does not match host name"), "tls_certificate", "Database certificate verification failed. For the requested local setup use DATABASE_SSLMODE=require; restart with the updated settings.", False),
        (("server closed", "connection reset", "unexpected eof", "eof detected", "connection is closed", "connection has been closed"), "connection_lost", "The database connection was closed unexpectedly. Check Supabase status and network or VPN stability, then retry.", True),
        (("ssl error", "ssl connection", "ssl negotiation", "does not support ssl"), "tls_negotiation", "The database TLS handshake failed. Check the exact PostgreSQL host and port from Supabase Connect and network access.", True),
        (("could not translate host", "failed to resolve", "getaddrinfo", "no such host", "name or service not known"), "dns_failure", "The database hostname could not be resolved. Check the exact pooler host from Supabase Connect and your DNS or VPN connection.", True),
        (("timeout", "timed out"), "connection_timeout", "The database connection timed out. Check Supabase project status and whether your network allows the configured PostgreSQL port.", True),
        (("connection refused", "actively refused"), "connection_refused", "The database connection was refused. Check Supabase project status, its host and port, and firewall access.", True),
    )
    for phrases, reason, detail, retryable in patterns:
        if any(phrase in message for phrase in phrases):
            return reason, detail, retryable
    return ("database_operation_failed",
            "PostgreSQL metadata operation failed. Check the reported operation and error_code, database connectivity, and permissions.", True)
