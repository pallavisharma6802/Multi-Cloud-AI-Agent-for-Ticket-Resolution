#!/usr/bin/env python3
"""Seed real VS Code support tickets through the live agent pipeline
(POST /api/v1/tickets) so the inbox/analytics have real, varied volume.

Usage: python data/seed_vscode_tickets.py [--base-url http://localhost:8000] [--n 20]
"""
from __future__ import annotations

import argparse
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

TICKETS = [
    # INSTALLATION
    ("Can't install VS Code on an M1 Mac", "I downloaded the macOS build but it says 'app is damaged and can't be opened'. How do I install it on Apple Silicon?"),
    ("Install fails on Ubuntu via apt", "Running apt install code gives a GPG signature error on the Microsoft repo. How do I fix the keyring?"),
    ("Can I install VS Code without admin rights on Windows", "My company laptop blocks the normal installer. Is there a per-user install that doesn't need admin?"),
    ("Portable version won't save settings", "I'm running the portable zip build from a USB drive but my settings reset every time I unplug it."),
    ("Uninstall leaves leftover extensions folder", "After uninstalling and reinstalling, all my old extensions are still there. How do I do a clean reinstall?"),
    ("Which build should I use on a Chromebook", "I'm on ChromeOS with Linux (Crostini) enabled. Which download target should I use?"),
    ("Silent install for a fleet of machines", "We need to roll out VS Code to 200 machines via a deployment script. Is there a silent/unattended install flag?"),

    # SETTINGS
    ("Settings sync not working across devices", "I enabled Settings Sync but my keybindings and extensions aren't showing up on my second laptop. What am I missing?"),
    ("How do I format on save only for Python files", "I want format-on-save enabled only for .py files using black, not globally for every language."),
    ("Workspace settings overriding my user settings unexpectedly", "I set a font size in user settings but a workspace .vscode/settings.json keeps overriding it project by project. How is precedence decided?"),
    ("Can't find where to change the color theme", "I just installed and want a dark theme but can't find the setting. Where is this normally?"),
    ("Settings Sync synced a broken keybinding", "After syncing, Ctrl+P no longer opens Quick Open on my second machine. How do I reset just keybindings?"),
    ("How to disable telemetry completely", "I want to turn off all usage/error reporting. Is there a single setting or several?"),
    ("Auto save keeps triggering linters mid-edit", "With files.autoSave on afterDelay, my linter runs constantly and is distracting. How do I tune the delay or disable autosave for one folder?"),

    # EXTENSIONS
    ("Extension marketplace won't load", "The Extensions view just spins forever and never lists anything, even for popular extensions. Is the marketplace down or is this a proxy issue?"),
    ("Java extension pack fails to download language server", "The Java extension shows 'Downloading Java Linker' forever and never finishes on a locked-down network."),
    ("Extension disabled itself after an update", "An extension that worked fine yesterday now shows 'disabled due to an error' after auto-updating overnight."),
    ("How to install an extension from a .vsix file offline", "My work machine has no internet access to the marketplace. How do I sideload an extension I downloaded elsewhere?"),
    ("Two linter extensions conflict and double-report errors", "ESLint and a second linter extension both report the same issue twice in the Problems panel. How do I disable one for just this workspace?"),
    ("Can I pin an extension to an older version", "An extension update broke my workflow. How do I roll back to a specific previous version and stop auto-update for it?"),
    ("Extension recommendations keep popping up for a removed tech stack", "We migrated off a framework months ago but VS Code still recommends its extension on every workspace open."),

    # EDITOR
    ("Multi-cursor selection not working with my keybinding", "Alt+Click used to add a cursor but now it does nothing. Did a recent update change the default?"),
    ("Minimap is distracting, how do I turn it off", "I'd like to hide the minimap on the right side of the editor permanently."),
    ("Bracket pair colorization is gone after update", "Nested brackets used to be color-coded but now they're all the same color. Is this feature removed or just toggled off?"),
    ("Can't drag a tab into a new split group", "Dragging a tab to the right edge used to split the editor but now it just reorders tabs."),
    ("Word wrap only works in some files", "Word wrap is on in Settings but some file types still require horizontal scrolling. Is this per-language?"),
    ("Copilot smart actions missing from right-click menu", "I used to be able to right-click and get inline AI suggestions but that menu item is gone now."),
    ("Zen Mode hides the status bar I need", "Zen Mode is great but I rely on the status bar's git branch indicator. Can I keep that visible?"),

    # LANGUAGES
    ("TypeScript IntelliSense extremely slow", "Autocomplete takes 5-10 seconds in a large monorepo. Is there a way to scope the TS server to a single workspace folder?"),
    ("Python interpreter not detected in virtualenv", "I created a venv but the status bar still shows the system Python and autocomplete doesn't see installed packages."),
    ("C++ IntelliSense shows squiggles for valid std:: includes", "Standard library headers are flagged as 'cannot be opened' even though the project builds fine from the command line."),
    ("Go to Definition jumps to a .d.ts file instead of source", "In a TypeScript project, Ctrl+Click on a function takes me to a type declaration file, not the actual implementation."),
    ("Rust analyzer never finishes indexing a large workspace", "The 'rust-analyzer: Indexing' status never completes on a 50-crate workspace, and autocomplete just doesn't work."),
    ("PHP IntelliSense doesn't see Composer autoload classes", "Classes loaded via Composer's autoloader show 'undefined class' even though the app runs fine."),
    ("Formatting on save reformats the whole file instead of changed lines", "I only want the lines I touched reformatted on save, but it reformats the entire file every time."),

    # TERMINAL
    ("Integrated terminal opens to the wrong shell", "Every new terminal opens PowerShell but I want it to default to WSL bash. How do I change the default profile?"),
    ("Can't find 'Open in Integrated Terminal' option", "Right-clicking a folder in Explorer no longer shows the Open in Integrated Terminal entry. It worked last week."),
    ("Terminal font doesn't match my editor font", "I set a custom font for the editor but the integrated terminal still uses the default monospace font."),
    ("Terminal colors look washed out compared to iTerm2", "ANSI colors render differently than my external terminal. Is there a setting to match 256-color output?"),
    ("Multiple terminal splits lose focus unpredictably", "When I have 3 terminal panes split, clicking one sometimes sends input to a different one."),
    ("Terminal doesn't inherit my shell's PATH additions", "Tools installed via my .zshrc PATH exports work in a normal terminal but 'command not found' in the integrated one."),
    ("How to clear terminal scrollback automatically between runs", "I'd like each new debug run to start with a clean terminal instead of appending to old output."),

    # GIT
    ("Git graph shows no commits after pull", "After pulling from origin, Source Control shows no changes and the commit graph is empty even though 'git log' in a real terminal shows commits."),
    ("Merge conflict markers not highlighted", "When a merge conflict happens, the <<<<<<< markers show as plain text instead of the usual colored conflict UI."),
    ("Can't stage individual hunks, only whole files", "I want to stage part of a file's changes but Source Control only offers 'Stage File', no per-hunk option."),
    ("Git blame annotations missing in the editor", "I used to see inline git blame info at the end of each line. It's gone after a recent update."),
    ("Push fails with a permission denied but git CLI works fine", "Pushing from Source Control panel fails silently, but the same push from an external terminal succeeds."),
    ("Commit message box won't accept multi-line input", "Pressing Enter in the commit message box submits instead of adding a new line."),
    ("Submodule changes not shown in Source Control", "A git submodule has uncommitted changes but Source Control only shows the parent repo as clean."),

    # DEBUGGING
    ("Debugger won't stop at breakpoints in Python", "I set breakpoints in a Flask app but the debugger runs straight through them. launch.json uses the debugpy adapter."),
    ("Node debugger attaches but can't resolve source maps", "Breakpoints in TypeScript source show as unverified even though sourceMap is enabled in tsconfig."),
    ("Watch panel shows 'not available' for a variable in scope", "A variable I can see being used right above the current line shows as unavailable in the Watch panel."),
    ("Conditional breakpoint never triggers", "I set a condition like i === 5 on a breakpoint inside a loop but execution never pauses."),
    ("Debug console doesn't let me evaluate expressions", "Typing an expression into the Debug Console while paused just echoes it back instead of evaluating."),
    ("Can't attach debugger to an already-running process", "I want to attach to a Node process started outside VS Code but the 'Attach to Process' picker shows nothing."),
    ("Step Into always skips into library code I don't care about", "Debugging steps into node_modules internals instead of staying in my own code."),

    # REMOTE_CLOUD
    ("Remote-SSH connection keeps dropping", "Remote-SSH disconnects every few minutes with 'Could not establish connection'. Works fine with a plain ssh client."),
    ("Dev Container build fails on first open", "Reopening in container fails during the postCreateCommand step with a permissions error on /workspace."),
    ("Remote Explorer doesn't show my saved SSH hosts", "I have hosts configured in ~/.ssh/config but the Remote Explorer sidebar shows an empty list."),
    ("Dev Container rebuild loses all installed packages", "Every time I 'Rebuild Container' I have to reinstall apt packages again even though nothing in the Dockerfile changed."),
    ("Codespaces session times out too quickly", "My GitHub Codespace disconnects after a short idle period, even mid-task. Can the timeout be extended?"),
    ("Port forwarding doesn't auto-detect my dev server", "I started a server on port 3000 inside a container but VS Code doesn't prompt to forward it like it usually does."),
    ("Remote-WSL extension can't find my distro", "I have Ubuntu installed via WSL2 but the 'Reopen in WSL' command says no distributions are available."),

    # AI_FEATURES
    ("Copilot Chat not citing any files", "When I ask Copilot Chat about my codebase it answers generically and never references actual files in my repo."),
    ("Copilot suggestions disabled for one language only", "I want inline Copilot suggestions off just for Markdown files but on everywhere else."),
    ("Copilot keeps suggesting an outdated API from training data", "Inline suggestions reference a library function that was removed from our codebase months ago."),
    ("How do I give Copilot Chat more context about my project", "Copilot Chat answers as if it's never seen my repo structure. Is there a way to point it at specific files?"),
    ("Agent mode edits files I didn't ask it to touch", "I asked for a change in one file and the agent also modified an unrelated config file."),
    ("Inline chat keeps appearing when I don't want it", "Selecting a line of code pops up an inline Copilot suggestion box unexpectedly."),
    ("Can I see how many tokens a Copilot session used", "I want to understand usage/cost for my Copilot Chat sessions. Is that visible anywhere in the UI?"),

    # GETTING_STARTED
    ("First time setup: where do I even start with VS Code for Python", "I'm new to VS Code coming from PyCharm. What's the minimum setup to get a working Python environment?"),
    ("What's the difference between a Workspace and a Folder", "The docs mention 'workspace' a lot but I just open folders. Am I missing something?"),
    ("How do I open two projects side by side", "I want to work on a frontend and backend repo in the same window, side by side."),
    ("Recommended starter extensions for web development", "I'm starting a React project and don't know which extensions are considered 'must-haves'."),
    ("Keyboard shortcuts cheat sheet for beginners", "Is there an official printable list of the most common keyboard shortcuts?"),
    ("How is VS Code different from Visual Studio", "I keep confusing these two products when searching for help. Can you clarify what each one is?"),

    # ENTERPRISE
    ("Can we centrally manage extension allowlists for the org", "Security wants to restrict which extensions employees can install company-wide. Is there a policy mechanism?"),
    ("Proxy settings needed for corporate network", "Behind our corporate proxy, the extension marketplace and auto-update both fail. How do I configure the proxy?"),
    ("Group Policy templates for VS Code on Windows", "We manage Windows machines via Group Policy. Are there official ADMX templates for VS Code settings?"),
    ("Disabling telemetry org-wide via managed settings", "Compliance requires telemetry off for all users. Is there a way to enforce this centrally rather than per-machine?"),
    ("SSO login for an internal extension gallery", "We host a private extension gallery internally. Can VS Code authenticate to it via our SSO provider?"),

    # API_REFERENCE
    ("How do I register a custom command from an extension", "I'm building an extension and want to contribute a new command to the Command Palette. What's the API for that?"),
    ("TextDocument API not firing onDidChangeTextDocument reliably", "My extension's change listener misses some edits when they happen very quickly in succession."),
    ("How to contribute a custom view to the Activity Bar", "I want my extension to add its own icon and panel to the Activity Bar, similar to Source Control."),
    ("WebView postMessage not reaching the extension host", "Messages sent from my webview's JS via vscode.postMessage never trigger my onDidReceiveMessage handler."),
    ("Extension API for reading workspace folder configuration", "What's the correct API call to read a workspace-level setting rather than the global one?"),

    # RELEASE_NOTES
    ("What changed in the latest VS Code update regarding terminal profiles", "After auto-updating, my terminal profile behavior changed. What does this version's release notes say changed?"),
    ("Did this version remove the old Debug Console layout", "The debug console looks different after updating. Was this an intentional redesign in the latest release?"),
    ("New Copilot features in the most recent release", "I heard there were new agent-mode capabilities added recently. What exactly shipped?"),
    ("Breaking change in settings.json schema after update", "Some of my settings now show as deprecated warnings after the latest update. What replaced them?"),

    # REFERENCE / GENERAL
    ("Where can I find the full list of built-in snippets", "I want to see every built-in code snippet available for JavaScript before writing my own."),
    ("Is there a complete list of all default keybindings", "I want a reference of every default keybinding, not just the common ones."),
    ("Documentation for the tasks.json schema", "I'm writing a custom build task and need the full schema reference for tasks.json."),
    ("What file types does VS Code support out of the box", "Before installing extensions, what languages/file types have built-in support?"),

    # Mixed / edge cases (harder, more ambiguous, good for exercising escalation realistically)
    ("VS Code crashed and I lost unsaved changes", "The editor crashed while I had unsaved changes in several files. Is there any local history or autosave I can recover from?"),
    ("Can VS Code auto-translate comments in my codebase", "We have a legacy codebase with comments in another language. Can VS Code translate them inline?"),
    ("I was charged twice for a paid extension", "My credit card was charged twice for a marketplace extension purchase this month."),
    ("Requesting a refund for a Visual Studio subscription mixup", "I think I was billed for a product I didn't mean to purchase and want a refund."),
    ("My account was locked after too many sign-in attempts", "I can't sign into Settings Sync anymore, it says my account is temporarily locked."),
    ("How do I delete my telemetry data that was already collected", "I turned off telemetry but want data already sent deleted. What's the process?"),
    ("VS Code window is completely blank after update, no error", "After the last update, the window opens but shows a blank gray screen with no UI at all."),
    ("Can I run VS Code entirely offline with no network calls at all", "For an air-gapped environment, I need zero network calls, including update checks and telemetry."),
    ("Extension host keeps crashing with an out of memory error", "The extension host process restarts every few minutes with an out-of-memory message in the logs."),
    ("How do I completely reset VS Code to factory defaults", "I want to wipe every setting, extension, and cache and start completely fresh."),
    ("Please escalate, I need to speak with a human about data deletion", "I have a GDPR data deletion request and need to talk to an actual person, not an automated response."),
    ("Workspace file association broken after installing a new extension", "A newly installed extension hijacked the default editor for .json files and I can't change it back."),
    ("Settings.json got corrupted and VS Code won't start", "After a bad edit to settings.json, VS Code now fails to launch entirely with no window appearing."),
    ("Can I legally redistribute VS Code inside our internal product", "Our company wants to embed VS Code in an internal tool. What are the licensing terms?"),
    ("Keybinding conflict between two extensions I can't resolve", "Two different extensions both bind Ctrl+Shift+R and I can't tell which one is winning or how to fix it."),
]


def submit_one(args_base_url, i, title, desc, total):
    try:
        r = requests.post(
            f"{args_base_url}/api/v1/tickets",
            json={
                "title": title,
                "description": desc,
                "user_email": f"seed-user-{i}@example.com",
                "domain_pack": "vscode_support",
            },
            timeout=180,
        )
        if r.status_code in (200, 201):
            body = r.json()
            print(f"[{i+1}/{total}] OK {body['ticket_id']} "
                  f"conf={body['confidence_score']:.2f} review={body['requires_human_review']}")
            return True
        print(f"[{i+1}] FAIL {r.status_code}: {r.text[:200]}")
        return False
    except Exception as e:
        print(f"[{i+1}] ERROR {e}")
        return False


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://localhost:8000")
    ap.add_argument("--n", type=int, default=len(TICKETS))
    ap.add_argument("--concurrency", type=int, default=2)
    args = ap.parse_args()

    subset = TICKETS[: args.n]
    ok = fail = 0
    with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        futures = [
            pool.submit(submit_one, args.base_url, i, title, desc, len(subset))
            for i, (title, desc) in enumerate(subset)
        ]
        for f in as_completed(futures):
            if f.result():
                ok += 1
            else:
                fail += 1
    print(f"\ndone: {ok} ok, {fail} failed")
    sys.exit(0 if fail == 0 else 1)


if __name__ == "__main__":
    main()
