from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from build_anatomy import analyze_repository, render_anatomy_html


class CodeAnatomyTests(unittest.TestCase):
    def test_python_and_typescript_dependency_resolution(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".gitignore").write_text("ignored_dir/\n", encoding="utf-8")
            (root / "ignored_dir").mkdir()
            (root / "ignored_dir" / "secret.py").write_text("x = 1\n", encoding="utf-8")

            pkg = root / "src" / "demo"
            pkg.mkdir(parents=True)
            (pkg / "models.py").write_text("class Item:\n    pass\n", encoding="utf-8")
            (pkg / "service.py").write_text(
                "from .models import Item\n\ndef run() -> Item:\n    return Item()\n",
                encoding="utf-8",
            )
            (pkg / "cli.py").write_text(
                "from demo.service import run\n\ndef main() -> None:\n    run()\n",
                encoding="utf-8",
            )

            web = root / "web"
            web.mkdir()
            (web / "api.ts").write_text("export function fetchItems() { return []; }\n", encoding="utf-8")
            (web / "AppView.tsx").write_text(
                "import { fetchItems } from './api';\nexport function AppView() { return fetchItems(); }\n",
                encoding="utf-8",
            )

            tests_dir = root / "tests"
            tests_dir.mkdir()
            (tests_dir / "test_cli.py").write_text(
                "from demo.cli import main\ndef test_ok(): main()\n",
                encoding="utf-8",
            )

            graph = analyze_repository(root, exclude_tests=False, custom_title="PolyglotDemo")
            ids = {n["id"] for n in graph["nodes"]}
            self.assertNotIn("ignored_dir/secret.py", ids)
            self.assertIn("src/demo/cli.py", ids)
            self.assertIn("web/AppView.tsx", ids)

            edge_pairs = {(e["from"], e["to"]) for e in graph["edges"]}
            self.assertIn(("src/demo/cli.py", "src/demo/service.py"), edge_pairs)
            self.assertIn(("src/demo/service.py", "src/demo/models.py"), edge_pairs)
            self.assertIn(("web/AppView.tsx", "web/api.ts"), edge_pairs)

            # Verify --exclude-tests removes test_cli.py
            no_test_graph = analyze_repository(root, exclude_tests=True)
            no_test_ids = {n["id"] for n in no_test_graph["nodes"]}
            self.assertNotIn("tests/test_cli.py", no_test_ids)

            # Verify zero absolute path leaks & zero external CDNs in HTML output
            html = render_anatomy_html(graph)
            self.assertNotIn(str(root), html)
            self.assertNotIn("https://", html)
            self.assertIn("PolyglotDemo", html)
            self.assertLess(len(html), 150_000)

    def test_swift_intra_target_type_resolution_and_annotations(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            core = root / "Sources" / "MyCore"
            app = root / "Sources" / "MyApp"
            core.mkdir(parents=True)
            app.mkdir(parents=True)

            (core / "Models.swift").write_text(
                "public struct SnapshotData {\n    public let count: Int\n}\n",
                encoding="utf-8",
            )
            (core / "ScannerService.swift").write_text(
                "public enum ScannerService {\n    public static func scan() -> SnapshotData { SnapshotData(count: 1) }\n}\n",
                encoding="utf-8",
            )
            (app / "MyApp.swift").write_text(
                "import MyCore\npublic struct MyApp {\n    public func boot() { _ = ScannerService.scan() }\n}\n",
                encoding="utf-8",
            )

            annotations = {
                "subtitle": "Annotated Swift architecture",
                "modules": {
                    "Sources/MyCore/ScannerService.swift": {
                        "summary": "Custom semantic summary for ScannerService."
                    }
                },
                "tour": [
                    {
                        "title": "1. Scanner Hub",
                        "module": "Sources/MyCore/ScannerService.swift",
                        "body": "Collects live SnapshotData."
                    }
                ],
            }
            graph = analyze_repository(root, annotations=annotations)
            edge_pairs = {(e["from"], e["to"]) for e in graph["edges"]}
            self.assertIn(("Sources/MyApp/MyApp.swift", "Sources/MyCore/ScannerService.swift"), edge_pairs)
            self.assertIn(("Sources/MyCore/ScannerService.swift", "Sources/MyCore/Models.swift"), edge_pairs)

            scanner_node = next(n for n in graph["nodes"] if n["id"] == "Sources/MyCore/ScannerService.swift")
            self.assertEqual(scanner_node["summary"], "Custom semantic summary for ScannerService.")
            self.assertEqual(len(graph["tour"]), 1)
            json_dump = json.dumps(graph)
            self.assertNotIn(str(root), json_dump)


if __name__ == "__main__":
    unittest.main()
