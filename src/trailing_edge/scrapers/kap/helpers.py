"""Shared name-normalization and role-inference helpers."""


def normalize_name(name: str) -> str:
    return " ".join(name.strip().casefold().split())


def infer_role_type(role: str | None) -> str:
    if not role:
        return "SHAREHOLDER"
    r = role.casefold()
    if any(k in r for k in ["yönetim kurulu", "yk ", "board"]):
        return "BOARD"
    if any(k in r for k in ["denetim", "auditor"]):
        return "AUDITOR"
    if any(k in r for k in ["müdür", "direktör", "ceo", "cfo", "başkan"]):
        return "EXEC"
    return "SHAREHOLDER"


def infer_is_independent(role: str | None) -> bool:
    return bool(role and "bağımsız" in role.casefold())
