"""AI 建议端到端测试。"""
import pytest

from app.models.dataset import Dataset


@pytest.mark.asyncio
async def test_suggestion_state_transitions(async_client, db_session):
    """建议状态流转端到端校验。"""
    dataset = Dataset(
        name="测试数据建议状态",
        description="建议状态测试",
        filename="suggest_state.csv",
        file_path="uploads/suggest_state.csv",
        file_size=1,
        file_type="csv",
    )
    db_session.add(dataset)
    await db_session.commit()

    task_resp = await async_client.post("/api/v1/tasks", json={"dataset_id": dataset.id})
    assert task_resp.status_code == 201
    task_id = task_resp.json()["data"]["id"]

    create_resp = await async_client.post(f"/api/v1/tasks/{task_id}/suggestions")
    assert create_resp.status_code == 201

    reject_resp = await async_client.post(f"/api/v1/tasks/{task_id}/suggestions/reject")
    assert reject_resp.status_code == 200
