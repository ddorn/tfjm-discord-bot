def has_role(member, role: str):
    """Return whether the member has a role with this name."""

    return any(r.name == role for r in member.roles)
