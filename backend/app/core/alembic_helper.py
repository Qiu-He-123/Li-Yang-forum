"""Alembic 迁移辅助工具。

T3-1：使用应用已有的 engine 执行 alembic upgrade head，
避免 alembic command.upgrade 创建独立 engine（in-memory SQLite 会拿到不同 DB）。
"""
from pathlib import Path
from typing import Optional

from alembic.config import Config as AlembicConfig
from alembic.environment import EnvironmentContext
from alembic.script import ScriptDirectory
from loguru import logger
from sqlalchemy import Engine, inspect


def _build_alembic_config(database_url: Optional[str] = None) -> AlembicConfig:
    """构造 AlembicConfig，自动定位 backend/alembic.ini。"""
    # backend/alembic.ini 相对当前文件路径：app/core/_alembic_helper.py -> parents[2]
    ini_path = Path(__file__).resolve().parents[2] / "alembic.ini"
    cfg = AlembicConfig(str(ini_path))
    if database_url:
        cfg.set_main_option("sqlalchemy.url", database_url)
    return cfg


def _run_migrations_with_engine(engine: Engine, target_revision: str = "head") -> None:
    """用应用 engine 的连接执行 alembic 迁移到 target_revision。

    核心：复用 engine 的同一连接，避免 in-memory SQLite 拿到不同 DB。
    必须用 EnvironmentContext.configure() 而非 MigrationContext.configure()，
    否则 op 全局代理不会建立，迁移文件中的 op.add_column / op.batch_alter_table 会报
    "proxy object has not yet been established for the Alembic 'Operations' class"。
    """
    cfg = _build_alembic_config()
    script = ScriptDirectory.from_config(cfg)

    with engine.begin() as conn:
        # 是否 SQLite？需要 batch 模式
        is_sqlite = conn.dialect.name == "sqlite"

        def _do_upgrade(rev, context):
            return script._upgrade_revs(target_revision, rev)

        # EnvironmentContext.configure() 会正确建立 op 全局代理
        env_ctx = EnvironmentContext(cfg, script)
        env_ctx.configure(
            connection=conn,
            fn=_do_upgrade,
            target_metadata=None,  # upgrade 不需要 target_metadata
            render_as_batch=is_sqlite,
        )
        with env_ctx.begin_transaction():
            env_ctx.run_migrations()


def ensure_schema(engine: Engine, database_url: str, env: str = "dev") -> None:
    """确保数据库 schema 最新。

    优先用 alembic upgrade head；失败时（如 in-memory SQLite 且无迁移历史）
    退化为 Base.metadata.create_all 兜底（仅 dev）。
    """
    # 检查数据库是否已有任何表（判断是空库还是已有 schema）
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())

    if not existing_tables or "alembic_version" not in existing_tables:
        # 空库或无 alembic 版本表：尝试 alembic upgrade head
        try:
            _run_migrations_with_engine(engine, "head")
            logger.info("[ALEMBIC] upgrade head 完成（env={}）", env)
            return
        except Exception as exc:
            logger.warning("[ALEMBIC] upgrade head 失败：{}", exc)
            if env != "dev":
                raise RuntimeError(
                    "[FATAL] 生产环境 alembic 迁移失败，请检查迁移文件。"
                    f"错误：{exc}"
                ) from exc
            # dev 环境兜底：用 Base.metadata.create_all
            logger.warning("[ALEMBIC] dev 兜底使用 Base.metadata.create_all 创建 schema")
            # 延迟导入避免循环依赖
            from app.core.database import Base
            import app.models  # noqa: F401  保证模型注册
            Base.metadata.create_all(bind=engine)
            # 标记为 head 避免下次重复迁移
            try:
                _stamp_head(engine)
            except Exception as stamp_exc:
                logger.warning("[ALEMBIC] stamp head 失败：{}", stamp_exc)
    else:
        # 已有 alembic_version 表：执行 upgrade
        try:
            _run_migrations_with_engine(engine, "head")
            logger.info("[ALEMBIC] upgrade head 完成（已有版本表）")
        except Exception as exc:
            logger.warning("[ALEMBIC] upgrade head 失败：{}", exc)
            if env != "dev":
                raise RuntimeError(
                    "[FATAL] 生产环境 alembic 迁移失败，请检查迁移文件。"
                    f"错误：{exc}"
                ) from exc


def _stamp_head(engine: Engine) -> None:
    """标记当前 schema 为 head（不执行迁移，仅写 alembic_version 表）。"""
    cfg = _build_alembic_config()
    script = ScriptDirectory.from_config(cfg)
    head_rev = script.get_current_head()

    with engine.begin() as conn:
        # 确保 alembic_version 表存在
        conn.exec_driver_sql(
            "CREATE TABLE IF NOT EXISTS alembic_version (version_num VARCHAR(32) NOT NULL, "
            "CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num))"
        )
        # 清空并写入 head（用参数化查询避免 B608 误报 SQL 注入）
        conn.exec_driver_sql("DELETE FROM alembic_version")
        conn.exec_driver_sql("INSERT INTO alembic_version (version_num) VALUES (?)", (head_rev,))
