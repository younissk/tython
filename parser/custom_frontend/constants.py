from __future__ import annotations

import re

ENUM_SENTINEL = "__custom_enum_decl__"
BINDING_SENTINEL = "__custom_binding_decl__"
RECORD_LITERAL_SENTINEL = "__custom_record_literal__"
CLASS_MEMBER_SENTINEL = "__custom_class_member__"
CLASS_MARKER_SENTINEL = "__custom_class_marker__"
RECORD_MARKER_SENTINEL = "__custom_record_marker__"
PUB_DECORATOR_SENTINEL = "__custom_pub__"
SETUP_METHOD_NAME = "__tython_setup__"

RESERVED_WORDS = {
    "const",
    "var",
    "pub",
    "record",
    "class",
    "setup",
    "init",
    "is",
    "this",
    "true",
    "false",
    "none",
    "int",
    "float",
    "bool",
    "str",
}

ENUM_HEADER_RE = re.compile(
    r"^(?P<indent>[ \t]*)enum[ \t]+(?P<name>[A-Za-z_][A-Za-z0-9_]*)[ \t]*:[ \t]*(?:#.*)?$"
)
IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
BINDING_RE = re.compile(
    r"^(?P<indent>[ \t]*)(?:(?P<pub>pub)[ \t]+)?(?P<kind>const|var)[ \t]+(?P<name>[A-Za-z_][A-Za-z0-9_]*)"
    r"(?:[ \t]*:[ \t]*(?P<type>[^=]+?))?[ \t]*=[ \t]*(?P<expr>.+)$"
)
BINDING_NO_INIT_RE = re.compile(
    r"^(?P<indent>[ \t]*)(?:(?P<pub>pub)[ \t]+)?(?P<kind>const|var)[ \t]+(?P<name>[A-Za-z_][A-Za-z0-9_]*)"
    r"(?:[ \t]*:[ \t]*(?P<type>.+))?[ \t]*$"
)
TYPE_BASE_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
CLASS_HEADER_RE = re.compile(
    r"^(?P<indent>[ \t]*)(?:(?P<pub>pub)[ \t]+)?class[ \t]+(?P<name>[A-Za-z_][A-Za-z0-9_]*)(?:[ \t]+is[ \t]+(?P<record>[A-Za-z_][A-Za-z0-9_]*(?:[ \t]*,[ \t]*[A-Za-z_][A-Za-z0-9_]*)*))?[ \t]*$"
)
RECORD_HEADER_RE = re.compile(
    r"^(?P<indent>[ \t]*)(?:(?P<pub>pub)[ \t]+)?record[ \t]+(?P<name>[A-Za-z_][A-Za-z0-9_]*)[ \t]*$"
)
CLASS_MEMBER_RE = re.compile(
    r"^(?:(?P<pub>pub)[ \t]+)?(?:(?P<init>init)[ \t]+)?(?P<kind>var|const)[ \t]+(?P<name>[A-Za-z_][A-Za-z0-9_]*)(?:[ \t]*:[ \t]*(?P<type>[^=]+?))?(?:[ \t]*=[ \t]*(?P<expr>.+))?$"
)
RECORD_FIELD_RE = re.compile(r"^(?P<name>[A-Za-z_][A-Za-z0-9_]*)[ \t]*:[ \t]*(?P<type>.+)$")
