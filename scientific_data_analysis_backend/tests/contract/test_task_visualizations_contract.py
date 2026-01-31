"""任务状态与图表契约测试。"""
import pytest

from app.models.dataset import Dataset


@pytest.mark.asyncio
async def test_task_status_contract(async_client, db_session):
    """任务状态查询契约校验。"""
    dataset = Dataset(
        name="测试数据状态",
        description="状态测试数据集",
        filename="status.csv",
        file_path="uploads/status.csv",
        file_size=1,
        file_type="csv",
    )
    db_session.add(dataset)
    await db_session.commit()

    create_resp = await async_client.post("/api/v1/tasks", json={"dataset_id": dataset.id})
    assert create_resp.status_code == 201
    task_id = create_resp.json()["data"]["id"]

    status_resp = await async_client.get(f"/api/v1/tasks/{task_id}/status")
    assert status_resp.status_code == 200
    payload = status_resp.json()
    assert payload.get("success") is True
    assert payload.get("data")
    assert payload["data"].get("stage")


@pytest.mark.asyncio
async def test_task_visualization_contract(async_client, db_session):
    """任务图表创建与列表契约校验。"""
    dataset = Dataset(
        name="测试数据图表",
        description="图表测试数据集",
        filename="chart.csv",
        file_path="uploads/chart.csv",
        file_size=1,
        file_type="csv",
    )
    db_session.add(dataset)
    await db_session.commit()

    create_resp = await async_client.post("/api/v1/tasks", json={"dataset_id": dataset.id})
    assert create_resp.status_code == 201
    task_id = create_resp.json()["data"]["id"]

    create_chart = await async_client.post(
        f"/api/v1/tasks/{task_id}/visualizations",
        json={"chart_type": "scatter", "config": {"title": "示例图"}},
    )
    assert create_chart.status_code == 201

    list_resp = await async_client.get(f"/api/v1/tasks/{task_id}/visualizations")
    assert list_resp.status_code == 200
    payload = list_resp.json()
    assert payload.get("success") is True
    assert isinstance(payload.get("data"), list)
