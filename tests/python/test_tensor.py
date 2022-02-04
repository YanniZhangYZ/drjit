import drjit as dr
import pytest
import numpy as np

#  pkgs = ["drjit.cuda", "drjit.cuda.ad",
#          "drjit.llvm", "drjit.llvm.ad"]

pkgs = ["drjit.llvm", "drjit.llvm.ad"]
pkgs_ad = ["drjit.llvm.ad"]

def get_class(name):
    """Resolve a package+class name into the corresponding type"""
    if 'cuda' in name:
        if not dr.has_backend(dr.JitBackend.CUDA):
            pytest.skip('CUDA mode is unsupported')
    elif 'llvm' in name:
        if not dr.has_backend(dr.JitBackend.LLVM):
            pytest.skip('LLVM mode is unsupported')

    name = name.split('.')
    value = __import__(".".join(name[:-1]))
    for item in name[1:]:
        value = getattr(value, item)

    return value

class Checker:
    """
    Compares a Tensor indexing operation against a NumPy reference
    and asserts if there is a mismatch.
    """
    def __init__(self, shape, tensor_type):
        import numpy as np
        self.shape = shape
        size = np.prod(shape)
        self.array_n = np.arange(size, dtype=np.uint32).reshape(shape)
        self.array_e = tensor_type(dr.arange(tensor_type.Array, size), shape)

    def __getitem__(self, args):
        import numpy as np
        ref_n = self.array_n.__getitem__(args)
        ref_e = self.array_e.__getitem__(args)
        assert ref_n.shape == ref_e.shape
        assert np.all(ref_n.ravel() == ref_e.array.numpy())


@pytest.mark.parametrize("pkg", pkgs)
def test01_slice_index(pkg):
  t = get_class(pkg + ".TensorXu")
  c = Checker((10,), t)
  c[:]
  c[3]
  c[1:5]
  c[-5]

  c = Checker((10, 20), t)
  c[:]
  c[5, 0]
  c[5, 0:2]
  c[:, 5]
  c[5, :]
  c[:, :]
  c[1:3, 2:7:2]
  c[8:2:-1, 7:0:-1]
  c[0:0, 0:0]


@pytest.mark.parametrize("pkg", pkgs)
def test02_slice_ellipsis(pkg):
    t = get_class(pkg + ".TensorXu")
    c = Checker((10, 20, 30, 40), t)

    c[...]
    c[1, ...]
    c[..., 1]
    c[4, ..., 3]
    c[0, 1:3, ..., 3]


@pytest.mark.parametrize("pkg", pkgs)
def test03_slice_append_dim(pkg):
    t = get_class(pkg + ".TensorXu")
    c = Checker((10, 20, 30, 40), t)

    c[None]
    c[..., None]
    c[1, None, ...]
    c[..., None, 1, None]
    c[None, 4, ..., 3, None]


@pytest.mark.parametrize("pkg", pkgs)
def test04_broadcasting(pkg):
    t = get_class(pkg + ".TensorXu")
    for i in range(1, 5):
        for j in range(1, 5):
            for k in range(1, 5):
                shape = [i, j, k]
                for l in range(len(shape)):
                    shape_2 = list(shape)
                    shape_2[l] = 1
                    array_n1 = np.arange(np.prod(shape),   dtype=np.uint32).reshape(shape)
                    array_n2 = np.arange(np.prod(shape_2), dtype=np.uint32).reshape(shape_2)

                    array_e1 = t(dr.arange(t.Index, np.prod(shape)),   shape)
                    array_e2 = t(dr.arange(t.Index, np.prod(shape_2)), shape_2)

                    out_n = array_n1 + array_n2
                    out_e = array_e1 + array_e2

                    assert out_n.shape == out_e.shape
                    assert np.all(out_n.ravel() == out_e.array.numpy())
                    assert np.all((array_n1 * 2).ravel() == (array_e1 * 2).array.numpy())

    with pytest.raises(Exception) as e:
        a = dr.full(t, 1, (3, 3))
        b = dr.full(t, 1, (2, 2))
        c = a + b
    e.match('incompatible tensor shapes for dimension')


@pytest.mark.parametrize("pkg", pkgs)
def test05_initialization_casting(pkg):
    tu = get_class(pkg + ".TensorXu")
    tf = get_class(pkg + ".TensorXf")
    tf64 = get_class(pkg + ".TensorXf")

    t0 = dr.full(tu, 1, (2, 3, 4))
    t1 = dr.full(tf, 2, (2, 3, 4))
    t2 = dr.zero(tf64, (2, 3, 4))

    assert dr.shape(t0) == (2, 3, 4)

    t3 = t0 + t1 + t2
    assert type(t3) is tf64

    assert t3.shape == (2, 3, 4)
    assert t3.array == dr.full(t3.Array, 3, 2*3*4)

    t3[:, 1, :] = 12
    assert t3[:, 0, :] == 3
    assert t3[:, 1, :] == 12


@pytest.mark.parametrize("pkg", pkgs_ad)
def test05_ad(pkg):
    f = get_class(pkg + ".TensorXf")
    z0 = dr.full(f, 1, (2, 3, 4))
    assert not dr.grad_enabled(z0)
    dr.enable_grad(z0)
    assert dr.grad_enabled(z0)
    assert not dr.grad_enabled(dr.detach(z0))
    assert dr.ravel(z0) is z0.array

    z1 = z0 + z0
    dr.backward(z1)
    g = dr.grad(z0)
    assert g.shape == (2, 3, 4)
    assert len(g.array) == 2*3*4
    assert g.array == 2


@pytest.mark.parametrize("pkg", pkgs)
def test06_numpy_conversion(pkg):
    f = get_class(pkg + ".TensorXf")

    value = f(dr.arange(f.Array, 2*3*4), (2, 3, 4))
    value_np = value.numpy()
    assert value_np.shape == (2, 3, 4)
    assert np.all(value_np.ravel() == value.array.numpy())

    value_2 = f(value_np)
    assert value.shape == value_2.shape
    assert value.array == value_2.array

    value_np = np.ones((1,1,1,1))
    value_3 = f(value_np)
    assert value_np.shape == value_3.shape
    assert np.all(value_np == value_3.array)


@pytest.mark.parametrize("pkg", pkgs)
def test07_jax_conversion(pkg):
    jax = pytest.importorskip("jax")
    f = get_class(pkg + ".TensorXf")

    value = f(dr.arange(f.Array, 2*3*4), (2, 3, 4))
    value_jax = value.jax()
    assert value_jax.shape == (2, 3, 4)
    assert jax.numpy.all(value_jax.ravel() == value.array.jax())

    value_2 = f(value_jax)
    assert value.shape == value_2.shape
    assert value.array == value_2.array


@pytest.mark.parametrize("pkg", pkgs)
def test08_pytorch_conversion(pkg):
    torch = pytest.importorskip("torch")
    f = get_class(pkg + ".TensorXf")

    value = f(dr.arange(f.Array, 2*3*4), (2, 3, 4))
    value_torch = value.torch()
    assert value_torch.shape == (2, 3, 4)
    assert torch.all(value_torch.flatten() == value.array.torch())

    value_2 = f(value_torch)
    assert value.shape == value_2.shape
    assert value.array == value_2.array


@pytest.mark.parametrize("pkg", pkgs)
def test09_tensorflow_conversion(pkg):
    tf = pytest.importorskip("tensorflow")
    f = get_class(pkg + ".TensorXf")
    tf.constant(0)

    value = f(dr.arange(f.Array, 2*3*4), (2, 3, 4))
    value_tf = value.tf()
    assert value_tf.shape == (2, 3, 4)
    assert tf.reduce_all(tf.equal(tf.reshape(value_tf, (2*3*4,)), value.array.tf()))

    value_2 = f(value_tf)
    assert value.shape == value_2.shape
    assert value.array == value_2.array


@pytest.mark.parametrize("pkg", pkgs)
def test10_tensorflow_arithmetic(pkg):
    t = get_class(pkg + ".TensorXf")
    f = get_class(pkg + ".Float32")

    tt = t([1, 2, 3, 4, 5, 6], [2, 3])
    ff = f(2.0)

    assert ff * tt == tt * ff
    assert ff * tt == t([2, 4, 6, 8, 10, 12], [2, 3])


class PowerOfTwo(dr.CustomOp):
    def eval(self, value):
        self.value = value
        return value * value

    def forward(self):
        grad_in = self.grad_in('value')
        self.set_grad_out(2.0 * self.value * grad_in)

    def backward(self):
        grad_out = self.grad_out()
        self.set_grad_in('value', 2.0 * self.value * grad_out)

    def name(self):
        return "power of two"


@pytest.mark.parametrize("pkg", ["drjit.llvm.ad", "drjit.cuda.ad"])
def test11_custom_op(pkg):
    t = get_class(pkg + ".TensorXf")
    f = get_class(pkg + ".Float32")

    tt = t([1, 2, 3, 4, 5, 6], [2, 3])
    dr.enable_grad(tt)

    tt2 = dr.custom(PowerOfTwo, tt)

    dr.set_grad(tt2, 1.0)
    dr.enqueue(dr.ADMode.Backward, tt2)
    dr.traverse(f, dr.ADMode.Backward)

    assert dr.grad(tt).array == [2.0, 4.0, 6.0, 8.0, 10.0, 12.0]


@pytest.mark.parametrize("pkg", pkgs_ad)
def test12_select(pkg):
    for tp in [get_class(pkg + ".TensorXf"), get_class(pkg + ".TensorXu")]:
        initial = tp([1, 2, 3, 4], shape=(4, 1))

        next = initial + 10
        valid = initial >= 2.5
        assert type(valid) == dr.mask_t(initial)

        result = dr.select(valid, next, initial)
        assert type(result) == tp

        expected = tp([1, 2, 13, 14], shape=dr.shape(initial))
        assert dr.allclose(result, expected)
