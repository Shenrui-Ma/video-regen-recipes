import importlib.util
import pathlib
import tempfile
import unittest

T = pathlib.Path(__file__).resolve().parents[1]

class PatchTests(unittest.TestCase):
    def test_public_int8_patch_promotes_before_both_stride_products(self):
        source = T / 'vendor/comfy-kitchen/upstream/quantization.py'
        patched = T / 'vendor/comfy-kitchen/patched/quantization.py'
        self.assertTrue(source.exists() and patched.exists(), 'Public exact source and tested INT8 fix not shipped')
        import ast
        tree = ast.parse(patched.read_text())
        stores = [n for n in ast.walk(tree) if isinstance(n, ast.Assign)
                  and any(isinstance(t, ast.Name) and t.id == 'c_ptrs' for t in n.targets)]
        self.assertEqual(len(stores), 2)
        expected = 'c_ptr + stride_cm * offs_am.to(tl.int64)[:, None] + stride_cn * offs_bn.to(tl.int64)[None, :]'
        for node in stores:
            self.assertEqual(ast.unparse(node.value), expected)
        original = source.read_text()
        self.assertEqual(original.count('stride_cm * offs_am[:, None] + stride_cn * offs_bn[None, :]'), 2)
        import ctypes
        m, n = 75008, 28672
        self.assertLess(ctypes.c_int32((m-1)*n).value, 0)
        self.assertGreater((m-1)*n, 2**31-1)
        class Offset:
            def __init__(self, value, width=32):
                self.width = width
                self.value = ctypes.c_int32(value).value if width == 32 else value
            def __getitem__(self, _):
                return self
            def to(self, _):
                return Offset(self.value, 64)
            def __mul__(self, other):
                return Offset(self.value * other, self.width)
            __rmul__ = __mul__
            def __add__(self, other):
                if isinstance(other, Offset):
                    return Offset(self.value + other.value, max(self.width, other.width))
                return Offset(self.value + other, self.width)
            __radd__ = __add__
        import types
        for path, fixed in ((source, False), (patched, True)):
            tree = ast.parse(path.read_text())
            for node in ast.walk(tree):
                if not isinstance(node, ast.Assign) or not any(isinstance(t, ast.Name) and t.id == 'c_ptrs' for t in node.targets):
                    continue
                expr = compile(ast.Expression(node.value), '<actual-kernel-store>', 'eval')
                for rows in (74880, 75008, 78080):
                    env = {'c_ptr': 0, 'stride_cm': n, 'stride_cn': 1,
                           'offs_am': Offset(rows-1), 'offs_bn': Offset(n-1),
                           'tl': types.SimpleNamespace(int64=64)}
                    value = eval(expr, {'__builtins__': {}}, env).value
                    expected_offset = rows*n-1
                    if fixed:
                        self.assertEqual(value, expected_offset)
                    else:
                        self.assertEqual(value, ctypes.c_int32(expected_offset).value)

    def test_distributed_patch_files_apply_to_exact_public_sources(self):
        import json, subprocess
        lock = json.loads((T/'references/dependencies.lock.json').read_text())
        cases = [('comfy-kitchen', 'quantization.py', 'output-index-int64.patch'),
                 ('motion-context', 'nodes.py', 'payload-before-audio.patch')]
        for package, filename, patchname in cases:
            with tempfile.TemporaryDirectory() as temp:
                target = pathlib.Path(temp)/filename
                target.write_bytes((T/'vendor'/package/'upstream'/filename).read_bytes())
                result = subprocess.run(['git', 'apply', str(T/'vendor'/package/patchname)], cwd=temp, capture_output=True,text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(target.read_bytes(), (T/'vendor'/package/'patched'/filename).read_bytes())
