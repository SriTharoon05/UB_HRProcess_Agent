import re
from urllib.parse import urlsplit

from app.models import LinkedInProfile


def valid_contact_email(email: str) -> bool:
    """Accept a bounded mailbox address; provider member IDs are not email."""
    local, separator, domain = email.partition("@")
    atom = r"[A-Za-z0-9!#$%&'*+/=?^_`{|}~-]+"
    labels = domain.split(".")
    return bool(
        separator
        and len(email) <= 320
        and len(local) <= 64
        and len(domain) <= 253
        and re.fullmatch(atom + r"(?:\." + atom + r")*", local)
        and len(labels) >= 2
        and all(re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?", label) for label in labels)
    )


def profile_text(value, max_length=200) -> str | None:
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value if value and len(value) <= max_length and value.isprintable() else None


def profile_locale(value) -> str | None:
    # LinkedIn userinfo may return {"language": "en", "country": "US"}.
    if isinstance(value, dict):
        language, country = value.get("language"), value.get("country")
        if not isinstance(language, str) or not re.fullmatch(r"[A-Za-z]{2,3}", language):
            return None
        if country is None:
            return language.lower()
        if not isinstance(country, str) or not re.fullmatch(r"[A-Za-z]{2}|[0-9]{3}", country):
            return None
        return f"{language.lower()}-{country.upper()}"
    value = profile_text(value, 64)
    if not value or not re.fullmatch(r"[A-Za-z]{2,3}(?:[-_][A-Za-z0-9]{2,8})*", value):
        return None
    return value.replace("_", "-")


def profile_picture(value) -> str | None:
    value = profile_text(value, 2048)
    if not value or any(character.isspace() for character in value) or "\\" in value:
        return None
    try:
        parts = urlsplit(value)
        if parts.scheme != "https" or not parts.hostname or parts.username or parts.password:
            return None
        if parts.hostname != "licdn.com" and not parts.hostname.endswith(".licdn.com"):
            return None
        if parts.port not in (None, 443):
            return None
    except ValueError:
        return None
    return value


def linkedin_profile(claims: dict, issuer: str) -> LinkedInProfile:
    email = profile_text(claims.get("email"), 320)
    email = email if email and valid_contact_email(email) else None
    return LinkedInProfile(
        sub=claims["sub"],
        issuer=issuer,
        name=profile_text(claims.get("name")),
        given_name=profile_text(claims.get("given_name")),
        family_name=profile_text(claims.get("family_name")),
        picture=profile_picture(claims.get("picture")),
        locale=profile_locale(claims.get("locale")),
        email=email,
        email_verified=claims["email_verified"] if email and type(claims.get("email_verified")) is bool else None,
    )
