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
