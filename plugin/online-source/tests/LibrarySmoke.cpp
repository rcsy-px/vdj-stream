#include <cassert>
#include <string>
#include <vector>
#include "vdjOnlineSource.h"

struct Text : IVdjString {
    std::string value;
    void VDJ_API operator=(const char* text) override { value = text; }
};
struct Folders : IVdjSubfoldersList {
    std::vector<std::string> ids;
    void VDJ_API add(const char* id, const char*) override { ids.emplace_back(id); }
};
struct Menu : IVdjContextMenu {
    std::vector<std::string> entries;
    void VDJ_API add(const char* label) override { entries.emplace_back(label); }
};
struct Tracks : IVdjTracksList {
    bool finished = false, video = false;
    std::string id;
    void VDJ_API add(const char* track, const char*, const char*, const char*, const char*, const char*,
        const char*, const char*, const char*, float, float, int, int, bool isVideo, bool) override {
        id = track; video = isVideo;
    }
    void VDJ_API finish() override { finished = true; }
};
int main(int argc, char** argv) {
    assert(argc == 2);
    auto module = LoadLibraryA(argv[1]);
    assert(module);
    using Factory = HRESULT (VDJ_API *)(const GUID&, const GUID&, void**);
    auto factory = reinterpret_cast<Factory>(GetProcAddress(module, "DllGetClassObject"));
    assert(factory);
    void* object = nullptr;
    assert(factory(CLSID_VdjPlugin8, IID_IVdjPluginOnlineSource, &object) == S_OK);
    auto plugin = static_cast<IVdjPluginOnlineSource*>(object);
    Folders folders;
    assert(plugin->GetFolderList(&folders) == S_OK && folders.ids.size() == 2);
    Tracks tracks;
    assert(plugin->GetFolder("videos", &tracks) == S_OK);
    assert(tracks.finished && tracks.video && tracks.id == "video:abcdefghijk");
    Text url, error;
    assert(plugin->GetStreamUrl(tracks.id.c_str(), url, error) == S_OK);
    assert(url.value.find("/stream/library/") != std::string::npos);
    Menu menu;
    assert(plugin->GetContextMenu("abcdefghijk", &menu) == S_OK && menu.entries.size() == 6);
    assert(plugin->OnContextMenu("abcdefghijk", 2) == S_OK);
    assert(plugin->OnContextMenu("abcdefghijk", 1) == S_OK);
    assert(plugin->OnContextMenu("abcdefghijk", 99) != S_OK);
    plugin->Release();
    FreeLibrary(module);
}
