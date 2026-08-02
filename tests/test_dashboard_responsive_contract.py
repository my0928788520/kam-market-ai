from pathlib import Path


def test_css_contains_required_responsive_and_accessibility_contracts():
    css = (Path(__file__).parents[1] / "src" / "kam_market_ai" / "dashboard" / "static" / "dashboard.css").read_text(encoding="utf-8")
    assert "@media (max-width: 1023px)" in css
    assert "@media (max-width: 480px)" in css
    assert "prefers-reduced-motion" in css
    assert ".skip-link:focus" in css and ".decision-grid" in css
