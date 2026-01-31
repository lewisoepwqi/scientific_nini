"""AI 建议契约测试。"""
import pytest

from app.models.dataset import Dataset


@pytest.mark.asyncio
async def test_suggestion_contract(async_client, db_session):
    """建议生成与采纳契约校验。"""
    dataset = Dataset(
        name="测试数据建议",
        description="建议测试数据集",
        filename="suggest.csv",
        file_path="uploads/suggest.csv",
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

    reject_resp = await async_client.post(f"/api/v1/tasks/{task_id}/suggestions/reject")
    assert reject_resp.status_code == 200
