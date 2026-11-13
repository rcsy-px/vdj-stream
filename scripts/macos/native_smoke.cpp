#include <cassert>
#include <cstring>
#include <dlfcn.h>
#include <string>
#include "vdjOnlineSource.h"

struct Text : IVdjString {
    std::string value;
    void operator=(const char* text) override { value = text; }
};
struct Tracks : IVdjTracksList {
    int count = 0;
    bool finished = false;
    void add(const char* id, const char* title, const char* artist,
        const char*, const char*, const char*, const char*, const char*, const char*,
        float length, float, int, int, bool, bool) override {
        assert(std::string(id) == "abcdefghijk");
        assert(std::string(title) == "Test track");
        assert(std::string(artist) == "Test artist");
        assert(length == 123);
        ++count;
    }
    void finish() override { finished = true; }
};

int main(int argc, char** argv) {
    assert(argc == 2);
    void* library = dlopen(argv[1], RTLD_NOW | RTLD_LOCAL);
    if (!library) { fprintf(stderr, "%s\n", dlerror()); return 1; }
    using Factory = HRESULT (*)(const GUID&, const GUID&, void**);
    auto factory = reinterpret_cast<Factory>(dlsym(library, "DllGetClassObject"));
    assert(factory);
    void* object = nullptr;
    assert(factory(CLSID_VdjPlugin8, IID_IVdjPluginOnlineSource, &object) == S_OK);
    auto* plugin = static_cast<IVdjPluginOnlineSource*>(object);
    assert(plugin->OnLoad() == S_OK);
    TVdjPluginInfo8 info{};
    assert(plugin->OnGetPluginInfo(&info) == S_OK);
    assert(std::string(info.Version).find("macos-preview") != std::string::npos);
    Tracks tracks;
    assert(plugin->OnSearch("Beyonc\xc3\xa9 & test", &tracks) == S_OK);
    assert(tracks.count == 1 && tracks.finished);
    Tracks failure;
    assert(plugin->OnSearch("failure", &failure) != S_OK);
    assert(failure.finished && failure.count == 0);
    Text url, error;
    assert(plugin->GetStreamUrl("abcdefghijk", url, error) == S_OK);
    assert(url.value == "http://127.0.0.1:8765/stream/test.webm");
    assert(plugin->GetStreamUrl("busy", url, error) != S_OK);
    assert(error.value.find("busy") != std::string::npos);
    assert(plugin->GetStreamUrl("timeout", url, error) != S_OK);
    assert(error.value.find("timed out") != std::string::npos);
    assert(plugin->GetStreamUrl("missing", url, error) != S_OK);
    assert(error.value.find("Could not load") != std::string::npos);
    plugin->Release();
    dlclose(library);
}
