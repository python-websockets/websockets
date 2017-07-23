/* C implementation of performance sensitive functions. */

#define PY_SSIZE_T_CLEAN
#include <Python.h>

#if __AVX__
#include <x86intrin.h>
#endif

const Py_ssize_t MASK_LEN = 4;

static PyObject *
apply_mask(PyObject *self, PyObject *args, PyObject *kwds)
{

    // Inputs are treated as immutable, which causes an extra memory copy.

    static char *kwlist[] = {"data", "mask", NULL};
    const char *input;
    Py_ssize_t input_len;
    const char *mask;
    Py_ssize_t mask_len;

    // Initialize a PyBytesObject then get a pointer to the underlying char *
    // in order to avoid an extra memory copy in PyBytes_FromStringAndSize.

    PyObject *result;
    char *output;
    Py_ssize_t i = 0;

    if (!PyArg_ParseTupleAndKeywords(
            args, kwds, "s#s#", kwlist, &input, &input_len, &mask, &mask_len))
    {
        return NULL;
    }

    if (mask_len != MASK_LEN)
    {
        PyErr_SetString(PyExc_ValueError, "mask must contain 4 bytes");
        return NULL;
    }

    result = PyBytes_FromStringAndSize(NULL, input_len);
    if (result == NULL)
    {
        return NULL;
    }

    // Since we juste created result, we don't need error checks.
    output = PyBytes_AS_STRING(result);

    // Apparently GCC cannot figure out the following optimizations by itself.

#if __AVX__

    // With AVX support, XOR by blocks of 32 bytes = 256 bits.

    Py_ssize_t input_len_256 = input_len & ~31;
    __m256 mask_256 = _mm256_set1_epi32(*(int *)mask);

    for (; i < input_len_256; i += 32)
    {
        __m256i in_256 = _mm256_loadu_si256((__m256i *)(input + i));
        __m256i out_256 = _mm256_xor_si256(in_256, mask_256);
        _mm256_storeu_si256((__m256i *)(output + i), out_256);
    }

#endif

    // XOR the remainder of the input byte by byte.

    for (; i < input_len; i++)
    {
        output[i] = input[i] ^ mask[i % MASK_LEN];
    }

    return result;

}

static PyMethodDef speedups_methods[] = {
    {
        "apply_mask",
        (PyCFunction)apply_mask,
        METH_VARARGS | METH_KEYWORDS,
        "Apply masking to websocket message.",
    },
    {NULL, NULL, 0, NULL},      /* Sentinel */
};

static struct PyModuleDef speedups_module = {
    PyModuleDef_HEAD_INIT,
    "websocket.speedups",       /* m_name */
    "C implementation of performance sensitive functions.",
                                /* m_doc */
    -1,                         /* m_size */
    speedups_methods,           /* m_methods */
};

PyMODINIT_FUNC
PyInit_speedups(void)
{
    return PyModule_Create(&speedups_module);
}
