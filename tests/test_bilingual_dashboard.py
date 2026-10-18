"""Regression checks for bilingual static dashboard language controls.

These checks are intentionally lightweight and complement (not replace) browser-level
accessibility and interaction tests.
"""


from pathlib import Path  # noqa: I001


ROOT = Path(__file__).resolve().parents[1]


def read_page(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def test_main_dashboard_has_persistent_fa_en_switch_and_rtl_support() -> None:
    html = read_page("index.html")
    assert 'id="languageSelect"' in html
    assert 'localStorage.getItem("gridpulse-language")' in html
    assert 'localStorage.setItem("gridpulse-language"' in html
    assert 'document.documentElement.dir=chosen==="fa"?"rtl":"ltr"' in html
    assert "GRIDPULSE_I18N.fa" in html
    assert "document.querySelectorAll(\"[placeholder]\")" in html


def test_plant_intelligence_suite_has_persistent_fa_en_switch_and_rtl_support() -> None:
    html = read_page("docs/plant-intelligence-suite.html")
    assert 'id="lang"' in html
    assert 'localStorage.getItem("gridpulse-oem-language")' in html
    assert 'localStorage.setItem("gridpulse-oem-language",currentLanguage)' in html
    assert 'document.documentElement.dir=currentLanguage==="fa"?"rtl":"ltr"' in html
    assert 'document.body.classList.toggle("rtl",currentLanguage==="fa")' in html
    assert "function translateSuiteText(lang)" in html
    assert 'document.querySelectorAll("[placeholder]")' in html


def test_both_dashboards_include_persian_translations() -> None:
    main = read_page("index.html")
    suite = read_page("docs/plant-intelligence-suite.html")
    assert "داشبورد" in main
    assert "در حال انجام" in suite
    assert "گریدپالس" in main


def test_main_dashboard_has_one_click_excel_exports_and_embedded_charts() -> None:
    html = read_page("index.html")
    assert "function exportGridPulseExcel(scope=\"all\")" in html
    assert "ExcelJS" in html
    assert "wb.xlsx.writeBuffer()" in html
    assert 'extension:"png"' in html
    assert 'data-xlsx-scope' in html
    for scope in ("overview", "data", "analytics", "engineering", "maintenance", "sources"):
        assert f'"{scope}"' in html
    assert "source_id" in html
    assert "verification_status" in html
