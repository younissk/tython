from __future__ import annotations

import ast

from ..custom_frontend import (
    BINDING_SENTINEL,
    CLASS_MARKER_SENTINEL,
    CLASS_MEMBER_SENTINEL,
    ENUM_SENTINEL,
    PUB_DECORATOR_SENTINEL,
    RECORD_LITERAL_SENTINEL,
    RECORD_MARKER_SENTINEL,
    SETUP_METHOD_NAME,
)


from .constants import (
    BUILTIN_NAMES,
    CONST_NAME_RE,
    IDENTIFIER_RE,
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
    RecordDecl,
    RecordFieldDecl,
    Scope,
    Symbol,
)
from .type_utils import (
    annotation_to_custom_type,
    extract_int_literal,
    function_type_matches_signature,
    is_function_type,
    iter_type_atoms,
    signature_to_function_type,
)


class SemanticChecker:
    def __init__(self) -> None:
        self._scopes: list[Scope] = [Scope(kind="module", function_id=None, symbols={})]
        self._next_function_id = 1
        self._function_signatures: dict[str, FunctionSignature] = {}
        self._record_decls: dict[str, RecordDecl] = {}
        self._class_decls: dict[str, ClassDecl] = {}
        self._return_type_stack: list[str] = []
        self._loop_depth = 0
        self._current_class_name: str | None = None
        self._class_method_names: set[str] = set()
        self._class_field_names: set[str] = set()
        self._current_class_member_map: dict[str, ClassMemberDecl] = {}
        for builtin in BUILTIN_NAMES:
            self._scopes[0].symbols[builtin] = Symbol(
                name=builtin,
                kind="const",
                type_name=None,
                lineno=0,
                function_id=None,
                initialized=True,
            )

    def check(self, tree: ast.AST) -> None:
        if not isinstance(tree, ast.Module):
            raise SyntaxError(err("E2001", 1, "custom parser expects module input"))
        self._check_statements(tree.body)

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
            if isinstance(stmt, (ast.Return, ast.Break, ast.Continue)):
                terminated_at = stmt

    def _check_statement(self, stmt: ast.stmt) -> None:
        if self._is_binding_decl_stmt(stmt):
            decl = self._extract_binding_decl(stmt)
            self._declare_binding(decl)
            return

        if self._is_enum_decl_stmt(stmt):
            enum_name = self._extract_enum_name(stmt)
            self._check_type_name(enum_name, stmt.lineno)
            self._declare_name(
                enum_name,
                "const",
                enum_name,
                stmt.lineno,
                initialized=True,
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
        raw_signature = self._extract_function_signature(stmt, return_type)
        signature = FunctionSignature(
            name=raw_signature.name,
            params=raw_signature.params,
            return_type=raw_signature.return_type,
            is_public=is_public,
        )

        self._declare_name(stmt.name, "const", None, stmt.lineno, initialized=True)
        self._function_signatures[stmt.name] = signature

        function_id = self._next_function_id
        self._next_function_id += 1

        self._scopes.append(Scope(kind="function", function_id=function_id, symbols={}))
        self._return_type_stack.append(return_type)
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
                        "E2061",
                        stmt.lineno,
                        f"function '{stmt.name}' may exit without returning {return_type}",
                        "Return a value on every reachable control path.",
                    )
                )
        finally:
            self._return_type_stack.pop()
            self._scopes.pop()

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

        record_decl = RecordDecl(
            name=stmt.name,
            fields=fields,
            is_public=is_public,
            location=(stmt.lineno, stmt.col_offset),
        )
        self._record_decls[stmt.name] = record_decl
        self._declare_name(stmt.name, "const", stmt.name, stmt.lineno, initialized=True)

    def _check_class_decl(self, stmt: ast.ClassDef, marker: tuple[str | None, bool]) -> None:
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
                continue

            if isinstance(member_stmt, ast.FunctionDef):
                self._sync_pending_class_member_context(current_field_names, methods, members)
                if member_stmt.name == SETUP_METHOD_NAME:
                    setup_count += 1
                    self._check_setup_method(member_stmt, stmt.name)
                    continue
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
        self._declare_name(stmt.name, "const", stmt.name, stmt.lineno, initialized=True)
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

        previous = self._begin_class_callable_scope(
            class_name=class_name,
            lineno=stmt.lineno,
            return_type="none",
        )
        try:
            self._check_statements(stmt.body)
        finally:
            self._end_class_callable_scope(previous)

    def _check_class_method_decl(self, stmt: ast.FunctionDef, class_name: str) -> FunctionSignature:
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
        signature = self._extract_method_signature(stmt, return_type, is_public=is_public)

        previous = self._begin_class_callable_scope(
            class_name=class_name,
            lineno=stmt.lineno,
            return_type=return_type,
            method_names=self._class_method_names | {stmt.name},
            field_names=self._class_field_names,
        )
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
            self._end_class_callable_scope(previous)

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
        self._declare_name("self", "const", class_name, lineno, initialized=True)
        return previous_class, previous_method_names, previous_field_names, previous_member_map

    def _end_class_callable_scope(
        self, previous: tuple[str | None, set[str], set[str], dict[str, ClassMemberDecl]]
    ) -> None:
        previous_class, previous_method_names, previous_field_names, previous_member_map = previous
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
                    if not function_type_matches_signature(field.type_name, method, lineno):
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

            params.append(FunctionParam(name=arg.arg, type_name=type_name, has_default=has_default))

        return FunctionSignature(name=stmt.name, params=params, return_type=return_type)

    def _extract_method_signature(
        self, stmt: ast.FunctionDef, return_type: str, *, is_public: bool
    ) -> FunctionSignature:
        args = stmt.args
        if args.posonlyargs or args.vararg is not None or args.kwarg is not None or args.kwonlyargs:
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
            params.append(FunctionParam(name=arg.arg, type_name=type_name, has_default=has_default))

        return FunctionSignature(
            name=stmt.name,
            params=params,
            return_type=return_type,
            is_public=is_public,
        )

    def _has_pub_decorator(self, stmt: ast.FunctionDef) -> bool:
        return any(
            isinstance(dec, ast.Name) and dec.id == PUB_DECORATOR_SENTINEL
            for dec in stmt.decorator_list
        )

    def _ensure_supported_function_decorators(self, stmt: ast.FunctionDef) -> None:
        for decorator in stmt.decorator_list:
            if isinstance(decorator, ast.Name) and decorator.id == PUB_DECORATOR_SENTINEL:
                continue
            raise SyntaxError(
                err(
                    "E2136",
                    getattr(stmt, "lineno", 1),
                    "unsupported function decorator",
                    "Only `pub` visibility metadata is supported.",
                )
            )

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
                raise SyntaxError(err("E2138", stmt.lineno, "invalid record visibility marker"))
            return arg.value
        return None

    def _extract_class_marker(self, stmt: ast.ClassDef) -> tuple[str | None, bool] | None:
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
                raise SyntaxError(err("E2140", stmt.lineno, "invalid class conformance marker"))
            if not isinstance(is_public, ast.Constant) or not isinstance(is_public.value, bool):
                raise SyntaxError(err("E2141", stmt.lineno, "invalid class visibility marker"))
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
            raise SyntaxError(err("E2143", stmt.lineno, "class member kind must be string"))
        if not isinstance(name, ast.Constant) or not isinstance(name.value, str):
            raise SyntaxError(err("E2144", stmt.lineno, "class member name must be string"))
        if not isinstance(type_name, ast.Constant) or (
            type_name.value is not None and not isinstance(type_name.value, str)
        ):
            raise SyntaxError(err("E2145", stmt.lineno, "class member type must be string/none"))
        if not isinstance(has_init, ast.Constant) or not isinstance(has_init.value, bool):
            raise SyntaxError(err("E2146", stmt.lineno, "class member initializer flag must be bool"))
        if not isinstance(is_public, ast.Constant) or not isinstance(is_public.value, bool):
            raise SyntaxError(err("E2147", stmt.lineno, "class member public flag must be bool"))
        if not isinstance(in_class, ast.Constant) or not isinstance(in_class.value, bool):
            raise SyntaxError(err("E2148", stmt.lineno, "class member class-context flag must be bool"))
        if not in_class.value:
            raise SyntaxError(err("E2149", stmt.lineno, "class member declaration used outside class"))
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

    def _block_guarantees_return(self, body: list[ast.stmt]) -> bool:
        for stmt in body:
            if self._statement_guarantees_return(stmt):
                return True
        return False

    def _statement_guarantees_return(self, stmt: ast.stmt) -> bool:
        if isinstance(stmt, ast.Return):
            return True
        if isinstance(stmt, ast.If):
            if not stmt.orelse:
                return False
            return self._block_guarantees_return(stmt.body) and self._block_guarantees_return(
                stmt.orelse
            )
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
        self._declare_name(target.id, "var", None, lineno, initialized=True)
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
            )
            return symbol.type_name

        if self._is_record_literal_expr(expr):
            return self._check_record_literal_expression(expr)

        if isinstance(expr, ast.Constant):
            return self._infer_constant_type(expr)

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
            value_type = self._check_expression(expr.value)
            class_decl = self._class_decls.get(value_type or "")
            if class_decl is not None:
                if expr.attr in class_decl.methods:
                    return signature_to_function_type(class_decl.methods[expr.attr])
                for member in class_decl.members:
                    if member.name == expr.attr:
                        return member.type_name
            if (
                isinstance(expr.value, ast.Name)
                and expr.value.id == "self"
                and self._current_class_name is not None
            ):
                if expr.attr not in self._class_field_names and expr.attr not in self._class_method_names:
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
        self._check_expression(expr.func)

        if isinstance(expr.func, ast.Attribute) and expr.func.attr in {"setup", SETUP_METHOD_NAME}:
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

        for arg in expr.args:
            self._check_expression(arg)
        for kw in expr.keywords:
            self._check_expression(kw.value)

        if not isinstance(expr.func, ast.Name):
            return None

        if expr.func.id == "len":
            return "int"
        if expr.func.id == "print":
            return "none"
        if expr.func.id == "range":
            return "int[]"

        class_decl = self._class_decls.get(expr.func.id)
        if class_decl is not None:
            return self._check_class_constructor_call(expr, class_decl)

        signature = self._function_signatures.get(expr.func.id)
        if signature is None:
            return None

        if expr.args:
            self._check_positional_call(expr, signature)
        else:
            self._check_named_call(expr, signature)

        return signature.return_type

    def _check_positional_call(self, expr: ast.Call, signature: FunctionSignature) -> None:
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

        missing = [p.name for p in signature.params if not p.has_default and p.name not in seen]
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
        if not isinstance(type_node, ast.Constant) or not isinstance(type_node.value, str):
            raise SyntaxError(err("E2154", expr.lineno, "record literal type must be a string"))
        if not isinstance(fields_node, ast.List):
            raise SyntaxError(err("E2155", expr.lineno, "record literal fields must be a list"))

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

        seen: set[str] = set()
        values_by_name: dict[str, ast.expr] = {}
        for element in fields_node.elts:
            if not isinstance(element, ast.Tuple) or len(element.elts) != 2:
                raise SyntaxError(err("E2157", expr.lineno, "invalid record field entry"))
            key_node, value_node = element.elts
            if not isinstance(key_node, ast.Constant) or not isinstance(key_node.value, str):
                raise SyntaxError(err("E2158", expr.lineno, "record field name must be string"))
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

    def _check_class_constructor_call(self, expr: ast.Call, class_decl: ClassDecl) -> str:
        if expr.args:
            raise SyntaxError(
                err(
                    "E2163",
                    expr.lineno,
                    f"class constructor '{class_decl.name}' requires named arguments",
                    "Use named constructor arguments only.",
                )
            )

        init_members = [m for m in class_decl.members if m.kind in {"init_var", "init_const"}]
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

        missing = [m.name for m in init_members if not m.has_initializer and m.name not in seen]
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

    def _check_self_member_assignment(self, attr: str, value: ast.expr, lineno: int) -> None:
        if not self._current_class_member_map:
            raise SyntaxError(err("E2169", lineno, "instance assignment outside class context"))
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

        if decl.kind == "const" and not CONST_NAME_RE.fullmatch(decl.name):
            raise SyntaxError(
                err(
                    "E2013",
                    lineno,
                    f"invalid const name '{decl.name}'",
                    "Use UPPER_SNAKE_CASE for const bindings.",
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
        )

    def _check_assignment_target(self, assignment: Assignment) -> None:
        symbol = self._resolve_name(
            assignment.target,
            assignment.location[0],
            for_write=True,
            require_initialized=False,
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

        symbol.initialized = True

    def _declare_name(
        self,
        name: str,
        kind: str,
        type_name: str | None,
        lineno: int,
        initialized: bool,
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

        scope.symbols[name] = Symbol(
            name=name,
            kind=kind,
            type_name=type_name,
            lineno=lineno,
            function_id=self._current_function_id(),
            initialized=initialized,
        )

    def _resolve_name(
        self,
        name: str,
        lineno: int,
        for_write: bool,
        require_initialized: bool,
    ) -> Symbol:
        for scope in reversed(self._scopes):
            symbol = scope.symbols.get(name)
            if symbol is None:
                continue
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
            raise SyntaxError(err("E2026", stmt.lineno, "binding kind must be a string"))
        if kind.value not in {"const", "var"}:
            raise SyntaxError(err("E2027", stmt.lineno, "binding kind must be 'const' or 'var'"))
        if not isinstance(name, ast.Constant) or not isinstance(name.value, str):
            raise SyntaxError(err("E2028", stmt.lineno, "binding name must be a string"))
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
        if not isinstance(is_public, ast.Constant) or not isinstance(is_public.value, bool):
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
        if not isinstance(enum_name, ast.Constant) or not isinstance(enum_name.value, str):
            raise SyntaxError(
                err("E2032", stmt.lineno, "enum name must be a string literal")
            )
        return enum_name.value

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
        if inferred is None or inferred == "unknown[]":
            return True
        if declared == inferred:
            return True
        if declared in {"int", "float"} and inferred in {"int", "float"}:
            return True
        return False



