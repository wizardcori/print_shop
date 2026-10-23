"""LinkBox transfer summary generation."""
import os
from PySide6.QtWidgets import QMessageBox
def create_transfer_summary(parent, table, target_folder, default_color_options):
    """Write the current transfer table rows to the target folder."""
    if not target_folder:
        return ''
    folder_name = os.path.basename(os.path.normpath(target_folder))
    summary_path = os.path.join(target_folder, f'summary_{folder_name}.txt')
    try:
        os.makedirs(target_folder, exist_ok=True)
        records = []
        user_name = user_info = cookie = zone = request_time = ''
        for row in range(table.rowCount()):
            file_item = table.item(row, 3)
            if file_item is None or str(file_item.data(Qt.UserRole) or '') != str(target_folder):
                continue
            cells = [table.item(row, column) for column in range(table.columnCount())]
            values = [cell.text() if cell else '' for cell in cells]
            if not user_name:
                user_name, user_info, zone, cookie = values[0], values[1], values[2], values[10]
                request_time = values[8]
            if table.cellWidget(row, 4) is not None:
                labels = table.cellWidget(row, 4).findChildren(QLabel)
                values[4] = labels[0].text() if labels else values[4]
            color_combo = table.cellWidget(row, 5)
            if isinstance(color_combo, QComboBox):
                values[5] = color_combo.currentText()
            completed = bool(table.item(row, 6).data(Qt.UserRole + 3))
            records.append((
                values[3], values[4],
                    values[5] if len(values) > 5 else default_color_options[0],
                '완료' if completed else '미완료'
            ))
        records.sort(key=lambda record: record[0].lower())
        with open(summary_path, 'w', encoding=CONFIG_ENCODING) as summary:
            summary.write(f'사용자명: {user_name}\n')
            summary.write(f'사용자 부가정보: {user_info}\n')
            summary.write(f'쿠키: {cookie}\n')
            summary.write(f'구역: {zone}\n')
            summary.write(f'요청시간: {request_time}\n\n')
            filename_width = max([len('파일명')] + [len(str(record[0])) for record in records])
            color_width = max([len('컬러유무')] + [len(str(record[2])) for record in records])
            completed_width = max([len('완료여부')] + [len(str(record[3])) for record in records])
            summary.write(
                f'{"파일명":<{filename_width}}  {"카피수":>6}  {"컬러유무":<{color_width}}  '
                f'{"완료여부":<{completed_width}}\n'
            )
            summary.write(
                f'{"-" * filename_width}  {"-" * 6}  {"-" * color_width}  '
                f'{"-" * completed_width}\n'
            )
            for filename, copy_count, color_value, completed_value in records:
                summary.write(
                    f'{str(filename):<{filename_width}}  {str(copy_count):>6}  '
                    f'{str(color_value):<{color_width}}  {str(completed_value):<{completed_width}}\n'
                )
        return summary_path
    except OSError as exc:
        QMessageBox.warning(parent, "요약정보 실패", str(exc))
        return ''

