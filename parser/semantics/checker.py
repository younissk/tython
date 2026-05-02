from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

from ..custom_frontend import (
    BINDING_SENTINEL,
    CLASS_MARKER_SENTINEL,
    CLASS_MEMBER_SENTINEL,
    ENUM_SENTINEL,
    FILE_IMPORT_SENTINEL,
    NATIVE_IMPORT_SENTINEL,
    PYIMPORT_SENTINEL,
    PUB_DECORATOR_SENTINEL,
    RECOVERABLE_ERROR_BASE_NAME,
    RECORD_LITERAL_SENTINEL,
    RECORD_MARKER_SENTINEL,
    SETUP_METHOD_NAME,
    THROWS_DECORATOR_SENTINEL,
    TRY_PROPAGATE_SENTINEL,
    parse_custom_source,
)


from .constants import (
    BUILTIN_NAMES,
    CONST_NAME_RE,
    IDENTIFIER_RE,
    MATRIX_BUILTIN_NAME,
    MATRIX_METHODS,
    MATRIX_PROPERTIES,
    PRIMITIVE_TYPES,
    RESERVED_WORDS,
    TYPE_NAME_RE,
    VAR_NAME_RE,
)
from .errors import err
from .models import (
    Assignment,
    BindingDecl,
    ClassDecl,
    ClassMemberDecl,
    FunctionParam,
    FunctionSignature,
    ReferenceSite,
    RecordDecl,
    RecordFieldDecl,
    SemanticAnalysis,
    SemanticSymbol,
    Scope,
    Symbol,
    SourceRange,
)
from .type_utils import (
    annotation_to_custom_type,
    extract_int_literal,
    function_type_matches_signature,
    is_function_type,
    iter_type_atoms,
    signature_to_function_type,
)
from .pyimport_stubs import PyImportStubIndex


@dataclass(frozen=True)
class TryContext:
    handled_types: set[str]
    catch_all: bool


class SemanticChecker:
    def __init__(
        self, *, project_root: Path | None = None, source_path: Path | None = None
    ) -> None:
        self._project_root = project_root
        self._source_path = source_path
        self._pyimport_stubs: PyImportStubIndex | None = None
        self._file_module_cache: dict[
            Path,
            tuple[
                dict[str, tuple[str, str | None, bool]],
                dict[str, FunctionSignature],
                dict[str, RecordDecl],
                dict[str, ClassDecl],
            ],
        ] = {}
        self._scopes: list[Scope] = [Scope(kind="module", function_id=None, symbols={})]
        self._next_function_id = 1
        self._function_signatures: dict[str, FunctionSignature] = {}
        self._record_decls: dict[str, RecordDecl] = {}
        self._class_decls: dict[str, ClassDecl] = {}
        self._analysis = SemanticAnalysis()
        self._return_type_stack: list[str] = []
        self._loop_depth = 0
        self._current_class_name: str | None = None
        self._current_callable_name: str | None = None
        self._class_method_names: set[str] = set()
        self._class_field_names: set[str] = set()
        self._current_class_member_map: dict[str, ClassMemberDecl] = {}
        self._throws_stack: list[set[str]] = []
        self._try_context_stack: list[TryContext] = []
        self._matrix_expr_info: dict[int, tuple[int | None, str | None]] = {}
        for builtin in BUILTIN_NAMES:
            self._scopes[0].symbols[builtin] = Symbol(
                name=builtin,
                qualified_name=builtin,
                kind="const",
                type_name=None,
                py_module=None,
                lineno=0,
                col_offset=0,
                function_id=None,
                initialized=True,
            )

    def check(self, tree: ast.AST) -> None:
        if not isinstance(tree, ast.Module):
            raise SyntaxError(err("E2001", 1, "custom parser expects module input"))
        self._analysis = SemanticAnalysis()
        self._matrix_expr_info = {}
        self._check_statements(tree.body)

    @property
    def analysis(self) -> SemanticAnalysis:
        return self._analysis

    def _check_statements(self, statements: list[ast.stmt]) -> None:
        terminated_at: ast.stmt | None = None
        for stmt in statements:
            if terminated_at is not None:
                raise SyntaxError(
                    err(
                        "E2087",
                        getattr(stmt, "lineno", 1),
                        "unreachable statement after control-flow terminator",
                        "Remove statements that come after return/break/continue in the same block.",
                    )
                )
            self._check_statement(stmt)
            if isinstance(stmt, (ast.Return, ast.Break, ast.Continue, ast.Raise)):
                terminated_at = stmt

    def _check_statement(self, stmt: ast.stmt) -> None:
        if self._is_native_import_stmt(stmt):
            target, alias = self._extract_native_import(stmt)
            if "/" not in target:
                raise SyntaxError(
                    err(
                        "E2200",
                        stmt.lineno,
                        "native import must use slash-separated module path",
                        "Use `import pkg/mod` form.",
                    )
                )
            bound_name = alias or target.rsplit("/", 1)[-1]
            self._declare_name(bound_name, "const", None, stmt.lineno, initialized=True)
            return

        if self._is_file_import_stmt(stmt):
            path, alias = self._extract_file_import(stmt)
            if not (path.startswith("./") or path.startswith("../")):
                raise SyntaxError(
                    err(
                        "E2210",
                        stmt.lineno,
                        "file import path must be relative",
                        "Use `./` or `../` path prefix.",
                    )
                )
            self._declare_name(
                alias,
                "const",
                "Module",
                stmt.lineno,
                initialized=True,
                detail=f"import {path}",
            )
            resolved = self._resolve_file_import_path(path)
            if resolved is not None:
                self._import_file_module(alias, resolved)
            return

        if self._is_pyimport_stmt(stmt):
            module_name, alias = self._extract_pyimport(stmt)
            atoms = module_name.split(".")
            if any(not IDENTIFIER_RE.fullmatch(atom) for atom in atoms):
                raise SyntaxError(
                    err(
                        "E2211",
                        stmt.lineno,
                        f"invalid pyimport module '{module_name}'",
                        "Use dotted Python module path identifiers only.",
                    )
                )
            bound_name = alias or module_name.split(".", 1)[0]
            self._declare_name(
                bound_name,
                "const",
                None,
                stmt.lineno,
                initialized=True,
                detail=f"pyimport {module_name}",
            )
            sym = self._lookup_symbol(bound_name)
            if sym is not None:
                sym.py_module = module_name
            return

        if self._is_binding_decl_stmt(stmt):
            decl = self._extract_binding_decl(stmt)
            self._declare_binding(decl)
            return

        if self._is_enum_decl_stmt(stmt):
            enum_name = self._extract_enum_name(stmt)
            self._check_type_name(enum_name, stmt.lineno)
            self._record_symbol(
                name=enum_name,
                qualified_name=enum_name,
                kind="enum",
                type_name=enum_name,
                location=(stmt.lineno, stmt.col_offset + 1),
                parent_qname=None,
                is_public=True,
            )
            self._declare_name(
                enum_name,
                "const",
                enum_name,
                stmt.lineno,
                initialized=True,
                location=(stmt.lineno, stmt.col_offset + 1),
                symbol_kind="enum",
                is_public=True,
            )
            return

        if isinstance(stmt, ast.Assign):
            if len(stmt.targets) != 1:
                raise SyntaxError(
                    err(
                        "E2002",
                        stmt.lineno,
                        "only simple name assignment is supported",
                        "Assign to one target per statement.",
                    )
                )
            target = stmt.targets[0]
            if isinstance(target, ast.Name):
                assignment = Assignment(
                    target=target.id,
                    value=stmt.value,
                    location=(stmt.lineno, stmt.col_offset),
                )
                self._check_expression(assignment.value)
                self._check_assignment_target(assignment)
                return
            if self._is_self_attribute_target(target):
                self._check_expression(stmt.value)
                self._check_self_member_assignment(target.attr, stmt.value, stmt.lineno)
                return
            raise SyntaxError(
                err(
                    "E2002",
                    stmt.lineno,
                    "only simple name assignment or `this.member` assignment is supported",
                    "Assign to one identifier target like `name = expr` or `this.name = expr`.",
                )
            )

        if isinstance(stmt, ast.AnnAssign):
            if not isinstance(stmt.target, ast.Name):
                raise SyntaxError(
                    err(
                        "E2003",
                        stmt.lineno,
                        "only simple name annotations are supported",
                        "Use `name: Type` or `name: Type = value`.",
                    )
                )
            if stmt.value is None:
                raise SyntaxError(
                    err(
                        "E2004",
                        stmt.lineno,
                        "standalone annotations are not valid runtime assignments",
                        "Use `var name: Type` in Tython syntax for empty declaration.",
                    )
                )
            self._check_expression(stmt.value)
            self._check_assignment_target(
                Assignment(
                    target=stmt.target.id,
                    value=stmt.value,
                    location=(stmt.lineno, stmt.col_offset),
                )
            )
            return

        if isinstance(stmt, ast.FunctionDef):
            self._check_function_decl(stmt)
            return

        if isinstance(stmt, ast.ClassDef):
            self._check_class_or_record_decl(stmt)
            return

        if isinstance(stmt, ast.If):
            cond_type = self._check_expression(stmt.test)
            if cond_type != "bool":
                raise SyntaxError(
                    err(
                        "E2037",
                        stmt.lineno,
                        "if condition must be bool",
                        "Use a boolean expression such as `count > 0`.",
                    )
                )
            self._with_block_scope(lambda: self._check_statements(stmt.body))
            self._with_block_scope(lambda: self._check_statements(stmt.orelse))
            return

        if isinstance(stmt, ast.Try):
            self._check_try_statement(stmt)
            return

        if isinstance(stmt, ast.For):
            raise SyntaxError(
                err(
                    "E2084",
                    stmt.lineno,
                    "for loops are not supported in v1",
                    "Use `while` loops only.",
                )
            )

        if isinstance(stmt, ast.While):
            cond_type = self._check_expression(stmt.test)
            if cond_type != "bool":
                raise SyntaxError(
                    err(
                        "E2038",
                        stmt.lineno,
                        "while condition must be bool",
                        "Use a boolean expression such as `ready == true`.",
                    )
                )
            self._loop_depth += 1
            try:
                self._with_block_scope(lambda: self._check_statements(stmt.body))
            finally:
                self._loop_depth -= 1
            self._with_block_scope(lambda: self._check_statements(stmt.orelse))
            return

        if isinstance(stmt, ast.Break):
            if self._loop_depth <= 0:
                raise SyntaxError(
                    err(
                        "E2085",
                        stmt.lineno,
                        "break is only valid inside while loops",
                        "Move `break` into a `while` body.",
                    )
                )
            return

        if isinstance(stmt, ast.Continue):
            if self._loop_depth <= 0:
                raise SyntaxError(
                    err(
                        "E2086",
                        stmt.lineno,
                        "continue is only valid inside while loops",
                        "Move `continue` into a `while` body.",
                    )
                )
            return

        if isinstance(stmt, ast.Pass):
            return

        if isinstance(stmt, ast.Raise):
            self._check_raise(stmt)
            return

        if isinstance(stmt, ast.Return):
            self._check_return(stmt)
            return

        if isinstance(stmt, ast.Expr):
            if not isinstance(stmt.value, ast.Call):
                raise SyntaxError(
                    err(
                        "E2088",
                        stmt.lineno,
                        "only call expressions are allowed as standalone statements",
                        "Use assignments/returns for non-call expressions.",
                    )
                )
            self._check_expression(stmt.value)
            return

        raise SyntaxError(
            err(
                "E2005",
                getattr(stmt, "lineno", 1),
                f"unsupported statement {type(stmt).__name__}",
                "Use Tython-supported statements only.",
            )
        )

    def _check_function_decl(self, stmt: ast.FunctionDef) -> None:
        self._ensure_supported_function_decorators(stmt)
        is_public = self._has_pub_decorator(stmt)

        if self._scopes[-1].kind != "module":
            raise SyntaxError(
                err(
                    "E2058",
                    stmt.lineno,
                    "nested function declarations are not allowed",
                    "Declare functions only at module scope.",
                )
            )

        if not VAR_NAME_RE.fullmatch(stmt.name):
            raise SyntaxError(
                err(
                    "E2059",
                    stmt.lineno,
                    f"invalid function name '{stmt.name}'",
                    "Use snake_case for function names.",
                )
            )

        if stmt.returns is None:
            raise SyntaxError(
                err(
                    "E2060",
                    stmt.lineno,
                    f"function '{stmt.name}' is missing return type",
                    "Add `-> Type` in function declaration.",
                )
            )

        return_type = annotation_to_custom_type(stmt.returns)
        self._validate_type_name(return_type, stmt.lineno)
        declared_throws = self._extract_declared_throws(stmt)
        for thrown_type in declared_throws:
            self._validate_type_name(thrown_type, stmt.lineno)
            if thrown_type not in self._record_decls:
                raise SyntaxError(
                    err(
                        "E2182",
                        stmt.lineno,
                        f"throws type '{thrown_type}' is not a declared record",
                        "Declare error records before using them in throws.",
                    )
                )
        raw_signature = self._extract_function_signature(stmt, return_type)
        signature = FunctionSignature(
            name=raw_signature.name,
            params=raw_signature.params,
            return_type=raw_signature.return_type,
            throws=declared_throws,
            is_public=is_public,
            location=(stmt.lineno, stmt.col_offset + 1),
        )

        self._declare_name(
            stmt.name,
            "const",
            None,
            stmt.lineno,
            initialized=True,
            location=(stmt.lineno, stmt.col_offset + 1),
            symbol_kind="function",
            is_public=is_public,
        )
        previous_callable = self._current_callable_name
        self._current_callable_name = stmt.name
        self._function_signatures[stmt.name] = signature

        function_id = self._next_function_id
        self._next_function_id += 1

        self._scopes.append(Scope(kind="function", function_id=function_id, symbols={}))
        self._return_type_stack.append(return_type)
        self._throws_stack.append(set(declared_throws))
        try:
            for param in signature.params:
                self._declare_name(
                    param.name,
                    "var",
                    param.type_name,
                    stmt.lineno,
                    initialized=True,
                    location=param.location,
                    symbol_kind="parameter",
                )
            self._check_statements(stmt.body)
            if return_type != "none" and not self._block_guarantees_return(stmt.body):
                raise SyntaxError(
                    err(
                        "E2061",
                        stmt.lineno,
                        f"function '{stmt.name}' may exit without returning {return_type}",
                        "Return a value on every reachable control path.",
                    )
                )
        finally:
            self._throws_stack.pop()
            self._return_type_stack.pop()
            self._scopes.pop()
            self._current_callable_name = previous_callable

    def _check_class_or_record_decl(self, stmt: ast.ClassDef) -> None:
        if self._scopes[-1].kind != "module":
            raise SyntaxError(
                err(
                    "E2100",
                    stmt.lineno,
                    "class/record declarations are only allowed at module scope",
                    "Declare classes and records at module scope.",
                )
            )

        self._check_type_name(stmt.name, stmt.lineno)

        marker = self._extract_record_marker(stmt)
        if marker is not None:
            self._check_record_decl(stmt, marker)
            return

        class_marker = self._extract_class_marker(stmt)
        if class_marker is not None:
            self._check_class_decl(stmt, class_marker)
            return

        raise SyntaxError(
            err(
                "E2101",
                stmt.lineno,
                f"class '{stmt.name}' is missing Tython declaration marker",
                "Use Tython `class` or `record` syntax instead of raw Python class syntax.",
            )
        )

    def _check_record_decl(self, stmt: ast.ClassDef, is_public: bool) -> None:
        self._record_symbol(
            name=stmt.name,
            qualified_name=stmt.name,
            kind="record",
            type_name=stmt.name,
            location=(stmt.lineno, stmt.col_offset + 1),
            parent_qname=None,
            is_public=is_public,
        )
        fields: list[RecordFieldDecl] = []
        seen_names: set[str] = set()
        for member_stmt in stmt.body:
            if self._is_record_marker_stmt(member_stmt):
                continue
            if not self._is_class_member_decl_stmt(member_stmt):
                raise SyntaxError(
                    err(
                        "E2102",
                        getattr(member_stmt, "lineno", stmt.lineno),
                        "records may contain only typed fields",
                        "Use only `name: Type` fields in records.",
                    )
                )
            member = self._extract_class_member_decl(member_stmt)
            if member.kind != "record_field":
                raise SyntaxError(
                    err(
                        "E2103",
                        member.location[0],
                        "invalid record member",
                        "Records allow typed fields only; no init/setup/pub/var/const/method bodies.",
                    )
                )
            if member.type_name is None:
                raise SyntaxError(
                    err(
                        "E2104",
                        member.location[0],
                        f"record field '{member.name}' requires a type annotation",
                        "Declare record fields as `name: Type`.",
                    )
                )
            if member.name in seen_names:
                raise SyntaxError(
                    err(
                        "E2105",
                        member.location[0],
                        f"duplicate record field '{member.name}'",
                        "Use unique record field names.",
                    )
                )
            seen_names.add(member.name)
            self._validate_type_name(member.type_name, member.location[0])
            fields.append(
                RecordFieldDecl(
                    name=member.name,
                    type_name=member.type_name,
                    location=member.location,
                )
            )
            self._record_symbol(
                name=member.name,
                qualified_name=f"{stmt.name}.{member.name}",
                kind="field",
                type_name=member.type_name,
                location=member.location,
                parent_qname=stmt.name,
                is_public=True,
            )

        record_decl = RecordDecl(
            name=stmt.name,
            fields=fields,
            is_public=is_public,
            location=(stmt.lineno, stmt.col_offset),
        )
        self._record_decls[stmt.name] = record_decl
        self._declare_name(
            stmt.name,
            "const",
            stmt.name,
            stmt.lineno,
            initialized=True,
            location=(stmt.lineno, stmt.col_offset + 1),
            symbol_kind="record",
            is_public=is_public,
        )

    def _check_class_decl(
        self, stmt: ast.ClassDef, marker: tuple[str | None, bool]
    ) -> None:
        conforms_to, is_public = marker
        if conforms_to is not None and "," in conforms_to:
            raise SyntaxError(
                err(
                    "E2106",
                    stmt.lineno,
                    "a class may conform to only one record in v1",
                    "Use a single record in `class Name is Record`.",
                )
            )

        self._record_symbol(
            name=stmt.name,
            qualified_name=stmt.name,
            kind="class",
            type_name=stmt.name,
            location=(stmt.lineno, stmt.col_offset + 1),
            parent_qname=None,
            is_public=is_public,
        )
        members: list[ClassMemberDecl] = []
        methods: dict[str, FunctionSignature] = {}
        setup_count = 0
        seen_members: set[str] = set()
        current_field_names: set[str] = set()

        for member_stmt in stmt.body:
            if self._is_class_marker_stmt(member_stmt):
                continue

            if self._is_class_member_decl_stmt(member_stmt):
                member = self._extract_class_member_decl(member_stmt)
                self._check_class_member_decl(member)
                if member.name in seen_members:
                    raise SyntaxError(
                        err(
                            "E2107",
                            member.location[0],
                            f"duplicate class member '{member.name}'",
                            "Use unique class member names.",
                        )
                    )
                seen_members.add(member.name)
                members.append(member)
                current_field_names.add(member.name)
                self._record_symbol(
                    name=member.name,
                    qualified_name=f"{stmt.name}.{member.name}",
                    kind="field",
                    type_name=member.type_name,
                    location=member.location,
                    parent_qname=stmt.name,
                    is_public=member.is_public,
                )
                continue

            if isinstance(member_stmt, ast.FunctionDef):
                self._sync_pending_class_member_context(
                    current_field_names, methods, members
                )
                if member_stmt.name == SETUP_METHOD_NAME:
                    setup_count += 1
                    self._record_symbol(
                        name=SETUP_METHOD_NAME,
                        qualified_name=f"{stmt.name}.{SETUP_METHOD_NAME}",
                        kind="method",
                        type_name="none",
                        location=(member_stmt.lineno, member_stmt.col_offset + 1),
                        parent_qname=stmt.name,
                        is_public=False,
                    )
                    self._check_setup_method(member_stmt, stmt.name)
                    continue
                self._record_symbol(
                    name=member_stmt.name,
                    qualified_name=f"{stmt.name}.{member_stmt.name}",
                    kind="method",
                    type_name=None,
                    location=(member_stmt.lineno, member_stmt.col_offset + 1),
                    parent_qname=stmt.name,
                    is_public=self._has_pub_decorator(member_stmt),
                )
                signature = self._check_class_method_decl(member_stmt, stmt.name)
                if signature.name in methods:
                    raise SyntaxError(
                        err(
                            "E2108",
                            member_stmt.lineno,
                            f"duplicate method '{signature.name}' in class '{stmt.name}'",
                            "Use unique method names.",
                        )
                    )
                methods[signature.name] = signature
                continue

            raise SyntaxError(
                err(
                    "E2109",
                    getattr(member_stmt, "lineno", stmt.lineno),
                    "unsupported class member",
                    "Use init/var/const members, methods, and optional setup block only.",
                )
            )

        if setup_count > 1:
            raise SyntaxError(
                err(
                    "E2110",
                    stmt.lineno,
                    "class may define at most one setup block",
                    "Keep a single `setup` block per class.",
                )
            )

        self._current_class_member_map = {}

        class_decl = ClassDecl(
            name=stmt.name,
            conforms_to=conforms_to,
            is_public=is_public,
            members=members,
            methods=methods,
            setup_count=setup_count,
            location=(stmt.lineno, stmt.col_offset),
        )
        self._class_decls[stmt.name] = class_decl
        self._declare_name(
            stmt.name,
            "const",
            stmt.name,
            stmt.lineno,
            initialized=True,
            location=(stmt.lineno, stmt.col_offset + 1),
            symbol_kind="class",
            is_public=is_public,
        )
        self._check_class_conformance(class_decl, stmt.lineno)

    def _check_class_member_decl(self, member: ClassMemberDecl) -> None:
        if member.kind == "record_field":
            raise SyntaxError(
                err(
                    "E2111",
                    member.location[0],
                    "record field declarations are not allowed in classes",
                    "Use class members (`init var`, `init const`, `var`, `const`) inside classes.",
                )
            )

        if member.kind in {"init_var", "init_const"} and not member.is_public:
            raise SyntaxError(
                err(
                    "E2112",
                    member.location[0],
                    "init fields are always public",
                    "Remove explicit private/public modifiers from init fields.",
                )
            )

        if member.type_name is None:
            raise SyntaxError(
                err(
                    "E2113",
                    member.location[0],
                    f"class member '{member.name}' requires a type annotation",
                    "Declare class members as `name: Type`.",
                )
            )
        self._validate_type_name(member.type_name, member.location[0])

        if member.kind == "const" and not member.has_initializer:
            raise SyntaxError(
                err(
                    "E2114",
                    member.location[0],
                    f"class const field '{member.name}' requires a default value in v1",
                    "Provide `= value` or use `init const`.",
                )
            )

        if member.has_initializer and member.initializer is not None:
            init_type = self._check_expression(member.initializer)
            if not self._is_type_compatible(member.type_name, init_type):
                raise SyntaxError(
                    err(
                        "E2115",
                        member.location[0],
                        f"initializer type mismatch for class member '{member.name}'",
                        f"Expected {member.type_name} but got {init_type}.",
                    )
                )

    def _check_setup_method(self, stmt: ast.FunctionDef, class_name: str) -> None:
        self._ensure_supported_function_decorators(stmt)
        declared_throws = self._extract_declared_throws(stmt)
        if declared_throws:
            raise SyntaxError(
                err(
                    "E2183",
                    stmt.lineno,
                    "setup cannot declare throws",
                    "Handle setup errors inside setup or panic explicitly.",
                )
            )
        if self._has_pub_decorator(stmt):
            raise SyntaxError(
                err(
                    "E2116",
                    stmt.lineno,
                    "`setup` cannot be public",
                    "Use bare `setup { ... }` only.",
                )
            )
        if stmt.returns is None or annotation_to_custom_type(stmt.returns) != "none":
            raise SyntaxError(
                err(
                    "E2117",
                    stmt.lineno,
                    "setup must return none",
                    "Use `setup { ... }` with implicit none return.",
                )
            )
        if len(stmt.args.args) != 1 or stmt.args.args[0].arg != "self":
            raise SyntaxError(
                err(
                    "E2118",
                    stmt.lineno,
                    "setup must be parameterless",
                    "Use `setup { ... }` with no parameters.",
                )
            )

        previous_callable = self._current_callable_name
        self._current_callable_name = f"{class_name}.setup"
        previous = self._begin_class_callable_scope(
            class_name=class_name,
            lineno=stmt.lineno,
            return_type="none",
        )
        self._throws_stack.append(set())
        try:
            self._check_statements(stmt.body)
        finally:
            self._throws_stack.pop()
            self._end_class_callable_scope(previous)
            self._current_callable_name = previous_callable

    def _check_class_method_decl(
        self, stmt: ast.FunctionDef, class_name: str
    ) -> FunctionSignature:
        self._ensure_supported_function_decorators(stmt)
        is_public = self._has_pub_decorator(stmt)

        if not VAR_NAME_RE.fullmatch(stmt.name):
            raise SyntaxError(
                err(
                    "E2119",
                    stmt.lineno,
                    f"invalid method name '{stmt.name}'",
                    "Use snake_case for class methods.",
                )
            )
        if stmt.returns is None:
            raise SyntaxError(
                err(
                    "E2120",
                    stmt.lineno,
                    f"method '{stmt.name}' is missing return type",
                    "Add `-> Type` to method declaration.",
                )
            )

        return_type = annotation_to_custom_type(stmt.returns)
        self._validate_type_name(return_type, stmt.lineno)
        signature = self._extract_method_signature(
            stmt, return_type, is_public=is_public
        )
        declared_throws = self._extract_declared_throws(stmt)
        for thrown_type in declared_throws:
            self._validate_type_name(thrown_type, stmt.lineno)
            if thrown_type not in self._record_decls:
                raise SyntaxError(
                    err(
                        "E2182",
                        stmt.lineno,
                        f"throws type '{thrown_type}' is not a declared record",
                        "Declare error records before using them in throws.",
                    )
                )
        signature = FunctionSignature(
            name=signature.name,
            params=signature.params,
            return_type=signature.return_type,
            throws=declared_throws,
            is_public=signature.is_public,
            location=(stmt.lineno, stmt.col_offset + 1),
        )

        previous_callable = self._current_callable_name
        self._current_callable_name = f"{class_name}.{stmt.name}"
        previous = self._begin_class_callable_scope(
            class_name=class_name,
            lineno=stmt.lineno,
            return_type=return_type,
            method_names=self._class_method_names | {stmt.name},
            field_names=self._class_field_names,
        )
        self._throws_stack.append(set(declared_throws))
        try:
            for param in signature.params:
                self._declare_name(
                    param.name,
                    "var",
                    param.type_name,
                    stmt.lineno,
                    initialized=True,
                )
            self._check_statements(stmt.body)
            if return_type != "none" and not self._block_guarantees_return(stmt.body):
                raise SyntaxError(
                    err(
                        "E2121",
                        stmt.lineno,
                        f"method '{stmt.name}' may exit without returning {return_type}",
                        "Return a value on every reachable control path.",
                    )
                )
        finally:
            self._throws_stack.pop()
            self._end_class_callable_scope(previous)
            self._current_callable_name = previous_callable

        return signature

    def _sync_pending_class_member_context(
        self,
        current_field_names: set[str],
        methods: dict[str, FunctionSignature],
        members: list[ClassMemberDecl],
    ) -> None:
        self._class_field_names = set(current_field_names)
        self._class_method_names = set(methods.keys())
        self._current_class_member_map = {member.name: member for member in members}

    def _begin_class_callable_scope(
        self,
        *,
        class_name: str,
        lineno: int,
        return_type: str,
        method_names: set[str] | None = None,
        field_names: set[str] | None = None,
    ) -> tuple[str | None, set[str], set[str], dict[str, ClassMemberDecl]]:
        previous_class = self._current_class_name
        previous_method_names = self._class_method_names
        previous_field_names = self._class_field_names
        previous_member_map = self._current_class_member_map

        self._current_class_name = class_name
        if method_names is not None:
            self._class_method_names = set(method_names)
        if field_names is not None:
            self._class_field_names = set(field_names)

        function_id = self._next_function_id
        self._next_function_id += 1
        self._scopes.append(Scope(kind="function", function_id=function_id, symbols={}))
        self._return_type_stack.append(return_type)
        self._declare_name(
            "self",
            "const",
            class_name,
            lineno,
            initialized=True,
            location=(lineno, 1),
            symbol_kind="parameter",
        )
        return (
            previous_class,
            previous_method_names,
            previous_field_names,
            previous_member_map,
        )

    def _end_class_callable_scope(
        self,
        previous: tuple[str | None, set[str], set[str], dict[str, ClassMemberDecl]],
    ) -> None:
        (
            previous_class,
            previous_method_names,
            previous_field_names,
            previous_member_map,
        ) = previous
        self._return_type_stack.pop()
        self._scopes.pop()
        self._current_class_name = previous_class
        self._class_method_names = previous_method_names
        self._class_field_names = previous_field_names
        self._current_class_member_map = previous_member_map

    def _check_class_conformance(self, class_decl: ClassDecl, lineno: int) -> None:
        if class_decl.conforms_to is None:
            return
        record_decl = self._record_decls.get(class_decl.conforms_to)
        if record_decl is None:
            raise SyntaxError(
                err(
                    "E2122",
                    lineno,
                    f"class '{class_decl.name}' conforms to unknown record '{class_decl.conforms_to}'",
                    "Declare the record before using `is` conformance.",
                )
            )

        member_map = {member.name: member for member in class_decl.members}
        for field in record_decl.fields:
            member = member_map.get(field.name)
            method = class_decl.methods.get(field.name)
            if is_function_type(field.type_name):
                if method is not None:
                    if not method.is_public:
                        raise SyntaxError(
                            err(
                                "E2123",
                                lineno,
                                f"private method '{field.name}' cannot satisfy public record requirement",
                                "Mark method as `pub func`.",
                            )
                        )
                    if not function_type_matches_signature(
                        field.type_name, method, lineno
                    ):
                        raise SyntaxError(
                            err(
                                "E2124",
                                lineno,
                                f"method '{field.name}' does not match required record function type",
                                f"Expected {field.type_name}.",
                            )
                        )
                    continue
                if member is None or not member.is_public:
                    raise SyntaxError(
                        err(
                            "E2125",
                            lineno,
                            f"class '{class_decl.name}' is missing public member '{field.name}' required by record '{record_decl.name}'",
                            "Add a matching public method/member to satisfy conformance.",
                        )
                    )
                if member.type_name is None or member.type_name != field.type_name:
                    raise SyntaxError(
                        err(
                            "E2126",
                            lineno,
                            f"member '{field.name}' type mismatch for record conformance",
                            f"Expected {field.type_name}.",
                        )
                    )
                continue

            if member is None or not member.is_public:
                raise SyntaxError(
                    err(
                        "E2127",
                        lineno,
                        f"class '{class_decl.name}' is missing public field '{field.name}' required by record '{record_decl.name}'",
                        "Add matching public field or init field.",
                    )
                )
            if member.type_name is None or member.type_name != field.type_name:
                raise SyntaxError(
                    err(
                        "E2128",
                        lineno,
                        f"field '{field.name}' type mismatch for record conformance",
                        f"Expected {field.type_name}.",
                    )
                )

    def _extract_function_signature(
        self, stmt: ast.FunctionDef, return_type: str
    ) -> FunctionSignature:
        args = stmt.args
        if args.posonlyargs:
            raise SyntaxError(
                err(
                    "E2062",
                    stmt.lineno,
                    "positional-only function parameters are not supported",
                    "Use standard named parameters.",
                )
            )
        if args.vararg is not None or args.kwarg is not None or args.kwonlyargs:
            raise SyntaxError(
                err(
                    "E2063",
                    stmt.lineno,
                    "varargs/keyword-only parameters are not supported",
                    "Use fixed parameter lists in v1.",
                )
            )

        params: list[FunctionParam] = []
        seen: set[str] = set()
        defaults_start = len(args.args) - len(args.defaults)
        seen_default = False

        for index, arg in enumerate(args.args):
            if arg.annotation is None:
                raise SyntaxError(
                    err(
                        "E2064",
                        arg.lineno,
                        f"parameter '{arg.arg}' is missing a type",
                        "Declare every parameter as `name: Type`.",
                    )
                )

            if arg.arg in seen:
                raise SyntaxError(
                    err(
                        "E2065",
                        arg.lineno,
                        f"duplicate parameter name '{arg.arg}'",
                        "Use unique names for function parameters.",
                    )
                )
            seen.add(arg.arg)

            type_name = annotation_to_custom_type(arg.annotation)
            self._validate_type_name(type_name, arg.lineno)

            has_default = index >= defaults_start
            if has_default:
                seen_default = True
                default_expr = args.defaults[index - defaults_start]
                default_type = self._check_expression(default_expr)
                if not self._is_type_compatible(type_name, default_type):
                    raise SyntaxError(
                        err(
                            "E2066",
                            arg.lineno,
                            f"default value type mismatch for parameter '{arg.arg}'",
                            f"Expected {type_name} but got {default_type}.",
                        )
                    )
            elif seen_default:
                raise SyntaxError(
                    err(
                        "E2067",
                        arg.lineno,
                        "required parameters must come before defaulted parameters",
                        "Move parameters without defaults before defaulted ones.",
                    )
                )

            params.append(
                FunctionParam(
                    name=arg.arg,
                    type_name=type_name,
                    has_default=has_default,
                    location=(arg.lineno, arg.col_offset + 1),
                )
            )

        return FunctionSignature(
            name=stmt.name,
            params=params,
            return_type=return_type,
            location=(stmt.lineno, stmt.col_offset + 1),
        )

    def _extract_method_signature(
        self, stmt: ast.FunctionDef, return_type: str, *, is_public: bool
    ) -> FunctionSignature:
        args = stmt.args
        if (
            args.posonlyargs
            or args.vararg is not None
            or args.kwarg is not None
            or args.kwonlyargs
        ):
            raise SyntaxError(
                err(
                    "E2129",
                    stmt.lineno,
                    "unsupported method parameter form",
                    "Use fixed named method parameters in v1.",
                )
            )

        if not args.args or args.args[0].arg != "self":
            raise SyntaxError(
                err(
                    "E2130",
                    stmt.lineno,
                    "methods must declare implicit receiver as `this`",
                    "Declare methods with Tython syntax; receiver is injected automatically.",
                )
            )
        if args.args[0].annotation is not None:
            raise SyntaxError(
                err(
                    "E2131",
                    stmt.lineno,
                    "method receiver must not be annotated",
                    "Do not annotate the implicit receiver.",
                )
            )

        params: list[FunctionParam] = []
        seen: set[str] = set()
        method_args = args.args[1:]
        defaults_start = len(method_args) - len(args.defaults)
        seen_default = False

        for index, arg in enumerate(method_args):
            if arg.annotation is None:
                raise SyntaxError(
                    err(
                        "E2132",
                        arg.lineno,
                        f"parameter '{arg.arg}' is missing a type",
                        "Declare every method parameter as `name: Type`.",
                    )
                )
            if arg.arg in seen:
                raise SyntaxError(
                    err(
                        "E2133",
                        arg.lineno,
                        f"duplicate parameter name '{arg.arg}'",
                        "Use unique method parameter names.",
                    )
                )
            seen.add(arg.arg)
            type_name = annotation_to_custom_type(arg.annotation)
            self._validate_type_name(type_name, arg.lineno)

            has_default = index >= defaults_start
            if has_default:
                seen_default = True
                default_expr = args.defaults[index - defaults_start]
                default_type = self._check_expression(default_expr)
                if not self._is_type_compatible(type_name, default_type):
                    raise SyntaxError(
                        err(
                            "E2134",
                            arg.lineno,
                            f"default value type mismatch for parameter '{arg.arg}'",
                            f"Expected {type_name} but got {default_type}.",
                        )
                    )
            elif seen_default:
                raise SyntaxError(
                    err(
                        "E2135",
                        arg.lineno,
                        "required parameters must come before defaulted parameters",
                        "Move parameters without defaults before defaulted ones.",
                    )
                )
            params.append(
                FunctionParam(
                    name=arg.arg,
                    type_name=type_name,
                    has_default=has_default,
                    location=(arg.lineno, arg.col_offset + 1),
                )
            )

        return FunctionSignature(
            name=stmt.name,
            params=params,
            return_type=return_type,
            is_public=is_public,
            location=(stmt.lineno, stmt.col_offset + 1),
        )

    def _has_pub_decorator(self, stmt: ast.FunctionDef) -> bool:
        return any(
            isinstance(dec, ast.Name) and dec.id == PUB_DECORATOR_SENTINEL
            for dec in stmt.decorator_list
        )

    def _ensure_supported_function_decorators(self, stmt: ast.FunctionDef) -> None:
        for decorator in stmt.decorator_list:
            if (
                isinstance(decorator, ast.Name)
                and decorator.id == PUB_DECORATOR_SENTINEL
            ):
                continue
            if (
                isinstance(decorator, ast.Call)
                and isinstance(decorator.func, ast.Name)
                and decorator.func.id == THROWS_DECORATOR_SENTINEL
                and all(
                    isinstance(arg, ast.Constant) and isinstance(arg.value, str)
                    for arg in decorator.args
                )
                and not decorator.keywords
            ):
                continue
            raise SyntaxError(
                err(
                    "E2136",
                    getattr(stmt, "lineno", 1),
                    "unsupported function decorator",
                    "Only internal `pub` and `throws` metadata decorators are supported.",
                )
            )

    def _extract_declared_throws(self, stmt: ast.FunctionDef) -> list[str]:
        declared: list[str] = []
        seen: set[str] = set()
        for decorator in stmt.decorator_list:
            if not isinstance(decorator, ast.Call):
                continue
            if not isinstance(decorator.func, ast.Name):
                continue
            if decorator.func.id != THROWS_DECORATOR_SENTINEL:
                continue
            if decorator.keywords:
                raise SyntaxError(
                    err(
                        "E2184",
                        stmt.lineno,
                        "throws decorator metadata must use positional type names",
                        "Use internal throws metadata as generated by frontend.",
                    )
                )
            for arg in decorator.args:
                if not isinstance(arg, ast.Constant) or not isinstance(arg.value, str):
                    raise SyntaxError(
                        err(
                            "E2184",
                            stmt.lineno,
                            "throws decorator metadata must use string type names",
                            "Use internal throws metadata as generated by frontend.",
                        )
                    )
                if arg.value in seen:
                    raise SyntaxError(
                        err(
                            "E2185",
                            stmt.lineno,
                            f"duplicate throws type '{arg.value}'",
                            "List each throws type once.",
                        )
                    )
                seen.add(arg.value)
                declared.append(arg.value)
        return declared

    def _is_record_marker_stmt(self, stmt: ast.stmt) -> bool:
        return (
            isinstance(stmt, ast.Expr)
            and isinstance(stmt.value, ast.Call)
            and isinstance(stmt.value.func, ast.Name)
            and stmt.value.func.id == RECORD_MARKER_SENTINEL
        )

    def _is_class_marker_stmt(self, stmt: ast.stmt) -> bool:
        return (
            isinstance(stmt, ast.Expr)
            and isinstance(stmt.value, ast.Call)
            and isinstance(stmt.value.func, ast.Name)
            and stmt.value.func.id == CLASS_MARKER_SENTINEL
        )

    def _extract_record_marker(self, stmt: ast.ClassDef) -> bool | None:
        for member in stmt.body:
            if not self._is_record_marker_stmt(member):
                continue
            call = member.value
            assert isinstance(call, ast.Call)
            if len(call.args) != 1 or call.keywords:
                raise SyntaxError(err("E2137", stmt.lineno, "invalid record marker"))
            arg = call.args[0]
            if not isinstance(arg, ast.Constant) or not isinstance(arg.value, bool):
                raise SyntaxError(
                    err("E2138", stmt.lineno, "invalid record visibility marker")
                )
            return arg.value
        return None

    def _extract_class_marker(
        self, stmt: ast.ClassDef
    ) -> tuple[str | None, bool] | None:
        for member in stmt.body:
            if not self._is_class_marker_stmt(member):
                continue
            call = member.value
            assert isinstance(call, ast.Call)
            if len(call.args) != 2 or call.keywords:
                raise SyntaxError(err("E2139", stmt.lineno, "invalid class marker"))
            conformance, is_public = call.args
            if not isinstance(conformance, ast.Constant) or (
                conformance.value is not None and not isinstance(conformance.value, str)
            ):
                raise SyntaxError(
                    err("E2140", stmt.lineno, "invalid class conformance marker")
                )
            if not isinstance(is_public, ast.Constant) or not isinstance(
                is_public.value, bool
            ):
                raise SyntaxError(
                    err("E2141", stmt.lineno, "invalid class visibility marker")
                )
            return conformance.value, is_public.value
        return None

    def _is_class_member_decl_stmt(self, stmt: ast.stmt) -> bool:
        return (
            isinstance(stmt, ast.Expr)
            and isinstance(stmt.value, ast.Call)
            and isinstance(stmt.value.func, ast.Name)
            and stmt.value.func.id == CLASS_MEMBER_SENTINEL
        )

    def _extract_class_member_decl(self, stmt: ast.stmt) -> ClassMemberDecl:
        call = stmt.value
        assert isinstance(call, ast.Call)
        if len(call.args) != 7 or call.keywords:
            raise SyntaxError(
                err(
                    "E2142",
                    getattr(stmt, "lineno", 1),
                    "internal class member IR shape is invalid",
                    "Report this as an internal parser bug.",
                )
            )
        kind, name, type_name, initializer, has_init, is_public, in_class = call.args
        if not isinstance(kind, ast.Constant) or not isinstance(kind.value, str):
            raise SyntaxError(
                err("E2143", stmt.lineno, "class member kind must be string")
            )
        if not isinstance(name, ast.Constant) or not isinstance(name.value, str):
            raise SyntaxError(
                err("E2144", stmt.lineno, "class member name must be string")
            )
        if not isinstance(type_name, ast.Constant) or (
            type_name.value is not None and not isinstance(type_name.value, str)
        ):
            raise SyntaxError(
                err("E2145", stmt.lineno, "class member type must be string/none")
            )
        if not isinstance(has_init, ast.Constant) or not isinstance(
            has_init.value, bool
        ):
            raise SyntaxError(
                err("E2146", stmt.lineno, "class member initializer flag must be bool")
            )
        if not isinstance(is_public, ast.Constant) or not isinstance(
            is_public.value, bool
        ):
            raise SyntaxError(
                err("E2147", stmt.lineno, "class member public flag must be bool")
            )
        if not isinstance(in_class, ast.Constant) or not isinstance(
            in_class.value, bool
        ):
            raise SyntaxError(
                err(
                    "E2148", stmt.lineno, "class member class-context flag must be bool"
                )
            )
        if not in_class.value:
            raise SyntaxError(
                err("E2149", stmt.lineno, "class member declaration used outside class")
            )
        return ClassMemberDecl(
            kind=kind.value,
            name=name.value,
            type_name=type_name.value,
            initializer=initializer,
            has_initializer=has_init.value,
            is_public=is_public.value,
            location=(stmt.lineno, stmt.col_offset),
        )

    def _check_return(self, stmt: ast.Return) -> None:
        if not self._return_type_stack:
            raise SyntaxError(
                err(
                    "E2068",
                    stmt.lineno,
                    "return is only valid inside functions",
                    "Move `return` inside a function body.",
                )
            )

        expected = self._return_type_stack[-1]
        if stmt.value is None:
            raise SyntaxError(
                err(
                    "E2069",
                    stmt.lineno,
                    "bare return is not allowed",
                    "Use `return none` for none-returning functions.",
                )
            )

        actual = self._check_expression(stmt.value)
        if expected == "none":
            if actual != "none":
                raise SyntaxError(
                    err(
                        "E2070",
                        stmt.lineno,
                        "none-returning function must return none",
                        "Use `return none` or omit return at end.",
                    )
                )
            return

        if not self._is_type_compatible(expected, actual):
            raise SyntaxError(
                err(
                    "E2071",
                    stmt.lineno,
                    f"return type mismatch: expected {expected}, got {actual}",
                    "Return a value that matches the declared return type.",
                )
            )

    def _check_try_statement(self, stmt: ast.Try) -> None:
        handled_types: set[str] = set()
        catch_all = False
        bound_types: list[str] = []

        for index, handler in enumerate(stmt.handlers):
            bound_type, is_catch_all = self._analyze_except_handler(
                handler=handler,
                index=index,
                total=len(stmt.handlers),
            )
            if is_catch_all:
                catch_all = True
            elif catch_all:
                raise SyntaxError(
                    err(
                        "E2173",
                        handler.lineno,
                        "typed catch cannot appear after catch-all",
                        "Move catch-all handler to the last catch clause.",
                    )
                )
            if bound_type != RECOVERABLE_ERROR_BASE_NAME:
                handled_types.add(bound_type)
            bound_types.append(bound_type)

        self._try_context_stack.append(
            TryContext(handled_types=handled_types, catch_all=catch_all)
        )
        try:
            self._with_block_scope(lambda: self._check_statements(stmt.body))
        finally:
            self._try_context_stack.pop()

        for handler, bound_type in zip(stmt.handlers, bound_types):
            self._with_block_scope(
                lambda handler=handler, bound_type=bound_type: (
                    self._check_except_handler_body(handler, bound_type)
                )
            )

        self._with_block_scope(lambda: self._check_statements(stmt.orelse))
        self._with_block_scope(lambda: self._check_statements(stmt.finalbody))

    def _analyze_except_handler(
        self, *, handler: ast.ExceptHandler, index: int, total: int
    ) -> tuple[str, bool]:
        catch_type = handler.type
        if catch_type is None:
            if index != total - 1:
                raise SyntaxError(
                    err(
                        "E2174",
                        handler.lineno,
                        "catch-all handler must be last",
                        "Move catch-all handler to the end of catch clauses.",
                    )
                )
            return RECOVERABLE_ERROR_BASE_NAME, True

        if not isinstance(catch_type, ast.Name):
            raise SyntaxError(
                err(
                    "E2175",
                    handler.lineno,
                    "catch type must be a named error record",
                    "Use `catch err: ErrorType { ... }`.",
                )
            )

        if catch_type.id == RECOVERABLE_ERROR_BASE_NAME:
            if index != total - 1:
                raise SyntaxError(
                    err(
                        "E2174",
                        handler.lineno,
                        "catch-all handler must be last",
                        "Move catch-all handler to the end of catch clauses.",
                    )
                )
            return RECOVERABLE_ERROR_BASE_NAME, True

        if catch_type.id not in self._record_decls:
            raise SyntaxError(
                err(
                    "E2176",
                    handler.lineno,
                    f"catch type '{catch_type.id}' is not a declared record",
                    "Declare error records before using them in catch clauses.",
                )
            )
        return catch_type.id, False

    def _check_except_handler_body(
        self, handler: ast.ExceptHandler, bound_type: str
    ) -> None:
        if handler.name:
            self._declare_name(
                handler.name,
                "const",
                bound_type,
                handler.lineno,
                initialized=True,
            )
        self._check_statements(handler.body)

    def _check_raise(self, stmt: ast.Raise) -> None:
        if stmt.exc is None:
            raise SyntaxError(
                err(
                    "E2177",
                    stmt.lineno,
                    "raise requires an error value",
                    "Use `raise ErrorType { ... }`.",
                )
            )

        if stmt.cause is not None:
            raise SyntaxError(
                err(
                    "E2178",
                    stmt.lineno,
                    "`raise ... from ...` is not supported",
                    "Raise recoverable errors directly without `from`.",
                )
            )

        error_type = self._check_expression(stmt.exc)
        if error_type is None or error_type not in self._record_decls:
            raise SyntaxError(
                err(
                    "E2179",
                    stmt.lineno,
                    "raised value must be a declared error record",
                    "Raise values of record error types only.",
                )
            )

        declared_throws = self._throws_stack[-1] if self._throws_stack else set()
        if error_type in declared_throws:
            return
        if self._is_error_handled_in_try_context(error_type):
            return
        if not self._throws_stack:
            raise SyntaxError(
                err(
                    "E2180",
                    stmt.lineno,
                    f"raise of '{error_type}' is not allowed at module scope",
                    "Handle this error inside a try/catch block.",
                )
            )
        raise SyntaxError(
            err(
                "E2181",
                stmt.lineno,
                f"raised error '{error_type}' is not declared in throws clause",
                "Add it to `throws` or handle it with try/catch.",
            )
        )

    def _is_error_handled_in_try_context(self, error_type: str) -> bool:
        for context in reversed(self._try_context_stack):
            if context.catch_all:
                return True
            if error_type in context.handled_types:
                return True
        return False

    def _is_throw_set_handled_in_try_context(self, throws: set[str]) -> bool:
        if not throws:
            return True
        for context in reversed(self._try_context_stack):
            if context.catch_all:
                return True
            if throws.issubset(context.handled_types):
                return True
        return False

    def _block_guarantees_return(self, body: list[ast.stmt]) -> bool:
        for stmt in body:
            if self._statement_guarantees_return(stmt):
                return True
        return False

    def _statement_guarantees_return(self, stmt: ast.stmt) -> bool:
        if isinstance(stmt, ast.Return):
            return True
        if isinstance(stmt, ast.Raise):
            return True
        if isinstance(stmt, ast.If):
            if not stmt.orelse:
                return False
            return self._block_guarantees_return(
                stmt.body
            ) and self._block_guarantees_return(stmt.orelse)
        if isinstance(stmt, ast.Try):
            if stmt.finalbody and self._block_guarantees_return(stmt.finalbody):
                return True
            normal_path_returns = self._block_guarantees_return(stmt.body)
            if stmt.orelse:
                normal_path_returns = (
                    normal_path_returns or self._block_guarantees_return(stmt.orelse)
                )
            handlers_return = bool(stmt.handlers) and all(
                self._block_guarantees_return(handler.body) for handler in stmt.handlers
            )
            return normal_path_returns and (not stmt.handlers or handlers_return)
        return False

    def _check_for_loop_block(
        self,
        target: ast.expr,
        body: list[ast.stmt],
        orelse: list[ast.stmt],
        lineno: int,
    ) -> None:
        if not isinstance(target, ast.Name):
            raise SyntaxError(
                err(
                    "E2008",
                    lineno,
                    "only simple loop variables are supported",
                    "Use a single identifier loop variable.",
                )
            )
        self._declare_name(
            target.id,
            "var",
            None,
            lineno,
            initialized=True,
            location=(target.lineno, target.col_offset + 1),
            symbol_kind="variable",
        )
        self._check_statements(body)
        self._with_block_scope(lambda: self._check_statements(orelse))

    def _check_expression(self, expr: ast.expr) -> str | None:
        if isinstance(expr, ast.NamedExpr):
            raise SyntaxError(
                err(
                    "E2039",
                    getattr(expr, "lineno", 1),
                    "assignment expressions are not allowed",
                    "Use assignment as a separate statement.",
                )
            )

        if isinstance(expr, ast.Name):
            symbol = self._resolve_name(
                expr.id,
                expr.lineno,
                for_write=False,
                require_initialized=True,
                location=(expr.lineno, expr.col_offset + 1),
            )
            matrix_rank, matrix_element_type = self._matrix_info_for_symbol(symbol)
            self._set_matrix_expr_info(
                expr, matrix_rank=matrix_rank, matrix_element_type=matrix_element_type
            )
            return symbol.type_name

        if self._is_record_literal_expr(expr):
            return self._check_record_literal_expression(expr)

        if isinstance(expr, ast.Constant):
            return self._infer_constant_type(expr)

        if isinstance(expr, ast.JoinedStr):
            for part in expr.values:
                if isinstance(part, ast.FormattedValue):
                    self._check_expression(part.value)
                    if part.format_spec is not None:
                        self._check_expression(part.format_spec)
            return "str"

        if isinstance(expr, ast.FormattedValue):
            self._check_expression(expr.value)
            if expr.format_spec is not None:
                self._check_expression(expr.format_spec)
            return "str"

        if isinstance(expr, ast.List):
            element_types: set[str] = set()
            for element in expr.elts:
                element_type = self._check_expression(element)
                if element_type is not None:
                    element_types.add(element_type)
            if len(element_types) > 1:
                raise SyntaxError(
                    err(
                        "E2009",
                        expr.lineno,
                        "mixed-type list literal is not supported",
                        "Use elements of one consistent type per list literal.",
                    )
                )
            if not element_types:
                return "unknown[]"
            return f"{next(iter(element_types))}[]"

        if isinstance(expr, ast.UnaryOp):
            operand_type = self._check_expression(expr.operand)
            if isinstance(expr.op, ast.Not):
                if operand_type != "bool":
                    raise SyntaxError(
                        err(
                            "E2040",
                            expr.lineno,
                            "operator `not` requires bool operand",
                            "Use a boolean expression before `not`.",
                        )
                    )
                return "bool"
            if isinstance(expr.op, ast.USub):
                if operand_type not in {"int", "float"}:
                    raise SyntaxError(
                        err(
                            "E2041",
                            expr.lineno,
                            "unary `-` requires numeric operand",
                            "Use int or float with unary minus.",
                        )
                    )
                return operand_type
            raise SyntaxError(
                err(
                    "E2042",
                    expr.lineno,
                    f"unsupported unary operator {type(expr.op).__name__}",
                    "Only `-` and `not` are supported unary operators.",
                )
            )

        if isinstance(expr, ast.BinOp):
            return self._check_binop(expr)

        if isinstance(expr, ast.BoolOp):
            if not isinstance(expr.op, (ast.And, ast.Or)):
                raise SyntaxError(
                    err(
                        "E2043",
                        expr.lineno,
                        "unsupported boolean operator",
                        "Use `and` or `or`.",
                    )
                )
            for value in expr.values:
                value_type = self._check_expression(value)
                if value_type != "bool":
                    raise SyntaxError(
                        err(
                            "E2044",
                            expr.lineno,
                            "boolean operators require bool operands",
                            "Use bool expressions with `and`/`or`.",
                        )
                    )
            return "bool"

        if isinstance(expr, ast.IfExp):
            return self._check_ternary_expression(expr)

        if isinstance(expr, ast.Compare):
            return self._check_compare(expr)

        if isinstance(expr, ast.Call):
            return self._check_call(expr)

        if isinstance(expr, ast.Attribute):
            if isinstance(expr.value, ast.Name):
                symbol = self._lookup_symbol(expr.value.id)
                if symbol is not None and symbol.type_name == "Module":
                    member = self._lookup_symbol(f"{expr.value.id}.{expr.attr}")
                    if member is not None:
                        self._record_reference(
                            name=expr.attr,
                            qualified_name=member.qualified_name,
                            location=self._attribute_location(expr),
                            kind="read",
                        )
                        return member.type_name
                if symbol is not None and symbol.py_module is not None:
                    stubs = self._stub_index()
                    if stubs is not None:
                        sig = stubs.lookup_function(symbol.py_module, expr.attr)
                        if sig is not None:
                            return signature_to_function_type(sig)
                        var_type = stubs.lookup_variable(symbol.py_module, expr.attr)
                        if var_type is not None:
                            return var_type

            value_type = self._check_expression(expr.value)
            if value_type == "Matrix":
                matrix_rank, matrix_element_type = self._matrix_info_for_expr(
                    expr.value
                )
                if expr.attr in MATRIX_PROPERTIES:
                    if expr.attr == "rows" or expr.attr == "cols":
                        if matrix_rank == 1:
                            raise SyntaxError(
                                err(
                                    "E2150",
                                    expr.lineno,
                                    f".{expr.attr} only works on rank-2 Matrix values",
                                    f"This Matrix has rank {matrix_rank}.",
                                )
                            )
                    if expr.attr == "shape":
                        self._set_matrix_expr_info(
                            expr, matrix_rank=None, matrix_element_type=None
                        )
                        return "int[]"
                    if expr.attr == "rank":
                        self._set_matrix_expr_info(
                            expr, matrix_rank=None, matrix_element_type=None
                        )
                        return "int"
                    if expr.attr in {"rows", "cols"}:
                        self._set_matrix_expr_info(
                            expr, matrix_rank=None, matrix_element_type=None
                        )
                        return "int"
                    if expr.attr == "dtype":
                        self._set_matrix_expr_info(
                            expr, matrix_rank=None, matrix_element_type=None
                        )
                        return "str"
                if expr.attr in MATRIX_METHODS:
                    raise SyntaxError(
                        err(
                            "E2150",
                            expr.lineno,
                            f"Matrix.{expr.attr} must be called as a method",
                            f"Use Matrix.{expr.attr}(...).",
                        )
                    )
                raise SyntaxError(
                    err(
                        "E2150",
                        expr.lineno,
                        f"Matrix has no member '{expr.attr}'",
                        "Use Matrix methods and properties only.",
                    )
                )
            class_decl = self._class_decls.get(value_type or "")
            if class_decl is not None:
                if expr.attr in class_decl.methods:
                    self._record_reference(
                        name=expr.attr,
                        qualified_name=f"{class_decl.name}.{expr.attr}",
                        location=self._attribute_location(expr),
                        kind="read",
                    )
                    return signature_to_function_type(class_decl.methods[expr.attr])
                for member in class_decl.members:
                    if member.name == expr.attr:
                        self._record_reference(
                            name=expr.attr,
                            qualified_name=f"{class_decl.name}.{expr.attr}",
                            location=self._attribute_location(expr),
                            kind="read",
                        )
                        return member.type_name
            if (
                isinstance(expr.value, ast.Name)
                and expr.value.id == "self"
                and self._current_class_name is not None
            ):
                if (
                    expr.attr not in self._class_field_names
                    and expr.attr not in self._class_method_names
                ):
                    raise SyntaxError(
                        err(
                            "E2150",
                            expr.lineno,
                            f"unknown member '{expr.attr}' on this instance",
                            "Use `this.member` for declared class fields/methods only.",
                        )
                    )
                member = self._current_class_member_map.get(expr.attr)
                if member is not None:
                    self._record_reference(
                        name=expr.attr,
                        qualified_name=f"{self._current_class_name}.{expr.attr}",
                        location=self._attribute_location(expr),
                        kind="read",
                    )
                    return member.type_name
            return value_type

        if isinstance(expr, ast.Subscript):
            return self._check_subscript(expr)

        if isinstance(expr, (ast.Lambda, ast.Dict, ast.Set, ast.Tuple, ast.Await)):
            raise SyntaxError(
                err(
                    "E2045",
                    getattr(expr, "lineno", 1),
                    f"expression form {type(expr).__name__} is not supported",
                    "Use Tython core expression forms only.",
                )
            )

        raise SyntaxError(
            err(
                "E2010",
                getattr(expr, "lineno", 1),
                f"unsupported expression {type(expr).__name__}",
                "Use a Tython-supported expression form.",
            )
        )

    def _check_ternary_expression(self, expr: ast.IfExp) -> str | None:
        cond_type = self._check_expression(expr.test)
        if cond_type != "bool":
            raise SyntaxError(
                err(
                    "E2089",
                    expr.lineno,
                    "ternary condition must be bool",
                    "Use a boolean condition in `if cond: x else y`.",
                )
            )

        true_type = self._check_expression(expr.body)
        false_type = self._check_expression(expr.orelse)

        if true_type is None or false_type is None:
            return true_type if true_type is not None else false_type

        if true_type == false_type:
            return true_type

        if true_type in {"int", "float"} and false_type in {"int", "float"}:
            return "float" if "float" in {true_type, false_type} else "int"

        if self._is_type_compatible(true_type, false_type):
            return true_type
        if self._is_type_compatible(false_type, true_type):
            return false_type

        raise SyntaxError(
            err(
                "E2090",
                expr.lineno,
                "ternary branch types are not compatible",
                f"Use compatible branch types, got {true_type} and {false_type}.",
            )
        )

    def _check_binop(self, expr: ast.BinOp) -> str | None:
        left = self._check_expression(expr.left)
        right = self._check_expression(expr.right)
        left_matrix_rank, left_matrix_element_type = self._matrix_info_for_expr(
            expr.left
        )
        right_matrix_rank, right_matrix_element_type = self._matrix_info_for_expr(
            expr.right
        )
        left_is_matrix = left == "Matrix"
        right_is_matrix = right == "Matrix"

        if left_is_matrix or right_is_matrix:
            if isinstance(expr.op, ast.Add):
                if not (left_is_matrix and right_is_matrix):
                    raise SyntaxError(
                        err(
                            "E2047",
                            expr.lineno,
                            "Matrix + requires another Matrix",
                            "Use Matrix + Matrix for matrix addition.",
                        )
                    )
                self._require_same_matrix_rank(
                    left_matrix_rank, right_matrix_rank, expr.lineno, "+"
                )
                result_element_type = self._promote_numeric_types(
                    left_matrix_element_type, right_matrix_element_type
                )
                self._set_matrix_expr_info(
                    expr,
                    matrix_rank=left_matrix_rank or right_matrix_rank,
                    matrix_element_type=result_element_type,
                )
                return "Matrix"

            if isinstance(expr.op, ast.Sub):
                if not (left_is_matrix and right_is_matrix):
                    raise SyntaxError(
                        err(
                            "E2047",
                            expr.lineno,
                            "Matrix - requires another Matrix",
                            "Use Matrix - Matrix for matrix subtraction.",
                        )
                    )
                self._require_same_matrix_rank(
                    left_matrix_rank, right_matrix_rank, expr.lineno, "-"
                )
                result_element_type = self._promote_numeric_types(
                    left_matrix_element_type, right_matrix_element_type
                )
                self._set_matrix_expr_info(
                    expr,
                    matrix_rank=left_matrix_rank or right_matrix_rank,
                    matrix_element_type=result_element_type,
                )
                return "Matrix"

            if isinstance(expr.op, ast.Mult):
                if left_is_matrix and right_is_matrix:
                    raise SyntaxError(
                        err(
                            "E2047",
                            expr.lineno,
                            "Matrix * Matrix is not allowed",
                            "Use Matrix @ Matrix for matrix multiplication, or Matrix.hadamard(Matrix) for element-wise multiplication.",
                        )
                    )
                if left_is_matrix:
                    if right not in {"int", "float"}:
                        raise SyntaxError(
                            err(
                                "E2047",
                                expr.lineno,
                                "Matrix * requires a numeric scalar",
                                "Use Matrix * int or Matrix * float.",
                            )
                        )
                    matrix_rank = left_matrix_rank
                    matrix_element_type = self._promote_numeric_types(
                        left_matrix_element_type, right
                    )
                else:
                    if left not in {"int", "float"}:
                        raise SyntaxError(
                            err(
                                "E2047",
                                expr.lineno,
                                "scalar * Matrix requires a numeric scalar",
                                "Use int * Matrix or float * Matrix.",
                            )
                        )
                    matrix_rank = right_matrix_rank
                    matrix_element_type = self._promote_numeric_types(
                        left, right_matrix_element_type
                    )
                self._set_matrix_expr_info(
                    expr,
                    matrix_rank=matrix_rank,
                    matrix_element_type=matrix_element_type,
                )
                return "Matrix"

            if isinstance(expr.op, ast.Div):
                if left_is_matrix and right_is_matrix:
                    raise SyntaxError(
                        err(
                            "E2047",
                            expr.lineno,
                            "Matrix / Matrix is not allowed",
                            "Use Matrix / scalar for scalar division.",
                        )
                    )
                if not left_is_matrix:
                    raise SyntaxError(
                        err(
                            "E2047",
                            expr.lineno,
                            "scalar / Matrix is not allowed",
                            "Use Matrix / scalar instead.",
                        )
                    )
                if right not in {"int", "float"}:
                    raise SyntaxError(
                        err(
                            "E2047",
                            expr.lineno,
                            "Matrix / requires a numeric scalar",
                            "Use Matrix / int or Matrix / float.",
                        )
                    )
                matrix_rank = left_matrix_rank
                self._set_matrix_expr_info(
                    expr,
                    matrix_rank=matrix_rank,
                    matrix_element_type="float",
                )
                return "Matrix"

            if isinstance(expr.op, ast.MatMult):
                if not (left_is_matrix and right_is_matrix):
                    raise SyntaxError(
                        err(
                            "E2047",
                            expr.lineno,
                            "Matrix @ requires another Matrix",
                            "Use Matrix @ Matrix for matrix multiplication.",
                        )
                    )
                result_type, result_rank, result_element_type = self._matrix_matmul_result(
                    left_matrix_rank,
                    left_matrix_element_type,
                    right_matrix_rank,
                    right_matrix_element_type,
                )
                if result_type == "Matrix":
                    self._set_matrix_expr_info(
                        expr,
                        matrix_rank=result_rank,
                        matrix_element_type=result_element_type,
                    )
                return result_type

            raise SyntaxError(
                err(
                    "E2047",
                    expr.lineno,
                    f"Matrix does not support {type(expr.op).__name__}",
                    "Use Matrix +, -, @, *, /, or Matrix.hadamard().",
                )
            )

        if isinstance(expr.op, ast.Add):
            if left == "str" and right == "str":
                return "str"
            if left in {"int", "float"} and right in {"int", "float"}:
                return "float" if "float" in {left, right} else "int"
            raise SyntaxError(
                err(
                    "E2046",
                    expr.lineno,
                    "operator `+` supports numeric addition or str+str only",
                    "Use matching numeric types or two strings.",
                )
            )

        if isinstance(expr.op, ast.Sub):
            self._require_numeric_pair(left, right, expr.lineno, "-")
            return "float" if "float" in {left, right} else "int"

        if isinstance(expr.op, ast.Mult):
            self._require_numeric_pair(left, right, expr.lineno, "*")
            return "float" if "float" in {left, right} else "int"

        if isinstance(expr.op, ast.Div):
            self._require_numeric_pair(left, right, expr.lineno, "/")
            return "float"

        if isinstance(expr.op, ast.FloorDiv):
            self._require_numeric_pair(left, right, expr.lineno, "//")
            return "float" if "float" in {left, right} else "int"

        if isinstance(expr.op, ast.Mod):
            self._require_numeric_pair(left, right, expr.lineno, "%")
            return "float" if "float" in {left, right} else "int"

        raise SyntaxError(
            err(
                "E2047",
                expr.lineno,
                f"unsupported arithmetic operator {type(expr.op).__name__}",
                "Use only +, -, *, /, //, %.",
            )
        )

    def _check_compare(self, expr: ast.Compare) -> str:
        if len(expr.ops) != 1:
            raise SyntaxError(
                err(
                    "E2048",
                    expr.lineno,
                    "chained comparisons are not allowed",
                    "Split into explicit comparisons joined by `and`.",
                )
            )

        op = expr.ops[0]
        right_expr = expr.comparators[0]
        left_type = self._check_expression(expr.left)
        right_type = self._check_expression(right_expr)

        if isinstance(op, (ast.Is, ast.IsNot, ast.In, ast.NotIn)):
            raise SyntaxError(
                err(
                    "E2049",
                    expr.lineno,
                    "operator is not supported",
                    "Use ==, !=, <, <=, >, >= only.",
                )
            )

        if not isinstance(op, (ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE)):
            raise SyntaxError(
                err(
                    "E2050",
                    expr.lineno,
                    "comparison operator is not supported",
                    "Use ==, !=, <, <=, >, >= only.",
                )
            )

        if isinstance(op, (ast.Eq, ast.NotEq)):
            if not self._is_equality_compatible(left_type, right_type):
                raise SyntaxError(
                    err(
                        "E2051",
                        expr.lineno,
                        "equality operands are not type-compatible",
                        "Compare values of the same type (except comparisons with none).",
                    )
                )
            return "bool"

        if left_type not in {"int", "float"} or right_type not in {"int", "float"}:
            raise SyntaxError(
                err(
                    "E2052",
                    expr.lineno,
                    "ordering comparisons require numeric operands",
                    "Use int/float with <, <=, >, >=.",
                )
            )
        return "bool"

    def _check_call(self, expr: ast.Call) -> str | None:
        result_type, _ = self._infer_call_result(expr, enforce_checked_throws=True)
        return result_type

    def _infer_call_result(
        self, expr: ast.Call, *, enforce_checked_throws: bool
    ) -> tuple[str | None, set[str]]:
        if isinstance(expr.func, ast.Name) and expr.func.id in {
            NATIVE_IMPORT_SENTINEL,
            FILE_IMPORT_SENTINEL,
            PYIMPORT_SENTINEL,
        }:
            return "none", set()

        if isinstance(expr.func, ast.Name) and expr.func.id == TRY_PROPAGATE_SENTINEL:
            return self._check_try_propagate_call(expr)

        if isinstance(expr.func, ast.Name) and expr.func.id == "panic":
            if len(expr.args) != 1 or expr.keywords:
                raise SyntaxError(
                    err(
                        "E2186",
                        expr.lineno,
                        "panic expects exactly one argument",
                        'Use `panic("message")`.',
                    )
                )
            self._check_expression(expr.args[0])
            return "none", set()

        if isinstance(expr.func, ast.Name) and expr.func.id == MATRIX_BUILTIN_NAME:
            return self._check_matrix_constructor_call(expr), set()

        if isinstance(expr.func, ast.Attribute) and expr.func.attr in {
            "setup",
            SETUP_METHOD_NAME,
        }:
            raise SyntaxError(
                err(
                    "E2151",
                    expr.lineno,
                    "setup cannot be called manually",
                    "setup runs automatically during construction.",
                )
            )

        if expr.args and expr.keywords:
            raise SyntaxError(
                err(
                    "E2072",
                    expr.lineno,
                    "mixed positional and named arguments are not allowed",
                    "Use either all positional or all named arguments.",
                )
            )

        if isinstance(expr.func, ast.Attribute):
            owner_type = self._check_expression(expr.func.value)
            if isinstance(expr.func.value, ast.Name):
                symbol = self._lookup_symbol(expr.func.value.id)
                if symbol is not None and symbol.type_name == "Module":
                    member = self._lookup_symbol(
                        f"{expr.func.value.id}.{expr.func.attr}"
                    )
                    if member is not None and member.type_name is not None:
                        class_decl = self._class_decls.get(member.type_name)
                        if class_decl is not None:
                            result = self._check_class_constructor_call(expr, class_decl)
                            return result, set()
                if symbol is not None and symbol.py_module is not None:
                    stubs = self._stub_index()
                    if stubs is not None:
                        sig = stubs.lookup_function(symbol.py_module, expr.func.attr)
                        if sig is not None:
                            # Enforce arity, but keep args permissive (stubs are optional).
                            self._check_pyimport_stub_call(expr, sig)
                            return sig.return_type, set()
            if owner_type == "Matrix":
                result_type, result_rank, result_element_type = self._check_matrix_method_call(
                    expr, expr.func.value, expr.func.attr
                )
                if result_type == "Matrix":
                    self._set_matrix_expr_info(
                        expr,
                        matrix_rank=result_rank,
                        matrix_element_type=result_element_type,
                    )
                return result_type, set()

            class_decl = self._class_decls.get(owner_type or "")
            signature = class_decl.methods.get(expr.func.attr) if class_decl else None
            if signature is not None:
                self._record_reference(
                    name=expr.func.attr,
                    qualified_name=f"{class_decl.name}.{expr.func.attr}",
                    location=self._attribute_location(expr.func),
                    kind="call",
                )
                if expr.args:
                    self._check_positional_call(expr, signature)
                else:
                    self._check_named_call(expr, signature)
                thrown = set(signature.throws)
                if (
                    enforce_checked_throws
                    and thrown
                    and not self._is_throw_set_handled_in_try_context(thrown)
                ):
                    raise SyntaxError(
                        err(
                            "E2192",
                            expr.lineno,
                            f"call to throwing method '{expr.func.attr}' must be handled",
                            "Wrap call in try/catch or use `try method(...)` in a throws-compatible function.",
                        )
                    )
                return signature.return_type, thrown

        if isinstance(expr.func, ast.Name):
            if expr.func.id == "len":
                for arg in expr.args:
                    self._check_expression(arg)
                for kw in expr.keywords:
                    self._check_expression(kw.value)
                return "int", set()
            if expr.func.id == "print":
                for arg in expr.args:
                    self._check_expression(arg)
                for kw in expr.keywords:
                    self._check_expression(kw.value)
                return "none", set()
            if expr.func.id == "range":
                for arg in expr.args:
                    self._check_expression(arg)
                for kw in expr.keywords:
                    self._check_expression(kw.value)
                return "int[]", set()

            class_decl = self._class_decls.get(expr.func.id)
            if class_decl is not None:
                self._record_reference(
                    name=expr.func.id,
                    qualified_name=expr.func.id,
                    location=(expr.func.lineno, expr.func.col_offset + 1),
                    kind="call",
                )
                result = self._check_class_constructor_call(expr, class_decl)
                return result, set()

            signature = self._function_signatures.get(expr.func.id)
            if signature is not None:
                self._record_reference(
                    name=expr.func.id,
                    qualified_name=expr.func.id,
                    location=(expr.func.lineno, expr.func.col_offset + 1),
                    kind="call",
                )
                if expr.args:
                    self._check_positional_call(expr, signature)
                else:
                    self._check_named_call(expr, signature)
                thrown = set(signature.throws)
                if (
                    enforce_checked_throws
                    and thrown
                    and not self._is_throw_set_handled_in_try_context(thrown)
                ):
                    raise SyntaxError(
                        err(
                            "E2192",
                            expr.lineno,
                            f"call to throwing function '{signature.name}' must be handled",
                            "Wrap call in try/catch or use `try fn(...)` in a throws-compatible function.",
                        )
                    )
                return signature.return_type, thrown

            for arg in expr.args:
                self._check_expression(arg)
            for kw in expr.keywords:
                self._check_expression(kw.value)
            return None, set()

        for arg in expr.args:
            self._check_expression(arg)
        for kw in expr.keywords:
            self._check_expression(kw.value)
        return None, set()

    def _check_try_propagate_call(self, expr: ast.Call) -> tuple[str | None, set[str]]:
        if len(expr.args) != 1 or expr.keywords:
            raise SyntaxError(
                err(
                    "E2187",
                    expr.lineno,
                    "try propagation requires exactly one call argument",
                    "Use `try fn(...)`.",
                )
            )
        if not self._throws_stack:
            raise SyntaxError(
                err(
                    "E2188",
                    expr.lineno,
                    "try propagation is only valid inside callable scope",
                    "Use `try` inside a function or method with throws.",
                )
            )

        call_expr = expr.args[0]
        if not isinstance(call_expr, ast.Call):
            raise SyntaxError(
                err(
                    "E2189",
                    expr.lineno,
                    "try propagation target must be a call expression",
                    "Use `try fn(...)`.",
                )
            )

        result_type, thrown = self._infer_call_result(
            call_expr, enforce_checked_throws=False
        )
        if not thrown:
            raise SyntaxError(
                err(
                    "E2190",
                    expr.lineno,
                    "try propagation requires a throwing call",
                    "Use plain call for non-throwing functions.",
                )
            )

        declared = self._throws_stack[-1]
        if not thrown.issubset(declared):
            missing = ", ".join(sorted(thrown - declared))
            raise SyntaxError(
                err(
                    "E2191",
                    expr.lineno,
                    f"try propagation uses undeclared throws type(s): {missing}",
                    "Add missing types to function throws clause or catch them locally.",
                )
            )
        return result_type, thrown

    def _check_positional_call(
        self, expr: ast.Call, signature: FunctionSignature
    ) -> None:
        params = signature.params
        required = sum(1 for p in params if not p.has_default)

        if len(expr.args) < required or len(expr.args) > len(params):
            raise SyntaxError(
                err(
                    "E2073",
                    expr.lineno,
                    f"wrong number of arguments for '{signature.name}'",
                    f"Expected between {required} and {len(params)} positional args.",
                )
            )

        for idx, arg in enumerate(expr.args):
            expected = params[idx].type_name
            actual = self._check_expression(arg)
            if not self._is_type_compatible(expected, actual):
                raise SyntaxError(
                    err(
                        "E2074",
                        expr.lineno,
                        f"argument type mismatch for parameter '{params[idx].name}'",
                        f"Expected {expected} but got {actual}.",
                    )
                )

    def _check_named_call(self, expr: ast.Call, signature: FunctionSignature) -> None:
        if not expr.keywords:
            if any(not p.has_default for p in signature.params):
                raise SyntaxError(
                    err(
                        "E2075",
                        expr.lineno,
                        f"missing required arguments for '{signature.name}'",
                        "Provide required parameters by name.",
                    )
                )
            return

        param_by_name = {p.name: p for p in signature.params}
        seen: set[str] = set()

        for keyword in expr.keywords:
            if keyword.arg is None:
                raise SyntaxError(
                    err(
                        "E2076",
                        expr.lineno,
                        "variadic named argument expansion is not supported",
                        "Pass explicit named arguments.",
                    )
                )

            if keyword.arg in seen:
                raise SyntaxError(
                    err(
                        "E2077",
                        expr.lineno,
                        f"duplicate named argument '{keyword.arg}'",
                        "Pass each named argument at most once.",
                    )
                )
            seen.add(keyword.arg)

            if keyword.arg not in param_by_name:
                raise SyntaxError(
                    err(
                        "E2078",
                        expr.lineno,
                        f"unknown named argument '{keyword.arg}'",
                        "Use only declared parameter names.",
                    )
                )

            expected = param_by_name[keyword.arg].type_name
            actual = self._check_expression(keyword.value)
            if not self._is_type_compatible(expected, actual):
                raise SyntaxError(
                    err(
                        "E2079",
                        expr.lineno,
                        f"argument type mismatch for parameter '{keyword.arg}'",
                        f"Expected {expected} but got {actual}.",
                    )
                )

        missing = [
            p.name for p in signature.params if not p.has_default and p.name not in seen
        ]
        if missing:
            raise SyntaxError(
                err(
                    "E2080",
                    expr.lineno,
                    f"missing required named arguments: {', '.join(missing)}",
                    "Provide all required parameters.",
                )
            )

    def _check_subscript(self, expr: ast.Subscript) -> str | None:
        value_type = self._check_expression(expr.value)
        matrix_rank, matrix_element_type = self._matrix_info_for_expr(expr.value)

        if value_type == "Matrix":
            if isinstance(expr.slice, ast.Slice):
                raise SyntaxError(
                    err(
                        "E2053",
                        expr.lineno,
                        "slice expressions are not supported",
                        "Use Matrix[i] or Matrix[i, j] with integer indexes only.",
                    )
                )

            if isinstance(expr.slice, ast.Tuple):
                if len(expr.slice.elts) != 2:
                    raise SyntaxError(
                        err(
                            "E2053",
                            expr.lineno,
                            "Matrix tuple indexing requires exactly two indexes",
                            "Use Matrix[i, j] for two-dimensional lookup.",
                        )
                    )
                if matrix_rank == 1:
                    raise SyntaxError(
                        err(
                            "E2150",
                            expr.lineno,
                            "Matrix[i, j] only works on rank-2 Matrix values",
                            "Use a rank-2 Matrix before two-dimensional indexing.",
                        )
                    )

                for index_expr in expr.slice.elts:
                    index_type = self._check_expression(index_expr)
                    if index_type != "int":
                        raise SyntaxError(
                            err(
                                "E2054",
                                expr.lineno,
                                "index expression must be int",
                                "Use integer indexes only.",
                            )
                        )
                    if (
                        isinstance(index_expr, ast.Constant)
                        and isinstance(index_expr.value, int)
                        and index_expr.value < 0
                    ):
                        raise SyntaxError(
                            err(
                                "E2055",
                                expr.lineno,
                                "negative indexes are not supported",
                                "Use a non-negative index.",
                            )
                        )

                result_type = matrix_element_type or "float"
                self._set_matrix_expr_info(
                    expr, matrix_rank=None, matrix_element_type=None
                )
                return result_type

            index_type = self._check_expression(expr.slice)
            if index_type != "int":
                raise SyntaxError(
                    err(
                        "E2054",
                        expr.lineno,
                        "index expression must be int",
                        "Use an integer index expression.",
                    )
                )

            literal_index = extract_int_literal(expr.slice)
            if literal_index is not None and literal_index < 0:
                raise SyntaxError(
                    err(
                        "E2055",
                        expr.lineno,
                        "negative indexes are not supported",
                        "Use a non-negative index.",
                    )
                )

            if matrix_rank == 2:
                self._set_matrix_expr_info(
                    expr,
                    matrix_rank=1,
                    matrix_element_type=matrix_element_type,
                )
                return "Matrix"
            if matrix_rank == 1:
                self._set_matrix_expr_info(
                    expr, matrix_rank=None, matrix_element_type=None
                )
                return matrix_element_type or "float"

            self._set_matrix_expr_info(
                expr, matrix_rank=None, matrix_element_type=None
            )
            return "Matrix"

        if isinstance(expr.slice, ast.Slice):
            raise SyntaxError(
                err(
                    "E2053",
                    expr.lineno,
                    "slice expressions are not supported",
                    "Use single index access like items[i].",
                )
            )

        index_type = self._check_expression(expr.slice)
        if index_type != "int":
            raise SyntaxError(
                err(
                    "E2054",
                    expr.lineno,
                    "index expression must be int",
                    "Use an integer index expression.",
                )
            )

        literal_index = extract_int_literal(expr.slice)
        if literal_index is not None and literal_index < 0:
            raise SyntaxError(
                err(
                    "E2055",
                    expr.lineno,
                    "negative indexes are not supported",
                    "Use a non-negative index.",
                )
            )

        if value_type is None:
            return None
        if not value_type.endswith("[]"):
            raise SyntaxError(
                err(
                    "E2056",
                    expr.lineno,
                    f"cannot index non-list type '{value_type}'",
                    "Indexing is allowed only on list types.",
                )
            )
        return value_type[:-2]

    def _is_record_literal_expr(self, expr: ast.expr) -> bool:
        return (
            isinstance(expr, ast.Call)
            and isinstance(expr.func, ast.Name)
            and expr.func.id == RECORD_LITERAL_SENTINEL
        )

    def _check_record_literal_expression(self, expr: ast.expr) -> str:
        assert isinstance(expr, ast.Call)
        if len(expr.args) != 2 or expr.keywords:
            raise SyntaxError(
                err(
                    "E2153",
                    getattr(expr, "lineno", 1),
                    "internal record literal IR shape is invalid",
                    "Report this as an internal parser bug.",
                )
            )
        type_node, fields_node = expr.args
        if not isinstance(type_node, ast.Constant) or not isinstance(
            type_node.value, str
        ):
            raise SyntaxError(
                err("E2154", expr.lineno, "record literal type must be a string")
            )
        if not isinstance(fields_node, ast.List):
            raise SyntaxError(
                err("E2155", expr.lineno, "record literal fields must be a list")
            )

        record_decl = self._record_decls.get(type_node.value)
        if record_decl is None:
            raise SyntaxError(
                err(
                    "E2156",
                    expr.lineno,
                    f"unknown record type '{type_node.value}'",
                    "Declare the record before constructing it.",
                )
            )
        self._record_reference(
            name=type_node.value,
            qualified_name=type_node.value,
            location=(expr.lineno, expr.col_offset + 1),
            kind="call",
        )

        seen: set[str] = set()
        values_by_name: dict[str, ast.expr] = {}
        for element in fields_node.elts:
            if not isinstance(element, ast.Tuple) or len(element.elts) != 2:
                raise SyntaxError(
                    err("E2157", expr.lineno, "invalid record field entry")
                )
            key_node, value_node = element.elts
            if not isinstance(key_node, ast.Constant) or not isinstance(
                key_node.value, str
            ):
                raise SyntaxError(
                    err("E2158", expr.lineno, "record field name must be string")
                )
            field_name = key_node.value
            if field_name in seen:
                raise SyntaxError(
                    err(
                        "E2159",
                        expr.lineno,
                        f"duplicate record field '{field_name}'",
                        "Provide each field at most once.",
                    )
                )
            seen.add(field_name)
            values_by_name[field_name] = value_node

        decl_fields = {field.name: field for field in record_decl.fields}
        for field_name in values_by_name:
            if field_name not in decl_fields:
                raise SyntaxError(
                    err(
                        "E2160",
                        expr.lineno,
                        f"unknown record field '{field_name}' for '{record_decl.name}'",
                        "Use only fields declared on the record.",
                    )
                )
        for field in record_decl.fields:
            if field.name not in values_by_name:
                raise SyntaxError(
                    err(
                        "E2161",
                        expr.lineno,
                        f"missing required record field '{field.name}'",
                        "Provide all required record fields.",
                    )
                )
            actual = self._check_expression(values_by_name[field.name])
            if not self._is_type_compatible(field.type_name, actual):
                raise SyntaxError(
                    err(
                        "E2162",
                        expr.lineno,
                        f"record field type mismatch for '{field.name}'",
                        f"Expected {field.type_name} but got {actual}.",
                    )
                )
        return record_decl.name

    def _check_class_constructor_call(
        self, expr: ast.Call, class_decl: ClassDecl
    ) -> str:
        if expr.args:
            raise SyntaxError(
                err(
                    "E2163",
                    expr.lineno,
                    f"class constructor '{class_decl.name}' requires named arguments",
                    "Use named constructor arguments only.",
                )
            )

        init_members = [
            m for m in class_decl.members if m.kind in {"init_var", "init_const"}
        ]
        by_name = {member.name: member for member in init_members}
        seen: set[str] = set()
        for keyword in expr.keywords:
            if keyword.arg is None:
                raise SyntaxError(
                    err(
                        "E2164",
                        expr.lineno,
                        "variadic named argument expansion is not supported",
                        "Pass explicit named constructor arguments.",
                    )
                )
            if keyword.arg in seen:
                raise SyntaxError(
                    err(
                        "E2165",
                        expr.lineno,
                        f"duplicate constructor argument '{keyword.arg}'",
                        "Pass each constructor argument at most once.",
                    )
                )
            seen.add(keyword.arg)
            member = by_name.get(keyword.arg)
            if member is None:
                raise SyntaxError(
                    err(
                        "E2166",
                        expr.lineno,
                        f"unknown constructor argument '{keyword.arg}' for '{class_decl.name}'",
                        "Use only init field names as constructor arguments.",
                    )
                )
            assert member.type_name is not None
            actual = self._check_expression(keyword.value)
            if not self._is_type_compatible(member.type_name, actual):
                raise SyntaxError(
                    err(
                        "E2167",
                        expr.lineno,
                        f"constructor argument type mismatch for '{keyword.arg}'",
                        f"Expected {member.type_name} but got {actual}.",
                    )
                )

        missing = [
            m.name for m in init_members if not m.has_initializer and m.name not in seen
        ]
        if missing:
            raise SyntaxError(
                err(
                    "E2168",
                    expr.lineno,
                    f"missing required constructor arguments: {', '.join(missing)}",
                    "Provide all required init fields.",
                )
            )
        return class_decl.name

    def _is_self_attribute_target(self, target: ast.expr) -> bool:
        return (
            isinstance(target, ast.Attribute)
            and isinstance(target.value, ast.Name)
            and target.value.id == "self"
            and self._current_class_name is not None
        )

    def _check_self_member_assignment(
        self, attr: str, value: ast.expr, lineno: int
    ) -> None:
        if not self._current_class_member_map:
            raise SyntaxError(
                err("E2169", lineno, "instance assignment outside class context")
            )
        member = self._current_class_member_map.get(attr)
        if member is None:
            raise SyntaxError(
                err(
                    "E2170",
                    lineno,
                    f"unknown instance field '{attr}'",
                    "Assign only to declared class fields.",
                )
            )
        if member.kind in {"init_const", "const"}:
            raise SyntaxError(
                err(
                    "E2171",
                    lineno,
                    f"cannot assign immutable field '{attr}'",
                    "Assign only to `init var`/`var` fields.",
                )
            )
        if member.type_name is not None:
            actual = self._check_expression(value)
            if not self._is_type_compatible(member.type_name, actual):
                raise SyntaxError(
                    err(
                        "E2172",
                        lineno,
                        f"assignment type mismatch for field '{attr}'",
                        f"Expected {member.type_name} but got {actual}.",
                    )
                )
        if self._current_class_name is not None:
            self._record_reference(
                name=attr,
                qualified_name=f"{self._current_class_name}.{attr}",
                location=(lineno, 1),
                kind="write",
            )

    def _require_numeric_pair(
        self, left: str | None, right: str | None, lineno: int, operator: str
    ) -> None:
        if left not in {"int", "float"} or right not in {"int", "float"}:
            raise SyntaxError(
                err(
                    "E2057",
                    lineno,
                    f"operator `{operator}` requires numeric operands",
                    "Use int or float operands.",
                )
            )

    def _is_equality_compatible(self, left: str | None, right: str | None) -> bool:
        if left is None or right is None:
            return True
        if left == right:
            return True
        if left == "none" or right == "none":
            return True
        if left in {"int", "float"} and right in {"int", "float"}:
            return True
        return False

    def _infer_constant_type(self, expr: ast.Constant) -> str | None:
        if isinstance(expr.value, bool):
            return "bool"
        if isinstance(expr.value, int):
            return "int"
        if isinstance(expr.value, float):
            return "float"
        if isinstance(expr.value, str):
            return "str"
        if expr.value is None:
            return "none"
        return None

    def _declare_binding(self, decl: BindingDecl) -> None:
        lineno = decl.location[0]

        if decl.name in RESERVED_WORDS:
            raise SyntaxError(
                err(
                    "E2011",
                    lineno,
                    f"reserved word '{decl.name}' cannot be used as an identifier",
                    "Choose a different identifier name.",
                )
            )
        if not IDENTIFIER_RE.fullmatch(decl.name):
            raise SyntaxError(
                err(
                    "E2012",
                    lineno,
                    f"invalid identifier '{decl.name}'",
                    "Use letters, digits, or underscores and start with a letter/underscore.",
                )
            )

        if decl.kind == "const":
            if self._scopes[-1].kind == "module":
                if not CONST_NAME_RE.fullmatch(decl.name):
                    raise SyntaxError(
                        err(
                            "E2013",
                            lineno,
                            f"invalid const name '{decl.name}'",
                            "Use UPPER_SNAKE_CASE for module const bindings.",
                        )
                    )
            else:
                if not VAR_NAME_RE.fullmatch(decl.name):
                    raise SyntaxError(
                        err(
                            "E2013",
                            lineno,
                            f"invalid const name '{decl.name}'",
                            "Use snake_case for local const bindings.",
                        )
                    )
        if decl.kind == "var" and not VAR_NAME_RE.fullmatch(decl.name):
            raise SyntaxError(
                err(
                    "E2014",
                    lineno,
                    f"invalid var name '{decl.name}'",
                    "Use snake_case for var bindings.",
                )
            )

        if not decl.has_initializer and decl.type_annotation is None:
            raise SyntaxError(
                err(
                    "E2015",
                    lineno,
                    f"binding '{decl.name}' without initializer requires a type annotation",
                    "Declare as `var name: Type` or provide `= value`.",
                )
            )

        if decl.type_annotation is not None:
            self._validate_type_name(decl.type_annotation, lineno)

        inferred = (
            self._check_expression(decl.initializer)
            if decl.has_initializer and decl.initializer is not None
            else None
        )
        matrix_rank = None
        matrix_element_type = None
        if inferred == "Matrix" and decl.initializer is not None:
            matrix_rank, matrix_element_type = self._matrix_info_for_expr(
                decl.initializer
            )
        if decl.type_annotation is not None and not self._is_type_compatible(
            decl.type_annotation, inferred
        ):
            raise SyntaxError(
                err(
                    "E2016",
                    lineno,
                    f"incompatible initializer type for '{decl.name}'",
                    f"Initializer type '{inferred}' does not match declared type '{decl.type_annotation}'.",
                )
            )

        inferred_type = decl.type_annotation or inferred
        self._declare_name(
            decl.name,
            decl.kind,
            inferred_type,
            lineno,
            initialized=decl.has_initializer,
            location=decl.location,
            symbol_kind="constant" if decl.kind == "const" else "variable",
            is_public=decl.is_public,
            matrix_rank=matrix_rank,
            matrix_element_type=matrix_element_type,
        )

    def _check_assignment_target(self, assignment: Assignment) -> None:
        symbol = self._resolve_name(
            assignment.target,
            assignment.location[0],
            for_write=True,
            require_initialized=False,
            location=assignment.location,
        )

        current_function = self._current_function_id()
        if current_function != symbol.function_id:
            raise SyntaxError(
                err(
                    "E2017",
                    assignment.location[0],
                    f"cannot rebind outer binding '{assignment.target}'",
                    "Assign only to names declared in the current lexical function/module scope.",
                )
            )

        inferred = self._check_expression(assignment.value)
        if symbol.type_name is not None and not self._is_type_compatible(
            symbol.type_name, inferred
        ):
            raise SyntaxError(
                err(
                    "E2018",
                    assignment.location[0],
                    f"assignment type mismatch for '{assignment.target}'",
                    f"Assigned type '{inferred}' does not match declared type '{symbol.type_name}'.",
                )
            )

        if symbol.kind == "const" and symbol.initialized:
            raise SyntaxError(
                err(
                    "E2019",
                    assignment.location[0],
                    f"cannot reassign const binding '{assignment.target}'",
                    "Const bindings are write-once after initialization.",
                )
            )

        if symbol.type_name == "Matrix":
            matrix_rank, matrix_element_type = self._matrix_info_for_expr(
                assignment.value
            )
            if matrix_rank is not None or matrix_element_type is not None:
                symbol.matrix_rank = matrix_rank
                symbol.matrix_element_type = matrix_element_type

        symbol.initialized = True

    def _declare_name(
        self,
        name: str,
        kind: str,
        type_name: str | None,
        lineno: int,
        initialized: bool,
        *,
        location: tuple[int, int] | None = None,
        symbol_kind: str | None = None,
        is_public: bool = False,
        matrix_rank: int | None = None,
        matrix_element_type: str | None = None,
        detail: str | None = None,
    ) -> None:
        scope = self._scopes[-1]
        if name in scope.symbols:
            raise SyntaxError(
                err(
                    "E2020",
                    lineno,
                    f"duplicate declaration '{name}' in same scope",
                    "Use a unique identifier name in this scope.",
                )
            )

        for outer in reversed(self._scopes[:-1]):
            if name in outer.symbols:
                raise SyntaxError(
                    err(
                        "E2021",
                        lineno,
                        f"shadowing is forbidden for name '{name}'",
                        "Rename the inner binding to avoid shadowing.",
                    )
                )

        qualified_name = (
            f"{self._current_callable_name}.{name}"
            if self._current_callable_name is not None
            else name
        )
        scope.symbols[name] = Symbol(
            name=name,
            qualified_name=qualified_name,
            kind=kind,
            type_name=type_name,
            py_module=None,
            lineno=lineno,
            col_offset=(location[1] if location is not None else 1),
            function_id=self._current_function_id(),
            initialized=initialized,
            matrix_rank=matrix_rank,
            matrix_element_type=matrix_element_type,
            is_public=is_public,
        )
        self._record_symbol(
            name=name,
            qualified_name=qualified_name,
            kind=symbol_kind or kind,
            type_name=type_name,
            location=location or (lineno, 1),
            parent_qname=self._current_callable_name,
            is_public=is_public,
            detail=detail,
        )

    def _resolve_name(
        self,
        name: str,
        lineno: int,
        for_write: bool,
        require_initialized: bool,
        *,
        location: tuple[int, int] | None = None,
    ) -> Symbol:
        for scope in reversed(self._scopes):
            symbol = scope.symbols.get(name)
            if symbol is None:
                continue
            self._record_reference(
                name=name,
                qualified_name=symbol.qualified_name,
                location=location or (lineno, 1),
                kind="write" if for_write else "read",
            )
            if require_initialized and not symbol.initialized:
                raise SyntaxError(
                    err(
                        "E2022",
                        lineno,
                        f"name '{name}' is declared but not initialized",
                        "Initialize it before reading, e.g. `name = value`.",
                    )
                )
            return symbol

        if for_write:
            raise SyntaxError(
                err(
                    "E2023",
                    lineno,
                    f"assignment to undeclared name '{name}'",
                    "Declare it first with `var` or `const`.",
                )
            )

        if self._current_class_name is not None:
            member = self._current_class_member_map.get(name)
            if member is not None:
                raise SyntaxError(
                    err(
                        "E2024",
                        lineno,
                        f"use of undeclared name '{name}'",
                        f"Did you mean `this.{name}`?",
                    )
                )

        raise SyntaxError(
            err(
                "E2024",
                lineno,
                f"use of undeclared name '{name}'",
                "Declare it before use.",
            )
        )

    def _with_block_scope(self, callback: callable) -> None:
        self._scopes.append(
            Scope(kind="block", function_id=self._current_function_id(), symbols={})
        )
        try:
            callback()
        finally:
            self._scopes.pop()

    def _current_function_id(self) -> int | None:
        for scope in reversed(self._scopes):
            if scope.kind == "function":
                return scope.function_id
        return None

    def _is_native_import_stmt(self, stmt: ast.stmt) -> bool:
        return (
            isinstance(stmt, ast.Expr)
            and isinstance(stmt.value, ast.Call)
            and isinstance(stmt.value.func, ast.Name)
            and stmt.value.func.id == NATIVE_IMPORT_SENTINEL
        )

    def _is_file_import_stmt(self, stmt: ast.stmt) -> bool:
        return (
            isinstance(stmt, ast.Expr)
            and isinstance(stmt.value, ast.Call)
            and isinstance(stmt.value.func, ast.Name)
            and stmt.value.func.id == FILE_IMPORT_SENTINEL
        )

    def _is_pyimport_stmt(self, stmt: ast.stmt) -> bool:
        return (
            isinstance(stmt, ast.Expr)
            and isinstance(stmt.value, ast.Call)
            and isinstance(stmt.value.func, ast.Name)
            and stmt.value.func.id == PYIMPORT_SENTINEL
        )

    def _extract_native_import(self, stmt: ast.stmt) -> tuple[str, str | None]:
        call = stmt.value
        assert isinstance(call, ast.Call)
        if len(call.args) != 2 or call.keywords:
            raise SyntaxError(
                err(
                    "E2201",
                    stmt.lineno,
                    "internal native import IR shape is invalid",
                    "Report this as an internal parser bug.",
                )
            )
        target_node, alias_node = call.args
        if not isinstance(target_node, ast.Constant) or not isinstance(
            target_node.value, str
        ):
            raise SyntaxError(
                err("E2202", stmt.lineno, "native import target must be string")
            )
        if not isinstance(alias_node, ast.Constant) or (
            alias_node.value is not None and not isinstance(alias_node.value, str)
        ):
            raise SyntaxError(
                err("E2203", stmt.lineno, "native import alias must be string/none")
            )
        return target_node.value, alias_node.value

    def _extract_file_import(self, stmt: ast.stmt) -> tuple[str, str]:
        call = stmt.value
        assert isinstance(call, ast.Call)
        if len(call.args) != 2 or call.keywords:
            raise SyntaxError(
                err(
                    "E2204",
                    stmt.lineno,
                    "internal file import IR shape is invalid",
                    "Report this as an internal parser bug.",
                )
            )
        path_node, alias_node = call.args
        if not isinstance(path_node, ast.Constant) or not isinstance(
            path_node.value, str
        ):
            raise SyntaxError(
                err("E2205", stmt.lineno, "file import path must be string")
            )
        if not isinstance(alias_node, ast.Constant) or not isinstance(
            alias_node.value, str
        ):
            raise SyntaxError(
                err("E2206", stmt.lineno, "file import alias must be string")
            )
        return path_node.value, alias_node.value

    def _extract_pyimport(self, stmt: ast.stmt) -> tuple[str, str | None]:
        call = stmt.value
        assert isinstance(call, ast.Call)
        if len(call.args) != 2 or call.keywords:
            raise SyntaxError(
                err(
                    "E2207",
                    stmt.lineno,
                    "internal pyimport IR shape is invalid",
                    "Report this as an internal parser bug.",
                )
            )
        module_node, alias_node = call.args
        if not isinstance(module_node, ast.Constant) or not isinstance(
            module_node.value, str
        ):
            raise SyntaxError(
                err("E2208", stmt.lineno, "pyimport module must be string")
            )
        if not isinstance(alias_node, ast.Constant) or (
            alias_node.value is not None and not isinstance(alias_node.value, str)
        ):
            raise SyntaxError(
                err("E2209", stmt.lineno, "pyimport alias must be string/none")
            )
        return module_node.value, alias_node.value

    def _is_binding_decl_stmt(self, stmt: ast.stmt) -> bool:
        return (
            isinstance(stmt, ast.Expr)
            and isinstance(stmt.value, ast.Call)
            and isinstance(stmt.value.func, ast.Name)
            and stmt.value.func.id == BINDING_SENTINEL
        )

    def _extract_binding_decl(self, stmt: ast.stmt) -> BindingDecl:
        call = stmt.value
        assert isinstance(call, ast.Call)
        if len(call.args) != 6 or call.keywords:
            raise SyntaxError(
                err(
                    "E2025",
                    stmt.lineno,
                    "internal binding IR shape is invalid",
                    "Report this as an internal parser bug.",
                )
            )
        kind, name, annotation, value, has_initializer, is_public = call.args
        if not isinstance(kind, ast.Constant) or not isinstance(kind.value, str):
            raise SyntaxError(
                err("E2026", stmt.lineno, "binding kind must be a string")
            )
        if kind.value not in {"const", "var"}:
            raise SyntaxError(
                err("E2027", stmt.lineno, "binding kind must be 'const' or 'var'")
            )
        if not isinstance(name, ast.Constant) or not isinstance(name.value, str):
            raise SyntaxError(
                err("E2028", stmt.lineno, "binding name must be a string")
            )
        if not isinstance(annotation, ast.Constant) or (
            annotation.value is not None and not isinstance(annotation.value, str)
        ):
            raise SyntaxError(
                err("E2029", stmt.lineno, "binding annotation must be a string or none")
            )
        if not isinstance(has_initializer, ast.Constant) or not isinstance(
            has_initializer.value, bool
        ):
            raise SyntaxError(
                err(
                    "E2030",
                    stmt.lineno,
                    "binding initializer flag must be a boolean",
                )
            )
        if not isinstance(is_public, ast.Constant) or not isinstance(
            is_public.value, bool
        ):
            raise SyntaxError(
                err(
                    "E2152",
                    stmt.lineno,
                    "binding visibility flag must be a boolean",
                )
            )

        return BindingDecl(
            kind=kind.value,
            name=name.value,
            type_annotation=annotation.value,
            initializer=value,
            has_initializer=has_initializer.value,
            is_public=is_public.value,
            location=(stmt.lineno, stmt.col_offset),
        )

    def _is_enum_decl_stmt(self, stmt: ast.stmt) -> bool:
        return (
            isinstance(stmt, ast.Expr)
            and isinstance(stmt.value, ast.Call)
            and isinstance(stmt.value.func, ast.Name)
            and stmt.value.func.id == ENUM_SENTINEL
        )

    def _extract_enum_name(self, stmt: ast.stmt) -> str:
        call = stmt.value
        assert isinstance(call, ast.Call)
        if len(call.args) != 2 or call.keywords:
            raise SyntaxError(
                err(
                    "E2031",
                    stmt.lineno,
                    "internal enum IR shape is invalid",
                    "Report this as an internal parser bug.",
                )
            )
        enum_name = call.args[0]
        if not isinstance(enum_name, ast.Constant) or not isinstance(
            enum_name.value, str
        ):
            raise SyntaxError(
                err("E2032", stmt.lineno, "enum name must be a string literal")
            )
        return enum_name.value

    def _node_range(
        self,
        node: ast.AST | ast.expr | ast.arg | ast.stmt,
        *,
        fallback_name: str | None = None,
    ) -> SourceRange:
        start_line = getattr(node, "lineno", 1) or 1
        start_col = getattr(node, "col_offset", 0) or 0
        end_line = getattr(node, "end_lineno", start_line) or start_line
        end_col = getattr(
            node, "end_col_offset", start_col + (len(fallback_name or "") or 1)
        )
        if end_line == start_line and end_col <= start_col:
            end_col = start_col + max(1, len(fallback_name or ""))
        return SourceRange(
            start=(start_line, start_col + 1), end=(end_line, end_col + 1)
        )

    def _attribute_location(self, expr: ast.Attribute) -> tuple[int, int]:
        end_line = getattr(expr, "end_lineno", expr.lineno) or expr.lineno
        end_col = getattr(expr, "end_col_offset", expr.col_offset + len(expr.attr)) or (
            expr.col_offset + len(expr.attr)
        )
        return end_line, max(1, end_col - len(expr.attr) + 1)

    def _record_symbol(
        self,
        *,
        name: str,
        qualified_name: str,
        kind: str,
        type_name: str | None,
        location: tuple[int, int],
        parent_qname: str | None,
        is_public: bool,
        detail: str | None = None,
    ) -> None:
        if qualified_name in self._analysis.symbols_by_qualified_name:
            return
        symbol = SemanticSymbol(
            name=name,
            qualified_name=qualified_name,
            kind=kind,
            detail=detail,
            type_name=type_name,
            location=SourceRange(
                start=location, end=(location[0], location[1] + max(1, len(name)))
            ),
            selection_range=SourceRange(
                start=location, end=(location[0], location[1] + max(1, len(name)))
            ),
            is_public=is_public,
            container_name=parent_qname,
        )
        self._analysis.symbols_by_qualified_name[qualified_name] = symbol
        if parent_qname is None:
            self._analysis.top_level_symbols.append(symbol)
            if name not in self._analysis.symbols_by_name:
                self._analysis.symbols_by_name[name] = symbol
            return

        parent = self._analysis.symbols_by_qualified_name.get(parent_qname)
        if parent is not None:
            parent.children.append(symbol)

    def _record_reference(
        self,
        *,
        name: str,
        qualified_name: str,
        location: tuple[int, int],
        kind: str,
    ) -> None:
        reference = ReferenceSite(
            name=name,
            qualified_name=qualified_name,
            location=SourceRange(
                start=location, end=(location[0], location[1] + max(1, len(name)))
            ),
            kind=kind,
        )
        self._analysis.references_by_qualified_name.setdefault(
            qualified_name, []
        ).append(reference)
        self._analysis.references_by_name.setdefault(name, []).append(reference)

    def _set_matrix_expr_info(
        self,
        expr: ast.AST,
        *,
        matrix_rank: int | None,
        matrix_element_type: str | None,
    ) -> None:
        self._matrix_expr_info[id(expr)] = (matrix_rank, matrix_element_type)

    def _lookup_symbol(self, name: str) -> Symbol | None:
        for scope in reversed(self._scopes):
            symbol = scope.symbols.get(name)
            if symbol is not None:
                return symbol
        return None

    def _matrix_info_for_symbol(
        self, symbol: Symbol
    ) -> tuple[int | None, str | None]:
        if (
            symbol.type_name != MATRIX_BUILTIN_NAME
            and symbol.matrix_rank is None
            and symbol.matrix_element_type is None
        ):
            return None, None
        return symbol.matrix_rank, symbol.matrix_element_type

    def _matrix_info_for_expr(self, expr: ast.AST) -> tuple[int | None, str | None]:
        info = self._matrix_expr_info.get(id(expr))
        if info is not None:
            return info
        if isinstance(expr, ast.Name):
            symbol = self._lookup_symbol(expr.id)
            if symbol is not None:
                return self._matrix_info_for_symbol(symbol)
        return None, None

    def _matrix_constructor_info(
        self, type_name: str | None, lineno: int
    ) -> tuple[int | None, str | None]:
        if type_name is None:
            raise SyntaxError(
                err(
                    "E2150",
                    lineno,
                    "Matrix constructor expects a list or nested list",
                    "Use Matrix([1, 2, 3]) or Matrix([[1, 2], [3, 4]]).",
                )
            )

        if type_name == MATRIX_BUILTIN_NAME:
            raise SyntaxError(
                err(
                    "E2150",
                    lineno,
                    "Matrix constructor expects list data, not Matrix",
                    "Pass a list or nested list to Matrix(...).",
                )
            )

        base = type_name
        rank = 0
        while base.endswith("[]"):
            rank += 1
            base = base[:-2]

        if rank not in {1, 2}:
            raise SyntaxError(
                err(
                    "E2150",
                    lineno,
                    "Matrix supports only rank-1 or rank-2 data",
                    "Use a one-dimensional list or a list of rows.",
                )
            )

        if base == "unknown":
            return rank, None

        if base not in {"int", "float"}:
            raise SyntaxError(
                err(
                    "E2150",
                    lineno,
                    "Matrix data must be numeric",
                    "Use int[] or float[] values only.",
                )
            )

        return rank, base

    def _promote_numeric_types(
        self, left: str | None, right: str | None
    ) -> str | None:
        if left == "float" or right == "float":
            return "float"
        if left == "int" or right == "int":
            return "int"
        return left or right

    def _require_same_matrix_rank(
        self,
        left_rank: int | None,
        right_rank: int | None,
        lineno: int,
        operator: str,
    ) -> None:
        if (
            left_rank is not None
            and right_rank is not None
            and left_rank != right_rank
        ):
            raise SyntaxError(
                err(
                    "E2047",
                    lineno,
                    f"Matrix {operator} requires matching ranks",
                    f"Got rank {left_rank} and rank {right_rank}.",
                )
            )

    def _check_matrix_constructor_call(self, expr: ast.Call) -> str:
        if len(expr.args) != 1 or expr.keywords:
            raise SyntaxError(
                err(
                    "E2150",
                    expr.lineno,
                    "Matrix constructor takes exactly one positional argument",
                    "Use Matrix(data) in v1.",
                )
            )

        arg_type = self._check_expression(expr.args[0])
        matrix_rank, matrix_element_type = self._matrix_constructor_info(
            arg_type, expr.lineno
        )
        self._set_matrix_expr_info(
            expr,
            matrix_rank=matrix_rank,
            matrix_element_type=matrix_element_type,
        )
        return MATRIX_BUILTIN_NAME

    def _check_matrix_method_call(
        self, expr: ast.Call, owner_expr: ast.expr, method_name: str
    ) -> tuple[str | None, int | None, str | None]:
        if method_name not in MATRIX_METHODS:
            raise SyntaxError(
                err(
                    "E2150",
                    expr.lineno,
                    f"Matrix has no method '{method_name}'",
                    "Use Matrix methods like sum, mean, transpose, inverse, determinant, norm, solve, or hadamard.",
                )
            )

        owner_rank, owner_element_type = self._matrix_info_for_expr(owner_expr)

        if method_name in {"sum", "mean", "min", "max"}:
            if len(expr.args) > 0:
                raise SyntaxError(
                    err(
                        "E2150",
                        expr.lineno,
                        f"Matrix.{method_name} expects named axis only",
                        "Use Matrix.method(axis: 0) or Matrix.method().",
                    )
                )

            if expr.keywords:
                if len(expr.keywords) != 1 or expr.keywords[0].arg != "axis":
                    raise SyntaxError(
                        err(
                            "E2150",
                            expr.lineno,
                            f"Matrix.{method_name} supports only axis",
                            "Use Matrix.method(axis: 0) or Matrix.method().",
                        )
                    )
                axis_type = self._check_expression(expr.keywords[0].value)
                if axis_type != "int":
                    raise SyntaxError(
                        err(
                            "E2054",
                            expr.lineno,
                            "axis expression must be int",
                            "Use axis: 0 or axis: 1.",
                        )
                    )
                if (
                    (axis_value := extract_int_literal(expr.keywords[0].value))
                    is not None
                    and axis_value not in {0, 1}
                ):
                    raise SyntaxError(
                        err(
                            "E2150",
                            expr.lineno,
                            "Matrix axis must be 0 or 1",
                            "Use axis: 0 or axis: 1.",
                        )
                    )
                if owner_rank == 1:
                    raise SyntaxError(
                        err(
                            "E2150",
                            expr.lineno,
                            f"Matrix.{method_name}(axis=...) only works on rank-2 Matrix values",
                            "Use Matrix.method() on vectors instead.",
                        )
                    )

                result_element_type = (
                    "float" if method_name == "mean" else owner_element_type
                )
                return "Matrix", 1, result_element_type

            result_element_type = (
                "float"
                if method_name == "mean"
                else (owner_element_type or "float")
            )
            return result_element_type, None, None

        if method_name == "transpose":
            if expr.args or expr.keywords:
                raise SyntaxError(
                    err(
                        "E2150",
                        expr.lineno,
                        "Matrix.transpose takes no arguments",
                        "Use Matrix.transpose().",
                    )
                )
            return "Matrix", owner_rank, owner_element_type

        if method_name in {"inverse", "determinant", "norm"}:
            if expr.args or expr.keywords:
                raise SyntaxError(
                    err(
                        "E2150",
                        expr.lineno,
                        f"Matrix.{method_name} takes no arguments",
                        f"Use Matrix.{method_name}().",
                    )
                )
            if method_name in {"inverse", "determinant"} and owner_rank == 1:
                raise SyntaxError(
                    err(
                        "E2150",
                        expr.lineno,
                        f"Matrix.{method_name} only works on rank-2 Matrix values",
                        "Use a rank-2 Matrix.",
                    )
                )
            if method_name == "inverse":
                return "Matrix", owner_rank, "float"
            return "float", None, None

        if method_name == "solve":
            if expr.keywords or len(expr.args) != 1:
                raise SyntaxError(
                    err(
                        "E2150",
                        expr.lineno,
                        "Matrix.solve expects exactly one Matrix argument",
                        "Use Matrix.solve(b).",
                    )
                )
            if owner_rank == 1:
                raise SyntaxError(
                    err(
                        "E2150",
                        expr.lineno,
                        "Matrix.solve only works on rank-2 Matrix values",
                        "Use a rank-2 Matrix on the left side.",
                    )
                )
            rhs_type = self._check_expression(expr.args[0])
            if rhs_type != "Matrix":
                raise SyntaxError(
                    err(
                        "E2150",
                        expr.lineno,
                        "Matrix.solve expects another Matrix",
                        "Pass a Matrix right-hand side.",
                    )
                )
            rhs_rank, _rhs_element_type = self._matrix_info_for_expr(expr.args[0])
            return "Matrix", rhs_rank, "float"

        if method_name == "hadamard":
            if expr.keywords or len(expr.args) != 1:
                raise SyntaxError(
                    err(
                        "E2150",
                        expr.lineno,
                        "Matrix.hadamard expects exactly one Matrix argument",
                        "Use Matrix.hadamard(other).",
                    )
                )
            rhs_type = self._check_expression(expr.args[0])
            if rhs_type != "Matrix":
                raise SyntaxError(
                    err(
                        "E2150",
                        expr.lineno,
                        "Matrix.hadamard expects another Matrix",
                        "Pass a Matrix right-hand side.",
                    )
                )
            rhs_rank, rhs_element_type = self._matrix_info_for_expr(expr.args[0])
            self._require_same_matrix_rank(
                owner_rank, rhs_rank, expr.lineno, ".hadamard"
            )
            return "Matrix", owner_rank, self._promote_numeric_types(
                owner_element_type, rhs_element_type
            )

        raise SyntaxError(
            err(
                "E2150",
                expr.lineno,
                f"Matrix has no method '{method_name}'",
                "Use Matrix methods only.",
            )
        )

    def _matrix_matmul_result(
        self,
        left_rank: int | None,
        left_element_type: str | None,
        right_rank: int | None,
        right_element_type: str | None,
    ) -> tuple[str, int | None, str | None]:
        result_element_type = self._promote_numeric_types(
            left_element_type, right_element_type
        )

        if left_rank == 1 and right_rank == 1:
            return result_element_type or "float", None, None

        if left_rank == 2 and right_rank == 2:
            return "Matrix", 2, result_element_type

        if (left_rank == 2 and right_rank == 1) or (
            left_rank == 1 and right_rank == 2
        ):
            return "Matrix", 1, result_element_type

        return "Matrix", left_rank or right_rank, result_element_type

    def _validate_type_name(self, type_name: str, lineno: int) -> None:
        for atom in iter_type_atoms(type_name, lineno):
            if atom in PRIMITIVE_TYPES:
                continue
            if not TYPE_NAME_RE.fullmatch(atom):
                raise SyntaxError(
                    err(
                        "E2033",
                        lineno,
                        f"invalid type name '{atom}'",
                        "Use PascalCase for user-defined types.",
                    )
                )

    def _check_type_name(self, name: str, lineno: int) -> None:
        if not TYPE_NAME_RE.fullmatch(name):
            raise SyntaxError(
                err(
                    "E2033",
                    lineno,
                    f"invalid type name '{name}'",
                    "Use PascalCase for user-defined types.",
                )
            )

    def _is_type_compatible(self, declared: str, inferred: str | None) -> bool:
        if declared == "py:any":
            return True
        if inferred is None or inferred == "unknown[]":
            return True
        if declared == inferred:
            return True
        if declared in {"int", "float"} and inferred in {"int", "float"}:
            return True
        return False

    def _resolve_file_import_path(self, raw: str) -> Path | None:
        if self._source_path is None:
            return None
        return (self._source_path.parent / raw).resolve()

    def _import_file_module(self, alias: str, path: Path) -> None:
        if not path.exists() or path.suffix != ".ty":
            return

        cached = self._file_module_cache.get(path)
        if cached is None:
            try:
                source = path.read_text()
                if source.startswith("\ufeff"):
                    source = source.removeprefix("\ufeff")
                tree = parse_custom_source(source).tree

                # Local import to avoid import-cycle: api -> checker.
                from .api import PreludeState, check_semantics_with_prelude

                state = check_semantics_with_prelude(
                    tree,
                    PreludeState(),
                    project_root=self._project_root,
                    source_path=path,
                )
                cached = (
                    dict(state),
                    dict(state.function_signatures),
                    dict(state.record_decls),
                    dict(state.class_decls),
                )
            except SyntaxError:
                return
            self._file_module_cache[path] = cached

        symbols, fn_sigs, record_decls, class_decls = cached

        # Merge type declarations so downstream code can use the imported types.
        for name, decl in record_decls.items():
            self._record_decls.setdefault(name, decl)
        for name, decl in class_decls.items():
            self._class_decls.setdefault(name, decl)
        for name, sig in fn_sigs.items():
            self._function_signatures.setdefault(name, sig)

        # Expose imported module names as alias.<name> in the current module scope.
        module_scope = self._scopes[0]
        for name, (kind, type_name, initialized) in symbols.items():
            qname = f"{alias}.{name}"
            if qname in module_scope.symbols:
                continue
            module_scope.symbols[qname] = Symbol(
                name=qname,
                qualified_name=qname,
                kind=kind,
                type_name=type_name,
                py_module=None,
                lineno=0,
                col_offset=0,
                function_id=None,
                initialized=initialized,
            )

    def _stub_index(self) -> PyImportStubIndex | None:
        if self._project_root is None:
            return None
        stubs_root = self._project_root / "stubs"
        if not stubs_root.exists():
            return None
        if self._pyimport_stubs is None:
            self._pyimport_stubs = PyImportStubIndex(stubs_root)
        return self._pyimport_stubs

    def _check_pyimport_stub_call(self, expr: ast.Call, signature: FunctionSignature) -> None:
        params = signature.params
        required = sum(1 for p in params if not p.has_default)
        if len(expr.args) < required or len(expr.args) > len(params):
            raise SyntaxError(
                err(
                    "E2073",
                    expr.lineno,
                    f"wrong number of arguments for '{signature.name}'",
                    f"Expected between {required} and {len(params)} positional args.",
                )
            )
        if expr.keywords:
            # Keep it simple: stub-based pyimport typing only supports positional args for now.
            for keyword in expr.keywords:
                self._check_expression(keyword.value)
        for arg in expr.args:
            self._check_expression(arg)
