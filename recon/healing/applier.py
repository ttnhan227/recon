from __future__ import annotations

import ast
import json
import shutil
from pathlib import Path

from recon.common.config import get_project_slug, get_recon_home
from recon.common.logging import logger
from recon.healing.patcher import ProposedPatch


class PatchApplier:
    """Safely applies source code patches to disk with AST syntax validation, centralized backups, and rollback capability."""

    @staticmethod
    def validate_syntax(content: str, file_ext: str) -> bool:
        """Validates that modified code is free of syntax compilation errors before touching disk."""
        ext = file_ext.lower()
        if ext == ".py":
            try:
                ast.parse(content)
                return True
            except SyntaxError as se:
                logger.error(f"Syntax validation failed for Python file: {se}")
                return False
        elif ext == ".json":
            try:
                json.loads(content)
                return True
            except Exception as je:
                logger.error(f"JSON validation failed: {je}")
                return False
        return True

    @staticmethod
    def get_backup_path(file_path: Path) -> Path:
        """Determines the centralized backup path in ~/.recon/backups/{project_slug}/..."""
        project_slug = get_project_slug(cwd=file_path.parent)
        backup_dir = get_recon_home() / "backups" / project_slug
        backup_dir.mkdir(parents=True, exist_ok=True)
        return backup_dir / f"{file_path.name}.recon.bak"

    @staticmethod
    def apply_patch(patch: ProposedPatch) -> Path | None:
        """Writes the proposed patch to disk ONLY after passing syntax validation and creating a centralized backup."""
        file_path = patch.file_path.resolve()
        if not file_path.exists():
            logger.error(f"Cannot apply patch: File not found: {file_path}")
            return None

        # Pre-Apply AST / Syntax Gate: Reject immediately if syntax is broken
        if not PatchApplier.validate_syntax(patch.modified_content, file_path.suffix):
            logger.error(f"Rejecting patch for {file_path.name}: Failed pre-apply syntax compilation check. Code was untouched.")
            return None

        # Create centralized backup in ~/.recon/backups/{project_slug}/
        backup_path = PatchApplier.get_backup_path(file_path)
        try:
            shutil.copy2(file_path, backup_path)
            # Write modified content
            file_path.write_text(patch.modified_content, encoding="utf-8")

            # Post-Apply Sanity Check for Python
            if file_path.suffix.lower() == ".py":
                try:
                    ast.parse(file_path.read_text(encoding="utf-8"))
                except SyntaxError:
                    logger.error(f"Post-write syntax check failed on {file_path}. Rolling back immediately!")
                    shutil.copy2(backup_path, file_path)
                    return None

            logger.info(f"Applied verified patch to {file_path}. Centralized backup saved at {backup_path}")
            return backup_path
        except Exception as e:
            logger.error(f"Failed to apply patch to {file_path}: {e}")
            if backup_path.exists():
                shutil.copy2(backup_path, file_path)
            return None

    @staticmethod
    def rollback(backup_path: Path | str, target_file_path: Path | str | None = None) -> bool:
        """Restores the original file from a centralized or local .recon.bak backup."""
        b_path = Path(backup_path).resolve()
        if not b_path.exists():
            logger.error(f"Backup file not found: {b_path}")
            return False

        if target_file_path:
            t_path = Path(target_file_path).resolve()
        else:
            orig_name = b_path.name.replace(".recon.bak", "")
            t_path = b_path.with_name(orig_name)

        try:
            shutil.copy2(b_path, t_path)
            b_path.unlink()
            logger.info(f"Rolled back {t_path} from backup.")
            return True
        except Exception as e:
            logger.error(f"Rollback failed for {t_path}: {e}")
            return False
