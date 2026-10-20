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


def test_excel_reporting_avoids_mixing_measurement_units_in_summary_charts() -> None:
    html = read_page("index.html")
    assert 'Observation count by metric (not measurement magnitude)' in html
    assert 'Filtered record count by metric and unit' in html
    assert 'This chart counts records by metric and unit.' in html
    assert 'values retain their original units' not in html


def test_excel_reporting_has_full_and_section_specific_workbooks() -> None:
    html = read_page("index.html")
    assert 'addEventListener("click",()=>exportGridPulseExcel("all"))' in html
    assert 'btn.addEventListener("click",()=>exportGridPulseExcel(scope))' in html
    assert 'gridpulse-"+scope+"-report-' in html
    assert 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' in html
    assert 'No example events are fabricated.' in html


def test_operations_suite_has_full_and_section_excel_exports() -> None:
    html = read_page("docs/plant-intelligence-suite.html")
    assert "function exportSuiteExcel(scope=\"all\")" in html
    assert 'b.dataset.suiteXlsx="all"' in html
    assert 'wb.xlsx.writeBuffer()' in html
    assert 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' in html
    for section in ("assets", "work", "losses", "rca", "rnd"):
        assert f'["{section}"' in html or f'"{section}"' in html
    assert "synthetic demo examples" in html
    assert "Asset health score (screening only)" in html


def test_excel_exports_include_metadata_quality_review_sheets() -> None:
    main = read_page("index.html")
    suite = read_page("docs/plant-intelligence-suite.html")
    assert 'gpAddTableSheet(wb,"Quality Review"' in main
    assert "Source provenance" in main
    assert "These checks evaluate metadata completeness" in main
    assert 'gpSuiteSheet(wb,"Quality Review"' in suite
    assert "Synthetic demo data" in suite


def test_main_dashboard_checks_backend_readiness_and_persists_connection_url() -> None:
    html = read_page("index.html")
    assert 'localStorage.setItem("gridpulse-api-base",base)' in html
    assert 'sessionStorage.setItem("gridpulse-api-key",key)' not in html
    assert 'gpAiRequest("/ready")' in html
    assert 'gpAiRequest("/api/v1/system/diagnostics")' in html
    assert 'AbortController()' in html
    assert "Check backend health" in html
    assert "Backend unavailable" in html


def test_main_dashboard_syncs_sources_observations_and_maintenance_without_losing_local_rows() -> None:
    html = read_page("index.html")
    assert 'id="syncBackendObservations"' in html
    assert 'id="backendSyncStatus"' in html
    assert 'gpAiRequest("/api/v1/sources")' in html
    assert 'gpAiFetchAllPages("/api/v1/observations",10000)' in html
    assert 'gpAiFetchAllPages("/api/v1/maintenance/events",10000)' in html
    assert 'const readiness=await gpAiRequest("/ready")' in html
    assert 'new URL(base)' in html
    assert 'credentials:"omit",cache:"no-store"' in html
    assert "An HTTPS dashboard requires an HTTPS remote API URL." in html
    assert 'connectionStatus.className="tag green"' in html
    assert 'backend_origin:true' in html
    assert 'Caller-supplied record; source truth is not independently verified.' in html
    assert 'importedMetrics.filter(record=>!record.backend_origin)' in html
    assert 'importedMaintenance.filter(event=>!event.backend_origin)' in html
    assert 'SOURCES.splice(0,SOURCES.length,...mergedSources.values())' in html
    assert 'renderOverviewSources();renderSources();renderMetrics();renderTrend();renderAnalytics();renderMaintenance();' in html
