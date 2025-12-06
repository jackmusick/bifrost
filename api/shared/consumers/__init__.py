# RabbitMQ message consumers
# Note: WorkflowExecutionConsumer lives in src/jobs/consumers/workflow_execution.py
from shared.consumers.git_sync import GitSyncConsumer
from shared.consumers.package_install import PackageInstallConsumer

__all__ = [
    "GitSyncConsumer",
    "PackageInstallConsumer",
]
