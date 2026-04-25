from __future__ import annotations

import re

CONST_NAME_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")
VAR_NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")
TYPE_NAME_RE = re.compile(r"^[A-Z][A-Za-z0-9]*$")
IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

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
    "throws",
    "catch",
    "panic",
    "true",
    "false",
    "none",
    "int",
    "float",
    "bool",
    "str",
}

BUILTIN_NAMES = {"print", "len", "range", "panic", "Matrix"}
PRIMITIVE_TYPES = {"int", "float", "bool", "str", "none"}

MATRIX_BUILTIN_NAME = "Matrix"
MATRIX_METHODS = {
    "sum",
    "mean",
    "min",
    "max",
    "transpose",
    "inverse",
    "determinant",
    "norm",
    "solve",
    "hadamard",
}
MATRIX_PROPERTIES = {"shape", "rank", "rows", "cols", "dtype"}
