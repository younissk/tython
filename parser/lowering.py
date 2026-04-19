import ast

from .custom_frontend import (
    BINDING_SENTINEL,
    CLASS_MARKER_SENTINEL,
    CLASS_MEMBER_SENTINEL,
    ENUM_SENTINEL,
    PUB_DECORATOR_SENTINEL,
    RECORD_LITERAL_SENTINEL,
    RECORD_MARKER_SENTINEL,
    SETUP_METHOD_NAME,
)


def lower(ir: ast.AST) -> ast.AST:
    if not isinstance(ir, ast.AST):
        raise TypeError(f"expected ast.AST, got {type(ir).__name__}")
    lowered = _LowerCustomIR().visit(ir)
    ast.fix_missing_locations(lowered)
    return lowered


class _LowerCustomIR(ast.NodeTransformer):
    def __init__(self) -> None:
        self._needs_enum_import = False
        self._needs_dataclass_import = False

    def visit_Module(self, node: ast.Module) -> ast.Module:
        self.generic_visit(node)

        lowered_body: list[ast.stmt] = []
        for stmt in node.body:
            lowered_stmt = self._lower_stmt(stmt)
            if lowered_stmt is None:
                lowered_body.append(stmt)
                continue
            lowered_body.append(lowered_stmt)

        if self._needs_enum_import and not _has_import_from(lowered_body, "enum", "Enum"):
            lowered_body.insert(
                0,
                ast.ImportFrom(
                    module="enum", names=[ast.alias(name="Enum", asname=None)], level=0
                ),
            )
        if self._needs_dataclass_import and not _has_import_from(
            lowered_body, "dataclasses", "dataclass"
        ):
            lowered_body.insert(
                0,
                ast.ImportFrom(
                    module="dataclasses",
                    names=[ast.alias(name="dataclass", asname=None)],
                    level=0,
                ),
            )

        node.body = lowered_body
        return node

    def visit_Call(self, node: ast.Call) -> ast.AST:
        self.generic_visit(node)
        if isinstance(node.func, ast.Name) and node.func.id == RECORD_LITERAL_SENTINEL:
            return self._lower_record_literal_call(node)
        return node

    def _lower_stmt(self, stmt: ast.stmt) -> ast.stmt | None:
        if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call):
            call = stmt.value
            if isinstance(call.func, ast.Name):
                if call.func.id == ENUM_SENTINEL:
                    return self._lower_enum_stmt(call)
                if call.func.id == BINDING_SENTINEL:
                    return self._lower_binding_stmt(call)
        if isinstance(stmt, ast.ClassDef):
            lowered = self._lower_classdef(stmt)
            if lowered is not None:
                return lowered
        return None

    def _lower_enum_stmt(self, call: ast.Call) -> ast.ClassDef:
        if len(call.args) != 2 or call.keywords:
            raise SyntaxError("internal enum IR shape is invalid")

        enum_name_node, members_node = call.args
        if not isinstance(enum_name_node, ast.Constant) or not isinstance(
            enum_name_node.value, str
        ):
            raise SyntaxError("enum name must be a string literal in custom IR")
        if not isinstance(members_node, ast.List):
            raise SyntaxError("enum members must be a literal list in custom IR")

        members: list[str] = []
        for element in members_node.elts:
            if not isinstance(element, ast.Constant) or not isinstance(
                element.value, str
            ):
                raise SyntaxError("enum member names must be string literals in custom IR")
            members.append(element.value)

        self._needs_enum_import = True
        return ast.ClassDef(
            name=enum_name_node.value,
            bases=[ast.Name(id="Enum", ctx=ast.Load())],
            keywords=[],
            body=[
                ast.Assign(
                    targets=[ast.Name(id=member, ctx=ast.Store())],
                    value=ast.Constant(value=member),
                )
                for member in members
            ],
            decorator_list=[],
        )

    def _lower_binding_stmt(self, call: ast.Call) -> ast.Assign | ast.AnnAssign:
        if len(call.args) != 6 or call.keywords:
            raise SyntaxError("internal binding IR shape is invalid")

        _, name_node, annotation_node, value, has_initializer_node, _ = call.args
        if not isinstance(name_node, ast.Constant) or not isinstance(name_node.value, str):
            raise SyntaxError("binding name must be a string literal in custom IR")
        if not isinstance(annotation_node, ast.Constant) or (
            annotation_node.value is not None and not isinstance(annotation_node.value, str)
        ):
            raise SyntaxError("binding annotation must be string or none in custom IR")
        if not isinstance(has_initializer_node, ast.Constant) or not isinstance(
            has_initializer_node.value, bool
        ):
            raise SyntaxError("binding initializer flag must be bool in custom IR")

        target = ast.Name(id=name_node.value, ctx=ast.Store())
        has_initializer = has_initializer_node.value
        if annotation_node.value is None:
            if not has_initializer:
                raise SyntaxError(
                    "binding without initializer requires an explicit type annotation"
                )
            return ast.Assign(targets=[target], value=value)

        annotation = ast.parse(_to_python_annotation(annotation_node.value), mode="eval").body
        ann_value = value if has_initializer else None
        return ast.AnnAssign(target=target, annotation=annotation, value=ann_value, simple=1)

    def _lower_classdef(self, stmt: ast.ClassDef) -> ast.ClassDef | None:
        marker = _extract_marker_call(stmt.body, RECORD_MARKER_SENTINEL)
        if marker is not None:
            return self._lower_record_class(stmt)

        marker = _extract_marker_call(stmt.body, CLASS_MARKER_SENTINEL)
        if marker is not None:
            return self._lower_runtime_class(stmt)
        return None

    def _lower_record_class(self, stmt: ast.ClassDef) -> ast.ClassDef:
        members = _extract_class_members(stmt.body)
        fields: list[ast.stmt] = []
        for member in members:
            kind = _const_str(member.args[0], "class member kind")
            if kind != "record_field":
                continue
            name = _const_str(member.args[1], "record field name")
            type_name = _const_optional_str(member.args[2], "record field type")
            if type_name is None:
                raise SyntaxError("record field type is required")
            fields.append(
                ast.AnnAssign(
                    target=ast.Name(id=name, ctx=ast.Store()),
                    annotation=ast.parse(_to_python_annotation(type_name), mode="eval").body,
                    value=None,
                    simple=1,
                )
            )

        self._needs_dataclass_import = True
        return ast.ClassDef(
            name=stmt.name,
            bases=[],
            keywords=[],
            body=fields or [ast.Pass()],
            decorator_list=[
                ast.Call(
                    func=ast.Name(id="dataclass", ctx=ast.Load()),
                    args=[],
                    keywords=[ast.keyword(arg="frozen", value=ast.Constant(value=True))],
                )
            ],
        )

    def _lower_runtime_class(self, stmt: ast.ClassDef) -> ast.ClassDef:
        members = _extract_class_members(stmt.body)
        methods: list[ast.FunctionDef] = []
        setup_method: ast.FunctionDef | None = None
        for member in stmt.body:
            if isinstance(member, ast.FunctionDef):
                clean = ast.FunctionDef(
                    name=member.name,
                    args=member.args,
                    body=member.body,
                    decorator_list=[
                        dec
                        for dec in member.decorator_list
                        if not (isinstance(dec, ast.Name) and dec.id == PUB_DECORATOR_SENTINEL)
                    ],
                    returns=member.returns,
                    type_comment=member.type_comment,
                )
                if clean.name == SETUP_METHOD_NAME:
                    setup_method = clean
                else:
                    methods.append(clean)

        init_members = [m for m in members if _const_str(m.args[0], "kind") in {"init_var", "init_const"}]
        normal_members = [m for m in members if _const_str(m.args[0], "kind") in {"var", "const"}]

        init_fn = self._build_init(init_members, normal_members, setup_method)
        body: list[ast.stmt] = [init_fn]
        body.extend(methods)
        if not body:
            body = [ast.Pass()]
        return ast.ClassDef(
            name=stmt.name,
            bases=[],
            keywords=[],
            body=body,
            decorator_list=[],
        )

    def _build_init(
        self,
        init_members: list[ast.Call],
        normal_members: list[ast.Call],
        setup_method: ast.FunctionDef | None,
    ) -> ast.FunctionDef:
        kwonlyargs: list[ast.arg] = []
        kw_defaults: list[ast.expr | None] = []
        body: list[ast.stmt] = []

        for member in init_members:
            name = _const_str(member.args[1], "member name")
            type_name = _const_optional_str(member.args[2], "member type")
            has_initializer = _const_bool(member.args[4], "initializer flag")
            initializer = member.args[3]
            kwonlyargs.append(
                ast.arg(
                    arg=name,
                    annotation=ast.parse(_to_python_annotation(type_name), mode="eval").body
                    if type_name
                    else None,
                )
            )
            kw_defaults.append(initializer if has_initializer else None)
            body.append(
                ast.Assign(
                    targets=[
                        ast.Attribute(
                            value=ast.Name(id="self", ctx=ast.Load()),
                            attr=name,
                            ctx=ast.Store(),
                        )
                    ],
                    value=ast.Name(id=name, ctx=ast.Load()),
                )
            )

        for member in normal_members:
            name = _const_str(member.args[1], "member name")
            has_initializer = _const_bool(member.args[4], "initializer flag")
            if not has_initializer:
                continue
            body.append(
                ast.Assign(
                    targets=[
                        ast.Attribute(
                            value=ast.Name(id="self", ctx=ast.Load()),
                            attr=name,
                            ctx=ast.Store(),
                        )
                    ],
                    value=member.args[3],
                )
            )

        if setup_method is not None:
            body.extend(setup_method.body)

        if not body:
            body = [ast.Pass()]

        return ast.FunctionDef(
            name="__init__",
            args=ast.arguments(
                posonlyargs=[],
                args=[ast.arg(arg="self", annotation=None)],
                vararg=None,
                kwonlyargs=kwonlyargs,
                kw_defaults=kw_defaults,
                kwarg=None,
                defaults=[],
            ),
            body=body,
            decorator_list=[],
            returns=ast.Constant(value=None),
            type_comment=None,
        )

    def _lower_record_literal_call(self, call: ast.Call) -> ast.Call:
        if len(call.args) != 2 or call.keywords:
            raise SyntaxError("internal record literal IR shape is invalid")
        type_node, fields_node = call.args
        if not isinstance(type_node, ast.Constant) or not isinstance(type_node.value, str):
            raise SyntaxError("record literal type must be a string literal")
        if not isinstance(fields_node, ast.List):
            raise SyntaxError("record literal fields must be a literal list")

        keywords: list[ast.keyword] = []
        for element in fields_node.elts:
            if not isinstance(element, ast.Tuple) or len(element.elts) != 2:
                raise SyntaxError("record literal field entry must be (name, value)")
            key_node, value_node = element.elts
            if not isinstance(key_node, ast.Constant) or not isinstance(key_node.value, str):
                raise SyntaxError("record literal field key must be string literal")
            keywords.append(ast.keyword(arg=key_node.value, value=value_node))

        return ast.Call(
            func=ast.Name(id=type_node.value, ctx=ast.Load()),
            args=[],
            keywords=keywords,
        )


def _to_python_annotation(custom_type: str) -> str:
    if custom_type.startswith("(") and ")->" in custom_type:
        return repr(custom_type)

    base = custom_type
    dims = 0
    while base.endswith("[]"):
        dims += 1
        base = base[:-2]

    if base == "none":
        base = "None"

    value = base
    for _ in range(dims):
        value = f"list[{value}]"
    return value


def _has_import_from(stmts: list[ast.stmt], module: str, name: str) -> bool:
    for stmt in stmts:
        if not isinstance(stmt, ast.ImportFrom):
            continue
        if stmt.module != module or stmt.level != 0:
            continue
        if any(alias.name == name for alias in stmt.names):
            return True
    return False


def _extract_marker_call(body: list[ast.stmt], marker_name: str) -> ast.Call | None:
    for stmt in body:
        if (
            isinstance(stmt, ast.Expr)
            and isinstance(stmt.value, ast.Call)
            and isinstance(stmt.value.func, ast.Name)
            and stmt.value.func.id == marker_name
        ):
            return stmt.value
    return None


def _extract_class_members(body: list[ast.stmt]) -> list[ast.Call]:
    members: list[ast.Call] = []
    for stmt in body:
        if (
            isinstance(stmt, ast.Expr)
            and isinstance(stmt.value, ast.Call)
            and isinstance(stmt.value.func, ast.Name)
            and stmt.value.func.id == CLASS_MEMBER_SENTINEL
        ):
            members.append(stmt.value)
    return members


def _const_str(node: ast.expr, label: str) -> str:
    if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
        raise SyntaxError(f"{label} must be a string literal in custom IR")
    return node.value


def _const_optional_str(node: ast.expr, label: str) -> str | None:
    if not isinstance(node, ast.Constant):
        raise SyntaxError(f"{label} must be string/none in custom IR")
    if node.value is None:
        return None
    if not isinstance(node.value, str):
        raise SyntaxError(f"{label} must be string/none in custom IR")
    return node.value


def _const_bool(node: ast.expr, label: str) -> bool:
    if not isinstance(node, ast.Constant) or not isinstance(node.value, bool):
        raise SyntaxError(f"{label} must be bool in custom IR")
    return node.value
