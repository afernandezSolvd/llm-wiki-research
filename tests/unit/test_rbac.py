"""Unit tests for RBAC role hierarchy."""
from app.auth.rbac import Role


def test_role_hierarchy():
    assert Role.reader < Role.editor < Role.admin


def test_role_from_str():
    assert Role.from_str("reader") == Role.reader
    assert Role.from_str("editor") == Role.editor
    assert Role.from_str("admin") == Role.admin


def test_min_role_comparison():
    assert Role.from_str("editor") >= Role.reader
    assert Role.from_str("admin") >= Role.editor
    assert not (Role.from_str("reader") >= Role.editor)
