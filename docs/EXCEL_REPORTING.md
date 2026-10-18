# GridPulse AI — Smart Excel Reporting

## One-click exports

The dashboard offers a full workbook from the top-bar **Full Excel report** button and section-specific **Excel + charts** buttons in Overview, Data explorer, Analytics lab, Engineering calculator, Maintenance, and Source registry.

- **Full workbook:** Executive Summary, Observations, Analytics, Engineering, Maintenance, and Sources worksheets.
- **Section export:** exports the selected section only.
- **Charts:** charts are embedded PNG images inside the workbook, generated from the current browser data. They are snapshots, not native editable Excel chart objects.
- **Data completeness:** observation and maintenance sheets retain the full exported row set, source identifiers, units, reporting periods, scope, and verification labels where supplied. Analytics follows the dashboard's current filters. The chart may be visually dense for large datasets; the worksheet rows remain the detailed record.
- **Formatting:** header styling, frozen headers, autofilters, wrapped cells, alternating row shading, and worksheet-level metadata/limitations are included.
- **Local privacy:** data is assembled in the browser and is not uploaded to GridPulse servers. The first export loads ExcelJS from jsDelivr; internet access is required for that initial library load.
- **No invented limits:** the export does not manufacture engineering limits, missing measurements, verified statuses, maintenance events, or live telemetry.

## Important limitations

This is a research prototype. The workbook contains only built-in research leads and records currently imported into the browser. It is not evidence of live connection to a power plant, SCADA/DCS/EMS or dispatch center. Built-in values may be unverified and must retain their status labels. Engineering calculator results are based on user-entered inputs and do not constitute operating instructions, protection settings, or return-to-service authorization.

For repeatable operational reporting, save the authorized source files and retain the generated workbook with the source dataset, reporting interval, units, reviewer, and validation record.
