# Changelog

## 0.3.0 - 2026-11-19

Added by: Knarkoffer

### Added

- Remember the window position and Always on top preference between launches
  in %LOCALAPPDATA%\GitHubRateGauge\settings.json.
- Restore saved positions onto a visible monitor work area after display
  layout changes, including monitors with negative desktop coordinates.
- Save preferences automatically after changes and when exiting.

## 0.2.0 - 2026-11-19

Added by: Knarkoffer

### Added

- Keep one application instance per Windows session and restore the running
  gauge on subsequent launches, including when it is hidden in the tray.

### Changed

- Use "GitHub Rate Gauge" consistently in the window title, tray tooltip,
  notifications, and README.
- Match both gauge faces and counters to the window's gray background (#c0c0c0).

## 0.1.0 - 2026-11-19

Added by: Knarkoffer

### Added

- Display GitHub core REST API and GraphQL quota consumption on two speedometers with
  Windows 95/98 styling and muted green, amber, and red bands at 60% and 80% usage.
- Show REST requests and GraphQL points used and remaining, each with its own
  reset time in local time.
- Label the gauge boxes "REST API" and "GraphQL API".
- Refresh both gauges every minute or on demand using one quota check through
  the existing GitHub CLI login.
- Keep the last successful reading visible when a refresh fails.
- Provide an Always on top checkbox, using native Windows Tkinter when launched
  from WSL and retaining the WSL GitHub CLI login for quota checks.
- Display the application version from VERSION and record changes in this file.
- Provide CMD and VBS launchers with hidden startup, a visible diagnostic mode,
  and automatic creation of a private Windows Python environment.
- Use a custom pixel-art gauge icon in the title bar and Windows taskbar.
- Minimize to the Windows notification area while quota checks continue.
- Show both quota readings and refresh status in the tray tooltip, with
  double-click and Open to restore, and Quit to exit.
- Show only the usage counts beside the short labels "REST" and "GraphQL" in
  the tray tooltip, without timestamps.
- Define dependencies and package metadata in pyproject.toml, with VERSION as
  the source for both the package version and the displayed application version.
- Install the project and its dependencies through the Windows launcher when
  needed, and include icons and version data in the installable package.
- Provide a github-rate-gauge Windows GUI entry point for installed copies.

### Fixed

- Return control to the WSL terminal immediately when starting the VBS launcher,
  while a hidden background launcher continues to report startup failures.
