"""自動更新：比對本機和 GitHub 上 main 分支的最新 commit，有新版就用 git 快轉（fast-forward）更新。

video_ui.py 啟動時呼叫 run(apply=True, quick=True)（可在網頁右上角的「選項」關閉），選項頁的「檢查更新」
呼叫 run(apply=False)，按「立即更新並重新啟動」再呼叫 run(apply=True)。更新完要由 video_ui.py 重新啟動才會載入新的程式碼。

版本就是 commit：顯示成「commit 日期（短 hash）」，例如 2026.09.27（7832df3），推上 GitHub 的 main 就算新版。

只支援用 git clone 下載的專案。下面這些情況只回報、不更新，不會動到本機的修改：
不在 main 分支、有還沒 commit 的修改、有還沒推上 GitHub 的 commit（或和 GitHub 各有新的 commit）、連不到 GitHub。
更新後會先試著載入新版，載入失敗（例如新版需要還沒安裝的套件）就退回原本的版本。
遠端是 GitHub 的 SSH 網址（git@github.com:…）時改走公開的 HTTPS：公開 repo 不用登入，
從 Finder 開 App 時也不會卡在 SSH 金鑰的密碼。
"""
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BRANCH = "main"
REPO_URL = "https://github.com/Kouzui-HUANG/ai-video-gen"  # 不是 git clone 的（例如下載 ZIP）時，提示改用這個重新下載

# 背景執行時不能停下來問帳號密碼：HTTPS 不問、SSH 用 BatchMode（沒有 agent 就直接失敗）
_ENV = {**os.environ, "GIT_TERMINAL_PROMPT": "0", "GIT_SSH_COMMAND": "ssh -o BatchMode=yes -o ConnectTimeout=5"}


class GitError(Exception):
    pass


def _git(*args, timeout=10, check=True):
    """在專案資料夾執行 git，回傳 stdout；check=False 時改回傳結束代碼。"""
    try:
        r = subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=timeout, env=_ENV)
    except subprocess.TimeoutExpired:
        raise GitError(f"git {args[0]} 超過 {timeout} 秒沒有完成") from None
    except OSError as e:
        raise GitError(f"無法執行 git：{e}") from None
    if not check:
        return r.returncode
    if r.returncode:
        raise GitError((r.stderr or r.stdout).strip() or f"git {args[0]} 失敗（結束代碼 {r.returncode}）")
    return r.stdout.strip()


def unsupported_reason():
    """不能自動更新的原因；可以的話回傳 None。"""
    if not (ROOT / ".git").exists():
        return (f"這份程式不是用 git clone 下載的（例如下載 ZIP），無法自動更新。要自動更新，請用 "
                f"git clone {REPO_URL}.git 重新下載，再把原本的 outputs/ 資料夾搬過去。")
    git = shutil.which("git")
    if not git:
        return "找不到 git，無法自動更新。"
    # macOS 沒裝命令列開發工具時 /usr/bin/git 只是個空殼，一執行就會跳出安裝視窗
    if sys.platform == "darwin" and git == "/usr/bin/git" and subprocess.run(["xcode-select", "-p"],
                                                                            capture_output=True).returncode:
        return "這台 Mac 沒有安裝命令列開發工具（git），無法自動更新。可在終端機執行 xcode-select --install 安裝。"
    return None


def commit_info(rev="HEAD"):
    sha, ts = _git("log", "-1", "--format=%H %ct", rev).split()
    day = time.strftime("%Y.%m.%d", time.localtime(int(ts)))
    return {"sha": sha, "short": sha[:7], "time": int(ts), "label": f"{day}（{sha[:7]}）"}


def current_version():
    """目前的版本（HEAD 的 commit）；不是 git clone 的或讀不到就回傳 None。"""
    if unsupported_reason():
        return None
    try:
        return commit_info()
    except GitError:
        return None


def _remote():
    """回傳（查詢和下載用的網址, GitHub 網頁網址或 None）。"""
    try:
        url = _git("config", "--get", "remote.origin.url")
    except GitError:
        return None, None
    m = re.fullmatch(r"(?:https://github\.com/|(?:ssh://)?git@github\.com[:/])([\w.-]+/[\w.-]+?)(?:\.git)?/?", url)
    if m:
        return f"https://github.com/{m.group(1)}.git", f"https://github.com/{m.group(1)}"
    return url, None


def _is_ancestor(a, b):
    """a 是不是 b 本身或 b 的祖先（b 已經包含 a 的所有修改）。"""
    code = _git("merge-base", "--is-ancestor", a, b, check=False)
    if code not in (0, 1):
        raise GitError(f"無法比較 {a[:7]} 和 {b[:7]}")
    return code == 0


def _smoke_test():
    """新版能不能載入（例如新版需要還沒安裝的套件）：在子程序 import video_ui，失敗就回傳原因。"""
    try:
        r = subprocess.run([sys.executable, "-c", "import video_ui"], cwd=ROOT, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=30)
    except subprocess.TimeoutExpired:
        return "載入新版超過 30 秒", None
    if not r.returncode:
        return None, None
    lines = (r.stderr or r.stdout).strip().splitlines()
    missing = re.search(r"No module named '([\w.]+)'", r.stderr or "")
    return (lines[-1] if lines else f"結束代碼 {r.returncode}"), missing and missing.group(1).split(".")[0]


def run(apply, quick=False):
    """檢查 GitHub 上 main 的最新版本；apply=True 且可以快轉時順便更新。回傳給網頁顯示的狀態：
    state：up_to_date、updated（已更新，要重新啟動）、available（有新版，apply=False 時）、ahead（本機比較新）、
    blocked（有新版但這次不能更新）、rolled_back（新版載入失敗，已退回）、offline、error、unsupported。
    quick：啟動時用，逾時較短（App 的 launch.sh 最多等伺服器 10 秒）。"""
    status = {"state": "", "message": "", "checked_at": time.time(), "current": None, "latest": None,
              "web": None, "update_available": False}

    def done(state, message, **fields):
        status.update(state=state, message=message, **fields)
        return status

    reason = unsupported_reason()
    if reason:
        return done("unsupported", reason)
    try:
        head = commit_info()
        status["current"] = head
        url, status["web"] = _remote()
        if not url:
            return done("unsupported", "這個 git 資料夾沒有設定遠端 origin，不知道要從哪裡更新。")
        try:
            out = _git("ls-remote", url, f"refs/heads/{BRANCH}", timeout=3 if quick else 20)
        except GitError as e:
            return done("offline", "連不到 GitHub，先用目前的版本。", detail=str(e))
        if not out:
            return done("error", f"GitHub 上找不到 {BRANCH} 分支。")
        latest = out.split()[0]
        if latest == head["sha"]:
            status["latest"] = head
            return done("up_to_date", "已是最新版本。")
        if _git("cat-file", "-e", f"{latest}^{{commit}}", check=False):  # 本機還沒有這個 commit 才下載
            try:
                _git("-c", "gc.auto=0", "-c", "maintenance.auto=false", "fetch", "--no-tags", "--quiet", url,
                     f"+refs/heads/{BRANCH}:refs/remotes/origin/{BRANCH}", timeout=5 if quick else 60)
            except GitError as e:
                return done("offline", "從 GitHub 下載新版失敗，先用目前的版本。", detail=str(e))
        status["latest"] = commit_info(latest)
        if _is_ancestor(latest, head["sha"]):
            return done("ahead", "本機有還沒推上 GitHub 的 commit，比 GitHub 上的新，不用更新。")
        status["update_available"] = True
        branch = _git("rev-parse", "--abbrev-ref", "HEAD")  # 不在分支上時是 HEAD
        if branch != BRANCH:
            return done("blocked", f"目前在「{branch}」分支，只有 {BRANCH} 分支會自動更新。" if branch != "HEAD"
                        else "目前不在任何分支上（detached HEAD），不會自動更新。")
        if not _is_ancestor(head["sha"], latest):
            return done("blocked", "本機和 GitHub 上各有新的 commit，無法自動更新，請手動合併（git pull）。")
        changed = _git("--no-optional-locks", "status", "--porcelain", "--untracked-files=no").splitlines()
        if changed:
            return done("blocked", f"有 {len(changed)} 個檔案有還沒 commit 的修改，commit 或還原後才會更新。")
        if not apply:
            return done("available", f"GitHub 上有新版本 {status['latest']['label']}。")
        try:
            _git("merge", "--ff-only", "--quiet", latest, timeout=30)
        except GitError as e:
            return done("blocked", "git 無法快轉到新版本，這次先不更新。", detail=str(e))
        problem, missing = _smoke_test()
        if problem:
            _git("reset", "--keep", head["sha"], timeout=30)  # 工作區是乾淨的，退回只會拿掉剛才的更新
            hint = (f"新版需要還沒安裝的套件 {missing}：請在終端機執行 python3 -m pip install {missing}，下次啟動會再更新。"
                    if missing else "")
            return done("rolled_back", f"新版本 {status['latest']['label']}無法啟動，已退回原本的版本。{hint}",
                        detail=problem)
        return done("updated", f"已更新到 {status['latest']['label']}。", previous=head, current=status["latest"],
                    update_available=False)
    except (GitError, OSError, ValueError) as e:
        return done("error", "檢查更新時發生錯誤，先用目前的版本。", detail=str(e))
