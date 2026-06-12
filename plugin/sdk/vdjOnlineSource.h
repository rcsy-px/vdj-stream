#ifndef VdjOnlineSourceH
#define VdjOnlineSourceH

#include "vdjPlugin8.h"

struct IVdjString
{
    virtual void VDJ_API operator=(const char*) = 0;
};

struct IVdjTracksList
{
    virtual void VDJ_API add(
        const char* uniqueId,
        const char* title,
        const char* artist,
        const char* remix = 0,
        const char* genre = 0,
        const char* label = 0,
        const char* comment = 0,
        const char* coverUrl = 0,
        const char* streamUrl = 0,
        float length = 0,
        float bpm = 0,
        int key = 0,
        int year = 0,
        bool isVideo = 0,
        bool isKaraoke = 0) = 0;
    virtual void VDJ_API finish() = 0;
};

struct IVdjSubfoldersList
{
    virtual void VDJ_API add(const char* folderUniqueId, const char* folderName = 0) = 0;
};

struct IVdjContextMenu
{
    virtual void VDJ_API add(const char* menuEntry) = 0;
};

struct IVdjOAuth
{
    virtual void VDJ_API open(const char* authorizeUrl) = 0;
    virtual void VDJ_API getToken(const char* code, const char* tokenUrl, const char* tokenPost = 0) = 0;
    virtual void VDJ_API refreshToken(const char* refreshToken, const char* tokenUrl, const char* tokenPost = 0) = 0;
};

class IVdjPluginOnlineSource : public IVdjPlugin8
{
public:
    virtual HRESULT VDJ_API IsLogged() { return E_NOTIMPL; }
    virtual HRESULT VDJ_API OnLogin() { return E_NOTIMPL; }
    virtual HRESULT VDJ_API OnLogout() { return E_NOTIMPL; }
    IVdjOAuth* oauth;
    virtual HRESULT VDJ_API OnOAuth(
        const char*, size_t, const char*, const char*, const char*) { return E_NOTIMPL; }
    virtual HRESULT VDJ_API OnSearch(const char* search, IVdjTracksList* tracksList) = 0;
    virtual HRESULT VDJ_API OnSearchCancel() { return E_NOTIMPL; }
    virtual HRESULT VDJ_API GetStreamUrl(
        const char* uniqueId, IVdjString& url, IVdjString& errorMessage) { return E_NOTIMPL; }
    virtual HRESULT VDJ_API GetFolderList(IVdjSubfoldersList*) { return E_NOTIMPL; }
    virtual HRESULT VDJ_API GetFolder(const char*, IVdjTracksList*) { return E_NOTIMPL; }
    virtual HRESULT VDJ_API GetContextMenu(const char*, IVdjContextMenu*) { return E_NOTIMPL; }
    virtual HRESULT VDJ_API OnContextMenu(const char*, size_t) { return E_NOTIMPL; }
    virtual HRESULT VDJ_API GetFolderContextMenu(const char*, IVdjContextMenu*) { return E_NOTIMPL; }
    virtual HRESULT VDJ_API OnFolderContextMenu(const char*, size_t) { return E_NOTIMPL; }
};

static const GUID IID_IVdjPluginOnlineSource = {
    0x85d20f05, 0x0ccf, 0x4cab, {0xaa, 0x50, 0x1c, 0x04, 0xea, 0xb6, 0xb8, 0x5d}};

#endif
