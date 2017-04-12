/*
Copyright 2009 Facebook

Licensed under the Apache License, Version 2.0 (the "License"); you may
not use this file except in compliance with the License. You may obtain
a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
License for the specific language governing permissions and limitations
under the License.
*/

#define PY_SSIZE_T_CLEAN
#include <Python.h>

static PyObject* websocket_mask(PyObject* self, PyObject* args) {
    const char* mask;
    Py_ssize_t mask_len;
    const char* data;
    Py_ssize_t data_len;
    Py_ssize_t i;
    PyObject* result;
    char* buf;

    if (!PyArg_ParseTuple(args, "s#s#", &mask, &mask_len, &data, &data_len)) {
        return NULL;
    }

    result = PyBytes_FromStringAndSize(NULL, data_len);
    if (!result) {
        return NULL;
    }
    buf = PyBytes_AsString(result);
    for (i = 0; i < data_len; i++) {
        buf[i] = data[i] ^ mask[i % 4];
    }

    return result;
}

static PyMethodDef methods[] = {
    {"websocket_mask",  websocket_mask, METH_VARARGS, ""},
    {NULL, NULL, 0, NULL}
};

#if PY_MAJOR_VERSION >= 3
static struct PyModuleDef speedupsmodule = {
   PyModuleDef_HEAD_INIT,
   "speedups",
   NULL,
   -1,
   methods
};

PyMODINIT_FUNC
PyInit_speedups(void) {
    return PyModule_Create(&speedupsmodule);
}
#else  // Python 2.x
PyMODINIT_FUNC
initspeedups(void) {
    Py_InitModule("websockets.speedups", methods);
}
#endif
