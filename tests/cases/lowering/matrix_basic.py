from tython_std.matrix import Matrix

a = Matrix([[1, 2], [3, 4]])
total = a.sum()
axis0 = a.sum(axis=0)
row = a[0]
entry = a[0, 1]
scaled = 2 * a
