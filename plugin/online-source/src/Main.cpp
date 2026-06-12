#include <cstring>

#include "VdjCompanionSource.h"

HRESULT VDJ_API DllGetClassObject(
    const GUID& classId,
    const GUID& interfaceId,
    void** object)
{
    if (std::memcmp(&classId, &CLSID_VdjPlugin8, sizeof(GUID)) == 0 &&
        std::memcmp(&interfaceId, &IID_IVdjPluginOnlineSource, sizeof(GUID)) == 0)
    {
        *object = new VdjCompanionSource();
        return NO_ERROR;
    }
    return CLASS_E_CLASSNOTAVAILABLE;
}
