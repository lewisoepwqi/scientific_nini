"""Phase 2C：端到端与错误路径测试。"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from nini.agent.model_resolver import model_resolver
from nini.agent.session import session_manager
from nini.app import create_app
from nini.config import settings
from nini.skills.registry import create_default_registry
from tests.client_utils import LocalASGIClient, live_websocket_connect


@pytest.fixture
def app_with_temp_data(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """使用临时目录隔离测试数据。"""
    monkeypatch.setattr(settings, "data_dir", tmp_path / "data")
    session_manager._sessions.clear()
    return create_app()


def test_phase2c_upload_ttest_chart_pipeline(app_with_temp_data):
    """端到端回归：上传数据 -> t 检验 -> 生成图表。"""
    registry = create_default_registry()

    with LocalASGIClient(app_with_temp_data) as client:
        # 1) 创建会话
        create_resp = client.post("/api/sessions")
        assert create_resp.status_code == 200
        session_id = create_resp.json()["data"]["session_id"]

        # 2) 上传数据
        csv_content = (
            "group,value,day\n"
            "control,1.1,1\n"
            "control,1.3,2\n"
            "treatment,2.0,1\n"
            "treatment,2.2,2\n"
        )
        upload_resp = client.post(
            "/api/upload",
            data={"session_id": session_id},
            files={"file": ("experiment.csv", csv_content, "text/csv")},
        )
        assert upload_resp.status_code == 200
        assert upload_resp.json()["success"] is True

        # 3) 执行 t 检验
        session = session_manager.get_session(session_id)
        assert session is not None
        t_test_result = asyncio.run(
            registry.execute(
                "t_test",
                session=session,
                dataset_name="experiment.csv",
                value_column="value",
                group_column="group",
            )
        )
        assert t_test_result["success"] is True
        assert t_test_result["data"]["test_type"] == "独立样本 t 检验"
        assert isinstance(t_test_result["data"]["p_value"], float)

        # 4) 生成 Nature 风格箱线图
        chart_result = asyncio.run(
            registry.execute(
                "create_chart",
                session=session,
                dataset_name="experiment.csv",
                chart_type="box",
                y_column="value",
                group_column="group",
                journal_style="nature",
                title="Treatment vs Control",
            )
        )
        assert chart_result["success"] is True
        assert chart_result["has_chart"] is True
        assert "data" in chart_result["chart_data"]
        assert "layout" in chart_result["chart_data"]


def test_phase2c_upload_with_missing_session_returns_404(app_with_temp_data):
    """错误路径：会话不存在时上传返回 404。"""
    with LocalASGIClient(app_with_temp_data) as client:
        resp = client.post(
            "/api/upload",
            data={"session_id": "missing-session"},
            files={"file": ("x.csv", "a,b\n1,2\n", "text/csv")},
        )
        assert resp.status_code == 404
        assert resp.json()["detail"] == "会话不存在"


def test_phase2c_upload_unsupported_extension_returns_400(app_with_temp_data):
    """错误路径：不支持的文件类型返回 400。"""
    with LocalASGIClient(app_with_temp_data) as client:
        create_resp = client.post("/api/sessions")
        session_id = create_resp.json()["data"]["session_id"]

        resp = client.post(
            "/api/upload",
            data={"session_id": session_id},
            files={"file": ("bad.exe", "not-a-dataset", "application/octet-stream")},
        )
        assert resp.status_code == 400
        assert "不支持的文件类型" in resp.json()["detail"]


def test_phase2c_upload_xls_missing_xlrd_returns_friendly_error(
    app_with_temp_data,
    monkeypatch: pytest.MonkeyPatch,
):
    """错误路径：上传 .xls 且缺少 xlrd 时，返回可执行安装提示。"""

    def fake_read_dataframe(*args, **kwargs):
        raise ValueError(
            '解析 .xls 失败：缺少 xlrd 依赖（>=2.0.1）。请执行 `pip install "xlrd>=2.0.1"` 后重试。'
        )

    monkeypatch.setattr("nini.api.routes.read_dataframe", fake_read_dataframe)

    with LocalASGIClient(app_with_temp_data) as client:
        create_resp = client.post("/api/sessions")
        session_id = create_resp.json()["data"]["session_id"]

        resp = client.post(
            "/api/upload",
            data={"session_id": session_id},
            files={"file": ("legacy.xls", b"fake-xls", "application/vnd.ms-excel")},
        )
        assert resp.status_code == 400
        detail = resp.json()["detail"]
        assert "xlrd" in detail
        assert "pip install" in detail


def test_phase2c_websocket_empty_message_returns_error(
    app_with_temp_data,
):
    """错误路径：WebSocket 空消息返回错误事件。"""
    with live_websocket_connect(app_with_temp_data, "/ws") as ws:
        ws.send_text(json.dumps({"type": "chat", "content": "   "}))
        event = ws.receive_json()
        assert event["type"] == "error"
        assert event["data"] == "消息内容不能为空"


def test_phase2c_websocket_model_unavailable_returns_error(
    app_with_temp_data,
    monkeypatch: pytest.MonkeyPatch,
):
    """错误路径：模型不可用时返回 error 事件。"""

    async def fake_chat(*args, **kwargs):
        raise RuntimeError("没有可用的 LLM 客户端")
        yield  # pragma: no cover

    monkeypatch.setattr(model_resolver, "chat", fake_chat)

    with live_websocket_connect(app_with_temp_data, "/ws") as ws:
        ws.send_text(json.dumps({"type": "chat", "content": "你好"}))
        session_event = ws.receive_json()

        assert session_event["type"] == "session"
        assert "session_id" in session_event["data"]

        # iteration_start 事件在每次迭代开始时发送
        iter_event = ws.receive_json()
        assert iter_event["type"] == "iteration_start"

        error_event = ws.receive_json()
        assert error_event["type"] == "error"
        assert "没有可用的 LLM 客户端" in error_event["data"]
