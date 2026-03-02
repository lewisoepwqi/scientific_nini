## ADDED Requirements

### Requirement: Report generation calls backend API
The generateReport function SHALL call the backend API endpoint instead of using setTimeout mock.

#### Scenario: Generate report via API
- **WHEN** user clicks "Generate Report" button
- **THEN** the system SHALL POST to /api/sessions/{id}/generate-report
- **AND** it SHALL display loading state during generation
- **AND** it SHALL show success/error notification on completion

### Requirement: Report download fetches from workspace
The downloadReport function SHALL fetch the report file from workspace.

#### Scenario: Download generated report
- **WHEN** user clicks "Download Report" button
- **THEN** the system SHALL GET /api/sessions/{id}/workspace/files/{path}
- **AND** it SHALL trigger browser download with correct filename
- **AND** it SHALL handle download errors gracefully
