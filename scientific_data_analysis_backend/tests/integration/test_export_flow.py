"""分享包流程集成测试。"""
import pytest

from app.models.dataset import Dataset


@pytest.mark.asyncio
async def test_export_flow(async_client, db_session):
    """分享包生成与读取流程。"""
    dataset = Dataset(
        name="测试数据导出流程",
        description="导出流程测试",
        filename="export_flow.csv",
        file_path="uploads/export_flow.csv",
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
        json={"chart_type": "scatter", "config": {"title": "导出流程图"}},
    )
    assert viz_resp.status_code == 201
    viz_id = viz_resp.json()["data"]["id"]

    export_resp = await async_client.post(f"/api/v1/visualizations/{viz_id}/exports")
    assert export_resp.status_code == 201
    export_payload = export_resp.json()["data"]
    assert export_payload.get("dataset_version_ref")
