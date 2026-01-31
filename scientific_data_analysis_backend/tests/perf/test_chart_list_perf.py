"""图表列表性能基准测试。"""
import os
import time

import pytest

from app.models.dataset import Dataset

MAX_CHARTS = 50
THRESHOLD_SECONDS = 1.5


@pytest.mark.asyncio
async def test_chart_list_perf(async_client, db_session):
    """列表接口在 50 张图表规模下应保持可用响应。"""
    if os.getenv("RUN_PERF_TESTS") != "1":
        pytest.skip("性能测试需显式启用")

    dataset = Dataset(
        name="性能测试数据集",
        description="图表列表性能测试",
        filename="perf.csv",
        file_path="uploads/perf.csv",
        file_size=1,
        file_type="csv",
    )
    db_session.add(dataset)
    await db_session.commit()

    task_resp = await async_client.post("/api/v1/tasks", json={"dataset_id": dataset.id})
    assert task_resp.status_code == 201
    task_id = task_resp.json()["data"]["id"]

    for idx in range(MAX_CHARTS):
        create_resp = await async_client.post(
            f"/api/v1/tasks/{task_id}/visualizations",
            json={"chart_type": "scatter", "config": {"title": f"性能图{idx}"}},
        )
        assert create_resp.status_code == 201

    start = time.perf_counter()
    list_resp = await async_client.get(f"/api/v1/tasks/{task_id}/visualizations")
    duration = time.perf_counter() - start

    assert list_resp.status_code == 200
    assert duration <= THRESHOLD_SECONDS
