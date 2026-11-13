#include "VdjCompanionSource.h"
#include <curl/curl.h>
#include <limits>

namespace {
size_t Append(char* data, size_t size, size_t count, void* context)
{
    auto& body = *static_cast<std::string*>(context);
    if (size && count > std::numeric_limits<size_t>::max() / size) return 0;
    const auto length = size * count;
    if (length > 4 * 1024 * 1024 - body.size()) return 0;
    try { body.append(data, length); } catch (...) { return 0; }
    return length;
}
}

std::string VdjCompanionSource::HttpGet(
    const std::wstring& path, DWORD* statusCode, DWORD* networkError)
{
    *statusCode = 0;
    if (networkError) *networkError = 0;
    // UrlEncode produces ASCII, including UTF-8 percent escapes.
    const std::string url = "http://127.0.0.1:8765" + std::string(path.begin(), path.end());
    std::string body;
    CURL* request = curl_easy_init();
    if (!request) return body;
    curl_easy_setopt(request, CURLOPT_URL, url.c_str());
    curl_easy_setopt(request, CURLOPT_PROXY, "");
    curl_easy_setopt(request, CURLOPT_NOSIGNAL, 1L);
    curl_easy_setopt(request, CURLOPT_CONNECTTIMEOUT_MS, 2000L);
    curl_easy_setopt(request, CURLOPT_TIMEOUT_MS, 65000L);
    curl_easy_setopt(request, CURLOPT_WRITEFUNCTION, Append);
    curl_easy_setopt(request, CURLOPT_WRITEDATA, &body);
    curl_easy_setopt(request, CURLOPT_USERAGENT, "VdjCompanionSource-macOS");
    const auto result = curl_easy_perform(request);
    if (result == CURLE_OK) {
        long status = 0;
        curl_easy_getinfo(request, CURLINFO_RESPONSE_CODE, &status);
        *statusCode = static_cast<DWORD>(status);
    } else {
        body.clear();
        if (networkError) *networkError = result == CURLE_OPERATION_TIMEDOUT ? 12002 : 1;
    }
    curl_easy_cleanup(request);
    return body;
}
