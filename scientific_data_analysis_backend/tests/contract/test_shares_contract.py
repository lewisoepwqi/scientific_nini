"""任务分享契约测试。"""
import pytest

from app.models.dataset import Dataset


@pytest.mark.asyncio
async def test_share_contract(async_client, db_session):
    """任务分享创建契约。"""
    dataset = Dataset(
        name="测试数据分享",
        description="分享测试",
        filename="share.csv",
        file_path="uploads/share.csv",
        file_size=1,
        file_type="csv",
    )
    db_session.add(dataset)
    await db_session.commit()

    task_resp = await async_client.post("/api/v1/tasks", json={"dataset_id": dataset.id})
    assert task_resp.status_code == 201
    task_id = task_resp.json()["data"]["id"]

    share_resp = await async_client.post(
        f"/api/v1/tasks/{task_id}/shares",
        json={"member_id": "member-1", "permission": "view"},
    )
    assert share_resp.status_code == 201
