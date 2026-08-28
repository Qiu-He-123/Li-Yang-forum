==================================================
  Git Helper Scripts - Usage Guide
  Repo: https://github.com/Qiu-He-123/Li-Yang-forum
==================================================

This pack contains 7 .bat scripts for everyday Git
tasks. Just double-click the one you need.

IMPORTANT:
  - The filenames are in Chinese, but all text inside
    is English to avoid encoding problems in cmd.
  - Git must be installed on your computer.
    Download from: https://git-scm.com/download/win


[1] Git Clone Repository  (Git克隆仓库.bat)
    Use this FIRST to download the project.
    Run it anywhere. It creates a folder "Li-Yang-forum".
    After cloning, COPY all .bat files into that folder.

[2] Git Status  (Git查看状态.bat)
    Shows the current branch, recent commits, and
    which files changed (M=modified, ??=new, D=deleted).

[3] Local Git Save  (本地Git保存.bat)
    Stages all changes and makes a commit (local save).
    You will be asked for a short description.
    Nothing is uploaded yet - run Push after this.

[4] Git Push to Cloud  (Git上传云端.bat)
    Uploads your commits to GitHub.

[5] Git Pull Update  (Git拉取更新.bat)
    Downloads the latest version from GitHub.
    Run this before working if others changed things.

[6] Local Git Rollback  (本地Git回溯.bat)
    Go back to an older commit.
    Modes:
      [1] Soft  - keep your changes staged (safest)
      [2] Mixed - keep your changes unstaged
      [3] Hard  - DELETE all changes after that point
                 (only use if you are sure!)

[7] One-Click Sync  (一键同步.bat)
    Pull + Save + Push all at once.
    Good for a quick "I finished, sync everything".


TYPICAL WORKFLOW
-----------------
  First time:   run [1] Clone
  Start work:   run [5] Pull  (get latest)
  After work:   run [3] Save  -> then [4] Push
  Made a mess:  run [6] Rollback
  In a hurry:   run [7] One-Click Sync


NOTES
-----
  - If push/pull asks for a password, GitHub no longer
    accepts account passwords. Use a Personal Access
    Token (PAT) instead:
      GitHub -> Settings -> Developer settings ->
      Personal access tokens -> Generate new token
    Or use Git Credential Manager (installed with Git
    for Windows) which handles login in a popup window.
  - "backend/logs/app.log" is a runtime log and should
    not be committed. Add it to .gitignore.
