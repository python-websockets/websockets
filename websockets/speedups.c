#define PY_SSIZE_T_CLEAN
#include <Python.h>

#include <stdint.h> /* C99 or MSVC 2010+, OK for Python 3.3+ */

#ifndef HAS_SSE2
/* setup HAS_SSE2 macro according to compiler predefined macros */
#ifdef __SSE2__
#define HAS_SSE2 1
#else
#define HAS_SSE2 0
#endif
#endif /* not defined HAS_SSE2 */

#if HAS_SSE2
#include <emmintrin.h>
#endif

static PyObject* apply_mask(PyObject* self, PyObject* args) {
    const char* mask;
    const char* in;
    char* out;
    Py_ssize_t mask_len;
    Py_ssize_t len;
    PyObject* result;

    if (!PyArg_ParseTuple(args, "y#y#", &in, &len, &mask, &mask_len)) {
        return NULL;
    }

    if (mask_len != 4) {
        PyErr_SetString(PyExc_ValueError, "mask must contain 4 bytes");
        return NULL;
    }

    result = PyBytes_FromStringAndSize(NULL, len);
    if (NULL != result) {
        Py_ssize_t i = 0; /* initialize iterator */

        out = PyBytes_AS_STRING(result); /* "no error checking" form of PyBytes_AsString */

#if HAS_SSE2
        if (len >= 32) {
            const __m128i mask128 = _mm_set1_epi32(*(const int*)mask);

            for (; i < (len & ~(Py_ssize_t)31); i += 32) {
                __m128i src0 = _mm_loadu_si128((const __m128i*)(in + i +  0));
                __m128i src1 = _mm_loadu_si128((const __m128i*)(in + i + 16));
                __m128i dst0 = _mm_xor_si128(src0, mask128);
                __m128i dst1 = _mm_xor_si128(src1, mask128);
                _mm_storeu_si128((__m128i*)(out + i +  0), dst0);
                _mm_storeu_si128((__m128i*)(out + i + 16), dst1);
            }
        }
#endif

        /* There seems to be no information regarding alignment of PyBytes allocated buffer */
        /* CPython implementation seems to ensure an 8byte boundary */
        /* we add a check just to make sure we don't do anything unsupported otherwise */
        if ((((uint32_t)in | (uint32_t)out | (uint32_t)mask) & 7U) == 0) {
            const uint32_t mask_u32 = *(const uint32_t*)mask;
            const uint64_t mask_u64 = ((uint64_t)mask_u32 << 32) | mask_u32;

            /* any decent 32bit compiler will consider this as an uint32_t */
            /* loop unrolled 2 times => don't bother with checks */
            for (; i < (len & ~(Py_ssize_t)7); i += 8) {
                *(uint64_t*)(out + i) = *(const uint64_t*)(in + i) ^ mask_u64;
            }

            if (len & 4) {
                *(uint32_t*)(out + i) = *(const uint32_t*)(in + i) ^ mask_u32;
                i += 4;
            }
        }

        for (; i < len; i++) {
            out[i] = in[i] ^ mask[i & 3];
        }
    }
    return result;
}

static PyMethodDef methods[] = {
    {
        "apply_mask",
        apply_mask,
        METH_VARARGS,
        "Apply masking to websocket message."
    },
    { NULL, NULL, 0, NULL } /* Sentinel */
};

static struct PyModuleDef module = {
    PyModuleDef_HEAD_INIT,
    "websockets.speedups",
    "C implementation of performance sensitive functions.",
    -1,
    methods,
};

PyMODINIT_FUNC
PyInit_speedups(void) {
    return PyModule_Create(&module);
}
