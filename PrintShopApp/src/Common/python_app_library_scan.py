from __future__ import annotations

import argparse
import ast
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
import json
import os
from pathlib import Path
import sys
import threading
from typing import Any, Callable

from Common.log import logd, loge, set_file_tag
from Common.python_venv_setup import PythonLibManager

set_file_tag("APP_LIB_SCAN")
"""
[사용법 안내]
1. 앱별 라이브러리 스캔 (단일 앱 / 다중 앱 / JSON 내보내기 / 필터·비교·쿼리)
   $ python python_app_library_scan.py
   $ python python_app_library_scan.py app_scan --app_name PrintShopApp --source_root ./src
   $ python python_app_library_scan.py scan_all --source_root ./src --json_out ./scan_report.json
   $ python python_app_library_scan.py diff --source_root ./src --apps PrintShopApp,UpdateService

2. 코드에서 직접 호출
   scanner = AppLibraryScanner.create(
       app_name="PrintShopApp",
       source_root="./src",
       entry_point="./src/PrintShopApp/main_app.py",
   )
   record = scanner.get_app_record("PrintShopApp")
   used_libs = record.get_used_libraries()
   unused_libs = record.get_unused_import_libraries()
   found_libs = record.get_found_libraries()
"""


class ThreadSafeSingletonBase:
    _instances: dict[type, object] = {}
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        if cls not in cls._instances:
            with cls._lock:
                if cls not in cls._instances:
                    cls._instances[cls] = super().__new__(cls)
        return cls._instances[cls]


@dataclass(frozen=True)
class CodeLocation:
    """코드 내 위치(파일, 라인, 감싸고 있는 함수/스코프명)."""

    file: str
    line: int
    func_name: str

    def format_pos(self) -> str:
        return f"{self.file}:{self.line} ({self.func_name})"

    def to_dict(self) -> dict[str, Any]:
        return {
            "file": self.file,
            "line": self.line,
            "func_name": self.func_name,
        }


@dataclass(frozen=True)
class FirstSeenEntry:
    """라이브러리별 최초 발견 파일 및 라인 정보."""

    library: str
    file: str
    line: int
    func_name: str = "<module>"

    def get_library_name(self) -> str:
        return self.library

    def get_name_file_line(self) -> str:
        return f"{self.library}, {self.file}, {self.line}, {self.func_name}"


@dataclass(frozen=True)
class ImportRecord:
    """라이브러리 import 발생 위치."""

    library: str
    module: str
    symbol: str
    location: CodeLocation

    def format_detail(self) -> str:
        return f"{self.symbol} @ {self.location.format_pos()}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "library": self.library,
            "module": self.module,
            "symbol": self.symbol,
            "file": self.location.file,
            "line": self.location.line,
            "func_name": self.location.func_name,
        }


@dataclass(frozen=True)
class CallUsageEntry:
    """실제 호출(ast.Call)에서 사용된 라이브러리·모듈·호출식 및 위치 정보."""

    library: str
    module: str
    call_expr: str
    file: str
    line: int
    func_name: str = "<module>"

    def get_library_name(self) -> str:
        return self.library

    def get_call_info(self) -> str:
        return f"{self.library}.{self.call_expr}, {self.file}, {self.line}, {self.func_name}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "library": self.library,
            "module": self.module,
            "call_expr": self.call_expr,
            "file": self.file,
            "line": self.line,
            "func_name": self.func_name,
        }


@dataclass
class LibraryDetailReport:
    """라이브러리별 import 위치 및 실제 호출(ast.Call) 위치 상세 보고."""

    library: str
    imports: list[ImportRecord] = field(default_factory=list)
    calls: list[CallUsageEntry] = field(default_factory=list)

    @property
    def is_used(self) -> bool:
        """실제 호출(ast.Call)이 1건 이상 발생한 경우 True."""
        return len(self.calls) > 0

    @property
    def is_unused_import(self) -> bool:
        """import는 되었으나 실제 호출(ast.Call)이 없는 경우 True."""
        return len(self.imports) > 0 and len(self.calls) == 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "library": self.library,
            "is_used": self.is_used,
            "is_unused_import": self.is_unused_import,
            "imports": [imp.to_dict() for imp in self.imports],
            "calls": [call.to_dict() for call in self.calls],
        }


@dataclass(frozen=True)
class AppLibraryScanEntry:
    """앱 이름 및 진입점 컨텍스트를 포함한 라이브러리 스캔 결과 항목."""

    app_name: str
    entry_point: str
    first_seen: FirstSeenEntry
    calls: tuple[CallUsageEntry, ...] = ()
    imports: tuple[ImportRecord, ...] = ()

    def get_app_name(self) -> str:
        return self.app_name

    def get_entry_point(self) -> str:
        return self.entry_point

    def get_library_name(self) -> str:
        return self.first_seen.get_library_name()

    def get_name_file_line(self) -> str:
        return self.first_seen.get_name_file_line()

    def get_called_expressions(self) -> list[str]:
        return [c.call_expr for c in self.calls]

    def to_line_str(self) -> str:
        return f"[{self.app_name}] ({self.entry_point}) {self.first_seen.get_name_file_line()}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "app_name": self.app_name,
            "entry_point": self.entry_point,
            "library": self.first_seen.library,
            "file": self.first_seen.file,
            "line": self.first_seen.line,
            "func_name": self.first_seen.func_name,
            "is_used": len(self.calls) > 0,
            "is_unused_import": len(self.imports) > 0 and len(self.calls) == 0,
            "imports": [imp.to_dict() for imp in self.imports],
            "calls": [c.to_dict() for c in self.calls],
        }


@dataclass
class AppScanRecord:
    """단일 앱의 스캔 메타데이터 및 라이브러리 정보를 보관하는 앱별 자료구조."""

    app_name: str
    source_root: str
    entry_point: str
    only_used: bool = True
    visited_files: list[str] = field(default_factory=list)
    entries: list[AppLibraryScanEntry] = field(default_factory=list)
    all_entries: list[AppLibraryScanEntry] = field(default_factory=list)
    first_seen_by_lib: dict[str, FirstSeenEntry] = field(default_factory=dict)
    call_entries: list[CallUsageEntry] = field(default_factory=list)
    calls_by_lib: dict[str, list[CallUsageEntry]] = field(default_factory=dict)
    import_entries: list[ImportRecord] = field(default_factory=list)
    imports_by_lib: dict[str, list[ImportRecord]] = field(default_factory=dict)
    details_by_lib: dict[str, LibraryDetailReport] = field(default_factory=dict)
    scanned_at: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))
    scan_duration_ms: float = 0.0

    def get_library_names(self) -> list[str]:
        return [item.get_library_name() for item in self.entries]

    def get_used_libraries(self) -> list[str]:
        """실제 호출(ast.Call)로 사용된 라이브러리 목록만 반환."""
        return sorted(lib for lib, rep in self.details_by_lib.items() if rep.is_used)

    def get_found_libraries(self) -> list[str]:
        """스캔 시 발견된 전체 외부 라이브러리 목록 반환."""
        return sorted(self.details_by_lib.keys())

    def get_unused_import_libraries(self) -> list[str]:
        """import는 되었으나 실제 호출(ast.Call)되지 않은 라이브러리 목록 반환."""
        return sorted(lib for lib, rep in self.details_by_lib.items() if rep.is_unused_import)

    def get_detail_report(self, library_name: str) -> LibraryDetailReport | None:
        target = (library_name or "").strip()
        return self.details_by_lib.get(target)

    def get_called_libraries(self) -> list[str]:
        return self.get_used_libraries()

    def has_library(self, library_name: str) -> bool:
        target = (library_name or "").strip()
        return target in self.first_seen_by_lib

    def has_library_call(self, library_name: str) -> bool:
        target = (library_name or "").strip()
        return bool(self.calls_by_lib.get(target))

    def get_first_seen(self, library_name: str) -> FirstSeenEntry | None:
        target = (library_name or "").strip()
        return self.first_seen_by_lib.get(target)

    def get_library_calls(self, library_name: str) -> list[CallUsageEntry]:
        target = (library_name or "").strip()
        return list(self.calls_by_lib.get(target, ()))

    def get_library_imports(self, library_name: str) -> list[ImportRecord]:
        target = (library_name or "").strip()
        return list(self.imports_by_lib.get(target, ()))

    def filter_libraries(
        self,
        *,
        include: set[str] | list[str] | tuple[str, ...] | None = None,
        exclude: set[str] | list[str] | tuple[str, ...] | None = None,
        prefix: str | None = None,
    ) -> list[AppLibraryScanEntry]:
        inc_set = {x.strip() for x in (include or ()) if str(x).strip()}
        exc_set = {x.strip() for x in (exclude or ()) if str(x).strip()}
        pfx = (prefix or "").strip()

        filtered: list[AppLibraryScanEntry] = []
        for entry in self.entries:
            lib_name = entry.get_library_name()
            if inc_set and lib_name not in inc_set:
                continue
            if exc_set and lib_name in exc_set:
                continue
            if pfx and not lib_name.startswith(pfx):
                continue
            filtered.append(entry)
        return filtered

    def format_detail_summary(self) -> str:
        """실제 사용(호출) 라이브러리, 검색 전체 라이브러리, 미사용 import 및 위치(파일/라인/함수명)를 문자열로 반환."""
        lines: list[str] = []
        used_libs = self.get_used_libraries()
        found_libs = self.get_found_libraries()
        unused_libs = self.get_unused_import_libraries()

        lines.append(f"[{self.app_name}] 검색 발견 전체({len(found_libs)}): {found_libs}")
        lines.append(f"[{self.app_name}] 실제 사용(호출)({len(used_libs)}): {used_libs}")
        lines.append(f"[{self.app_name}] 미사용 import({len(unused_libs)}): {unused_libs}")

        lines.append("--- [실제 사용(호출) 라이브러리 상세] ---")
        if not used_libs:
            lines.append("  (없음)")
        for lib in used_libs:
            rep = self.details_by_lib[lib]
            lines.append(f"  * {lib}")
            for imp in rep.imports:
                lines.append(
                    f"      - import : {imp.location.file} | line {imp.location.line} | func: {imp.location.func_name} ({imp.symbol})"
                )
            for call in rep.calls:
                lines.append(
                    f"      - 사용(호출): {call.file} | line {call.line} | func: {call.func_name} -> {call.call_expr}()"
                )

        lines.append("--- [Import 되었지만 호출되지 않은 라이브러리 상세] ---")
        if not unused_libs:
            lines.append("  (없음)")
        for lib in unused_libs:
            rep = self.details_by_lib[lib]
            lines.append(f"  * {lib}")
            for imp in rep.imports:
                lines.append(
                    f"      - import : {imp.location.file} | line {imp.location.line} | func: {imp.location.func_name} ({imp.symbol})"
                )
            lines.append("      - 사용(호출): 없음")

        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        return {
            "app_name": self.app_name,
            "source_root": self.source_root,
            "entry_point": self.entry_point,
            "only_used": self.only_used,
            "scanned_at": self.scanned_at,
            "scan_duration_ms": round(self.scan_duration_ms, 2),
            "visited_file_count": len(self.visited_files),
            "library_count": len(self.entries),
            "used_library_count": len(self.get_used_libraries()),
            "found_library_count": len(self.get_found_libraries()),
            "unused_import_count": len(self.get_unused_import_libraries()),
            "call_count": len(self.call_entries),
            "visited_files": list(self.visited_files),
            "libraries": self.get_library_names(),
            "used_libraries": self.get_used_libraries(),
            "found_libraries": self.get_found_libraries(),
            "unused_import_libraries": self.get_unused_import_libraries(),
            "called_libraries": self.get_called_libraries(),
            "entries": [item.to_dict() for item in self.entries],
            "all_entries": [item.to_dict() for item in self.all_entries],
            "imports": [imp.to_dict() for imp in self.import_entries],
            "calls": [c.to_dict() for c in self.call_entries],
            "details_by_lib": {k: v.to_dict() for k, v in sorted(self.details_by_lib.items())},
        }


class AppScanRegistry:
    """여러 앱의 AppScanRecord를 앱 이름 키로 관리하는 레지스트리 자료구조."""

    def __init__(self) -> None:
        self._records: dict[str, AppScanRecord] = {}

    def upsert(self, record: AppScanRecord) -> AppScanRecord:
        self._records[record.app_name] = record
        return record

    def get(self, app_name: str) -> AppScanRecord | None:
        return self._records.get(app_name)

    def remove(self, app_name: str) -> bool:
        return self._records.pop(app_name, None) is not None

    def clear(self) -> None:
        self._records.clear()

    def app_names(self) -> list[str]:
        return sorted(self._records.keys())

    def all_records(self) -> dict[str, AppScanRecord]:
        return dict(self._records)

    def entries_for_app(self, app_name: str) -> list[AppLibraryScanEntry]:
        rec = self._records.get(app_name)
        return list(rec.entries) if rec is not None else []

    def calls_for_app(self, app_name: str, library_name: str | None = None) -> list[CallUsageEntry]:
        rec = self._records.get(app_name)
        if rec is None:
            return []
        if library_name:
            return rec.get_library_calls(library_name)
        return list(rec.call_entries)

    def imports_for_app(self, app_name: str, library_name: str | None = None) -> list[ImportRecord]:
        rec = self._records.get(app_name)
        if rec is None:
            return []
        if library_name:
            return rec.get_library_imports(library_name)
        return list(rec.import_entries)

    def to_dict(self) -> dict[str, dict[str, Any]]:
        return {name: rec.to_dict() for name, rec in sorted(self._records.items())}


def _build_line_scope_map(tree: ast.AST) -> dict[int, str]:
    """각 라인 번호가 속한 함수/메서드/클래스 스코프명을 반환합니다 (최상위는 '<module>')."""
    line_scopes: dict[int, str] = {}
    scope_stack: list[str] = ["<module>"]

    def visit(node: ast.AST) -> None:
        pushed = False
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            scope_stack.append(node.name)
            pushed = True
        elif isinstance(node, ast.ClassDef):
            scope_stack.append(node.name)
            pushed = True

        lineno = getattr(node, "lineno", None)
        if isinstance(lineno, int) and lineno > 0:
            current_scope = scope_stack[-1]
            if lineno not in line_scopes or current_scope != "<module>":
                line_scopes[lineno] = current_scope

        for child in ast.iter_child_nodes(node):
            visit(child)

        if pushed:
            scope_stack.pop()

    visit(tree)
    return line_scopes


class AppLibraryScanner(ThreadSafeSingletonBase):
    """진입점 및 관련 앱 파일 전체를 AST로 추적해 앱별 자료구조(AppScanRecord)를 보관하는 싱글톤 클래스."""

    _initialized: bool = False

    def __init__(
        self,
        app_name: str | None = None,
        source_root: str | Path | None = None,
        entry_point: str | Path | None = None,
        *,
        lib_manager: PythonLibManager | None = None,
        ignore_modules: set[str] | list[str] | tuple[str, ...] | None = None,
        package_map: dict[str, str] | None = None,
        only_used: bool = True,
        include_app_dir_files: bool = True,
    ) -> None:
        logd(
            f"AppLibraryScanner.__init__ 호출 (app_name={app_name}, source_root={source_root}, entry_point={entry_point}, only_used={only_used})"
        )
        if not self._initialized:
            logd("AppLibraryScanner 싱글톤 최초 초기화 진행")
            self.source_root: Path | None = (
                Path(source_root).resolve() if source_root is not None else None
            )
            self.lib_manager: PythonLibManager | None = lib_manager
            self.ignore_modules: set[str] = set(
                ignore_modules
                if ignore_modules is not None
                else PythonLibManager.DEFAULT_IGNORE_MODULES
            )
            self.package_map: dict[str, str] = dict(
                package_map if package_map is not None else PythonLibManager.DEFAULT_PACKAGE_MAP
            )
            self.include_app_dir_files: bool = bool(include_app_dir_files)
            self._stdlib: set[str] = set(getattr(sys, "stdlib_module_names", set()))
            self._local_modules_by_root: dict[Path, set[str]] = {}
            self._search_roots_by_root: dict[Path, list[Path]] = {}
            self._ast_cache: dict[tuple[Path, int], ast.AST] = {}
            if self.source_root is not None:
                self._local_modules_by_root[self.source_root] = self._collect_local_modules(
                    self.source_root
                )
            self.registry: AppScanRegistry = AppScanRegistry()
            self._initialized = True
            logd("AppLibraryScanner 싱글톤 최초 초기화 완료")
        else:
            logd("기존 AppLibraryScanner 싱글톤 인스턴스 재사용 및 옵션 동기화")
            self.include_app_dir_files = bool(include_app_dir_files)
            if source_root is not None:
                resolved = Path(source_root).resolve()
                if self.source_root != resolved:
                    self.source_root = resolved
                    self._search_roots_by_root.pop(resolved, None)
                    self._local_modules_by_root[resolved] = self._collect_local_modules(resolved)
                    logd(f"source_root 갱신: {self.source_root}")
                elif resolved not in self._local_modules_by_root:
                    self._local_modules_by_root[resolved] = self._collect_local_modules(resolved)
            if lib_manager is not None:
                self.lib_manager = lib_manager
                logd("lib_manager 참조 갱신")
            if ignore_modules is not None:
                self.ignore_modules = set(ignore_modules)
                logd(f"ignore_modules 동기화 (총 {len(self.ignore_modules)}개)")
            if package_map is not None:
                self.package_map = dict(package_map)
                logd(f"package_map 동기화 (총 {len(self.package_map)}개)")

        if app_name is not None and entry_point is not None:
            logd(f"초기화 단계에서 앱 스캔 및 앱별 자료구조 등록 실행: {app_name}")
            self.add_app(
                app_name=app_name,
                entry_point=entry_point,
                source_root=self.source_root,
                only_used=only_used,
            )

    @classmethod
    def create(
        cls,
        app_name: str,
        source_root: str | Path,
        entry_point: str | Path,
        *,
        lib_manager: PythonLibManager | None = None,
        ignore_modules: set[str] | list[str] | tuple[str, ...] | None = None,
        package_map: dict[str, str] | None = None,
        only_used: bool = True,
        include_app_dir_files: bool = True,
    ) -> "AppLibraryScanner":
        """APP_NAME, source_root, 진입점을 받아 스캔 완료된 AppLibraryScanner 싱글톤 인스턴스를 생성·반환합니다."""
        logd(
            f"AppLibraryScanner.create 호출: app_name={app_name}, source_root={source_root}, entry_point={entry_point}"
        )
        instance = cls(
            app_name=app_name,
            source_root=source_root,
            entry_point=entry_point,
            lib_manager=lib_manager,
            ignore_modules=ignore_modules,
            package_map=package_map,
            only_used=only_used,
            include_app_dir_files=include_app_dir_files,
        )
        logd(f"AppLibraryScanner.create 완료: app_name={app_name}")
        return instance

    def clear_caches(self) -> None:
        """탐색 루트, 로컬 모듈, AST 파싱 캐시를 초기화합니다."""
        self._search_roots_by_root.clear()
        self._local_modules_by_root.clear()
        self._ast_cache.clear()
        logd("AppLibraryScanner 캐시 초기화 완료")

    def _search_roots(self, root_path: Path) -> list[Path]:
        resolved_root = root_path.resolve()
        cached = self._search_roots_by_root.get(resolved_root)
        if cached is not None:
            return cached

        logd(f"탐색 루트 계산 시작: {resolved_root}")
        roots = [resolved_root]
        if resolved_root.name.lower() == "src":
            roots.append(resolved_root.parent)
        elif (resolved_root / "src").is_dir():
            roots.append((resolved_root / "src").resolve())

        unique: list[Path] = []
        for r in roots:
            if r.exists() and r not in unique:
                unique.append(r)
        self._search_roots_by_root[resolved_root] = unique
        logd(f"유효 탐색 루트 목록: {[str(p) for p in unique]}")
        return unique

    def _to_rel_posix(self, file_path: Path, root_path: Path) -> str:
        base = root_path.parent if root_path.name.lower() == "src" else root_path
        try:
            return file_path.resolve().relative_to(base.resolve()).as_posix()
        except ValueError:
            return file_path.resolve().as_posix()

    def _read_source(self, py_file: Path) -> str | None:
        if self.lib_manager is not None:
            return self.lib_manager._read_source(py_file)
        for enc in ("utf-8-sig", "utf-8", "cp949"):
            try:
                return py_file.read_text(encoding=enc)
            except UnicodeDecodeError:
                continue
            except OSError as exc:
                loge(f"소스 파일 읽기 오류 ({py_file}): {exc}")
                return None
        loge(f"소스 파일 인코딩 디코딩 실패 ({py_file})")
        return None

    def _parse_ast_cached(self, py_file: Path) -> ast.AST | None:
        resolved = py_file.resolve()
        try:
            mtime_ns = resolved.stat().st_mtime_ns
        except OSError:
            mtime_ns = -1

        cache_key = (resolved, mtime_ns)
        if mtime_ns >= 0 and cache_key in self._ast_cache:
            return self._ast_cache[cache_key]

        source = self._read_source(resolved)
        if source is None:
            return None

        try:
            tree = ast.parse(source, filename=str(resolved))
        except SyntaxError as exc:
            loge(f"문법 오류로 스캔 생략 ({resolved}): {exc}")
            return None

        if mtime_ns >= 0:
            self._ast_cache[cache_key] = tree
        return tree

    def _collect_local_modules(self, root_path: Path) -> set[str]:
        logd(f"스캐너 로컬 모듈 수집 시작: {root_path}")
        names: set[str] = set()

        if self.lib_manager is not None:
            try:
                names.update(self.lib_manager._collect_local_module_names())
                logd(f"lib_manager로부터 로컬 모듈 {len(names)}개 수집")
            except Exception as exc:
                loge(f"lib_manager 로컬 모듈 수집 실패, 자체 수집으로 폴백: {exc}")

        for root in self._search_roots(root_path):
            try:
                for _current_root, dirnames, filenames in os.walk(
                    root, topdown=True, followlinks=False
                ):
                    dirnames[:] = sorted(
                        d
                        for d in dirnames
                        if not d.startswith((".", "__"))
                        and d not in PythonLibManager.DEFAULT_EXCLUDE_DIRS
                        and not d.endswith(".egg-info")
                    )
                    for d in dirnames:
                        names.add(d)
                    for filename in sorted(filenames):
                        if filename.endswith(".py"):
                            stem = Path(filename).stem
                            if not stem.startswith("__"):
                                names.add(stem)
            except OSError as exc:
                loge(f"로컬 모듈 디렉토리 순회 오류 ({root}): {exc}")

        logd(f"스캐너 로컬 모듈 {len(names)}개 수집 완료")
        return names

    def _get_local_modules_for_root(self, root_path: Path) -> set[str]:
        resolved = root_path.resolve()
        if resolved in self._local_modules_by_root:
            return self._local_modules_by_root[resolved]
        mods = self._collect_local_modules(resolved)
        self._local_modules_by_root[resolved] = mods
        return mods

    def _map_to_pip_package(self, top_mod: str) -> str:
        if top_mod in self.package_map:
            return self.package_map[top_mod]
        if self.lib_manager is not None:
            return self.lib_manager.map_to_pip_package(top_mod)
        return top_mod

    def _resolve_local_files(
        self,
        module_path: str,
        root_path: Path,
        local_modules: set[str] | None = None,
        current_file: Path | None = None,
    ) -> list[Path]:
        parts = [p for p in module_path.split(".") if p]
        if not parts:
            return []

        candidate_bases: list[Path] = [*self._search_roots(root_path)]
        if current_file is not None:
            candidate_bases.append(current_file.parent.resolve())
            if current_file.parent.parent.is_dir():
                candidate_bases.append(current_file.parent.parent.resolve())
        if root_path.name.lower() == "src":
            candidate_bases.append(root_path.parent.resolve())

        found: list[Path] = []
        seen: set[Path] = set()
        for base in candidate_bases:
            if not base.exists():
                continue
            py_file = (base / Path(*parts)).with_suffix(".py")
            init_file = base / Path(*parts) / "__init__.py"
            for candidate in (py_file, init_file):
                if candidate.is_file():
                    resolved = candidate.resolve()
                    if resolved not in seen:
                        seen.add(resolved)
                        found.append(resolved)
        return found

    def _resolve_relative_files(
        self, current_file: Path, level: int, module: str | None
    ) -> list[Path]:
        base_dir = current_file.resolve().parent
        for _ in range(max(level - 1, 0)):
            base_dir = base_dir.parent

        if module:
            parts = [p for p in module.split(".") if p]
            candidates = [
                (base_dir / Path(*parts)).with_suffix(".py"),
                base_dir / Path(*parts) / "__init__.py",
            ]
        else:
            candidates = [base_dir / "__init__.py"]

        return [p.resolve() for p in candidates if p.is_file()]

    def _collect_app_directory_py_files(self, app_dir: Path) -> list[Path]:
        """앱 폴더(예: src/PrintShopApp) 내 모든 관련 .py 파일을 수집합니다."""
        if not self.include_app_dir_files or not app_dir.is_dir():
            return []
        collected: list[Path] = []
        try:
            for current_root, dirnames, filenames in os.walk(
                app_dir, topdown=True, followlinks=False
            ):
                dirnames[:] = sorted(
                    d
                    for d in dirnames
                    if not d.startswith((".", "__"))
                    and d not in PythonLibManager.DEFAULT_EXCLUDE_DIRS
                    and not d.endswith(".egg-info")
                )
                for filename in sorted(filenames):
                    if filename.endswith(".py"):
                        collected.append((Path(current_root) / filename).resolve())
        except OSError as exc:
            loge(f"앱 디렉토리 순회 오류 ({app_dir}): {exc}")
        return collected

    @staticmethod
    def _call_chain_parts(func_node: ast.AST) -> list[str]:
        """ast.Call.func에서 ['루트', '속성1', '속성2'] 체인을 추출합니다."""
        parts: list[str] = []
        curr: ast.AST = func_node
        while isinstance(curr, ast.Attribute):
            parts.append(curr.attr)
            curr = curr.value
        if isinstance(curr, ast.Name):
            parts.append(curr.id)
            parts.reverse()
            return parts
        return []

    @staticmethod
    def _normalize_call_expr(
        top_mod: str, sym_path: str, root_name: str, tail_parts: list[str]
    ) -> str:
        """중복 모듈 접두사를 제거하고 깔끔한 호출 표현식(예: QtGui.QTextCharFormat)을 만듭니다."""
        base = sym_path if sym_path else root_name
        parts = [p for p in [base, *tail_parts] if p]
        while len(parts) >= 2 and parts[0] == top_mod and parts[1] == top_mod:
            parts.pop(0)
        return ".".join(parts)

    def _is_external_top_module(self, top_mod: str, local_modules: set[str]) -> bool:
        if not top_mod:
            return False
        if top_mod in self._stdlib:
            return False
        if top_mod in local_modules:
            return False
        if top_mod in self.ignore_modules:
            return False
        return True

    def _process_file_ast(
        self,
        app_name: str,
        cur_file: Path,
        tree: ast.AST,
        rel_file: str,
        resolved_root: Path,
        local_modules: set[str],
        record_import: Callable[[str, str, str, CodeLocation], None],
        record_call: Callable[[str, str, str, CodeLocation], None],
    ) -> list[list[Path]]:
        """단일 파일 AST에서 import 위치와 실제 호출(ast.Call) 위치를 (파일, 라인, 함수명)으로 추출합니다."""
        line_scopes = _build_line_scope_map(tree)
        bound_to_import: dict[str, list[tuple[str, str, str]]] = {}
        local_targets: list[list[Path]] = []

        ordered_nodes = sorted(ast.walk(tree), key=lambda n: int(getattr(n, "lineno", 0) or 0))

        # 1) import 위치 수집 및 로컬 연계 파일 탐색
        for node in ordered_nodes:
            lineno = max(0, int(getattr(node, "lineno", 0) or 0))
            func_name = line_scopes.get(lineno, "<module>")
            loc = CodeLocation(file=rel_file, line=lineno, func_name=func_name)

            if isinstance(node, ast.Import):
                for alias in node.names:
                    top_mod = alias.name.split(".")[0]
                    bound = alias.asname or top_mod
                    bound_to_import.setdefault(bound, []).append((top_mod, alias.name, ""))
                    if self._is_external_top_module(top_mod, local_modules):
                        sym_label = (
                            f"{alias.name} as {alias.asname}" if alias.asname else alias.name
                        )
                        record_import(top_mod, alias.name, sym_label, loc)
                    local_targets.append(
                        self._resolve_local_files(
                            alias.name,
                            resolved_root,
                            local_modules=local_modules,
                            current_file=cur_file,
                        )
                    )

            elif isinstance(node, ast.ImportFrom):
                if node.level == 0 and node.module:
                    top_mod = node.module.split(".")[0]
                    local_targets.append(
                        self._resolve_local_files(
                            node.module,
                            resolved_root,
                            local_modules=local_modules,
                            current_file=cur_file,
                        )
                    )
                    for alias in node.names:
                        if alias.name == "*":
                            continue
                        bound = alias.asname or alias.name
                        sym_path = (
                            f"{node.module}.{alias.name}" if node.module != top_mod else alias.name
                        )
                        bound_to_import.setdefault(bound, []).append(
                            (top_mod, node.module, sym_path)
                        )
                        if self._is_external_top_module(top_mod, local_modules):
                            sym_label = (
                                f"{alias.name} as {alias.asname}" if alias.asname else alias.name
                            )
                            record_import(top_mod, node.module, sym_label, loc)
                        local_targets.append(
                            self._resolve_local_files(
                                f"{node.module}.{alias.name}",
                                resolved_root,
                                local_modules=local_modules,
                                current_file=cur_file,
                            )
                        )
                elif node.level > 0:
                    local_targets.append(
                        self._resolve_relative_files(cur_file, node.level, node.module)
                    )

        # 2) 실제 호출(ast.Call) 위치 수집
        for node in ordered_nodes:
            if not isinstance(node, ast.Call):
                continue
            chain = self._call_chain_parts(node.func)
            if not chain:
                continue
            root_name = chain[0]
            tail_parts = chain[1:]
            if root_name not in bound_to_import:
                continue

            lineno = max(0, int(getattr(node, "lineno", 0) or 0))
            func_name = line_scopes.get(lineno, "<module>")
            loc = CodeLocation(file=rel_file, line=lineno, func_name=func_name)

            for top_mod, full_mod, sym_path in bound_to_import[root_name]:
                if not self._is_external_top_module(top_mod, local_modules):
                    continue
                call_expr = self._normalize_call_expr(top_mod, sym_path, root_name, tail_parts)
                record_call(top_mod, full_mod, call_expr, loc)

        return local_targets

    def add_app(
        self,
        app_name: str,
        entry_point: str | Path,
        source_root: str | Path | None = None,
        only_used: bool = True,
    ) -> list[AppLibraryScanEntry]:
        """앱 진입점 및 관련 앱 파일을 스캔해 앱별 자료구조(AppScanRecord)에 보관하고 결과 리스트를 반환합니다."""
        started_at = datetime.now()
        logd(
            f"앱 스캔 시작: app_name={app_name}, entry_point={entry_point}, source_root={source_root}, only_used={only_used}"
        )
        start_file = Path(entry_point).resolve()
        resolved_root = (
            Path(source_root).resolve()
            if source_root is not None
            else (self.source_root or start_file.parent)
        )
        if self.source_root is None:
            self.source_root = resolved_root
            logd(f"source_root 자동 설정: {self.source_root}")

        local_modules = self._get_local_modules_for_root(resolved_root)
        logd(f"[{app_name}] 적용 로컬 모듈 수: {len(local_modules)}")

        if not start_file.is_file():
            loge(f"[{app_name}] 진입점 파일을 찾을 수 없습니다: {start_file}")
            empty_record = AppScanRecord(
                app_name=app_name,
                source_root=str(resolved_root),
                entry_point=str(start_file),
                only_used=only_used,
            )
            self.registry.upsert(empty_record)
            return []

        rel_entry = self._to_rel_posix(start_file, resolved_root)
        visited: set[Path] = set()
        visited_rel_files: list[str] = []
        queue: deque[Path] = deque([start_file])

        # 앱 디렉토리 내 모든 관련 .py 파일을 시드로 추가
        app_dir_files = self._collect_app_directory_py_files(start_file.parent)
        for py_file in app_dir_files:
            if py_file not in queue:
                queue.append(py_file)
        logd(f"[{app_name}] 앱 폴더({start_file.parent}) 내 .py 파일 {len(app_dir_files)}개 포함")

        details_by_lib: dict[str, LibraryDetailReport] = {}
        import_entries: list[ImportRecord] = []
        imports_by_lib: dict[str, list[ImportRecord]] = {}
        call_entries: list[CallUsageEntry] = []
        calls_by_lib: dict[str, list[CallUsageEntry]] = {}
        first_called_seen_map: dict[str, FirstSeenEntry] = {}
        first_any_seen_map: dict[str, FirstSeenEntry] = {}

        seen_import_keys: set[tuple[str, str, str, int, str]] = set()
        seen_first_call_keys: set[tuple[str, str]] = set()

        def ensure_detail(pkg_name: str) -> LibraryDetailReport:
            if pkg_name not in details_by_lib:
                details_by_lib[pkg_name] = LibraryDetailReport(library=pkg_name)
            return details_by_lib[pkg_name]

        def record_import(top_mod: str, full_mod: str, symbol: str, loc: CodeLocation) -> None:
            pkg_name = self._map_to_pip_package(top_mod)
            key = (pkg_name, symbol, loc.file, loc.line, loc.func_name)
            if key in seen_import_keys:
                return
            seen_import_keys.add(key)

            imp_rec = ImportRecord(
                library=pkg_name,
                module=full_mod,
                symbol=symbol,
                location=loc,
            )
            import_entries.append(imp_rec)
            imports_by_lib.setdefault(pkg_name, []).append(imp_rec)
            ensure_detail(pkg_name).imports.append(imp_rec)

            if pkg_name not in first_any_seen_map:
                first_any_seen_map[pkg_name] = FirstSeenEntry(
                    library=pkg_name,
                    file=loc.file,
                    line=loc.line,
                    func_name=loc.func_name,
                )

        def record_call(top_mod: str, full_mod: str, call_expr: str, loc: CodeLocation) -> None:
            pkg_name = self._map_to_pip_package(top_mod)
            dedup_key = (pkg_name, call_expr)
            if dedup_key in seen_first_call_keys:
                return
            seen_first_call_keys.add(dedup_key)

            call_entry = CallUsageEntry(
                library=pkg_name,
                module=full_mod,
                call_expr=call_expr,
                file=loc.file,
                line=loc.line,
                func_name=loc.func_name,
            )
            call_entries.append(call_entry)
            calls_by_lib.setdefault(pkg_name, []).append(call_entry)
            ensure_detail(pkg_name).calls.append(call_entry)

            if pkg_name not in first_called_seen_map:
                first_called_seen_map[pkg_name] = FirstSeenEntry(
                    library=pkg_name,
                    file=loc.file,
                    line=loc.line,
                    func_name=loc.func_name,
                )

            logd(f"[{app_name}] 실제 호출 기록: {pkg_name}.{call_expr} @ {loc.format_pos()}")

        while queue:
            cur_file = queue.popleft()
            if cur_file in visited:
                continue
            visited.add(cur_file)
            rel_file = self._to_rel_posix(cur_file, resolved_root)
            visited_rel_files.append(rel_file)

            tree = self._parse_ast_cached(cur_file)
            if tree is None:
                continue

            local_targets = self._process_file_ast(
                app_name=app_name,
                cur_file=cur_file,
                tree=tree,
                rel_file=rel_file,
                resolved_root=resolved_root,
                local_modules=local_modules,
                record_import=record_import,
                record_call=record_call,
            )

            for targets in local_targets:
                for target_file in targets:
                    if target_file not in visited:
                        queue.append(target_file)

        elapsed_ms = (datetime.now() - started_at).total_seconds() * 1000.0
        sorted_details = {
            lib_name: details_by_lib[lib_name] for lib_name in sorted(details_by_lib.keys())
        }
        sorted_calls_by_lib = {
            lib_name: calls_by_lib[lib_name] for lib_name in sorted(calls_by_lib.keys())
        }
        sorted_imports_by_lib = {
            lib_name: imports_by_lib[lib_name] for lib_name in sorted(imports_by_lib.keys())
        }

        all_entries = [
            AppLibraryScanEntry(
                app_name=app_name,
                entry_point=rel_entry,
                first_seen=(
                    first_called_seen_map.get(lib_name)
                    or first_any_seen_map.get(lib_name)
                    or FirstSeenEntry(library=lib_name, file="", line=0, func_name="<module>")
                ),
                calls=tuple(sorted_calls_by_lib.get(lib_name, ())),
                imports=tuple(sorted_imports_by_lib.get(lib_name, ())),
            )
            for lib_name in sorted(sorted_details.keys())
        ]

        if only_used:
            entries = [item for item in all_entries if len(item.calls) > 0]
            active_first_seen = {
                lib_name: first_called_seen_map[lib_name]
                for lib_name in sorted(first_called_seen_map.keys())
            }
        else:
            entries = list(all_entries)
            active_first_seen = {
                lib_name: (first_called_seen_map.get(lib_name) or first_any_seen_map[lib_name])
                for lib_name in sorted(first_any_seen_map.keys())
            }

        record = AppScanRecord(
            app_name=app_name,
            source_root=str(resolved_root),
            entry_point=rel_entry,
            only_used=only_used,
            visited_files=visited_rel_files,
            entries=entries,
            all_entries=all_entries,
            first_seen_by_lib=active_first_seen,
            call_entries=call_entries,
            calls_by_lib=sorted_calls_by_lib,
            import_entries=import_entries,
            imports_by_lib=sorted_imports_by_lib,
            details_by_lib=sorted_details,
            scan_duration_ms=elapsed_ms,
        )
        self.registry.upsert(record)
        logd(
            f"[{app_name}] 스캔 완료 ({elapsed_ms:.1f}ms) - 방문 파일 {len(visited)}개, 발견 {len(all_entries)}개, 실제 사용(호출) {len(record.get_used_libraries())}개, 미사용 import {len(record.get_unused_import_libraries())}개"
        )
        return list(entries)

    def discover_entry_points(
        self,
        source_root: str | Path | None = None,
        entry_filename: str = "main_app.py",
    ) -> dict[str, Path]:
        """소스 루트 하위 폴더에서 진입점 파일(기본 main_app.py)을 자동 탐색해 {app_name: entry_path} 맵을 반환합니다."""
        base_root = Path(source_root).resolve() if source_root is not None else self.source_root
        if base_root is None or not base_root.is_dir():
            return {}

        search_candidates = [base_root]
        if (base_root / "src").is_dir():
            search_candidates.append((base_root / "src").resolve())

        discovered: dict[str, Path] = {}
        for root in search_candidates:
            for child in sorted(root.iterdir()):
                if not child.is_dir():
                    continue
                if (
                    child.name.startswith((".", "__"))
                    or child.name in PythonLibManager.DEFAULT_EXCLUDE_DIRS
                ):
                    continue
                cand_entry = child / entry_filename
                if cand_entry.is_file() and child.name not in discovered:
                    discovered[child.name] = cand_entry.resolve()
        logd(f"자동 탐색된 앱 진입점 {len(discovered)}개: {sorted(discovered.keys())}")
        return discovered

    def scan_all_apps(
        self,
        source_root: str | Path | None = None,
        entry_filename: str = "main_app.py",
        only_used: bool = True,
    ) -> dict[str, list[AppLibraryScanEntry]]:
        """자동 탐색된 모든 앱의 라이브러리를 일괄 스캔해 {app_name: entries} 맵을 반환합니다."""
        discovered = self.discover_entry_points(
            source_root=source_root, entry_filename=entry_filename
        )
        results: dict[str, list[AppLibraryScanEntry]] = {}
        for app_name, entry_path in discovered.items():
            results[app_name] = self.add_app(
                app_name=app_name,
                entry_point=entry_path,
                source_root=source_root,
                only_used=only_used,
            )
        return results

    def get_app_record(self, app_name: str) -> AppScanRecord | None:
        """앱별 스캔 자료구조(AppScanRecord)를 반환합니다."""
        logd(f"앱별 자료구조 조회: app_name={app_name}")
        return self.registry.get(app_name)

    def get_all_app_records(self) -> dict[str, AppScanRecord]:
        """등록된 모든 앱의 스캔 자료구조 맵을 반환합니다."""
        logd(f"전체 앱 자료구조 조회 (등록 앱 수: {len(self.registry.app_names())})")
        return self.registry.all_records()

    def get_library_by_appname(self, app_name: str) -> list[AppLibraryScanEntry]:
        """앱별 자료구조에 보관된 APP_NAME의 라이브러리 스캔 항목 목록을 반환합니다."""
        logd(f"앱별 자료구조에서 라이브러리 조회: app_name={app_name}")
        entries = self.registry.entries_for_app(app_name)
        if not entries:
            logd(f"[{app_name}] 저장된 라이브러리 항목이 없습니다.")
        else:
            logd(f"[{app_name}] 조회 결과 {len(entries)}개 반환")
        return entries

    def get_used_libraries_by_appname(self, app_name: str) -> list[str]:
        """앱에서 실제 호출(ast.Call)로 사용된 라이브러리 목록만 반환합니다."""
        rec = self.registry.get(app_name)
        return rec.get_used_libraries() if rec else []

    def get_found_libraries_by_appname(self, app_name: str) -> list[str]:
        """앱 스캔 시 발견된 전체 외부 라이브러리 목록을 반환합니다."""
        rec = self.registry.get(app_name)
        return rec.get_found_libraries() if rec else []

    def get_unused_imports_by_appname(self, app_name: str) -> list[str]:
        """앱에서 import 되었으나 실제 호출되지 않은 라이브러리 목록을 반환합니다."""
        rec = self.registry.get(app_name)
        return rec.get_unused_import_libraries() if rec else []

    def get_library_calls_by_appname(
        self, app_name: str, library_name: str | None = None
    ) -> list[CallUsageEntry]:
        """앱별 자료구조에서 실제 호출(ast.Call)이 발생한 라이브러리 호출 목록을 반환합니다."""
        logd(f"앱별 실제 호출 내역 조회: app_name={app_name}, library_name={library_name}")
        return self.registry.calls_for_app(app_name, library_name)

    def get_library_imports_by_appname(
        self, app_name: str, library_name: str | None = None
    ) -> list[ImportRecord]:
        """앱별 자료구조에서 import 위치 목록을 반환합니다."""
        logd(f"앱별 import 내역 조회: app_name={app_name}, library_name={library_name}")
        return self.registry.imports_for_app(app_name, library_name)

    def get_common_libraries(self, app_a: str, app_b: str) -> list[str]:
        """두 앱이 공통으로 사용하는 외부 라이브러리 목록을 정렬 반환합니다."""
        rec_a = self.registry.get(app_a)
        rec_b = self.registry.get(app_b)
        if not rec_a or not rec_b:
            return []
        return sorted(set(rec_a.get_library_names()) & set(rec_b.get_library_names()))

    def get_unique_libraries(self, app_a: str, app_b: str) -> dict[str, list[str]]:
        """두 앱 간의 고유 라이브러리 차집합({app_a: [...], app_b: [...]})을 반환합니다."""
        rec_a = self.registry.get(app_a)
        rec_b = self.registry.get(app_b)
        libs_a = set(rec_a.get_library_names()) if rec_a else set()
        libs_b = set(rec_b.get_library_names()) if rec_b else set()
        return {
            app_a: sorted(libs_a - libs_b),
            app_b: sorted(libs_b - libs_a),
        }

    def export_json(self, output_path: str | Path) -> Path:
        """등록된 전체 앱 스캔 자료구조를 JSON 파일로 저장합니다."""
        out = Path(output_path).resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "exported_at": datetime.now().isoformat(timespec="seconds"),
            "apps": self.registry.to_dict(),
        }
        out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        logd(f"앱 스캔 JSON 내보내기 완료: {out}")
        return out


def print_main_route_help() -> None:
    """Print help for run_main_route()."""
    logd("print_main_route_help() 호출")
    print(
        "\n[run_main_route Help]\n"
        "  Functions:\n"
        "    app_scan     : Scan used/found/unused-import libraries and call/import locations for a single app.\n"
        "    scan_all     : Auto-discover and scan all apps under source_root.\n"
        "    diff         : Compare common and unique libraries between two apps.\n"
        "    help         : Show this help message.\n\n"
        "  Options:\n"
        "    function     : Target function name ('app_scan', 'scan_all', 'diff', or 'help').\n"
        "    source_root  : Source root directory path (default: './src').\n"
        "    app_name     : Target application name (default: 'PrintShopApp').\n"
        "    entry_point  : Application entry point file path (default: '<source_root>/<app_name>/main_app.py').\n"
        "    apps         : Comma-separated two app names for diff (e.g., 'PrintShopApp,UpdateService').\n"
        "    only_used    : Show only actually called libraries in entries ('true' or 'false', default: 'true').\n"
        "    json_out     : Optional JSON output path for scan results.\n"
    )


def _parse_bool_option(raw: str | None, default: bool) -> bool:
    if raw is None or not raw.strip():
        return default
    return raw.strip().lower() in ("1", "true", "t", "yes", "y", "on")


def _prompt_with_default(prompt_text: str, default_value: str) -> str:
    entered = input(prompt_text).strip()
    return entered if entered else default_value


def _print_record_details(scanner: AppLibraryScanner, app_name: str) -> None:
    rec = scanner.get_app_record(app_name)
    if rec is None:
        print(f"[{app_name}] 스캔 레코드가 없습니다.")
        return
    print(rec.format_detail_summary())


def _execute_app_scan(
    *,
    interactive: bool = False,
    source_root: str | Path | None = None,
    app_name: str | None = None,
    entry_point: str | Path | None = None,
    only_used: bool = True,
    json_out: str | Path | None = None,
) -> None:
    """Execute per-app library scan from entry point and print results."""
    if interactive:
        app_default = app_name.strip() if app_name else "PrintShopApp"
        app_opt = _prompt_with_default(f"app_name (default: {app_default}): ", app_default)
        src_default = str(source_root) if source_root is not None else "./src"
        src_opt = _prompt_with_default(f"source_root (default: {src_default}): ", src_default)
        computed_default_entry = str(Path(src_opt) / app_opt / "main_app.py")
        entry_default = str(entry_point) if entry_point is not None else computed_default_entry
        entry_opt = _prompt_with_default(f"entry_point (default: {entry_default}): ", entry_default)
        only_used_opt = _parse_bool_option(
            input(f"only_used [true/false] (default: {str(only_used).lower()}): "),
            only_used,
        )
    else:
        app_opt = app_name.strip() if app_name else "PrintShopApp"
        src_opt = str(source_root) if source_root is not None else "./src"
        entry_opt = (
            str(entry_point)
            if entry_point is not None
            else str(Path(src_opt) / app_opt / "main_app.py")
        )
        only_used_opt = bool(only_used)

    scanner = AppLibraryScanner.create(
        app_name=app_opt,
        source_root=src_opt,
        entry_point=entry_opt,
        only_used=only_used_opt,
    )
    entries = scanner.get_library_by_appname(app_opt)
    for entry in entries:
        calls_str = ", ".join(entry.get_called_expressions())
        suffix = f" [calls: {calls_str}]" if calls_str else ""
        print(
            f"{entry.get_app_name()} {entry.get_entry_point()} {entry.get_name_file_line()}{suffix}"
        )
    _print_record_details(scanner, app_opt)
    if json_out:
        scanner.export_json(json_out)


def _execute_scan_all(
    *,
    source_root: str | Path | None = None,
    only_used: bool = True,
    json_out: str | Path | None = None,
) -> None:
    src_opt = str(source_root) if source_root is not None else "./src"
    scanner = AppLibraryScanner(source_root=src_opt)
    results = scanner.scan_all_apps(source_root=src_opt, only_used=bool(only_used))
    for app_name, entries in sorted(results.items()):
        print(f"=== {app_name} (표시 {len(entries)} libraries) ===")
        for entry in entries:
            calls_str = ", ".join(entry.get_called_expressions())
            suffix = f" [calls: {calls_str}]" if calls_str else ""
            print(f"  {entry.get_name_file_line()}{suffix}")
        _print_record_details(scanner, app_name)
    if json_out:
        scanner.export_json(json_out)


def _execute_diff(
    *,
    source_root: str | Path | None = None,
    apps: str | None = None,
    only_used: bool = True,
) -> None:
    src_opt = str(source_root) if source_root is not None else "./src"
    parts = [p.strip() for p in (apps or "").split(",") if p.strip()]
    if len(parts) < 2:
        parts = ["PrintShopApp", "UpdateService"]
    app_a, app_b = parts[0], parts[1]

    scanner = AppLibraryScanner(source_root=src_opt)
    for name in (app_a, app_b):
        if scanner.get_app_record(name) is None:
            scanner.add_app(
                app_name=name,
                entry_point=Path(src_opt) / name / "main_app.py",
                source_root=src_opt,
                only_used=bool(only_used),
            )

    common = scanner.get_common_libraries(app_a, app_b)
    unique = scanner.get_unique_libraries(app_a, app_b)
    print(f"공통 라이브러리 ({app_a} ∩ {app_b}): {common}")
    print(f"{app_a} 전용 라이브러리: {unique.get(app_a, [])}")
    print(f"{app_b} 전용 라이브러리: {unique.get(app_b, [])}")


def run_main_route(
    function: str | None = None,
    *,
    source_root: str | Path | None = None,
    app_name: str | None = None,
    entry_point: str | Path | None = None,
    apps: str | None = None,
    only_used: bool = True,
    json_out: str | Path | None = None,
) -> None:
    """Run main route by English function name and options, with built-in help."""
    logd(f"run_main_route 시작 (function={function})")
    try:
        interactive = False
        func_name = (function or "").strip().lower()
        if not func_name:
            interactive = True
            print("Available functions: app_scan, scan_all, diff, help")
            func_name = input("function (default: app_scan): ").strip().lower() or "app_scan"

        if func_name in ("help", "--help", "-h", "h", "?"):
            print_main_route_help()
        elif func_name == "app_scan":
            _execute_app_scan(
                interactive=interactive,
                source_root=source_root,
                app_name=app_name,
                entry_point=entry_point,
                only_used=only_used,
                json_out=json_out,
            )
        elif func_name == "scan_all":
            _execute_scan_all(
                source_root=source_root,
                only_used=only_used,
                json_out=json_out,
            )
        elif func_name == "diff":
            _execute_diff(
                source_root=source_root,
                apps=apps,
                only_used=only_used,
            )
        else:
            loge(f"알 수 없는 기능명 입력됨: '{func_name}'")
            print(f"Unknown function: '{func_name}'")
            print_main_route_help()
    except (KeyboardInterrupt, EOFError):
        loge("사용자 입력 중단 또는 EOF로 라우트 실행 종료")
        print("\n실행이 중단되었습니다.")


def _build_cli_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="AppLibraryScanner CLI entrypoint",
        add_help=False,
    )
    parser.add_argument(
        "function",
        nargs="?",
        default=None,
        help="Target function ('app_scan', 'scan_all', 'diff', or 'help')",
    )
    parser.add_argument("-h", "--help", action="store_true", help="Show help message")
    parser.add_argument("--source_root", default=None, help="Source root directory")
    parser.add_argument("--app_name", default=None, help="Target application name")
    parser.add_argument("--entry_point", default=None, help="Application entry point file")
    parser.add_argument("--apps", default=None, help="Comma-separated app pair for diff")
    parser.add_argument("--json_out", default=None, help="JSON output file path")
    parser.add_argument(
        "--only_used",
        dest="only_used",
        action="store_true",
        default=True,
        help="Scan only actually called libraries",
    )
    parser.add_argument(
        "--all_imports",
        dest="only_used",
        action="store_false",
        help="Include imported libraries even if not called",
    )
    return parser


if __name__ == "__main__":
    logd("__main__ 진입 -> CLI 인자 파싱 및 run_main_route() 호출")
    cli_args = _build_cli_parser().parse_args()
    selected_fn = "help" if cli_args.help else cli_args.function
    run_main_route(
        selected_fn,
        source_root=cli_args.source_root,
        app_name=cli_args.app_name,
        entry_point=cli_args.entry_point,
        apps=cli_args.apps,
        only_used=cli_args.only_used,
        json_out=cli_args.json_out,
    )
