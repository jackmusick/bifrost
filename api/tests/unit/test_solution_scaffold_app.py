"""`bifrost solution scaffold-app` writes a working standalone_v2 skeleton with
the CLI-login dev loop wired in — no token pasting (Codex R4 DX)."""
from __future__ import annotations

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

import yaml  # noqa: E402
from click.testing import CliRunner  # noqa: E402

from bifrost.commands.solution import _v2_scaffold_files, solution_group  # noqa: E402


def _init_workspace(root: pathlib.Path) -> None:
    (root / "bifrost.solution.yaml").write_text("slug: s\nname: S\nscope: org\n")


def test_scaffold_files_shape_and_dev_wiring() -> None:
    files = _v2_scaffold_files("my-app", "https://inst.example")

    # All the files a normal Vite app needs.
    for f in ("package.json", "vite.config.ts", "index.html", "src/main.tsx",
              "src/App.tsx", ".env.example", "README.md"):
        assert f in files, f"{f} not scaffolded"

    pkg = json.loads(files["package.json"])
    assert pkg["name"] == "my-app"
    # `bifrost` resolves FROM THE INSTANCE (no public npm, no pasting).
    assert pkg["dependencies"]["bifrost"] == "https://inst.example/api/sdk/download"
    assert "react" in pkg["dependencies"]
    assert "lucide-react" in pkg["dependencies"]
    assert pkg["scripts"]["dev"] == "vite"

    # vite.config reads the CLI's own token (env OR the nearest .env up the
    # tree), so `npm run dev` authenticates with NO token pasting.
    vc = files["vite.config.ts"]
    assert "BIFROST_ACCESS_TOKEN" in vc
    assert "VITE_BIFROST_TOKEN" in vc
    assert "process.env.BIFROST_ACCESS_TOKEN" in vc  # env first
    assert "dirname" in vc  # walks up to find the .env
    # R7-P2-f: device-code login stores the token in the keyring / credentials.json
    # (not a .env), so the config must fall back to the CLI credential store via
    # `bifrost auth token` — otherwise the normal login path starts dev tokenless.
    assert "auth" in vc and "token" in vc
    assert "execFileSync" in vc
    # SECURITY (Codex R6-P1-c): the token is injected ONLY for `vite` serve
    # (dev), never for `vite build` — baking it into the production bundle would
    # leak a usable credential to every app user. The config must gate `define`
    # on the build command.
    assert 'command === "serve"' in vc

    # The README must NOT tell the developer to paste a token.
    assert "paste" not in files["README.md"].lower()

    # main.tsx follows the runtime contract: reads window.__BIFROST_APP__,
    # createRoot, registers unmount, falls back to the dev env.
    main = files["src/main.tsx"]
    assert "window.__BIFROST_APP__" in main
    assert "createRoot" in main
    assert "registerUnmount" in main
    assert "VITE_BIFROST_TOKEN" in main
    assert "BrowserRouter basename" in main
    # Codex #9: prefer the per-mount registry keyed by THIS entry's `m` nonce so
    # a fast app→app navigation can't make our still-loading entry read another
    # app's bootstrap. Reads the nonce from import.meta.url + the registry.
    assert "__BIFROST_APPS__" in main
    assert "import.meta.url" in main

    # App.tsx composes the optional platform header + shows a workflow call.
    app = files["src/App.tsx"]
    assert "BifrostHeader" in app
    assert "useWorkflow" in app


def test_scaffold_app_nested_path_anchors_manifests_at_root(tmp_path, monkeypatch) -> None:
    # With a nested --path, the .bifrost/ manifests must land at the DESCRIPTOR
    # root (not app_dir.parent.parent), and the manifest path entry must be a
    # POSIX root-relative path (so _app_source_dirs' POSIX comparisons match).
    _init_workspace(tmp_path)
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(
        solution_group,
        ["scaffold-app", "dash", "--path", "src/apps/dash", "--api-url", "http://localhost:8000"],
    )
    assert result.exit_code == 0, result.output

    # Manifests at the root — and no stray src/.bifrost.
    assert (tmp_path / ".bifrost" / "apps.yaml").is_file()
    assert (tmp_path / ".bifrost" / "workflows.yaml").is_file()
    assert not (tmp_path / "src" / ".bifrost").exists()
    # Sample workflow at the root, app files at the nested path.
    assert (tmp_path / "functions" / "hello.py").is_file()
    assert (tmp_path / "src" / "apps" / "dash" / "package.json").is_file()

    data = yaml.safe_load((tmp_path / ".bifrost" / "apps.yaml").read_text())
    (entry,) = data["apps"].values()
    assert entry["path"] == "src/apps/dash"


def test_scaffold_app_path_outside_workspace_refuses(tmp_path, monkeypatch) -> None:
    root = tmp_path / "ws"
    root.mkdir()
    _init_workspace(root)
    monkeypatch.chdir(root)

    result = CliRunner().invoke(
        solution_group,
        ["scaffold-app", "dash", "--path", "../elsewhere/dash", "--api-url", "http://localhost:8000"],
    )
    assert result.exit_code != 0
    assert "inside the solution workspace" in result.output
    # Nothing written — not the escape dir, not manifests.
    assert not (tmp_path / "elsewhere").exists()
    assert not (root / ".bifrost").exists()
    assert not (root / "functions").exists()


def test_scaffold_app_refuses_outside_solution_workspace(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)  # no bifrost.solution.yaml anywhere up the tree
    result = CliRunner().invoke(
        solution_group, ["scaffold-app", "dash", "--api-url", "http://localhost:8000"]
    )
    assert result.exit_code != 0
    assert "solution init" in result.output
    assert not (tmp_path / ".bifrost").exists()
