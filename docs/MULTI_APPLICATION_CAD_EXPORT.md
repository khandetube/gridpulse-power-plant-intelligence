# GridPulse multi-application CAD export

The API endpoint `POST /api/v1/cad/export-bundle` accepts a validated `EngineeringSpec` JSON body and returns synchronized exports derived from the same model.

## Formats

- `autocad_model.dxf`: editable DXF R12 geometry with an explicit layer table, millimetre coordinates, site boundary, equipment footprints and route centerlines. It is a conceptual plan export, not a full native DWG.
- `3dsmax_generator.ms`: MaxScript source to run inside 3ds Max. It creates editable box-envelope equipment and cylindrical route segments. It does not generate manufacturer-level meshes.
- `revit_dynamo_generator.py`: Python source for a Dynamo Python node inside an open Revit project. It creates conceptual DirectShape bounding solids. It does not generate a native RVT file outside Revit and does not yet create native Revit Pipe/Conduit MEP systems.
- `engineering_spec.json`: canonical shared model used by all exporters.
- `gridpulse_engineering_handoff.xlsx`: real multi-sheet Excel workbook available from `POST /api/v1/cad/export/xlsx`; includes project summary, equipment register, route register, route-point coordinates, design-check findings and design basis.
- In the static browser CAD studio, the **Excel multi-sheet report** button downloads Excel-compatible SpreadsheetML XML (open it with Excel). This browser-side export works without the Python API.

## Important operational distinction

The bundle generation is performed by the GridPulse Python API. Actual native application geometry is created only when the corresponding script is run in an installed compatible application. AutoCAD DXF is the only direct CAD interchange file in this bundle; 3ds Max and Revit receive scripts, not ready-made `.max` or `.rvt` project files.

The current engine generates conceptual parametric envelopes and schematic routes. It is not suitable for construction, procurement, safety certification or plant operation without discipline-specific calculations, validated families/blocks, connection logic, clash review and qualified engineer approval.

## Example

1. Generate a model through `POST /api/v1/cad/generate` or create a valid `EngineeringSpec`.
2. Submit the returned `spec` object as JSON to `POST /api/v1/cad/export-bundle`.
3. For a native `.xlsx` file, submit the same `spec` JSON body to `POST /api/v1/cad/export/xlsx` and save the binary response.
3. Save each value in the `exports` object under the matching filename.
4. Open the DXF in AutoCAD; run the MaxScript inside 3ds Max; run the Revit script in a Dynamo Python node inside Revit.
5. Review warnings and validate geometry in each application before relying on any output.

API authentication follows the existing `GRIDPULSE_API_KEY` policy. The GitHub Pages website is static and does not itself host this Python API.
