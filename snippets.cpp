#include <memory>

//http://stackoverflow.com/a/14905204
struct HandleCloser {
    typedef HANDLE pointer;
    void operator()(HANDLE h) {
        if(h != INVALID_HANDLE_VALUE) {
            CloseHandle(h);
        }
    }
};
typedef std::unique_ptr<HANDLE, HandleCloser> UniqueHandle;

HANDLE handle /* = ... */;
UniqueHandle foo(handle);
