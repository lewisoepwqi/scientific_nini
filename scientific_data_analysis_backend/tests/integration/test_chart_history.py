"""图表历史视图集成测试。"""
import pytest

from app.models.dataset import Dataset


@pytest.mark.asyncio
async def test_chart_history_contains_config(async_client, db_session):
    """历史视图需包含配置版本与渲染记录字段。"""
    dataset = Dataset(
        name="测试数据历史",
        description="历史测试数据集",
        filename="history.csv",
        file_path="uploads/history.csv",
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
        json={"chart_type": "scatter", "config": {"title": "历史图"}},
    )
    assert chart_resp.status_code == 201

    list_resp = await async_client.get(f"/api/v1/tasks/{task_id}/visualizations")
    assert list_resp.status_code == 200
    payload = list_resp.json()
    assert payload.get("success") is True
    items = payload.get("data", [])
    assert items
    assert "config_id" in items[0]
    assert "render_log" in items[0]
