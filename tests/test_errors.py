import pytest

from parser import parse_custom
from parser.custom_frontend import parse_custom_source
from parser.semantics import check_semantics_with_prelude


def test_error_message_has_code_line_and_hint_for_undeclared_use() -> None:
    source = "print(x)\n"
    with pytest.raises(SyntaxError) as exc:
        parse_custom(source)

    message = str(exc.value)
    assert "[E2024]" in message
    assert "Line 1" in message
    assert "Hint:" in message


def test_error_message_for_uninitialized_read_is_actionable() -> None:
    source = "var count: int\nprint(count)\n"
    with pytest.raises(SyntaxError) as exc:
        parse_custom(source)

    message = str(exc.value)
    assert "[E2022]" in message
    assert "declared but not initialized" in message
    assert "Initialize it before reading" in message


def test_prelude_keeps_inferred_type_across_snippets() -> None:
    declared: dict[str, tuple[str, str | None, bool]] = {}
    first = parse_custom_source("var test2 = 1\n")
    declared = check_semantics_with_prelude(first.tree, declared)

    second = parse_custom_source('test2 = "hi"\n')
    with pytest.raises(SyntaxError) as exc:
        check_semantics_with_prelude(second.tree, declared)

    message = str(exc.value)
    assert "[E2018]" in message
    assert "assignment type mismatch for 'test2'" in message


def test_error_for_truthy_if_condition_requires_bool() -> None:
    source = "var count = 1\nif count {\n    print(count)\n}\n"
    with pytest.raises(SyntaxError) as exc:
        parse_custom(source)
    message = str(exc.value)
    assert "[E2037]" in message
    assert "if condition must be bool" in message
    assert "Hint:" in message


def test_error_for_disallowed_chained_comparison() -> None:
    source = "var x = 5\nvar ok = 1 < x < 10\n"
    with pytest.raises(SyntaxError) as exc:
        parse_custom(source)
    message = str(exc.value)
    assert "[E2048]" in message
    assert "chained comparisons are not allowed" in message


def test_error_for_disallowed_slice_indexing() -> None:
    source = "var items: int[] = [1, 2, 3]\nvar part = items[1:2]\n"
    with pytest.raises(SyntaxError) as exc:
        parse_custom(source)
    message = str(exc.value)
    assert "[E2053]" in message
    assert "slice expressions are not supported" in message


def test_error_for_nested_func_declaration() -> None:
    source = "func outer() -> int {\n    func inner() -> int = 1\n    return inner()\n}\n"
    with pytest.raises(SyntaxError) as exc:
        parse_custom(source)
    message = str(exc.value)
    assert "[E2058]" in message
    assert "nested function declarations are not allowed" in message


def test_error_for_mixed_positional_and_named_call() -> None:
    source = (
        'func greet(name: str, title: str = "Mr") -> str = title + " " + name\n'
        'var bad = greet("Y", title: "Dr")\n'
    )
    with pytest.raises(SyntaxError) as exc:
        parse_custom(source)
    message = str(exc.value)
    assert "[E2072]" in message
    assert "mixed positional and named arguments are not allowed" in message


def test_error_for_empty_block_requires_pass() -> None:
    source = "if true {\n}\n"
    with pytest.raises(SyntaxError) as exc:
        parse_custom(source)
    message = str(exc.value)
    assert "[E1016]" in message
    assert "empty block is not allowed" in message


def test_error_for_break_outside_loop() -> None:
    source = "break\n"
    with pytest.raises(SyntaxError) as exc:
        parse_custom(source)
    message = str(exc.value)
    assert "[E2085]" in message
    assert "break is only valid inside while loops" in message


def test_error_for_unreachable_after_return() -> None:
    source = "func f() -> int {\n    return 1\n    print(2)\n}\n"
    with pytest.raises(SyntaxError) as exc:
        parse_custom(source)
    message = str(exc.value)
    assert "[E2087]" in message
    assert "unreachable statement after control-flow terminator" in message


def test_error_for_non_call_expression_statement() -> None:
    source = "var x = 1\nx + 1\n"
    with pytest.raises(SyntaxError) as exc:
        parse_custom(source)
    message = str(exc.value)
    assert "[E2088]" in message
    assert "only call expressions are allowed as standalone statements" in message


def test_error_for_ternary_non_bool_condition() -> None:
    source = 'var count = 1\nvar label = if count: "yes" else "no"\n'
    with pytest.raises(SyntaxError) as exc:
        parse_custom(source)
    message = str(exc.value)
    assert "[E2089]" in message
    assert "ternary condition must be bool" in message


def test_error_for_for_loop_not_supported() -> None:
    source = "for i in range(3) {\n    print(i)\n}\n"
    with pytest.raises(SyntaxError) as exc:
        parse_custom(source)
    message = str(exc.value)
    assert "[E2084]" in message
    assert "for loops are not supported in v1" in message


def test_error_for_pub_init_var() -> None:
    source = "class Fish {\n    pub init var name: str\n}\n"
    with pytest.raises(SyntaxError) as exc:
        parse_custom(source)
    message = str(exc.value)
    assert "[E1025]" in message
    assert "init fields are already public" in message


def test_error_for_manual_setup_call() -> None:
    source = (
        "class Fish {\n"
        "    init var name: str\n"
        "    setup {\n"
        "        print(this.name)\n"
        "    }\n"
        "}\n"
        "const F = Fish(name: \"Nemo\")\n"
        "F.setup()\n"
    )
    with pytest.raises(SyntaxError) as exc:
        parse_custom(source)
    message = str(exc.value)
    assert "[E2151]" in message
    assert "setup cannot be called manually" in message


def test_error_for_private_method_record_conformance() -> None:
    source = (
        "record Animal {\n"
        "    speak: () -> none\n"
        "}\n"
        "class Fish is Animal {\n"
        "    func speak() -> none {\n"
        "        print(\"x\")\n"
        "    }\n"
        "}\n"
    )
    with pytest.raises(SyntaxError) as exc:
        parse_custom(source)
    message = str(exc.value)
    assert "[E2123]" in message
    assert "private method 'speak'" in message
