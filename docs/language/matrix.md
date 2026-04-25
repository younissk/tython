# Matrix

`Matrix` is a standard-library datatype imported by the language prelude.
It is the language-facing wrapper for numerical array data.

## Construction

Use `Matrix(...)` for rank-1 and rank-2 data:

```txt
const v = Matrix([1, 2, 3])

const A = Matrix([[1, 2], [3, 4]])
```

`Matrix` rejects ambiguous or unsupported shapes at compile time when possible.

## Operators

Supported operators:

- `A + B`
- `A - B`
- `A @ B`
- `A * 3`
- `3 * A`
- `A / 3`

Rejected in v1:

- `A * B`
- `A / B`
- `A ** B`

Use `A.hadamard(B)` for element-wise multiplication.

## Methods

Matrix methods use method syntax:

```txt
A.sum()
A.sum(axis: 0)
A.mean()
A.transpose()
A.inverse()
A.determinant()
A.norm()
A.solve(b)
A.hadamard(B)
```

`sum`, `mean`, `min`, and `max` return a scalar when called without `axis`.
With `axis`, they return a `Matrix`.

## Properties

Use properties for metadata:

```txt
A.shape
A.rank
A.rows
A.cols
A.dtype
```

`rows` and `cols` only work on rank-2 values.
`shape` returns `int[]`.
`dtype` returns `"int"` or `"float"`.

## Indexing

```txt
v[0]
A[0]
A[0, 1]
```

Slicing is not part of v1.

## Runtime Model

The Python backend lowers `Matrix` to a small NumPy-backed wrapper.
NumPy stays hidden from user code, but the generated Python uses it internally.
