## 1. Backend - Model Updates

- [x] 1.1 Update `WSEvent` model in `src/nini/models/schemas.py` to support message metadata
- [x] 1.2 Add `message_id` and `operation` fields to event metadata structure
- [x] 1.3 Run type checks with `mypy src/nini` to ensure type safety

## 2. Backend - Agent Runner Modifications

- [x] 2.1 Add message sequence tracking to `AgentRunner.run()` in `src/nini/agent/runner.py`
- [x] 2.2 Generate `message_id` using `{turn_id}-{sequence}` format for TEXT events
- [x] 2.3 Set `operation="append"` for normal LLM streaming chunks
- [x] 2.4 Set `operation="replace"` for tool-generated complete content (generate_report)
- [x] 2.5 Set `operation="complete"` for stream finalization
- [x] 2.6 Fix `generate_report` duplicate sending issue by using `replace` operation

## 3. Backend - Testing

- [x] 3.1 Run backend tests: `pytest tests/ -q`
- [x] 3.2 Test WebSocket events include correct `message_id` format
- [x] 3.3 Verify `operation` field is set correctly for different event types

## 4. Frontend - Type Definitions

- [x] 4.1 Update `WSEvent` type in `web/src/store/types.ts` to include new metadata fields
- [x] 4.2 Add `MessageBuffer` interface definition
- [x] 4.3 Update `AppState` to include `_messageBuffer` state

## 5. Frontend - State Management

- [x] 5.1 Add `_messageBuffer` to store state in `web/src/store.ts`
- [x] 5.2 Initialize buffer with size limit and cleanup mechanism
- [x] 5.3 Add helper functions for buffer operations (add, update, cleanup)

## 6. Frontend - Event Handler Updates

- [x] 6.1 Modify `handleEvent` in `web/src/store/event-handler.ts` to extract `message_id` and `operation`
- [x] 6.2 Implement logic for `operation="append"` - accumulate to buffer
- [x] 6.3 Implement logic for `operation="replace"` - replace entire content
- [x] 6.4 Implement logic for `operation="complete"` - finalize and cleanup
- [x] 6.5 Add backward compatibility: handle events without `message_id` using legacy logic
- [x] 6.6 Add deduplication: check `message_id` before processing

## 7. Frontend - Build and Type Check

- [x] 7.1 Run type check: `cd web && npm run build`
- [x] 7.2 Fix any TypeScript errors
- [x] 7.3 Verify no build warnings

## 8. Integration Testing

- [x] 8.1 Test normal conversation flow (no duplicates)
- [x] 8.2 Test `generate_report` scenario - verify no duplicate report content
- [x] 8.3 Test page refresh - verify messages display correctly after reload
- [x] 8.4 Test backward compatibility - verify old code path still works
- [x] 8.5 Test multiple tool calls in single turn - verify message IDs are unique

## 9. Documentation

- [x] 9.1 Update API documentation with new WebSocket event fields
- [x] 9.2 Add code comments explaining message deduplication logic
- [x] 9.3 Update CHANGELOG.md with the fix description

## 10. Bug Fixes (Follow-up)

- [x] 10.1 Fix message duplication in same bubble when multiple messages have different message_ids in same turn
  - Problem: In `event-handler.ts` line 447-460, when `messageId` exists but no matching message found, code incorrectly updates the last assistant message with same `turnId` instead of creating a new message
  - Fix: Always create new message when `messageId` is provided but no existing match found
- [x] 10.2 Verify frontend build passes after fix
- [x] 10.3 Run full test suite to ensure no regressions
