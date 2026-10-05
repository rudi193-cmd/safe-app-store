# Python archaeology: building 33 years of CPython on a 2026 toolchain

Every CPython milestone from 0.9.8 (1993) to 3.15.0rc3 (2026), cloned from
`github.com/python/cpython`. Each one was built on x86_64 with gcc 13.3,
glibc and OpenSSL 3.0.13, then run against its own test suite. The work was
done in a cloud container (Claude Code session, 2026-10-03 → 2026-10-05).

`patches/` holds what each version needed in order to build, and `BUILD.txt`
says how to apply it. `pre-ai/` holds a CPython test fix built only from
pre-2021 lines, with the tool that checks its provenance.

**Provenance of everything below.** Build and test figures were measured in
the session. Dates come from git tags/commits unless marked. Two values are
**reconstructed, not measured**, and are labelled where they appear:
- `$Revision: 1.6 $` in 2.0's `Lib/xml/__init__.py`, inferred from the trunk
  commit count.
- `r25:51908` for 2.5's Subversion keywords, taken from 2.5 release banners
  published in 2006–07.

Test counts are **test modules** (regrtest files) unless stated. 0.9.8 and
1.0.0 only report pass/fail for the whole suite.

---

## 1. Every build

| Version | Released | Source used | Changes to build it today | Test results | What happened |
|---|---|---|---|---|---|
| **0.9.8** | Jan 1993 | tag `v0.9.8` | ~20 files: rebuilt the missing Makefile and headers, backported the dict object from Mar 1993, 64-bit fixes | Passed all; output matches the 1993 expected output | No build files or `dictobject.c` in the tag; `2*1` overflowed on 64-bit |
| **0.9.9** | Jul 1993 | tag `v0.9.9` | Compared only, not built | — | Old class syntax removed; `access` statement; `hash()`; fast locals |
| **1.0.0** | Jan 1994 | commit `2a7cbe9` (no tag exists) | 17 files | Passed all, plus one test typo fix taken from 1.1 | Release cut mid-reorganization; calls itself "0.9.0++"; varargs segfault; `.pyc` truncated big ints until 1.5 |
| **2.0** | Oct 2000 | tag `v2.0` | 2 lines + `-fwrapv` + 1 stray file deleted | **82/82** | `int_repr` one-byte overflow (fixed upstream in 2.2); modern gcc removing an overflow check; `sys.platform` = `linux6` |
| **2.2** (first `hmac`) | Dec 2001 | commit `22768184cb`; both git tags are mislabelled | **None** | **155 OK / 1 failed** | `test_mktime` assumes 32-bit `time_t`; `hmac`, `md5`, `sha` tests pass |
| **2.5** (first `hashlib`) | Sep 2006 | tag `v2.5` | 3 small: `touch` generated files, fill in Subversion keywords (`r25:51908`, reconstructed), multiarch path | **273 OK / 3 failed** | gdbm magic ×2, zlib `wbits=0`; `_hashlib` skipped (OpenSSL 3 version macro), built-in fallbacks used; hmac and hashlib tests pass |
| **3.0** | Dec 2008 | tag `v3.0` | 0 in the core; 3 small module fixes | **294 / 297** | Old `setup.py` couldn't find libraries; opaque ncurses structs; remaining failures were root user, zlib change, test race |
| **3.9.0** | Oct 2020 | tag `v3.9.0` | **None** | **393 / 399** | Mostly OpenSSL 3, plus tz database, one unconfirmed command-line test, VSOCK hang |
| **3.14.0** | Oct 2025 | tag `v3.14.0` | **None** | **460 / 462** | Both failures are the container: HTTPS proxy, no VSOCK device |
| **3.15.0rc3** | Oct 2026 | tag `v3.15.0rc3` | **None** | **471 / 473** | Same two container failures; `_decimal` no longer bundled |
| | | | | | |
| **RFC 2202 HMAC check** | 2001–2026 | 2.2 → 3.15rc3 | — | 6 builds produce identical values | HMAC-MD5 `9294727a…` and HMAC-SHA1 `b6173186…` match the shipped test vectors |
| **hmac/hashlib, current** | — | 3.14.0, 3.15.0rc3 | — | All pass, including slow tests and, on 3.14, bigmem | Nothing to fix, no PR; 8 vector downloads blocked by network policy, 3 bigmem tests need more than 15 GB |
| **VSOCK PR** | — | branch `gh-vsock-enodev-skip` on 3.14.0 | 8 lines, all verbatim from CPython of 2021-06-28 | Test skips cleanly; full `test_socket` passes; the provenance check passes and fails when given a new line | Still needed: 3.15.0rc3 and 3.14.8 still fail the same way after gh-145548 |

**Tests column:**
- 0.9.8 and 1.0.0 only report pass/fail for the whole suite.
- Every other figure counts test modules.
- 3.0's 294 includes test_dbm after the `whichdb` fix.

Across all of it:
- **Build effort:** it went from reconstructing missing files by hand (1993–94) to unmodified `./configure && make` (2020 onward).
- **Failures:** every failure traced came from outdated platform assumptions, newer system libraries, or the container. The only one not confirmed is 3.9's test_cmd_line.

### Per-version detail

| Version | Fixes, each verified with a check that fails without it |
|---|---|
| 0.9.8 | Reconstructed `PROTO.h`, `patchlevel.h`, `sigtype.h`, `fgetsintr.h`/`fgets_intr()`. Backported Guido's 1993-03-27 `dictobject.c` with a string-only hash. Fixed `int_mul`'s `(long)0x80000000` (positive on LP64). Sign-extended `rd_long` (Guido's own `XXX`). 32-bit integer-literal semantics. `va_list` aliasing, `getline`, `errno`, `getpgrp`/`setpgid`, `h_addr`, `struct timezone` |
| 1.0.0 | `INCLDIR` pointed at a non-existent `$(TOP)/Py`. Modules had moved to `Modules/`. `version.c` truncated and unused. `frozenmain.o` won the link for `main`. `vmkvalue` `va_copy`. `sys.maxint` backported (upstream wired it 1994-08-30). 64-bit test-branch sign typo fixed using the 1.1 correction. `.pyc` `TYPE_INT64` backported from 1.5 (`5000000000` read back as `705032704`) |
| 2.0 | Stray committed `Include/config.h` shadowed the generated one. `int_repr` `char buf[20]` → 64 (upstream 2.2). `-fwrapv` (`PyOS_strtol`'s `result == -result`). `$Revision$` unexpanded in `xml/__init__.py` (1.6, inferred) |
| 2.2 | None |
| 2.5 | `make` regenerating the AST needs Python 2, so `touch` the generated files. `$HeadURL$`/`$Revision$` unexpanded made startup fatal; reconstructed as `tags/r25`, `51908`. sqlite found the header but not the library under multiarch, which crashed `setup.py` |
| 3.0 | Multiarch library dir in `setup.py` (backport of 2.7.3/3.2.3). `_dbm` needs `gdbm_compat`. `is_pad()` instead of `WINDOW->_flags`. `whichdb` recognises gdbm magics `0x13579acd`/`0x13579acf` |
| 3.9.0 / 3.14.0 / 3.15.0rc3 | None |

### Things that looked like bugs and were not

| Symptom | Actual cause |
|---|---|
| 2.0 `test_import` "No module named @test" | `make test` sets `PYTHONPATH=` (empty, not unset), which in 2.0 puts the cwd on `sys.path` |
| 2.0 `u"☺"` became 3 code points | The test file held raw UTF-8 bytes, not the escape. Correct pre-PEP 263 Latin-1 behaviour |
| 2.0 `2**63` → `OverflowError` | Correct for 2.0; int→long unification arrived in 2.2 |
| 3.0 ASCII stdout | Uninstalled build tree: `_functools` not importable before `site` runs, so locale detection fails |
| 3.0 / 3.14 / 3.15 `test_httpservers`, `test_urllib` | Root user (`chmod 0` doesn't stop root); the container's HTTPS proxy |
| 3.9 `test_socket` hang, 3.14 / 3.15 VSOCK error | The VM has `/dev/vsock` (CID 3) but no loopback transport, so `connect()` to its own CID returns `ENODEV` |

---

## 2. Release cadence

| Version | Date (git tag) | Gap |
|---|---|---|
| 0.9.8 | 1993-01-10 | |
| 0.9.9 | 1993-07-29 | 6 mo |
| 1.0.0 | 1994-01-26 (commit) | 6 mo |
| 1.0.1 | 1994-02-15 | 3 wk |
| 1.1 | 1994-10-11 | 8 mo |
| 1.2 | 1995-04-10 | 6 mo |
| 1.3 | 1995-10-12 | 6 mo |
| 1.4 | 1996-10-25 | 1 yr |
| 1.5 | 1997-12-31 | 14 mo |
| 1.5.2 | 1999-04-13 | 15 mo |
| 2.0 | 2000-10-16 | 18 mo |
| 3.0 | 2008-12-03 | |
| 3.1 – 3.8 | 2009-06 → 2019-10 | 7–20 mo |
| 3.9 | 2020-10-04 | 12 mo |
| 3.10 – 3.14 | every October, 2021–2025 | 12 mo (PEP 602) |

3.14 is the fourteenth feature release since 3.0, not "3.0 + 0.14".

---

## 3. Releases around Python 3.10 and 3.14, and what each project says about AI

Merged from medium-depth web searches on 2026-10-03/04.

| Project | Autumn 2021 | Autumn 2025 | AI and how it's built |
|---|---|---|---|
| **Python** | **3.10**, Oct 4 | **3.14**, Oct 7 | AI allowed in contributions; you must understand and defend the change; disclosure "appreciated, not required" |
| **Java** | 17 (LTS), Sep 14 | 25 (LTS), Sep 16 | **OpenJDK bans** AI-generated content "in part or in full" (interim policy, copyright grounds; start date not confirmed) |
| **.NET** | 6 (LTS), Nov 8 | 10 (LTS), Nov 11 | GitHub's Copilot coding agent has opened PRs in `dotnet/runtime` since May 2025: 878 PRs, 535 merged, about 95k lines added. Every one was requested by a human maintainer |
| **Windows** | 11 launches, Oct 5 | 10 support ends, Oct 14 | Nadella: 20–30% of Microsoft's code is AI-written (company-wide, Apr 2025) |
| **Apple** | iOS 15 (Sep 20), macOS Monterey (Oct 25) | iOS 26 + macOS Tahoe 26 (Sep 15) | Reported Claude-based coding tool in Xcode for internal use (May 2025); Xcode 26.3 later added agents. No statement about the OS releases themselves |
| **Android** | 12: source Oct 4, Pixels Oct 19 | 16, Jun 10 (moved to a Q2 release) | Google: AI-generated share of new code went from ~25% (2024) to "well over 30%" (Apr 2025) to 75% (reported later). No AOSP-specific AI policy found |
| **Linux kernel** | 5.15 (LTS), Oct 31 | 6.17, Sep 28 | An undisclosed all-LLM patch landed in 6.15. The resulting policy allows AI with an `Assisted-by:` tag and a human sign-off; it shipped with 7.0 |
| **Ubuntu** | 21.10, Oct 14 | 25.10, Oct 9 | Canonical allows AI-assisted contributions with the contributor fully responsible; has said it will ship AI-co-authored code (2026) |
| **Fedora** | 35, Nov 2 | 43, Oct 28 | AI allowed with disclosure when a significant part is AI output; approved Oct 22, 2025 |
| **GNOME** | 41, Sep 22 | 49 (in Ubuntu 25.10) | Extensions site rejects visibly AI-generated "slop" (Dec 2025); AI help is fine if you can explain the code |
| **KDE** | Plasma 5.23 "25th Anniversary Edition", Oct 14 | Plasma 6.5, Oct 21 | Still undecided. A draft rule ("don't be lazy", human in the loop) set off a fight, the discussion was locked, and a petition followed (Sep 2026) |
| **Firefox** | — | 144 (Oct) | Firefox AI Coding Policy: same quality bar, understand every line, self-review first. Mozilla also reported Claude found 100+ Firefox bugs in two weeks |
| **Other** | Facebook/Instagram/WhatsApp down ~6 hrs on Oct 4, Python 3.10's release day | GIMP 3.0.6, VirtualBox 7.2.4 | — |

Findings:
- **2021:** no project on the list said anything about AI. GitHub Copilot's preview was three months old (2021-06-29) and invite-only.
- **2025–26:** every project has taken a position:
  - **Banned:** OpenJDK, Gentoo, NetBSD.
  - **Allowed, disclosure required:** Linux, Fedora.
  - **Allowed, disclosure optional:** Python.
  - **Allowed, contributor accountable:** Firefox, Canonical.
  - **Undecided:** KDE.
- **Release-level evidence:** .NET 10 is the only release on the list with a published, counted record of agent-written code going into it.

---

## 4. hmac and hashlib: first stable release vs. current

| | `hmac`: 2.2 (Dec 2001) | `hashlib`: 2.5 (Sep 2006) | 3.14.0 | 3.15.0rc3 |
|---|---|---|---|---|
| Focused tests | `test_hmac`, `test_md5`, `test_sha` pass | `test_hmac`, `test_hashlib` (26), `test_md5`, `test_sha` pass | `test_hmac` + `test_hashlib` pass, incl. `-u cpu` and `-M 8G` | pass, incl. `-u cpu`; 3 bigmem need more than 15 GB |
| Backend | `md5`/`sha` C modules | built-in fallbacks (`_hashlib` skipped) | OpenSSL 3.0.13 + HACL* | OpenSSL 3.0.13 + HACL* |
| Not run | — | — | 8 NIST/BLAKE2/SHA-3 vector downloads (network policy denies `www.pythontest.net`) | same 8 |

RFC 2202 case 1 is identical across 2.2, 2.5, 3.0, 3.9.0, 3.14.0 and 3.15.0rc3:
HMAC-MD5 `9294727a3638bb1c13f48ef8158bfc9d` (also in 2.2's own `test_hmac.py`),
HMAC-SHA1 `b617318655057264e28bc0b6fb378c8ef146be00` (in 3.15's `test_hmac.py`).

---

## 5. The pre-AI VSOCK fix (`pre-ai/`)

Constraint: every added line must exist verbatim, apart from leading whitespace,
in CPython at `dcb1caef5bd8` (2021-06-28 23:02 +0100), the last commit before
GitHub Copilot's technical preview. The upstream fix gh-145548 was not read
while writing it.

| Added line | Pre-AI origin |
|---|---|
| `self.cli = socket.socket(socket.AF_VSOCK, socket.SOCK_STREAM)` | `Lib/test/test_socket.py:513` |
| `self.addCleanup(self.cli.close)` | `Lib/test/test_socket.py:514` |
| `cid = get_cid()` | `Lib/test/test_socket.py:515` |
| `try:` | ubiquitous |
| `self.cli.connect((cid, VSOCKPORT))` | `Lib/test/test_socket.py:516` |
| `except OSError as e:` | ubiquitous |
| `if e.errno == errno.ENODEV:` | `Lib/test/test_socket.py:2192` |
| `self.skipTest(str(e))` | `Lib/test/test_c_locale_coercion.py:413` |

| Check | Result |
|---|---|
| VSOCK test before / after | ERROR → skipped `[Errno 19] No such device` (3/3 runs) |
| full `test_socket` after | 745 run, 276 skipped, SUCCESS |
| probe removed | ERROR returns |
| `preai_gate.py` on the diff | 0 lines without pre-AI origin |
| gate with one novel line added | fails, exit 1 |
| 3.15.0rc3 and 3.14.8 (both contain gh-145548) | still fail identically, so the fix is still needed |

**Not verified:** behaviour on a host where VSOCK works, and the
`VMADDR_CID_ANY` remap. The commit message and description are AI-written,
and the description says so.

---

## Sources

Web sources for section 3 (accessed 2026-10-03/04):
- [Linux App Release Roundup (October 2025) – OMG! Ubuntu](https://www.omgubuntu.co.uk/2025/11/linux-app-release-roundup-october-2025)
- [Ubuntu 25.10 released – OMG! Ubuntu](https://www.omgubuntu.co.uk/2025/10/ubuntu-25-10-released)
- [The 6.17 kernel has been released – LWN](https://lwn.net/Articles/1038266/)
- [Windows 10 support has ended – Microsoft](https://support.microsoft.com/en-us/windows/deployment/updates-lifecycle/windows-10-support-has-ended-on-october-14-2025)
- [Java 25 GA – OpenJDK](https://mail.openjdk.org/pipermail/announce/2025-September/000360.html)
- [macOS Tahoe 26 launch date – 9to5Mac](https://9to5mac.com/2025/09/09/apple-confirms-macos-tahoe-26-launch-date-september-15/)
- [Plasma 6.5 – KDE](https://kde.org/announcements/plasma/6/6.5.0/)
- [Fedora 43 release – Linuxiac](https://linuxiac.com/fedora-43-final-build-approved-official-release-set-for-october-28/)
- [.NET 10 released – InfoQ](https://www.infoq.com/news/2025/11/dotnet-10-release/)
- [Windows 11 – Wikipedia](https://en.wikipedia.org/wiki/Windows_11)
- [Ubuntu 21.10 date – 9to5Linux](https://9to5linux.com/ubuntu-21-10-impish-indri-is-slated-for-release-on-october-14th-2021)
- [The Arrival of Java 17 – Inside.java](https://inside.java/2021/09/14/the-arrival-of-java17/)
- [macOS Monterey date – AppleInsider](https://appleinsider.com/articles/21/10/18/macos-monterey-will-be-released-on-october-25)
- [Android 12 – Wikipedia](https://en.wikipedia.org/wiki/Android_12)
- [Linux 5.15 – Kernel Newbies](https://kernelnewbies.org/Linux_5.15)
- [Fedora release history – Wikipedia](https://en.wikipedia.org/wiki/Fedora_Linux_release_history)
- [.NET releases – dotnet/core](https://github.com/dotnet/core/blob/main/releases.md)
- [2021 Facebook outage – Wikipedia](https://en.wikipedia.org/wiki/2021_Facebook_outage)
- [iOS 15 date – 9to5Mac](https://9to5mac.com/2021/09/14/ios-15-release-date/)
- [GNOME 41 released – GNOME](https://mail.gnome.org/archives/devel-announce-list/2021-September/msg00002.html)
- [GitHub Copilot – Wikipedia](https://en.wikipedia.org/wiki/GitHub_Copilot)
- [Nadella: 30% of Microsoft code by AI – CNBC](https://www.cnbc.com/2025/04/29/satya-nadella-says-as-much-as-30percent-of-microsoft-code-is-written-by-ai.html)
- [Kernel ML-tools policy – LWN](https://lwn.net/Articles/1049830/)
- [Fedora AI-assisted contributions policy – LWN](https://lwn.net/Articles/1042947/)
- [CPython AI tools guidelines – devguide](https://devguide.python.org/getting-started/ai-tools/)
- [Oracle bans AI contributions to OpenJDK – Techzine](https://www.techzine.eu/news/devops/143395/oracle-bans-ai-generated-contributions-to-openjdk/)
- [Google 75% of new code AI – Fast Company](https://www.fastcompany.com/91531519/google-ceo-says-75-of-the-companys-code-is-ai-generated)
- [Gentoo bans AI code – The Register](https://www.theregister.com/2024/04/16/gentoo_linux_ai_ban/)
- [Android 16 – Wikipedia](https://en.wikipedia.org/wiki/Android_16)
- [Plasma 25th Anniversary Edition – KDE](https://kde.org/announcements/plasma/5/5.23.0/)
- [Ten Months with Copilot Coding Agent in dotnet/runtime – .NET Blog](https://devblogs.microsoft.com/dotnet/ten-months-with-cca-in-dotnet-runtime/)
- [GNOME rejects AI-generated extensions – Linuxiac](https://linuxiac.com/gnome-will-reject-shell-extensions-with-ai-generated-code/)
- [KDE LLM policy discussion locked – XDA](https://www.xda-developers.com/kdes-proposed-llm-policy-discussion-gets-locked-after-a-fiery-community-clash/)
- [Firefox AI Coding Policy – Mozilla](https://firefox-source-docs.mozilla.org/contributing/ai-coding.html)
- [Canonical contribution AI guidance](https://canonical.com/juju/docs/12-factor/latest/how-to/contribute/)
- [Apple + Anthropic coding platform – MacRumors](https://www.macrumors.com/2025/05/02/apple-anthropic-ai-coding-platform/)
- [Python 2.5 release – python.org](https://www.python.org/downloads/release/python-250/) (for `r25:51908`, see 2006–07 banners such as [this PDF](https://people.bath.ac.uk/masrs/ma50177/pdfs/pyscicomp.pdf))
