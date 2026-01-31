"""AI 建议流程集成测试。"""
import pytest

from app.models.dataset import Dataset


@pytest.mark.asyncio
async def test_suggestion_flow(async_client, db_session):
    """建议生成与采纳流程。"""
    dataset = Dataset(
        name="测试数据建议流程",
        description="建议流程测试",
        filename="suggest_flow.csv",
        file_path="uploads/suggest_flow.csv",
        file_size=1,
        file_type="csv",
    )
    db_session.add(dataset)
    await db_session.commit()

    task_resp = await async_client.post("/api/v1/tasks", json={"dataset_id": dataset.id})
    assert task_resp.status_code == 201
    task_id = task_resp.json()["data"]["id"]

    suggestion_resp = await async_client.post(f"/api/v1/tasks/{task_id}/suggestions")
    assert suggestion_resp.status_code == 201

    accept_resp = await async_client.post(f"/api/v1/tasks/{task_id}/suggestions/accept")
    assert accept_resp.status_code == 200
