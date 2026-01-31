"""图表配置复用契约测试。"""
import pytest

from app.models.dataset import Dataset


@pytest.mark.asyncio
async def test_chart_config_clone_contract(async_client, db_session):
    """图表配置复用/克隆契约校验。"""
    dataset = Dataset(
        name="测试数据配置",
        description="配置测试数据集",
        filename="config.csv",
        file_path="uploads/config.csv",
        file_size=1,
        file_type="csv",
    )
    db_session.add(dataset)
    await db_session.commit()

    task_resp = await async_client.post("/api/v1/tasks", json={"dataset_id": dataset.id})
    assert task_resp.status_code == 201
    task_id = task_resp.json()["data"]["id"]

    chart_resp = await async_client.post(
        f"/api/v1/tasks/{task_id}/visualizations",
        json={"chart_type": "scatter", "config": {"title": "可复用图"}},
    )
    assert chart_resp.status_code == 201
    chart_payload = chart_resp.json()
    config_id = chart_payload.get("data", {}).get("config_id")
    assert config_id

    clone_resp = await async_client.post(f"/api/v1/chart-configs/{config_id}/clone")
    assert clone_resp.status_code == 201
    clone_payload = clone_resp.json()
    assert clone_payload.get("success") is True
    assert clone_payload.get("data")
