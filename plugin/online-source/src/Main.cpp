#include <cstring>

#include "VdjCompanionSource.h"

namespace {
bool SameGuid(const GUID& left, const GUID& right)
{
    // The macOS SDK GUID has trailing padding on 64-bit architectures.
    // Compare its fields, never uninitialized bytes supplied by the host.
    return left.Data1 == right.Data1 && left.Data2 == right.Data2 &&
        left.Data3 == right.Data3 && std::memcmp(left.Data4, right.Data4, 8) == 0;
}
}

HRESULT VDJ_API DllGetClassObject(
    const GUID& classId,
    const GUID& interfaceId,
    void** object)
{
    if (SameGuid(classId, CLSID_VdjPlugin8) &&
        SameGuid(interfaceId, IID_IVdjPluginOnlineSource))
    {
        *object = new VdjCompanionSource();
        return NO_ERROR;
    }
    return CLASS_E_CLASSNOTAVAILABLE;
}
