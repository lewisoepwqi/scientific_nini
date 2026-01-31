"""任务阶段端到端测试。"""
import pytest

from app.models.dataset import Dataset


@pytest.mark.asyncio
async def test_task_stage_initial(async_client, db_session):
    """创建任务后应返回合法阶段。"""
    dataset = Dataset(
        name="测试数据阶段",
        description="阶段测试数据集",
        filename="stage.csv",
        file_path="uploads/stage.csv",
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
    stage = status_resp.json()["data"]["stage"]
    assert stage in {
        "uploading",
        "parsed",
        "profiling",
        "suggestion_pending",
        "processing",
        "analysis_ready",
        "visualization_ready",
    }
