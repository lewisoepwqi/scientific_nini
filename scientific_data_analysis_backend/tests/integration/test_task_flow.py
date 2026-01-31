"""任务与多图表流程集成测试。"""
import pytest

from app.models.dataset import Dataset


@pytest.mark.asyncio
async def test_task_multi_chart_flow(async_client, db_session):
    """任务下多图表创建与列表流程。"""
    dataset = Dataset(
        name="测试数据流程",
        description="流程测试数据集",
        filename="flow.csv",
        file_path="uploads/flow.csv",
        file_size=1,
        file_type="csv",
    )
    db_session.add(dataset)
    await db_session.commit()

    task_resp = await async_client.post("/api/v1/tasks", json={"dataset_id": dataset.id})
    assert task_resp.status_code == 201
    task_id = task_resp.json()["data"]["id"]

    for idx in range(2):
        chart_resp = await async_client.post(
            f"/api/v1/tasks/{task_id}/visualizations",
            json={"chart_type": "scatter", "config": {"title": f"图表{idx}"}},
        )
        assert chart_resp.status_code == 201

    list_resp = await async_client.get(f"/api/v1/tasks/{task_id}/visualizations")
    assert list_resp.status_code == 200
    payload = list_resp.json()
    assert payload.get("success") is True
    assert len(payload.get("data", [])) >= 2
