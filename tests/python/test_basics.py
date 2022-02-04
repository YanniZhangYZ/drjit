import drjit as dr
import pytest
import gc


def get_class(name):
    """Resolve a package+class name into the corresponding type"""
    if 'cuda' in name:
        if not dr.has_backend(dr.JitBackend.CUDA):
            pytest.skip('CUDA mode is unsupported')
    elif 'llvm' in name:
        if not dr.has_backend(dr.JitBackend.LLVM):
            pytest.skip('LLVM mode is unsupported')
    elif 'packet' in name and not hasattr(dr, 'packet'):
        pytest.skip('Packet mode is unsupported')

    name = name.split('.')
    value = __import__(".".join(name[:-1]))
    for item in name[1:]:
        value = getattr(value, item)
    return value


def test01_construct():
    a = dr.scalar.Array3f(1, 2, 3)
    assert(repr(a) == "[1.0, 2.0, 3.0]")
    a = dr.scalar.Array3f([1, 2, 3])
    assert(repr(a) == "[1.0, 2.0, 3.0]")
    a = dr.scalar.Array3f((1, 2, 3))
    assert(repr(a) == "[1.0, 2.0, 3.0]")
    a = dr.scalar.Array3f(4)
    assert(repr(a) == "[4.0, 4.0, 4.0]")

    with pytest.raises(TypeError) as ei:
        a = dr.scalar.Array3f("asdf")

    assert "Array3f constructor expects: 1 or 3 values of type \"float\", a " \
        "matching list/tuple, or a NumPy/PyTorch/TF/Jax array." in str(ei.value)


@pytest.mark.parametrize("cname", ["drjit.scalar.Array1f",
                                   "drjit.scalar.Array1i",
                                   "drjit.packet.Float",
                                   "drjit.packet.Int",
                                   "drjit.cuda.Float",
                                   "drjit.cuda.Int",
                                   "drjit.cuda.ad.Float",
                                   "drjit.cuda.ad.Int",
                                   "drjit.llvm.Float",
                                   "drjit.llvm.Int",
                                   "drjit.llvm.ad.Float",
                                   "drjit.llvm.ad.Int"
                                   ])
def test02_basic_ops(cname):
    t = get_class(cname)

    # Test basic arithmetic operations
    import drjit.router as r
    nc = r._entry_evals
    v1 = t(4)
    v2 = t(2)
    assert v1[0] == 4
    assert v2[0] == 2
    v3 = v1 + v2
    assert v3[0] == 6
    v3 = v1 - v2
    assert v3[0] == 2
    v3 = v1 * v2
    assert v3[0] == 8

    if dr.scalar_t(t) is int:
        v3 = v1 // v2
        assert v3[0] == 2
        with pytest.raises(dr.Exception):
            v3 = v1 / v2
    else:
        v3 = v1 / v2
        assert v3[0] == 2.0
        with pytest.raises(dr.Exception):
            v3 = v1 // v2

    # Make sure that in-place ops are truly in-place
    v = t(1)
    v_id = id(v)

    if dr.scalar_t(t) is int:
        v //= v
        v >>= 0
        v <<= 0
        v %= v
    else:
        v /= v

    v += v
    v -= v
    v *= v

    assert v_id == id(v)

    # We now exactly how many times Array.entry()/set_entry()
    # should have been called during all of the above
    entry_evals = 6
    if 'scalar' in cname:
        entry_evals = 39 if dr.scalar_t(t) is int else 30

    assert r._entry_evals == nc + entry_evals
    assert not t.IsDynamic == hasattr(v3, 'x')


@pytest.mark.parametrize("pkg", ['drjit.packet', 'drjit.cuda', 'drjit.llvm'])
def test03_type_promotion(pkg):
    m = get_class(pkg)

    assert type(m.Array1b() | m.Array1b()) is m.Array1b
    assert type(m.Array1b() ^ m.Array1b()) is m.Array1b
    assert type(m.Array1b() & m.Array1b()) is m.Array1b

    with pytest.raises(dr.Exception) as ei:
        _ = m.Array1b() + m.Array1b()
    assert "add(): requires arithmetic operands!" in str(ei.value)

    assert type(m.Array1i() + m.Array1i()) is m.Array1i
    assert type(m.Array1i() + m.Array1u()) is m.Array1u
    assert type(m.Array1i() + m.Array1i64()) is m.Array1i64
    assert type(m.Array1i() + m.Array1u64()) is m.Array1u64
    assert type(m.Array1i() + m.Array1f()) is m.Array1f
    assert type(m.Array1i() + m.Array1f64()) is m.Array1f64

    with pytest.raises(dr.Exception) as ei:
        _ = dr.sqrt(m.Array1i())
    assert "sqrt(): requires floating point operands!" in str(ei.value)

    assert type(m.Array1f() + m.Array1f()) is m.Array1f
    assert type(m.Array1f() + m.Array1u()) is m.Array1f
    assert type(m.Array1f() + m.Array1i64()) is m.Array1f
    assert type(m.Array1f() + m.Array1u64()) is m.Array1f
    assert type(m.Array1f() + m.Array1f()) is m.Array1f
    assert type(m.Array1f() + m.Array1f64()) is m.Array1f64

    assert type(m.Array1f() | m.Array1b()) is m.Array1f
    assert type(m.Array1f() ^ m.Array1b()) is m.Array1f
    assert type(m.Array1f() & m.Array1b()) is m.Array1f


# Run various standard operations on a 3D array
def test04_operators():
    I3 = dr.scalar.Array3i
    F3 = dr.scalar.Array3f

    assert(I3(1, 2, 3) + I3(0, 1, 0) == I3(1, 3, 3))
    assert(I3(1, 2, 3) - I3(0, 1, 0) == I3(1, 1, 3))
    assert(I3(1, 2, 3) * I3(0, 1, 0) == I3(0, 2, 0))
    assert(I3(1, 2, 3) // I3(2, 2, 2) == I3(0, 1, 1))
    assert(I3(1, 2, 3) % I3(2, 2, 2) == I3(1, 0, 1))
    assert(I3(1, 2, 3) << 1 == I3(2, 4, 6))
    assert(I3(1, 2, 3) >> 1 == I3(0, 1, 1))
    assert(I3(1, 2, 3) & 1 == I3(1, 0, 1))
    assert(I3(1, 2, 3) | 1 == I3(1, 3, 3))
    assert(I3(1, 2, 3) ^ 1 == I3(0, 3, 2))
    assert(-I3(1, 2, 3) == I3(-1, -2, -3))
    assert(~I3(1, 2, 3) == I3(-2, -3, -4))
    assert(dr.abs(I3(1, -2, 3)) == I3(1, 2, 3))
    assert(abs(I3(1, -2, 3)) == I3(1, 2, 3))
    assert(dr.abs(I3(1, -2, 3)) == I3(1, 2, 3))
    assert(dr.fmadd(F3(1, 2, 3), F3(2, 3, 1), F3(1, 1, 1)) == F3(3, 7, 4))
    assert(dr.fmsub(F3(1, 2, 3), F3(2, 3, 1), F3(1, 1, 1)) == F3(1, 5, 2))
    assert(dr.fnmadd(F3(1, 2, 3), F3(2, 3, 1), F3(1, 1, 1)) == F3(-1, -5, -2))
    assert(dr.fnmsub(F3(1, 2, 3), F3(2, 3, 1), F3(1, 1, 1)) == F3(-3, -7, -4))


def all_arrays(cond=lambda x: True):
    a = list(dr.scalar.__dict__.items())
    if hasattr(dr, "packet"):
        a += dr.packet.__dict__.items()
    if hasattr(dr, "cuda"):
        a += dr.cuda.__dict__.items()
    if hasattr(dr, "llvm"):
        a += dr.llvm.__dict__.items()
    return [v for k, v in a if isinstance(v, type) and cond(v)
            and not dr.is_special_v(v)
            and not dr.is_tensor_v(v)
            and not dr.is_texture_v(v)
            and not dr.array_depth_v(v) >= 3
            and not (dr.array_depth_v(v) >= 2 and 'scalar' in v.__module__)]


# Run various standard operations on *every available* type
@pytest.mark.parametrize("t", all_arrays())
def test05_scalar(t):
    if not dr.is_array_v(t) or dr.array_size_v(t) == 0:
        return
    get_class(t.__module__)

    if dr.is_mask_v(t):
        assert dr.all_nested(t(True))
        assert dr.any_nested(t(True))
        assert dr.none_nested(t(False))
        assert dr.all_nested(t(False) ^ t(True))
        assert dr.all_nested(dr.eq(t(False), t(False)))
        assert dr.none_nested(dr.eq(t(True), t(False)))

    if dr.is_arithmetic_v(t):
        assert t(1) + t(1) == t(2)
        assert t(3) - t(1) == t(2)
        assert t(2) * t(2) == t(4)
        assert dr.min(t(2), t(3)) == t(2)
        assert dr.max(t(2), t(3)) == t(3)

        if dr.is_signed_v(t):
            assert t(2) * t(-2) == t(-4)
            assert dr.abs(t(-2)) == t(2)

        if dr.is_integral_v(t):
            assert t(6) // t(2) == t(3)
            assert t(7) % t(2) == t(1)
            assert t(7) >> 1 == t(3)
            assert t(7) << 1 == t(14)
            assert t(1) | t(2) == t(3)
            assert t(1) ^ t(3) == t(2)
            assert t(1) & t(3) == t(1)
        else:
            assert t(6) / t(2) == t(3)
            assert dr.sqrt(t(4)) == t(2)
            assert dr.fmadd(t(1), t(2), t(3)) == t(5)
            assert dr.fmsub(t(1), t(2), t(3)) == t(-1)
            assert dr.fnmadd(t(1), t(2), t(3)) == t(1)
            assert dr.fnmsub(t(1), t(2), t(3)) == t(-5)
            assert (t(1) & True) == t(1)
            assert (t(1) & False) == t(0)
            assert (t(1) | False) == t(1)

        assert dr.all_nested(t(3) > t(2))
        assert dr.all_nested(dr.eq(t(2), t(2)))
        assert dr.all_nested(dr.neq(t(3), t(2)))
        assert dr.all_nested(t(1) >= t(1))
        assert dr.all_nested(t(2) < t(3))
        assert dr.all_nested(t(1) <= t(1))
        assert dr.select(dr.eq(t(2), t(2)), t(4), t(5)) == t(4)
        assert dr.select(dr.eq(t(3), t(2)), t(4), t(5)) == t(5)
        t2 = t(2)
        assert dr.hsum(t2) == t.Value(2 * len(t2))
        assert dr.dot(t2, t2) == t.Value(4 * len(t2))
        assert dr.dot_async(t2, t2) == t(4 * len(t2))

        value = t(1)
        value[dr.eq(value, t(1))] = t(2)
        value[dr.eq(value, t(3))] = t(5)
        assert value == t(2)


def test06_reinterpret_cast():
    I3 = dr.scalar.Array3i
    F3 = dr.scalar.Array3f
    B3 = dr.scalar.Array3b
    LI3 = dr.scalar.Array3i64
    LF3 = dr.scalar.Array3f64

    assert dr.mask_t(I3) is B3
    assert dr.scalar_t(F3) is float
    assert dr.scalar_t(I3) is int
    assert dr.float_array_t(I3) is F3
    assert dr.int_array_t(F3) is I3
    assert dr.float_array_t(LI3) is LF3
    assert dr.int_array_t(LF3) is LI3

    assert dr.reinterpret_array(I3, F3(1)).x == 0x3f800000
    assert dr.reinterpret_array(F3, I3(0x3f800000)).x == 1.0


@pytest.mark.parametrize("pkg", ['drjit.cuda', 'drjit.llvm'])
def test07_gather_ravel_unravel(pkg):
    pkg = get_class(pkg)
    str_1 = '[[0.0, 1.0, 2.0],\n [3.0, 4.0, 5.0],\n [6.0, 7.0, 8.0],\n' \
        ' [9.0, 10.0, 11.0]]'
    str_2 = '[0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0, 11.0]'
    a = dr.arange(pkg.Float, 100)
    b = dr.gather(pkg.Array3f, a, pkg.UInt(0, 1, 2, 3))
    assert repr(b) == str_1
    c = dr.ravel(b)
    assert repr(c) == str_2
    d = dr.unravel(pkg.Array3f, c)
    assert repr(d) == str_1


@pytest.mark.parametrize("t", all_arrays(lambda a:
                                         getattr(a, 'IsFloat', False)))
def test07_sincos(t):
    def poly2(x, c0, c1, c2):
        x2 = dr.sqr(x)
        return dr.fmadd(x2, c2, dr.fmadd(x, c1, c0))

    def sincos(x):
        Float = type(x)
        Int = dr.int_array_t(Float)

        xa = dr.abs(x)

        j = Int(xa * 1.2732395447351626862)

        j = (j + Int(1)) & ~Int(1)

        y = Float(j)

        Shift = Float.Type.Size * 8 - 3

        sign_sin = dr.reinterpret_array(Float, j << Shift) ^ x
        sign_cos = dr.reinterpret_array(Float, (~(j - Int(2)) << Shift))

        y = xa - y * 0.78515625 \
               - y * 2.4187564849853515625e-4 \
               - y * 3.77489497744594108e-8

        z = y * y
        z |= dr.eq(xa, dr.Infinity)

        s = poly2(z, -1.6666654611e-1,
                  8.3321608736e-3,
                  -1.9515295891e-4) * z

        c = poly2(z, 4.166664568298827e-2,
                  -1.388731625493765e-3,
                  2.443315711809948e-5) * z

        s = dr.fmadd(s, y, y)
        c = dr.fmadd(c, z, dr.fmadd(z, -0.5, 1))

        polymask = dr.eq(j & Int(2), dr.zero(Int))

        return (
            dr.mulsign(dr.select(polymask, s, c), sign_sin),
            dr.mulsign(dr.select(polymask, c, s), sign_cos)
        )

    get_class(t.__module__)
    s, c = sincos(t(1))
    if t.Size != 0:
        assert dr.allclose(s**2 + c**2, 1)


@pytest.mark.parametrize("cname", ["drjit.packet.Int",
                                   "drjit.packet.Int64",
                                   "drjit.packet.UInt",
                                   "drjit.packet.UInt64",
                                   "drjit.cuda.Int",
                                   "drjit.cuda.Int64",
                                   "drjit.cuda.UInt",
                                   "drjit.cuda.UInt64",
                                   "drjit.llvm.Int",
                                   "drjit.llvm.Int64",
                                   "drjit.llvm.UInt",
                                   "drjit.llvm.UInt64"])
def test08_divmod(cname):
    t = get_class(cname)

    index = dr.arange(t, 10000000)
    index[index < len(index) // 2] = -index
    index *= 256203161

    for i in range(1, 100):
        assert index // i == index // dr.opaque(t, i, 1)
        assert index % i == index % dr.opaque(t, i, 1)

    if t.IsSigned:
        for i in range(1, 100):
            assert index // -i == index // dr.opaque(t, -i, 1)
            assert index % -i == index % dr.opaque(t, -i, 1)


@pytest.mark.parametrize("cname", ["drjit.cuda.Float", "drjit.llvm.Float"])
def test09_repeat_tile(cname):
    t = get_class(cname)
    a3 = get_class(cname.replace('Float', 'Array3f'))
    vec = t([1, 2, 3])
    tiled = t([1, 2, 3, 1, 2, 3, 1, 2, 3, 1, 2, 3, 1, 2, 3])
    reptd = t([1, 1, 1, 1, 1, 2, 2, 2, 2, 2, 3, 3, 3, 3, 3])

    assert dr.tile(vec, 5) == tiled
    assert dr.tile(a3(vec, vec + 1, vec + 2), 5) == \
        a3(tiled, tiled + 1, tiled + 2)

    assert dr.repeat(vec, 5) == reptd
    assert dr.repeat(a3(vec, vec + 1, vec + 2), 5) == \
        a3(reptd, reptd + 1, reptd + 2)


@pytest.mark.parametrize("cname", ["drjit.cuda.Int", "drjit.llvm.Int"])
def test10_meshgrid(cname):
    import numpy as np

    Int = get_class(cname)

    assert dr.meshgrid() == ()

    assert dr.meshgrid(Int(1, 2), indexing='ij') == Int(1, 2)
    assert dr.meshgrid(Int(1, 2), indexing='xy') == Int(1, 2)

    assert dr.meshgrid(Int(1, 2), Int(3, 4, 5)) == \
        (Int(1, 2, 1, 2, 1, 2), Int(3, 3, 4, 4, 5, 5))
    assert dr.meshgrid(Int(1, 2), Int(3, 4, 5), indexing='ij') == \
        (Int(1, 1, 1, 2, 2, 2), Int(3, 4, 5, 3, 4, 5))

    assert dr.meshgrid(Int(1, 2), Int(3, 4, 5), Int(5, 6), indexing='xy') == \
       (Int(1, 1, 2, 2, 1, 1, 2, 2, 1, 1, 2, 2),
        Int(3, 3, 3, 3, 4, 4, 4, 4, 5, 5, 5, 5),
        Int(5, 6, 5, 6, 5, 6, 5, 6, 5, 6, 5, 6))
    assert dr.meshgrid(Int(1, 2), Int(3, 4, 5), Int(5, 6), indexing='ij') == \
       (Int(1, 1, 1, 1, 1, 1, 2, 2, 2, 2, 2, 2),
        Int(3, 3, 4, 4, 5, 5, 3, 3, 4, 4, 5, 5),
        Int(5, 6, 5, 6, 5, 6, 5, 6, 5, 6, 5, 6))

    # Ensure consistency with NumPy
    a, b = dr.meshgrid(Int(1, 2), Int(3, 4, 5))
    a_np, b_np = np.meshgrid((1, 2), (3, 4, 5))
    assert a == a_np.ravel()
    assert b == b_np.ravel()
    a, b = dr.meshgrid(Int(1, 2), Int(3, 4, 5), indexing='ij')
    a_np, b_np = np.meshgrid((1, 2), (3, 4, 5), indexing='ij')
    assert a == a_np.ravel()
    assert b == b_np.ravel()

    a, b, c = dr.meshgrid(Int(1, 2), Int(3, 4, 5), Int(5, 6))
    a_np, b_np, c_np = np.meshgrid((1, 2), (3, 4, 5), Int(5, 6))
    assert a == a_np.ravel()
    assert b == b_np.ravel()
    assert c == c_np.ravel()
    a, b, c = dr.meshgrid(Int(1, 2), Int(3, 4, 5), Int(5, 6), indexing='ij')
    a_np, b_np, c_np = np.meshgrid((1, 2), (3, 4, 5), Int(5, 6), indexing='ij')
    assert a == a_np.ravel()
    assert b == b_np.ravel()
    assert c == c_np.ravel()



@pytest.mark.parametrize("cname", ["drjit.cuda.Int", "drjit.llvm.Int"])
def test11_block_sum(cname):
    Int = get_class(cname)
    assert dr.block_sum(Int(1, 2, 3, 4), 2) == Int(3, 7)


@pytest.mark.parametrize("cname", ["drjit.cuda.Float", "drjit.llvm.Float"])
def test12_binary_search(cname):
    t = get_class(cname)
    import numpy as np

    data_np = np.float32(np.sort(np.random.normal(size=10000)))
    search_np = np.float32(np.random.normal(size=10000))
    data = t(data_np)
    search = t(search_np)

    index = dr.binary_search(
        0, len(data) - 1,
        lambda index: dr.gather(t, data, index) < search
    )

    value = dr.gather(t, data, index)
    cond = dr.eq(index, len(data)-1) | (value >= search)
    assert dr.all(cond)


def test13_slice_setitem():
    a = dr.zero(dr.scalar.ArrayXf, 5)
    a[2] = 1.0
    assert dr.allclose(a, [0, 0, 1, 0, 0])
    a[2:] = [2.0, 1.0, 1.0]
    assert dr.allclose(a, [0, 0, 2, 1, 1])
    a[:] = 0.0
    assert dr.allclose(a, [0, 0, 0, 0, 0])

    v = dr.scalar.Array3f(0)
    v[2] = 1.0
    assert dr.allclose(v, [0, 0, 1])
    v[1:] = 2.0
    assert dr.allclose(v, [0, 2, 2])

    m = dr.scalar.Matrix3f(0)
    m[1:, 1] = 1.0
    assert dr.allclose(m, [[0, 0, 0], [0, 1, 0], [0, 1, 0]])
    m[0, 1:] = 2.0
    assert dr.allclose(m, [[0, 2, 2], [0, 1, 0], [0, 1, 0]])
    m[1:, 1:] = 3.0
    assert dr.allclose(m, [[0, 2, 2], [0, 3, 3], [0, 3, 3]])


def test14_slice_getitem():
    a = dr.scalar.ArrayXf(*range(5))
    assert dr.allclose(a[1:4], [1, 2, 3])
    assert dr.allclose(a[:], [0, 1, 2, 3, 4])

    a = dr.scalar.ArrayXi(*range(5))
    assert dr.allclose(a[1:4], [1, 2, 3])
    assert dr.allclose(a[:], [0, 1, 2, 3, 4])


def test15_test_avx512_approx():
    Float = get_class('drjit.llvm.Float')

    x = dr.linspace(Float, 0, 10, 1000)
    o = dr.full(Float, 1, 1000)
    assert dr.allclose(dr.rsqrt(x), o / dr.sqrt(x), rtol=2e-7, atol=0)
    assert dr.allclose(dr.rcp(x), o / x, rtol=2e-7, atol=0)


@pytest.mark.parametrize("cname", ["drjit.cuda.PCG32", "drjit.llvm.PCG32"])
def test16_custom(cname):
    t = get_class(cname)

    v1 = dr.zero(t, 100)
    v2 = dr.empty(t, 100)
    assert len(v1.state) == 100
    assert len(v2.inc) == 100

    v2.state = v1.state
    v1.state = dr.arange(type(v1.state), 100)
    v3 = dr.select(v1.state < 10, v1, v2)
    assert v3.state[3] == 3
    assert v3.state[11] == 0

    assert dr.width(v3) == 100
    v4 = dr.zero(t, 1)
    dr.schedule(v4)
    dr.resize(v4, 200)
    assert dr.width(v4) == 200

    assert dr.width(v3) == 100
    v4 = dr.zero(t, 1)
    dr.resize(v4, 200)
    assert dr.width(v4) == 200

    index = dr.arange(type(v1.state), 100)
    dr.scatter(v4, v1, index)
    v5 = dr.gather(t, v4, index)
    dr.eval(v5)
    assert v5.state == v1.state and v5.inc == v1.inc


def test17_opaque():
    Array3f = get_class('drjit.llvm.Array3f')

    v = dr.opaque(Array3f, 4.0)
    assert dr.width(v) == 1
    assert dr.allclose(v, 4.0)

    for i in range(len(v)):
        assert not v[i].is_literal_()
        assert v[i].is_evaluated_()

    v = dr.opaque(Array3f, 4.0, 1)
    assert dr.width(v) == 1
    assert dr.allclose(v, 4.0)

    v = dr.opaque(Array3f, 4.0, 10)
    assert dr.width(v) == 10
    assert dr.allclose(v, 4.0)


def test18_slice():
    Float   = get_class('drjit.llvm.Float')
    Array2f = get_class('drjit.llvm.Array2f')

    a = dr.arange(Float, 10)
    for i in range(10):
        assert dr.slice(a, i) == i

    a2 = Array2f(a, a * 10)
    for i in range(10):
        assert dr.slice(a2, i)[0] == i
        assert dr.slice(a2, i)[1] == i * 10

    a3 = (a, a * 10)
    for i in range(10):
        assert dr.slice(a3, i)[0] == i
        assert dr.slice(a3, i)[1] == i * 10


def test19_make_opaque():
    Float   = get_class('drjit.llvm.Float')
    Array3f = get_class('drjit.llvm.Array3f')
    TensorXf = get_class('drjit.llvm.TensorXf')

    a = Float(4.4)
    b = dr.full(Float, 3.3, 10)
    c = Array3f(2.2, 5.5, 6.6)
    t = dr.full(TensorXf, 4.4, (4, 4, 4))

    assert a.is_literal_()
    assert not a.is_evaluated_()
    assert b.is_literal_()
    assert not b.is_evaluated_()
    for i in range(len(c)):
        assert c[i].is_literal_()
        assert not c[i].is_evaluated_()
    assert t.array.is_literal_()
    assert not t.array.is_evaluated_()

    dr.make_opaque(a, b, c, t)

    assert not a.is_literal_()
    assert a.is_evaluated_()
    assert not b.is_literal_()
    assert b.is_evaluated_()
    for i in range(len(c)):
        assert not c[i].is_literal_()
        assert c[i].is_evaluated_()
    assert not t.array.is_literal_()
    assert t.array.is_evaluated_()


def test20_unsigned_negative():
    UInt32 = get_class('drjit.llvm.UInt32')

    a = UInt32(-1)
    assert a.is_literal_()
    assert a == 4294967295

    a = UInt32(1)
    b = -1
    c = a - b

    assert c.is_literal_()
    assert c == 2

@pytest.mark.parametrize("t", all_arrays())
def test21_masked_update(t):
    if dr.is_array_v(t) and not dr.is_mask_v(t):
        v1, v2 = t(1), t(5)
        v1[v1 < 2] = 3
        v2[v2 < 2] = 3

        assert v1 == t(3) and v2 == t(5)

        if t.IsJIT and t.Depth == 1:
            x = dr.arange(t, 100)
            x[x < 5] += 5
            y = dr.arange(t, 100)
            y = dr.select(y < 5, y + 5, y)
            assert x == y
