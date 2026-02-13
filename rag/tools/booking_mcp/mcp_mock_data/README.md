# PHKL MCP Mock Data (for doctor_finder.py and sp_appointment.py)

This folder contains JSON fixtures required by the MCP tools you created.

## Used directly by tools
- `districts.json` → `doctorFinder_listDistricts`
- `specialties.json` → `doctorFinder_listSpecialties`, `sp_validateAppointmentDraft`
- `providers.json` → `doctorFinder_searchProviders`, `doctorFinder_getDoctorDetails`
- `doctors.json` → `doctorFinder_search`, `doctorFinder_getDoctorDetails`
- `policies.json` → `sp_listLifeAssured`, `sp_checkEligibility`, `sp_validateAppointmentDraft`
- `appointment_confirmations.json` → `sp_getAppointmentConfirmation`, message composition tools

## Reference / examples
- `slot_windows_reference.json` → for visibility of fixed time windows
- `examples_doctor_finder_tool_calls.json` → example inputs you can feed into `call_tool`
- `examples_sp_tool_calls.json` → example inputs for SP tools

## Environment variable
Set this to point your MCP server to the folder:

```bash
export PHKL_MCP_DATA_DIR=/mnt/data/phkl_mcp_mock_data
```

Or place this folder as `./mcp_mock_data` next to your server entrypoint.
