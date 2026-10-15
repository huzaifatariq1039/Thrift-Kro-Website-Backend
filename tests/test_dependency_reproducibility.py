import json
import re
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_LINE = re.compile(
    r"^([A-Za-z0-9_.-]+)(?:\[[A-Za-z0-9_,.-]+\])?==([^ \\\n]+)"
)


def _locked_packages(path: Path) -> dict[str, str]:
    packages = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        match = PACKAGE_LINE.match(line)
        if match:
            packages[match.group(1).lower().replace("_", "-")] = match.group(2)
    return packages


class DependencyReproducibilityTests(unittest.TestCase):
    def test_runtime_is_exactly_pinned(self):
        runtime = (PROJECT_ROOT / ".python-version").read_text(encoding="utf-8").strip()
        self.assertRegex(runtime, r"^3\.12\.\d+$")

        workflow = (PROJECT_ROOT / ".github/workflows/backend-tests.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn('python-version-file: ".python-version"', workflow)

    def test_production_lock_is_complete_and_hash_checked(self):
        lock = (PROJECT_ROOT / "requirements.txt").read_text(encoding="utf-8")
        blocks = re.split(r"(?=^[A-Za-z0-9_.-]+==)", lock, flags=re.MULTILINE)
        package_blocks = [block for block in blocks if PACKAGE_LINE.match(block)]
        self.assertGreater(len(package_blocks), 40)
        for block in package_blocks:
            self.assertIn("--hash=sha256:", block)

        workflow = (PROJECT_ROOT / ".github/workflows/backend-tests.yml").read_text(
            encoding="utf-8"
        )
        railway = json.loads((PROJECT_ROOT / "railway.json").read_text(encoding="utf-8"))
        install_command = "python -m pip install --require-hashes -r requirements.txt"
        self.assertIn(install_command, workflow)
        self.assertIn("pip_audit -r requirements.txt --no-deps --disable-pip", workflow)
        self.assertEqual(railway["build"]["buildCommand"], install_command)

    def test_direct_dependencies_are_pinned_and_present_in_lock(self):
        direct_lines = [
            line.strip()
            for line in (PROJECT_ROOT / "requirements.in").read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        ]
        self.assertTrue(all(PACKAGE_LINE.match(line) for line in direct_lines))

        locked = _locked_packages(PROJECT_ROOT / "requirements.txt")
        for line in direct_lines:
            match = PACKAGE_LINE.match(line)
            name = match.group(1).lower().replace("_", "-")
            self.assertIn(name, locked)

    def test_critically_advised_jose_package_is_removed(self):
        production = _locked_packages(PROJECT_ROOT / "requirements.txt")
        self.assertNotIn("python-jose", production)
        self.assertEqual(production.get("pyjwt"), "2.15.1")

        source = "\n".join(
            (PROJECT_ROOT / path).read_text(encoding="utf-8")
            for path in ("app/core/security.py", "app/services/auth_lifecycle.py")
        )
        self.assertNotIn("from jose", source)

    def test_optional_ai_stack_is_not_in_api_deployment(self):
        production_text = (PROJECT_ROOT / "requirements.txt").read_text(encoding="utf-8")
        optional_text = (PROJECT_ROOT / "requirements-ai.txt").read_text(encoding="utf-8")
        production = _locked_packages(PROJECT_ROOT / "requirements.txt")
        optional = _locked_packages(PROJECT_ROOT / "requirements-ai.txt")
        ml_packages = {"torch", "torchvision", "ultralytics", "open-clip-torch"}
        self.assertTrue(ml_packages.isdisjoint(production))
        self.assertTrue(ml_packages.issubset(optional))
        self.assertNotIn("--extra-index-url", production_text)
        self.assertIn(
            "--extra-index-url https://download.pytorch.org/whl/cpu",
            optional_text,
        )

    def test_lock_script_targets_deployment_platform_and_hashes(self):
        script = (PROJECT_ROOT / "scripts/lock_dependencies.ps1").read_text(
            encoding="utf-8"
        )
        self.assertIn('"--python-platform", "x86_64-unknown-linux-gnu"', script)
        self.assertIn('"--generate-hashes"', script)
        self.assertIn("requirements-audit.txt", script)
        self.assertIn("--torch-backend cpu", script)
        self.assertIn("https://download.pytorch.org/whl/cpu", script)


if __name__ == "__main__":
    unittest.main()
