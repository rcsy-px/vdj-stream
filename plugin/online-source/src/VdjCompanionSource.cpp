#include "VdjCompanionSource.h"

#include <sstream>
#include <vector>
#include <winhttp.h>

#ifndef VDJ_COMPANION_VERSION
#define VDJ_COMPANION_VERSION "dev"
#endif

namespace
{
constexpr wchar_t kHost[] = L"127.0.0.1";
constexpr INTERNET_PORT kPort = 8765;

std::vector<std::string> Split(const std::string& value, char separator)
{
    std::vector<std::string> fields;
    std::stringstream stream(value);
    std::string field;
    while (std::getline(stream, field, separator))
    {
        fields.push_back(field);
    }
    return fields;
}
}

HRESULT VDJ_API VdjCompanionSource::OnLoad()
{
    return S_OK;
}

HRESULT VDJ_API VdjCompanionSource::OnGetPluginInfo(TVdjPluginInfo8* info)
{
    info->PluginName = "VDJ Companion Source";
    info->Author = "rcsy-px";
    info->Description = "Local YouTube search and streaming companion";
    info->Version = VDJ_COMPANION_VERSION;
    info->Bitmap = nullptr;
    info->Flags = VDJFLAG_EPHEMERAL;
    return S_OK;
}

HRESULT VDJ_API VdjCompanionSource::OnSearch(
    const char* search, IVdjTracksList* tracksList)
{
    DWORD statusCode = 0;
    const std::string body = HttpGet(
        L"/api/vdj/source/search?q=" + UrlEncode(search) + L"&limit=25",
        &statusCode);
    if (statusCode != 200)
    {
        tracksList->finish();
        return E_FAIL;
    }

    std::stringstream lines(body);
    std::string line;
    while (std::getline(lines, line))
    {
        const std::vector<std::string> fields = Split(line, '\t');
        if (fields.size() < 5)
        {
            continue;
        }
        float length = 0;
        try
        {
            length = static_cast<float>(std::stoi(fields[3]));
        }
        catch (...)
        {
        }
        tracksList->add(
            fields[0].c_str(),
            fields[1].c_str(),
            fields[2].c_str(),
            nullptr,
            nullptr,
            "YouTube Companion",
            nullptr,
            fields[4].empty() ? nullptr : fields[4].c_str(),
            nullptr,
            length);
    }
    tracksList->finish();
    return S_OK;
}

HRESULT VDJ_API VdjCompanionSource::GetStreamUrl(
    const char* uniqueId, IVdjString& url, IVdjString& errorMessage)
{
    DWORD statusCode = 0;
    const std::string body = HttpGet(
        L"/api/vdj/source/stream/" + UrlEncode(uniqueId),
        &statusCode);
    if (statusCode != 200 || body.empty())
    {
        errorMessage = statusCode == 0
            ? "VDJ Companion backend is offline. Run START.bat."
            : "VDJ Companion could not load this track. Check the local status page.";
        return E_FAIL;
    }
    url = body.c_str();
    return S_OK;
}

std::string VdjCompanionSource::HttpGet(
    const std::wstring& path, DWORD* statusCode)
{
    std::string body;
    HINTERNET session = WinHttpOpen(
        L"VdjCompanionSource/0.1.2",
        WINHTTP_ACCESS_TYPE_NO_PROXY,
        WINHTTP_NO_PROXY_NAME,
        WINHTTP_NO_PROXY_BYPASS,
        0);
    if (!session)
    {
        return body;
    }

    WinHttpSetTimeouts(session, 2000, 2000, 30000, 30000);
    HINTERNET connection = WinHttpConnect(session, kHost, kPort, 0);
    HINTERNET request = connection
        ? WinHttpOpenRequest(
              connection, L"GET", path.c_str(), nullptr, WINHTTP_NO_REFERER,
              WINHTTP_DEFAULT_ACCEPT_TYPES, 0)
        : nullptr;

    if (request &&
        WinHttpSendRequest(
            request, WINHTTP_NO_ADDITIONAL_HEADERS, 0,
            WINHTTP_NO_REQUEST_DATA, 0, 0, 0) &&
        WinHttpReceiveResponse(request, nullptr))
    {
        DWORD statusSize = sizeof(*statusCode);
        WinHttpQueryHeaders(
            request,
            WINHTTP_QUERY_STATUS_CODE | WINHTTP_QUERY_FLAG_NUMBER,
            WINHTTP_HEADER_NAME_BY_INDEX,
            statusCode,
            &statusSize,
            WINHTTP_NO_HEADER_INDEX);

        DWORD available = 0;
        while (WinHttpQueryDataAvailable(request, &available) && available > 0)
        {
            std::vector<char> buffer(available);
            DWORD read = 0;
            if (!WinHttpReadData(request, buffer.data(), available, &read))
            {
                break;
            }
            body.append(buffer.data(), read);
        }
    }

    if (request)
        WinHttpCloseHandle(request);
    if (connection)
        WinHttpCloseHandle(connection);
    WinHttpCloseHandle(session);
    return body;
}

std::wstring VdjCompanionSource::UrlEncode(const char* value)
{
    static constexpr wchar_t hex[] = L"0123456789ABCDEF";
    std::wstring encoded;
    for (const unsigned char ch : std::string(value ? value : ""))
    {
        if ((ch >= 'a' && ch <= 'z') || (ch >= 'A' && ch <= 'Z') ||
            (ch >= '0' && ch <= '9') || ch == '-' || ch == '_' || ch == '.' || ch == '~')
        {
            encoded.push_back(static_cast<wchar_t>(ch));
        }
        else
        {
            encoded.push_back(L'%');
            encoded.push_back(hex[ch >> 4]);
            encoded.push_back(hex[ch & 0x0F]);
        }
    }
    return encoded;
}
