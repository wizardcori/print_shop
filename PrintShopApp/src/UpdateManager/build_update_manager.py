import os
import sys

# 공통 빌더 임포트를 위한 경로 설정
current_dir = os.path.dirname(os.path.abspath(__file__))
src_dir = os.path.abspath(os.path.join(current_dir, ".."))
if src_dir not in sys.path:
    sys.path.insert(0, src_dir)

from base_sub_builder import BaseSubBuilder


class UpdateManagerBuilder(BaseSubBuilder):
    app_name = "PrintShopUpdateManager"  # 💡 콤마 제거 완료 (문자열로 고정)

    def __init__(self, python_path: str = None):
        super().__init__(
            source_dir=os.path.dirname(os.path.abspath(__file__)),
            app_name=self.app_name,
            exe_name=f"{self.app_name}.exe",
            spec_name=f"{self.app_name}.spec",
            sub_folder_name=self.app_name,
            python_path=python_path,
            dist_to_main_folder=False  # dist/UpdateService에 출력
        )


if __name__ == "__main__":
    builder = UpdateManagerBuilder()
    result = builder.run()
    if not result["success"]:
        sys.exit(1)
