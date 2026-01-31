"""分享包内容校验。"""
import pytest

from app.models.dataset import Dataset


@pytest.mark.asyncio
async def test_export_excludes_raw_data(async_client, db_session):
    """分享包不应包含原始数据内容。"""
    dataset = Dataset(
        name="测试数据内容",
        description="导出内容测试",
        filename="export_content.csv",
        file_path="uploads/export_content.csv",
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
        json={"chart_type": "scatter", "config": {"title": "导出内容图"}},
    )
    assert viz_resp.status_code == 201
    viz_id = viz_resp.json()["data"]["id"]

    export_resp = await async_client.post(f"/api/v1/visualizations/{viz_id}/exports")
    assert export_resp.status_code == 201
    payload = export_resp.json()["data"]
    assert "raw_data" not in payload
    assert "dataset_content" not in payload
