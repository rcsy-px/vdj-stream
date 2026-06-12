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

private:
    std::string HttpGet(const std::wstring& path, DWORD* statusCode);
    static std::wstring UrlEncode(const char* value);
};
