"""任务相关契约测试。"""
import pytest

from app.models.dataset import Dataset


@pytest.mark.asyncio
async def test_create_and_get_task_contract(async_client, db_session):
    """创建任务并读取任务详情的契约校验。"""
    dataset = Dataset(
        name="测试数据",
        description="契约测试数据集",
        filename="test.csv",
        file_path="uploads/test.csv",
        file_size=1,
        file_type="csv",
    )
    db_session.add(dataset)
    await db_session.commit()

    response = await async_client.post("/api/v1/tasks", json={"dataset_id": dataset.id})
    assert response.status_code == 201
    payload = response.json()
    assert payload.get("success") is True
    assert payload.get("data")
    task_id = payload["data"].get("id")
    assert task_id

    detail = await async_client.get(f"/api/v1/tasks/{task_id}")
    assert detail.status_code == 200
    detail_payload = detail.json()
    assert detail_payload.get("success") is True
    assert detail_payload.get("data")


@pytest.mark.asyncio
async def test_list_tasks_contract(async_client, db_session):
    """任务列表契约校验。"""
    dataset = Dataset(
        name="测试数据2",
        description="列表测试数据集",
        filename="test2.csv",
        file_path="uploads/test2.csv",
        file_size=1,
        file_type="csv",
    )
    db_session.add(dataset)
    await db_session.commit()

    create_resp = await async_client.post("/api/v1/tasks", json={"dataset_id": dataset.id})
    assert create_resp.status_code == 201

    list_resp = await async_client.get("/api/v1/tasks", params={"limit": 10, "offset": 0})
    assert list_resp.status_code == 200
    payload = list_resp.json()
    assert payload.get("success") is True
    assert isinstance(payload.get("data"), list)
