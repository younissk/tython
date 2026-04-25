from __future__ import annotations

import numbers

import numpy as np


class Matrix:
    def __init__(self, data, dtype=None):
        self._data = np.asarray(data, dtype=self._resolve_dtype(dtype))
        if self._data.ndim not in (1, 2):
            raise TypeError(
                "Matrix supports only rank 1 or rank 2 data. "
                f"Got shape {self._data.shape}."
            )

        if not (
            np.issubdtype(self._data.dtype, np.integer)
            or np.issubdtype(self._data.dtype, np.floating)
        ):
            raise TypeError("Matrix data must use int or float values.")

    def __repr__(self) -> str:
        return f"Matrix({self._data.tolist()!r})"

    def __len__(self) -> int:
        return len(self._data)

    def __add__(self, other):
        other_matrix = self._require_matrix(other, "+")
        self._require_same_shape(other_matrix, "+")
        return Matrix(self._data + other_matrix._data)

    def __sub__(self, other):
        other_matrix = self._require_matrix(other, "-")
        self._require_same_shape(other_matrix, "-")
        return Matrix(self._data - other_matrix._data)

    def __mul__(self, other):
        if isinstance(other, Matrix):
            raise TypeError(
                "Matrix * Matrix is not allowed. "
                "Use A @ B for matrix multiplication, or A.hadamard(B) for element-wise multiplication."
            )
        self._require_scalar(other, "*")
        return Matrix(self._data * other)

    def __rmul__(self, other):
        return self.__mul__(other)

    def __truediv__(self, other):
        if isinstance(other, Matrix):
            raise TypeError("Matrix / Matrix is not allowed. Use A / scalar instead.")
        self._require_scalar(other, "/")
        return Matrix(self._data / other)

    def __rtruediv__(self, other):
        raise TypeError("scalar / Matrix is not allowed. Use Matrix / scalar instead.")

    def __matmul__(self, other):
        other_matrix = self._require_matrix(other, "@")
        result = self._data @ other_matrix._data
        return self._wrap_result(result)

    def hadamard(self, other):
        other_matrix = self._require_matrix(other, ".hadamard")
        self._require_same_shape(other_matrix, ".hadamard")
        return Matrix(np.multiply(self._data, other_matrix._data))

    def sum(self, axis=None):
        return self._wrap_result(np.sum(self._data, axis=axis))

    def mean(self, axis=None):
        return self._wrap_result(np.mean(self._data, axis=axis))

    def min(self, axis=None):
        return self._wrap_result(np.min(self._data, axis=axis))

    def max(self, axis=None):
        return self._wrap_result(np.max(self._data, axis=axis))

    def transpose(self):
        return Matrix(np.transpose(self._data))

    def inverse(self):
        self._require_rank_2("inverse")
        return Matrix(np.linalg.inv(self._data))

    def determinant(self):
        self._require_rank_2("determinant")
        return float(np.linalg.det(self._data))

    def norm(self):
        return float(np.linalg.norm(self._data))

    def solve(self, b):
        other_matrix = self._require_matrix(b, ".solve")
        self._require_rank_2("solve")
        result = np.linalg.solve(self._data, other_matrix._data)
        return self._wrap_result(result)

    @property
    def shape(self):
        return [int(dim) for dim in self._data.shape]

    @property
    def rank(self):
        return self._data.ndim

    @property
    def rows(self):
        self._require_rank_2("rows")
        return self._data.shape[0]

    @property
    def cols(self):
        self._require_rank_2("cols")
        return self._data.shape[1]

    @property
    def dtype(self):
        if np.issubdtype(self._data.dtype, np.integer):
            return "int"
        if np.issubdtype(self._data.dtype, np.floating):
            return "float"
        raise TypeError(f"Unsupported Matrix dtype: {self._data.dtype}")

    def __getitem__(self, index):
        return self._wrap_result(self._data[index])

    def _wrap_result(self, result):
        if isinstance(result, np.ndarray):
            return Matrix(result)
        if isinstance(result, np.generic):
            return result.item()
        return result

    def _require_matrix(self, other, operation: str):
        if not isinstance(other, Matrix):
            raise TypeError(f"Matrix {operation} requires another Matrix.")
        return other

    def _require_same_shape(self, other: Matrix, operation: str) -> None:
        if self.shape != other.shape:
            raise TypeError(
                f"Matrix {operation} requires matching shapes. "
                f"Got {self.shape} and {other.shape}."
            )

    def _require_rank_2(self, operation: str) -> None:
        if self.rank != 2:
            raise TypeError(
                f"Matrix.{operation} only works on rank-2 Matrix values. "
                f"This Matrix has shape {self.shape}."
            )

    def _require_scalar(self, value, operation: str) -> None:
        if not isinstance(value, numbers.Real) or isinstance(value, bool):
            raise TypeError(
                f"Matrix {operation} requires a numeric scalar. "
                f"Got {type(value).__name__}."
            )

    def _resolve_dtype(self, dtype):
        if dtype is None:
            return None
        if dtype == "int":
            return np.int64
        if dtype == "float":
            return np.float64
        raise TypeError(f"Unknown Matrix dtype: {dtype}")
