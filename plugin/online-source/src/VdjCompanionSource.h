#pragma once

#include <string>

#include "vdjOnlineSource.h"

class VdjCompanionSource final : public IVdjPluginOnlineSource
{
public:
    HRESULT VDJ_API OnLoad() override;
    HRESULT VDJ_API OnGetPluginInfo(TVdjPluginInfo8* info) override;
    HRESULT VDJ_API OnSearch(const char* search, IVdjTracksList* tracksList) override;
    HRESULT VDJ_API GetStreamUrl(
        const char* uniqueId, IVdjString& url, IVdjString& errorMessage) override;
    HRESULT VDJ_API GetFolderList(IVdjSubfoldersList* folders) override;
    HRESULT VDJ_API GetFolder(const char* id, IVdjTracksList* tracks) override;
    HRESULT VDJ_API GetContextMenu(const char* id, IVdjContextMenu* menu) override;
    HRESULT VDJ_API OnContextMenu(const char* id, size_t index) override;

private:
    std::string HttpGet(const std::wstring& path, DWORD* statusCode, DWORD* networkError = nullptr, const std::string& token = "");
    static HRESULT ReadTracks(const std::string& body, IVdjTracksList* tracksList);
    static std::wstring UrlEncode(const char* value);
};
