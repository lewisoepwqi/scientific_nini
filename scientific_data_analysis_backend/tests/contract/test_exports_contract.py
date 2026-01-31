"""分享包契约测试。"""
import pytest

from app.models.dataset import Dataset


@pytest.mark.asyncio
async def test_export_contract(async_client, db_session):
    """分享包创建与读取契约。"""
    dataset = Dataset(
        name="测试数据导出",
        description="导出测试",
        filename="export.csv",
        file_path="uploads/export.csv",
        file_size=1,
        file_type="csv",
    )
    db_session.add(dataset)
    await db_session.commit()

    task_resp = await async_client.post("/api/v1/tasks", json={"dataset_id": dataset.id})
    assert task_resp.status_code == 201
    task_id = task_resp.json()["data"]["id"]

    viz_resp = await async_client.post(
        f"/api/v1/tasks/{task_id}/visualizations",
        json={"chart_type": "scatter", "config": {"title": "导出图"}},
    )
    assert viz_resp.status_code == 201
    viz_id = viz_resp.json()["data"]["id"]

    export_resp = await async_client.post(f"/api/v1/visualizations/{viz_id}/exports")
    assert export_resp.status_code == 201
    export_id = export_resp.json()["data"]["id"]

    get_resp = await async_client.get(f"/api/v1/exports/{export_id}")
    assert get_resp.status_code == 200
