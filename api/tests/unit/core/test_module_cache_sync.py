import importlib


def test_s3_client_disabled_when_provider_is_azure_blob(monkeypatch):
    monkeypatch.setenv("BIFROST_OBJECT_STORAGE_PROVIDER", "azure_blob")
    monkeypatch.setenv("BIFROST_S3_ACCESS_KEY", "access")
    monkeypatch.setenv("BIFROST_S3_SECRET_KEY", "secret")

    module_cache_sync = importlib.import_module("src.core.module_cache_sync")
    module_cache_sync._s3_available = None
    module_cache_sync._s3_client = None

    assert module_cache_sync._get_s3_client() is None


def test_object_storage_provider_prefers_blob_when_blob_configured(monkeypatch):
    monkeypatch.delenv("BIFROST_OBJECT_STORAGE_PROVIDER", raising=False)
    monkeypatch.setenv("BIFROST_AZURE_BLOB_ACCOUNT_URL", "https://example.blob.core.windows.net")
    monkeypatch.setenv("BIFROST_AZURE_BLOB_CONTAINER", "bifrost-objects")

    module_cache_sync = importlib.import_module("src.core.module_cache_sync")

    assert module_cache_sync._object_storage_provider() == "azure_blob"
