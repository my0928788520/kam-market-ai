from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"


def test_watchdog_is_paper_only_and_single_instance() -> None:
    script = (TOOLS / "watch_fubon_five_timeframe_dashboard.ps1").read_text(
        encoding="utf-8"
    )
    assert "System.Threading.Mutex" in script
    assert "Test-DashboardHealth" in script
    assert "Stop-ProjectDashboardProcesses" in script
    assert "-PaperTestArmed" in script
    assert "-LineAlerts" in script
    assert "-NoBrowser" in script
    assert "StartupGraceSeconds = 180" in script
    assert "TotalSeconds -lt $StartupGraceSeconds" in script
    assert "$dashboardStartedAt = [DateTime]::UtcNow" in script
    assert "& $python @noticeArguments | Out-Null\n    }\n    catch {" in script
    assert "live" not in script.lower().replace("live_order", "")


def test_autostart_uses_limited_current_user_task_and_can_be_removed() -> None:
    installer = (TOOLS / "install_kam_dashboard_autostart.ps1").read_text(
        encoding="utf-8"
    )
    uninstaller = (TOOLS / "uninstall_kam_dashboard_autostart.ps1").read_text(
        encoding="utf-8"
    )
    assert "New-ScheduledTaskTrigger -AtLogOn" in installer
    assert "-RunLevel Limited" in installer
    assert "-MultipleInstances IgnoreNew" in installer
    assert "Unregister-ScheduledTask" in uninstaller
    assert "journals" in uninstaller


def test_one_click_launcher_detects_session_waits_for_health_and_stays_paper_only() -> None:
    script = (TOOLS / "start_kam_dashboard.ps1").read_text(encoding="utf-8")

    assert "Taipei Standard Time" in script
    assert "Stop-OldKamProcesses" in script
    assert "Get-NetTCPConnection -LocalPort $Port" in script
    assert "watch_fubon_five_timeframe_dashboard.ps1" in script
    assert "Test-KamHealth" in script
    assert "$health.market_data_only -eq $true" in script
    assert "$health.live_order_allowed -eq $false" in script
    assert "-PaperTestArmed" in script
    assert "-NoBrowser" in script
    assert "StartupTimeoutSeconds = 300" in script
    assert "'-StartupGraceSeconds', '180'" in script
    assert "Start-Process $dashboardUrl" in script
    assert "-FilePath 'taskkill.exe'" in script
    assert "-ErrorAction SilentlyContinue" in script
    assert "place_order" not in script

    watchdog = (TOOLS / "watch_fubon_five_timeframe_dashboard.ps1").read_text(
        encoding="utf-8"
    )
    assert "-FilePath 'taskkill.exe'" in watchdog
    assert "& taskkill.exe" not in watchdog
