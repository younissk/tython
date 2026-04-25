import pytest

from tython_std.matrix import Matrix


def test_matrix_shape_returns_language_list_contract() -> None:
    matrix = Matrix([[1, 2], [3, 4]])

    assert matrix.shape == [2, 2]
    assert isinstance(matrix.shape, list)
    assert all(isinstance(dim, int) for dim in matrix.shape)


def test_matrix_dtype_returns_language_string_contract() -> None:
    ints = Matrix([1, 2, 3])
    floats = Matrix([1.0, 2.0, 3.0])
    promoted = ints / 2

    assert ints.dtype == "int"
    assert floats.dtype == "float"
    assert promoted.dtype == "float"


def test_matrix_rejects_bool_dtype_keyword() -> None:
    with pytest.raises(TypeError, match="Unknown Matrix dtype: bool"):
        Matrix([1, 2], dtype="bool")
