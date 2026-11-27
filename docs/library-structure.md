# Library structure

Libera names files to work with the major audiobook servers (Audiobookshelf, BookOrbit, Jellyfin, Emby)
without any renaming. This page explains the rules and why we chose them.

## The rules

1. **One folder per book.** Audiobookshelf, BookOrbit, Jellyfin and Emby all expect it, so books never share a folder.
2. **The Audible ID ends the name:** `Title [B002UZMLXM]`, on both the folder and the file. Audiobookshelf reads it
   from the name, and Libation relies on it. In Libera it also keeps two books with the same title apart and lets
   a rescan find a book again.
3. **One m4b per book.** This is the preferred and recommended format across all the major servers, so it is the
   default. Split by chapter only if you need to support a legacy player. The chapter files are numbered
   `- 01 -`, `- 02 -`, so they sort correctly.
4. **Safe names everywhere.** Libera replaces `< > " / \ | ? *`, turns `:` into ` - `, strips leading and trailing
   dots and spaces, and keeps every name under 200 bytes, so files work on Windows, macOS, Linux, and SMB shares.

## Folder layouts

Choose one in Settings. The layout only decides the folders above the book.

**Author / Title is recommended**: every server in the sources below accepts it as documented, it keeps the author
in the path (Audiobookshelf reads authors only from a parent folder), and it needs no series metadata. The series
layouts are the best fit for Audiobookshelf, but only it reads series from the path.

| Layout | Example |
|---|---|
| Title (flat) | `Title [ASIN]/` |
| **Author / Title (recommended)** | `Author/Title [ASIN]/` |
| Author / Year - Title | `Author/2007 - Title [ASIN]/` |
| Author / Series / Number - Title | `Author/Series/01 - Title [ASIN]/` |
| Author / Series / Number - Year - Title | `Author/Series/01 - 2007 - Title [ASIN]/` |

Folders use the first author only, so a co-authored book is filed under
its first author. Anything missing, such as a series, is left out of the name. Changing the layout affects future downloads only.

## Tags matter most

Every server reads the tags inside the audio file: title, author, narrator, series, cover, chapters. Most of them
rank tags above the file path. Names are only a fallback, so if a book shows the wrong author or series, fix its
tags. Libera embeds the chapters and cover when it decrypts a book.

## Not yet

- Windows reserved names (`CON`, `NUL`, …) are not avoided.
- Names are not normalised to Unicode NFC, which can matter on macOS shares.

## Sources

Ordered by popularity, maturity, and relevance to audiobooks.

| Tool | Source |
|---|---|
| Audiobookshelf | [Directory structure](https://audiobookshelf.org/docs/documentation/libraries/book-library/directory-structure), [Book scanner](https://www.audiobookshelf.org/guides/book-scanner/), [folder parser source](https://github.com/advplyr/audiobookshelf/blob/master/server/utils/scandir.js) |
| Libation | [Naming templates](https://getlibation.com/docs/features/naming-templates) |
| Jellyfin | [Books](https://jellyfin.org/docs/general/server/media/books/) |
| Calibre | [Template language](https://manual.calibre-ebook.com/template_lang.html) |
| BookOrbit | [Library file structure](https://bookorbit.app/library-file-structure/#audiobooks), [Adding books](https://bookorbit.app/adding-books/), [Creating a library](https://bookorbit.app/creating-a-library/) |
| Emby | [Audio book naming](https://emby.media/support/articles/Audio-Book-Naming.html) |
| Windows file names | [Naming a file](https://learn.microsoft.com/en-us/windows/win32/fileio/naming-a-file) |
