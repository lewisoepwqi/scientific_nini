# Capability: Tool Exception Hierarchy

## Purpose

Define a structured tool exception model so the runtime can distinguish user input errors, retryable timeouts, and system failures.

## Requirements

### Requirement: Tool layer uses structured exception hierarchy
The system SHALL define `ToolInputError`, `ToolTimeoutError`, and `ToolSystemError` under a shared `ToolError` base class, and tool execution paths SHALL use these exceptions instead of broad `except Exception` handling where classification is required.

#### Scenario: Input errors return user-friendly failures
- **WHEN** a tool receives invalid user input such as a missing dataset or invalid column name
- **THEN** the tool SHALL raise `ToolInputError`
- **AND** the error message SHALL be understandable to end users

#### Scenario: Timeout errors are marked retryable
- **WHEN** tool execution times out
- **THEN** the tool SHALL raise `ToolTimeoutError`
- **AND** the runtime SHALL mark the resulting failure as retryable

#### Scenario: System failures produce alertable errors
- **WHEN** a tool encounters a system-level failure such as missing dependencies or memory exhaustion
- **THEN** the tool SHALL raise `ToolSystemError`
- **AND** the runtime SHALL log the failure at error level with traceback information

#### Scenario: Unknown exceptions are handled defensively
- **WHEN** a tool raises an uncategorized exception
- **THEN** the runtime SHALL treat it as a system failure
- **AND** the failure SHALL be logged for investigation

### Requirement: Function tool registry dispatches exceptions by type
`FunctionToolRegistryOps.execute()` SHALL map structured tool exceptions to distinct log levels and response payloads.

#### Scenario: ToolInputError logs at info level
- **WHEN** tool execution raises `ToolInputError`
- **THEN** the registry SHALL return a failure result with the tool message
- **AND** it SHALL log at info level rather than error level

#### Scenario: ToolTimeoutError logs at warning level
- **WHEN** tool execution raises `ToolTimeoutError`
- **THEN** the registry SHALL return a failure result
- **AND** the result SHALL include `retryable: true`
- **AND** the registry SHALL log at warning level

#### Scenario: ToolSystemError logs at error level
- **WHEN** tool execution raises `ToolSystemError`
- **THEN** the registry SHALL return a failure result
- **AND** the registry SHALL log at error level with traceback information

### Requirement: Model resolver distinguishes retryable and permanent provider failures
`ModelResolver` SHALL distinguish retryable provider errors from permanent authentication or request errors so fallback behavior is predictable.

#### Scenario: Rate limit errors trigger fallback
- **WHEN** a provider returns a 429 rate limit error
- **THEN** the resolver SHALL log a warning
- **AND** it SHALL attempt the next available provider in the fallback chain

#### Scenario: Authentication errors stop fallback
- **WHEN** a provider returns 401 or 403 authentication-related failures
- **THEN** the resolver SHALL return a user-friendly authentication error
- **AND** it SHALL stop fallback for that request
