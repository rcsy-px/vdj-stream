# Library, setlists and video

Available in Windows 0.3.0 and macOS 0.3.0 beta 1. The macOS build remains a public beta; real-device VirtualDJ testing is still needed.

## Prepare a Windows test session

1. Quit VirtualDJ and stop the previously installed Companion backend.
2. Keep the stable Companion folder. Back up the existing
   `VDJ Companion Source.dll` from your VirtualDJ home's
   `Plugins64/OnlineSources` folder before installing this version.
3. Extract the release ZIP to a **new permanent folder**, then run its
   `START.bat`. The launcher installs the source plugin.
4. Confirm the panel shows **0.3.0**, then open VirtualDJ.

The new installation uses its own data folder. Do not run two Companion backends on port
8765 at once. To roll back, quit VirtualDJ, stop the new backend, restore the
backed-up DLL and start the stable Companion again. Your existing VirtualDJ
database and History are not modified by the history importer.

## Returning to search results

The **Last search** source folder restores the latest successful search results
without repeating the online search, even after a backend restart. Switching to
downloads or setlists does not clear them. A successful search with no matches
replaces the saved list with an empty list; a failed search leaves it intact.
The plugin also returns this list when VirtualDJ requests an empty search or the
root folder. Whether returning to the source root triggers this callback depends
on VirtualDJ. The search box text itself is controlled by VirtualDJ.

## Setlists

In the control panel's **Library & Setlists** section, create a named setlist or
select an existing one. This becomes the active destination for VirtualDJ's
**Add to active Companion setlist** context-menu action.

Search inside **VDJ Companion Source**, right-click a result and add it. The
source's subfolders include **Setlist: …** folders containing your saved tracks.
Reopen a folder after changes if VirtualDJ still shows the previous contents.
The same track is added only once per list; audio and video versions are distinct.

The panel can remove entries, delete a custom setlist and export an M3U8 playlist.
The export stores stable Companion track IDs, not expiring YouTube URLs. Reloading
it requires the Companion plugin/backend; an unsaved track also needs internet.
Deleting a setlist does not remove downloaded media.

## Played tracks

VirtualDJ already records played tracks in its **History** folder. This build
reads the last 60 history files every 30 seconds and shows Companion entries in
**Played in VirtualDJ**, both in the source folders and the panel. It understands
VirtualDJ's `#EXTVDJ` metadata as well as `#EXTINF` playlists.

History determines what counts as played. Loading a deck or downloading a track
does not mark it played. VirtualDJ normally records a track after 45 seconds;
the `historyDelay` setting controls this. Use the native History folders for
date-by-date sets, or add a track from the panel's played list to a named setlist.
Set `VDJ_HOME` when using a custom VirtualDJ home that cannot be detected.

## Offline audio

Right-click a result and choose **Download audio for offline use**. The panel
shows `queued`, `downloading`, `ready` or the failure reason. Completed files
appear in **Downloaded audio**. The original search/history/setlist entry will
also use the saved audio when available.

The Companion backend must keep running, but playing a saved file does not
require YouTube. Files are kept in `data/library/media`; the library index and
setlists live in `data/library/library.sqlite3`. Keep this folder when backing up
your library. Runtime logs are under `data/logs`.

One download runs at a time, with up to 20 queued and no library or per-file size
limit. The panel shows saved download size and free disk space; **Open download
folder** opens the media folder in Explorer or Finder. At least 2 GB of free disk
space is required. Downloads stop if free space drops below that reserve; free up
space and retry. The panel supports cancel, retry and remove. Unload
a track from VirtualDJ before removing its saved file. Interrupted downloads are
marked for retry on restart; partial files are never offered as ready media.

## Video

Choose **Download video (720p maximum)**, wait for `ready`, then load the track
from **Downloaded videos**. You can also add that video entry to a setlist.
The ordinary search results continue to load audio.

Video preparation selects MP4/H.264 up to 720p, with audio, and merges separate
streams when necessary. Both streams are verified before the file becomes
available. If the source has no matching format, preparation reports a failure;
it does not silently substitute an audio-only file.

Use VirtualDJ's video mixer/output to view the picture. This preview prepares
the complete file before use; it does not promise immediate live video streaming.

## Local acceptance checks

- Create a setlist, add two tracks from VirtualDJ, restart both apps and reload
  the saved entries. Export and reopen the playlist.
- Play a track beyond `historyDelay`; verify it appears in native History and
  **Played in VirtualDJ**. A track only loaded onto a deck must not appear.
- Download audio, disconnect the network, and load/seek it from the saved folder.
- Cancel a download and retry it; confirm no incomplete track is offered.
- Prepare a video, check picture/audio sync, seeking, cue points and two decks.
- Check removal of a saved file and restoring normal online playback afterward.

Automated checks cover persistence, history parsing, authorization, cancellation,
file ranges, storage limits, stream validation, the web panel and the Windows
native DLL interface. Actual VirtualDJ deck behavior remains a manual test.
